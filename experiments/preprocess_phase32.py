"""Create bounded Phase 3.2 cohorts from all packaged trace calendar windows.

The official upstream package says it temporally extends the original two-month
Alibaba trace by repeating daily/weekly patterns. Its extended interval axis is
used for scenario coverage, not represented as a year of independent observations.
"""
import argparse
import hashlib
import json
from pathlib import Path

from experiments.preprocess_phase3 import load_trace_frame, load_trace_workloads

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STARTS = tuple(f"2020-{month:02d}-01" for month in range(1, 13)) + ("2021-01-01",)
SIZES = (12, 24, 48)
SLOT_SECONDS = 900


def preprocess(raw_archive, output_path, *, starts=DEFAULT_STARTS, seed_base=32000):
    raw_archive = Path(raw_archive)
    frame = load_trace_frame(raw_archive)
    scenarios, source_manifests = {}, {}
    for pattern, window_slots in (("spread", 96), ("burst_2h", 8)):
        for size in SIZES:
            family = f"{pattern}_{size}tasks"
            selected, manifest = load_trace_workloads(
                raw_archive, starts=starts, tasks_per_scenario=size,
                window_slots=window_slots, deadline_slack_seconds=3600.0,
                source_region="north", min_runtime_seconds=900.0,
                max_runtime_seconds=7200.0, arrival_pattern=("burst" if pattern == "burst_2h" else "spread"),
                selection_seed=seed_base + size, trace_frame=frame)
            # Give cohort and window identity to each local task ID. Source IDs
            # are retained separately to support provenance audits.
            for index, items in enumerate(selected):
                for item in items:
                    item["task_id"] = f"phase32-{family}-{index}-{item['task_id']}"
            scenarios[family] = selected
            source_manifests[family] = manifest
    payload = {
        "schema_version": 1,
        "slot_seconds": SLOT_SECONDS,
        "workload_axis_warning": (
            "Packaged interval_15m timestamps are an upstream temporal extension of a two-month 2020 trace; "
            "they are not asserted to be observed production calendar timestamps. Raw task start fields are "
            "relative/surrogate epoch values and do not align to the interval_15m axis."
        ),
        "source_archive": raw_archive.name,
        "source_archive_sha256": hashlib.sha256(raw_archive.read_bytes()).hexdigest(),
        "source_audit": "data/processed/phase32/source_audit.json",
        "scenario_families": scenarios,
        "metadata": {
            "starts_are_package_axis_coordinates": list(starts),
            "per_instance_window_slots": {"spread": 96, "burst_2h": 8},
            "task_counts": list(SIZES),
            "selection_seeds": [seed_base + count for count in SIZES],
            "minimum_runtime_seconds": 900.0,
            "maximum_runtime_seconds": 7200.0,
            "deadline_slack_seconds_assumption": 3600.0,
            "ingress_region_assumption": "north",
            "network_input_size_field": "packaged bandwidth_gb field retained; source meaning is estimated input volume",
            "families": source_manifests,
        },
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=str(ROOT / "data/raw/phase3/result_df_full_year_2020.zip"))
    parser.add_argument("--output", default=str(ROOT / "data/processed/phase32/phase32_workloads.json"))
    parser.add_argument("--seed-base", type=int, default=32000)
    args = parser.parse_args()
    data = preprocess(args.archive, args.output, seed_base=args.seed_base)
    print(json.dumps({"families": len(data["scenario_families"]),
                      "instances": sum(len(v) for v in data["scenario_families"].values()),
                      "task_appearances": sum(len(tasks) for values in data["scenario_families"].values()
                                              for tasks in values),
                      "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
