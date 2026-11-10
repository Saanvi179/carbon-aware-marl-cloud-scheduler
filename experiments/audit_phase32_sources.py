"""Audit bundled Phase 3 workload timestamps, IDs and demand fields."""
import argparse
import json
from collections import Counter
from pathlib import Path
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def audit_workload(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        member = next(x for x in archive.infolist() if x.filename.endswith(".pkl"))
        with archive.open(member) as stream:
            frame = pd.read_pickle(stream)
    times = pd.to_datetime(frame["interval_15m"], utc=True, errors="coerce")
    task_ids, source_start_years, malformed = Counter(), Counter(), 0
    raw_start_values, task_timestamps, interval_task_deltas = [], [], []
    all_tasks = sum(len(tasks) for tasks in frame["tasks_matrix"])
    eligible = sampled_records = 0
    sample_stride = max(1, len(frame) // 500)
    # Bound this field-level audit to roughly 500 intervals. The full interval
    # index/count checks above still cover every packaged row.
    for row in frame.iloc[::sample_stride].itertuples(index=False):
        for raw in row.tasks_matrix:
            sampled_records += 1
            if len(raw) < 10:
                malformed += 1
                continue
            task_ids[str(raw[0])] += 1
            try:
                raw_start_values.append(float(raw[1]))
                task_timestamp = pd.Timestamp(raw[3])
                task_timestamps.append(task_timestamp)
                interval_task_deltas.append(float((pd.Timestamp(row.interval_15m) - task_timestamp).total_seconds()))
                source_start_years[str(pd.to_datetime(float(raw[1]), unit="s", utc=True).year)] += 1
                duration = float(raw[4])
                cpu, gpu = float(raw[5]) / 100, float(raw[6]) / 100
                memory, size = float(raw[7]), float(raw[9])
                if duration > 0 and 0 < cpu <= 64 and 0 <= gpu <= 8 and 0 <= memory <= 256 and size >= 0:
                    eligible += 1
            except (TypeError, ValueError, OverflowError, OSError):
                malformed += 1
    deltas = times.diff().dropna()
    duplicate_ids = sum(count - 1 for count in task_ids.values() if count > 1)
    month_counts = frame.assign(_time=times).groupby(times.dt.strftime("%Y-%m"), sort=True).size()
    return {
        "archive": Path(zip_path).name,
        "archive_bytes": Path(zip_path).stat().st_size,
        "uncompressed_pickle_bytes": member.file_size,
        "dataframe_rows": len(frame),
        "first_interval_utc": times.min().isoformat(),
        "last_interval_utc": times.max().isoformat(),
        "interval_timestamps_valid": bool(not times.isna().any()),
        "interval_timestamps_monotonic": bool(times.is_monotonic_increasing),
        "interval_timestamp_duplicates": int(times.duplicated().sum()),
        "interval_step_counts_seconds": {str(k.total_seconds()): int(v) for k, v in deltas.value_counts().items()},
        "non_15_minute_interval_steps": int((deltas != pd.Timedelta(minutes=15)).sum()),
        "task_records": all_tasks,
        "field_audit_sample_stride_intervals": sample_stride,
        "field_audit_sampled_task_records": sampled_records,
        "eligible_in_field_audit_sample_with_phase3_resource_filters": eligible,
        "sampled_unique_job_ids": len(task_ids),
        "sampled_job_ids_repeated": sum(count > 1 for count in task_ids.values()),
        "sampled_repeated_id_records_beyond_first": duplicate_ids,
        "sampled_raw_start_field_as_if_unix_year_counts_not_validated": dict(sorted(source_start_years.items())),
        "sampled_raw_start_field_numeric_min_max_seconds": [min(raw_start_values), max(raw_start_values)],
        "sampled_embedded_task_timestamp_min_max": [min(task_timestamps).isoformat(), max(task_timestamps).isoformat()],
        "sampled_interval_minus_embedded_task_timestamp_seconds_min_max": [min(interval_task_deltas), max(interval_task_deltas)],
        "sampled_malformed_or_invalid_records": malformed,
        "interval_rows_by_month": {str(k): int(v) for k, v in month_counts.items()},
        "warning": "Packaged timestamps are not independently verified production timestamps; official SustainCluster documentation says the original two-month trace is temporally extended by repeated daily/weekly patterns.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=str(ROOT / "data/raw/phase3/result_df_full_year_2020.zip"))
    parser.add_argument("--output", default=str(ROOT / "data/processed/phase32/source_audit.json"))
    args = parser.parse_args()
    report = audit_workload(args.archive)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
