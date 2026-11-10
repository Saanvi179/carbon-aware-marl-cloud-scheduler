"""Preprocess official SustainCluster carbon and Alibaba task-trace inputs.

The source files remain under data/raw/phase3. This script writes small, explicit
JSON subsets under data/processed/phase3 and never fills missing observations.
"""
import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path
import random
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CARBON_REGIONS = {
    "north": "US-NY-NYIS",
    "west": "US-CAL-CISO",
    "east": "US-TEX-ERCO",
}
CARBON_COLUMN = "Carbon Intensity gCO₂eq/kWh (direct)"
SLOT_SECONDS = 900
HOUR_SLOTS = 3600 // SLOT_SECONDS


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_carbon_profiles(raw_dir, year=2023):
    """Load direct gCO2e/kWh values and hold each hourly reading for 4 slots."""
    raw_dir = Path(raw_dir)
    profiles, details = {}, {}
    for region, upstream_zone in CARBON_REGIONS.items():
        path = raw_dir / f"{upstream_zone}_{year}_hourly.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing official carbon trace: {path}")
        frame = pd.read_csv(path)
        required = {"Datetime (UTC)", "Zone Id", CARBON_COLUMN, "Data Estimated"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{path.name} missing required columns: {sorted(required-set(frame.columns))}")
        times = pd.to_datetime(frame["Datetime (UTC)"], utc=True, errors="coerce")
        values = pd.to_numeric(frame[CARBON_COLUMN], errors="coerce")
        if times.isna().any() or values.isna().any():
            raise ValueError(f"{path.name} contains missing/invalid time or intensity; no imputation performed")
        if (values < 0).any():
            raise ValueError(f"{path.name} contains negative carbon intensity")
        expected_hours = 8784 if pd.Timestamp(year, 12, 31).is_leap_year else 8760
        if len(frame) != expected_hours or not times.is_monotonic_increasing or times.duplicated().any():
            raise ValueError(f"{path.name} is not a complete ordered {year} hourly series")
        if not times.diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
            raise ValueError(f"{path.name} has missing/non-hourly timestamps; no interpolation performed")
        if (frame["Zone Id"].astype(str) != upstream_zone).any():
            raise ValueError(f"Unexpected zone ID in {path.name}")
        numeric = values.astype(float).tolist()
        profiles[region] = [value for value in numeric for _ in range(HOUR_SLOTS)]
        estimated = frame["Data Estimated"].astype(str).str.strip().str.lower().isin(
            ("true", "1", "yes")).sum()
        details[region] = {
            "source_zone": upstream_zone,
            "source_file": path.name,
            "source_sha256": sha256(path),
            "year": year,
            "rows_hourly": len(frame),
            "rows_quarter_hour_hold": len(profiles[region]),
            "first_timestamp_utc": times.iloc[0].isoformat(),
            "last_timestamp_utc": times.iloc[-1].isoformat(),
            "estimated_source_rows": int(estimated),
            "min_direct_gco2e_kwh": min(numeric),
            "max_direct_gco2e_kwh": max(numeric),
            "hourly_to_15min": "zero-order hold; repeat observation 4 slots; no interpolation",
        }
    return profiles, details


def load_trace_frame(zip_path):
    """Load and validate the bundled processed task frame once for reuse."""
    with zipfile.ZipFile(zip_path) as archive:
        members = [item for item in archive.infolist() if item.filename.endswith(".pkl")]
        if len(members) != 1:
            raise ValueError("Expected exactly one processed pkl in workload archive")
        with archive.open(members[0]) as member:
            frame = pd.read_pickle(member)
    if not {"interval_15m", "tasks_matrix"}.issubset(frame.columns):
        raise ValueError("Unexpected Alibaba task trace schema")
    frame["interval_15m"] = pd.to_datetime(frame["interval_15m"], utc=True, errors="coerce")
    if frame["interval_15m"].isna().any() or not frame["interval_15m"].is_monotonic_increasing:
        raise ValueError("Trace interval timestamps are invalid or unordered")
    return frame


def load_trace_workloads(zip_path, *, starts, tasks_per_scenario=8,
                         window_slots=96, deadline_slack_seconds=3600.0,
                         source_region="north", min_runtime_seconds=0.0,
                         max_runtime_seconds=7200.0,
                         arrival_pattern="spread", selection_seed=None,
                         trace_frame=None):
    """Select actual trace jobs with their recorded arrivals.

    Arrival and resource/duration/data fields come from the bundled pkl. The
    source trace has no per-job SLA deadline; deadline is runtime plus the
    explicit configured slack and is therefore a scenario assumption.
    """
    zip_path = Path(zip_path)
    frame = trace_frame if trace_frame is not None else load_trace_frame(zip_path)
    slot_seconds = SLOT_SECONDS
    rng = random.Random(selection_seed) if selection_seed is not None else None
    scenarios = []
    metadata = []
    for scenario_index, start_value in enumerate(starts):
        start_time = pd.Timestamp(start_value, tz="UTC")
        end_time = start_time + pd.Timedelta(seconds=window_slots * slot_seconds)
        window = frame[(frame["interval_15m"] >= start_time) &
                       (frame["interval_15m"] < end_time)]
        if window.empty:
            raise ValueError(f"No workload records in trace window {start_time}–{end_time}")
        if arrival_pattern not in {"spread", "burst"}:
            raise ValueError("arrival_pattern must be 'spread' or 'burst'")
        # Spread takes one actual job per evenly divided interval. Burst takes
        # the first eligible actual jobs in source order; arrival slots remain
        # the recorded 15-minute intervals and are never cloned or shifted.
        bins = min(tasks_per_scenario, window_slots) if arrival_pattern == "spread" else 1
        selected = []
        for bin_index in range(bins):
            left = start_time + pd.Timedelta(seconds=bin_index * window_slots * slot_seconds // bins)
            right = start_time + pd.Timedelta(seconds=(bin_index + 1) * window_slots * slot_seconds // bins)
            chosen = None
            candidates = window[(window["interval_15m"] >= left) &
                                (window["interval_15m"] < right)]
            candidate_rows = list(candidates.iterrows())
            if rng is not None:
                rng.shuffle(candidate_rows)
            for row_index, row in candidate_rows:
                source_tasks = list(enumerate(row["tasks_matrix"]))
                if rng is not None:
                    rng.shuffle(source_tasks)
                for task_index, raw in source_tasks:
                    # Alibaba/SustainCluster fields: id, start/end, start_dt,
                    # duration_min, CPU%, GPU%, memory GB, GPU memory GB,
                    # bandwidth GB, weekday, weekday index.
                    if len(raw) < 10:
                        continue
                    try:
                        duration = float(raw[4]) * 60.0
                        cpu = float(raw[5]) / 100.0
                        gpu = float(raw[6]) / 100.0
                        memory = float(raw[7])
                        dataset = float(raw[9])
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not all(isfinite(value) for value in (duration, cpu, gpu, memory, dataset)):
                        continue
                    if (duration < min_runtime_seconds or duration <= 0 or duration > max_runtime_seconds or cpu <= 0 or
                            cpu > 64 or gpu < 0 or gpu > 8 or memory < 0 or memory > 256 or dataset < 0):
                        continue
                    arrival = int((row["interval_15m"] - start_time).total_seconds() // slot_seconds)
                    chosen = {
                        "task_id": f"ali2020-{scenario_index}-{row_index}-{task_index}-{raw[0]}",
                        "arrival_slot": arrival,
                        "gpu_count": gpu,
                        "cpu_cores": cpu,
                        "memory_gb": memory,
                        "dataset_gb": dataset,
                        "deadline_seconds": arrival * slot_seconds + duration + deadline_slack_seconds,
                        "runtime_seconds": duration,
                        "source_region": source_region,
                        "source_job_id": str(raw[0]),
                        "source_interval_utc": row["interval_15m"].isoformat(),
                    }
                    break
                if chosen:
                    break
            if chosen:
                selected.append(chosen)
            if arrival_pattern == "burst" and chosen:
                # Retain distinct jobs from the short recorded burst window.
                for row_index, source_row in candidates.iterrows():
                    for task_index, raw in enumerate(source_row["tasks_matrix"]):
                        if len(selected) >= tasks_per_scenario:
                            break
                        task_id = f"ali2020-{scenario_index}-{row_index}-{task_index}-{raw[0]}"
                        if any(item["task_id"] == task_id for item in selected):
                            continue
                        try:
                            duration, cpu, gpu = float(raw[4]) * 60, float(raw[5]) / 100, float(raw[6]) / 100
                            memory, dataset = float(raw[7]), float(raw[9])
                        except (TypeError, ValueError, OverflowError, IndexError):
                            continue
                        if (not all(isfinite(v) for v in (duration, cpu, gpu, memory, dataset)) or
                            duration < min_runtime_seconds or duration <= 0 or duration > max_runtime_seconds or cpu <= 0 or cpu > 64 or
                            gpu < 0 or gpu > 8 or memory < 0 or memory > 256 or dataset < 0):
                            continue
                        arrival = int((source_row["interval_15m"] - start_time).total_seconds() // slot_seconds)
                        selected.append({"task_id": task_id,
                            "arrival_slot": arrival, "gpu_count": gpu, "cpu_cores": cpu,
                            "memory_gb": memory, "dataset_gb": dataset,
                            "deadline_seconds": arrival * slot_seconds + duration + deadline_slack_seconds,
                            "runtime_seconds": duration, "source_region": source_region,
                            "source_job_id": str(raw[0]), "source_interval_utc": source_row["interval_15m"].isoformat()})
                    if len(selected) >= tasks_per_scenario:
                        break
                break
        if len(selected) != tasks_per_scenario:
            raise ValueError(f"Window at {start_time}: selected {len(selected)} of {tasks_per_scenario} jobs")
        scenarios.append(selected)
        metadata.append({
            "scenario": scenario_index,
            "source_start_row": int(window.index[0]),
            "start_utc": start_time.isoformat(),
            "end_utc_exclusive": end_time.isoformat(),
            "selected_tasks": len(selected),
            "window_slots_15m": window_slots,
            "arrival_pattern": arrival_pattern,
            "selection_seed": selection_seed,
            "selected_ids": [task["task_id"] for task in selected],
        })
    with zipfile.ZipFile(zip_path) as archive:
        uncompressed_bytes = next(item.file_size for item in archive.infolist()
                                  if item.filename.endswith(".pkl"))
    return scenarios, {
        "source_archive": zip_path.name,
        "source_sha256": sha256(zip_path),
        "source_uncompressed_member_bytes": uncompressed_bytes,
        "source_rows": len(frame),
        "source_interval_first_utc": frame["interval_15m"].iloc[0].isoformat(),
        "source_interval_last_utc": frame["interval_15m"].iloc[-1].isoformat(),
        "source_task_columns": ["job_id", "duration_min", "cpu_percent", "gpu_percent",
                                "memory_gb", "gpu_memory_gb", "bandwidth_gb"],
        "conversions": {"duration": "minutes to seconds", "cpu": "source CPU percent / 100 to cores",
                        "gpu": "source GPU percent / 100 to GPU units; fractions retained",
                        "memory": "GB unchanged", "dataset": "bandwidth_gb used as GB input size"},
        "deadline_assumption_seconds_after_runtime": deadline_slack_seconds,
        "source_region_assumption": source_region,
        "min_runtime_filter_seconds": min_runtime_seconds,
        "max_runtime_filter_seconds": max_runtime_seconds,
        "scenarios": metadata,
        "selected_task_count": sum(map(len, scenarios)),
    }


def preprocess(raw_dir, output_dir, *, tasks_per_scenario=8, window_slots=96,
               deadline_slack_seconds=3600.0):
    raw_dir, output_dir = Path(raw_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles, carbon_info = load_carbon_profiles(raw_dir)
    starts = ("2020-01-01 00:00:00", "2020-01-02 00:00:00",
              "2020-01-08 00:00:00")
    workloads, workload_info = load_trace_workloads(
        raw_dir / "result_df_full_year_2020.zip", starts=starts,
        tasks_per_scenario=tasks_per_scenario, window_slots=window_slots,
        deadline_slack_seconds=deadline_slack_seconds)
    (output_dir / "carbon_profiles_2023.json").write_text(json.dumps({
        "slot_seconds": SLOT_SECONDS, "profiles": profiles, "regions": carbon_info,
    }, indent=2), encoding="utf-8")
    (output_dir / "alibaba_workloads.json").write_text(json.dumps({
        "tasks": workloads, "metadata": workload_info,
    }, indent=2), encoding="utf-8")
    (output_dir / "phase3_manifest.json").write_text(json.dumps({
        "carbon": carbon_info, "workload": workload_info,
    }, indent=2), encoding="utf-8")
    return carbon_info, workload_info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(ROOT / "data/raw/phase3"))
    parser.add_argument("--output-dir", default=str(ROOT / "data/processed/phase3"))
    parser.add_argument("--tasks-per-scenario", type=int, default=8)
    parser.add_argument("--window-slots", type=int, default=96)
    parser.add_argument("--deadline-slack-seconds", type=float, default=3600.0)
    args = parser.parse_args()
    carbon, workload = preprocess(args.raw_dir, args.output_dir,
                                  tasks_per_scenario=args.tasks_per_scenario,
                                  window_slots=args.window_slots,
                                  deadline_slack_seconds=args.deadline_slack_seconds)
    print(json.dumps({"carbon_regions": len(carbon), "profiles_slots": 8760 * HOUR_SLOTS,
                      "selected_workload_tasks": workload["selected_task_count"],
                      "scenarios": len(workload["scenarios"])}, indent=2))


if __name__ == "__main__":
    main()
