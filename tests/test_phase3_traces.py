import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from environment.carbon_model import CarbonModel
from environment.cloud_environment import CloudEnvironment, Region
from environment.network_model import NetworkModel
from environment.resource_manager import Resources
from experiments.preprocess_phase3 import CARBON_COLUMN, CARBON_REGIONS, load_carbon_profiles, load_trace_workloads
from experiments.audit_phase32_sources import audit_workload
from environment.task_generator import Task


class Phase3TraceTests(unittest.TestCase):
    def test_carbon_trace_units_regions_hourly_hold_and_missing_value_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            times = pd.date_range("2023-01-01", periods=8760, freq="h", tz="UTC")
            for region_index, (region, zone) in enumerate(CARBON_REGIONS.items()):
                pd.DataFrame({"Datetime (UTC)": times, "Zone Id": zone,
                    CARBON_COLUMN: [100.0 + 100 * region_index + i for i in range(8760)],
                    "Data Estimated": [False] * 8760}).to_csv(root / f"{zone}_2023_hourly.csv", index=False)
            profiles, details = load_carbon_profiles(root)
            self.assertEqual(set(profiles), {"north", "west", "east"})
            self.assertEqual(details["north"]["source_zone"], CARBON_REGIONS["north"])
            self.assertEqual(profiles["north"][:8], [100.0] * 4 + [101.0] * 4)
            self.assertEqual(profiles["west"][0], 200.0)
            self.assertEqual(details["north"]["rows_hourly"], 8760)
            north_path = root / f"{CARBON_REGIONS['north']}_2023_hourly.csv"
            north = pd.read_csv(north_path)
            north.loc[2, CARBON_COLUMN] = float("nan")
            north.to_csv(north_path, index=False)
            with self.assertRaisesRegex(ValueError, "missing/invalid"):
                load_carbon_profiles(root)

    def test_source_audit_keeps_missing_interval_step_visible_and_flags_axis_mismatch(self):
        rows = []
        for minute, start_field in ((0, 1000.0), (15, 1900.0), (45, 2800.0)):
            task = ["repeat-job", start_field, start_field + 60,
                    pd.to_datetime(start_field, unit="s", utc=True), 20.0,
                    100.0, 50.0, 4.0, 1.0, 0.2, "Wednesday", 2]
            rows.append({"interval_15m": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(minutes=minute),
                         "tasks_matrix": [task]})
        frame = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "audit.zip"
            member = Path(directory) / "audit.pkl"
            frame.to_pickle(member)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(member, "audit.pkl")
            audit = audit_workload(archive_path)
        self.assertTrue(audit["interval_timestamps_monotonic"])
        self.assertEqual(audit["non_15_minute_interval_steps"], 1)
        self.assertEqual(audit["task_records"], 3)
        self.assertEqual(audit["sampled_job_ids_repeated"], 1)
        self.assertEqual(audit["sampled_raw_start_field_as_if_unix_year_counts_not_validated"], {"1970": 3})

    def test_burst_sampling_keeps_distinct_jobs_and_recorded_arrivals(self):
        tasks = [["same-job-multiple-instances", i, i + 10, pd.Timestamp("2020-01-01", tz="UTC"),
                  1.0, 100.0, 50.0, 4.0, 1.0, 0.2, "Wednesday", 2]
                 for i in range(5)]
        frame = pd.DataFrame([{"interval_15m": pd.Timestamp("2020-01-01", tz="UTC"),
                               "tasks_matrix": tasks}])
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "burst.zip"
            member = Path(directory) / "burst.pkl"
            frame.to_pickle(member)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(member, "burst.pkl")
            selected, metadata = load_trace_workloads(archive_path, starts=("2020-01-01",),
                tasks_per_scenario=4, window_slots=1, arrival_pattern="burst", selection_seed=17)
            repeated, _ = load_trace_workloads(archive_path, starts=("2020-01-01",),
                tasks_per_scenario=4, window_slots=1, arrival_pattern="burst", selection_seed=17)
        self.assertEqual(len(selected[0]), 4)
        self.assertEqual(selected, repeated)
        self.assertEqual(len({x["task_id"] for x in selected[0]}), 4)
        self.assertEqual({x["source_job_id"] for x in selected[0]}, {"same-job-multiple-instances"})
        self.assertEqual({x["arrival_slot"] for x in selected[0]}, {0})
        self.assertEqual(metadata["scenarios"][0]["arrival_pattern"], "burst")

    def test_real_trace_mode_uses_current_carbon_for_candidate_estimate(self):
        regions = [Region(name, Resources(2, 8, 32), 100, 300, 100, 1.0, 1.0)
                   for name in ("north", "west", "east")]
        profiles = {"north": [100.0, 1000.0], "west": [200.0, 2000.0],
                    "east": [300.0, 3000.0]}
        env = CloudEnvironment(regions, NetworkModel(), slot_seconds=60,
                               carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()},
                                                        candidate_forecast_known=False))
        task = Task("t", 0, 1, 1, 1.0, 0.1, 300, 120, "north")
        candidate = env._candidate_metrics("north", task, 0, [])
        expected_energy = candidate["energy"]
        self.assertEqual(candidate["carbon_intensity"], 100.0)
        self.assertAlmostEqual(candidate["carbon"], expected_energy * 100.0)
        assignments = [{"task": task, "region": "north", "start": 0.0, "end": 120.0}]
        _, realized_carbon = env._integrate_region("north", assignments)
        self.assertGreater(realized_carbon, candidate["carbon"])

    def test_online_candidate_estimate_does_not_query_future_carbon(self):
        class CurrentOnlyCarbon(CarbonModel):
            def intensity_at(self, region, time_seconds, slot_seconds):
                if time_seconds > 0:
                    raise AssertionError("online candidate estimate queried future carbon")
                return 100.0

        regions = [Region(name, Resources(2, 8, 32), 100, 300, 100, 1.0, 1.0)
                   for name in ("north", "west", "east")]
        env = CloudEnvironment(regions, NetworkModel(), slot_seconds=60,
                               carbon_model=CurrentOnlyCarbon(
                                   {name: [100.0, 1000.0] for name in ("north", "west", "east")},
                                   {name: 100.0 for name in ("north", "west", "east")},
                                   candidate_forecast_known=False))
        task = Task("t", 0, 1, 1, 1.0, 0.1, 300, 120, "north")
        candidate = env._candidate_metrics("north", task, 0, [])
        self.assertEqual(candidate["carbon_intensity"], 100.0)

    def test_trace_workload_preprocessing_is_reproducible_and_keeps_fractional_resources(self):
        rows = []
        for slot in range(4):
            task = [f"job-{slot}", slot * 900, slot * 900 + 600, pd.Timestamp("2020-01-01", tz="UTC"),
                    10.0, 250.5, 50.0, 12.0, 4.0, 0.3, "Wednesday", 2]
            rows.append({"interval_15m": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(minutes=15*slot),
                         "tasks_matrix": [task]})
        frame = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "tiny.zip"
            member = Path(directory) / "tiny.pkl"
            frame.to_pickle(member)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(member, "tiny.pkl")
            first, _ = load_trace_workloads(archive_path, starts=("2020-01-01",),
                                            tasks_per_scenario=2, window_slots=4)
            second, _ = load_trace_workloads(archive_path, starts=("2020-01-01",),
                                             tasks_per_scenario=2, window_slots=4)
            with self.assertRaisesRegex(ValueError, "selected 0 of 2"):
                load_trace_workloads(archive_path, starts=("2020-01-01",),
                                     tasks_per_scenario=2, window_slots=4,
                                     min_runtime_seconds=900)
        self.assertEqual(first, second)
        self.assertEqual([t["arrival_slot"] for t in first[0]], [0, 2])
        self.assertEqual(first[0][0]["cpu_cores"], 2.505)
        self.assertEqual(first[0][0]["gpu_count"], 0.5)
        self.assertEqual(first[0][0]["runtime_seconds"], 600.0)
        self.assertEqual(first[0][0]["dataset_gb"], 0.3)
        self.assertEqual(first[0][0]["deadline_seconds"], 4200.0)


if __name__ == "__main__":
    unittest.main()
