import unittest
from environment.task_generator import Task
from environment.resource_manager import Resources, AllocationLedger
from environment.network_model import NetworkModel
from environment.energy_model import energy_kwh
from environment.carbon_model import emissions_gco2e
from environment.carbon_model import CarbonModel, synthetic_carbon_profiles
from environment.agent_api import ActionType, RegionAction, make_observation
from environment.energy_model import interval_energy_kwh
from environment.cloud_environment import CloudEnvironment, Region
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


class SimulatorTests(unittest.TestCase):
    def test_synthetic_carbon_profiles_vary_over_full_horizon_and_region_rank(self):
        profiles = synthetic_carbon_profiles(96)
        self.assertEqual(set(profiles), {"north", "west", "east"})
        for values in profiles.values():
            self.assertEqual(len(values), 96)
            self.assertGreater(max(values) - min(values), 50.0)
            self.assertNotAlmostEqual(values[20], values[80])
        best_regions = {min(profiles, key=lambda region: profiles[region][slot]) for slot in range(96)}
        self.assertGreater(len(best_regions), 1)

    def task(self, **kw):
        values = dict(task_id="t", arrival_slot=0, gpu_count=1, cpu_cores=2,
                      memory_gb=4, dataset_gb=0.1, deadline_seconds=600,
                      runtime_seconds=60, source_region="a")
        values.update(kw)
        return Task(**values)

    def environment(self):
        regions = [Region("a", Resources(1, 4, 8), 500),
                   Region("b", Resources(2, 8, 16), 100),
                   Region("c", Resources(1, 4, 8), 300)]
        return CloudEnvironment(regions, NetworkModel({("a", "b"): (10, .1),
                                                        ("a", "c"): (10, .1)}))

    def test_resource_constraints_and_release(self):
        res, task = Resources(1, 2, 4), self.task()
        self.assertTrue(res.can_fit(task))
        res.reserve(task)
        self.assertFalse(res.can_fit(task))
        res.release(task)
        self.assertTrue(res.can_fit(task))

    def test_duplicate_allocation_rejected(self):
        ledger = AllocationLedger()
        self.assertTrue(ledger.claim("t", "a"))
        self.assertFalse(ledger.claim("t", "b"))

    def test_migration_latency(self):
        network = NetworkModel({("a", "b"): (8, .2)})
        self.assertAlmostEqual(network.migration_latency("a", "b", 1), 1.2)
        self.assertEqual(network.migration_latency("a", "a", 1), 0)

    def test_energy_and_carbon_units(self):
        e = energy_kwh(1, 100, 0, 3600, 1)
        self.assertAlmostEqual(e, 0.1)
        self.assertAlmostEqual(emissions_gco2e(e, 500), 50)

    def test_shared_idle_power_counted_once_for_concurrent_work(self):
        # 2 GPUs x 100 W + one shared 50 W overhead for 60 seconds.
        e = interval_energy_kwh([1, 1], 100, 50, 60, 1)
        self.assertAlmostEqual(e, 250 * 60 / 3_600_000)
        self.assertLess(e, 2 * (150 * 60 / 3_600_000))

    def test_carbon_profile_changes_by_slot(self):
        carbon = CarbonModel({"a": [100, 900]}, {"a": 500})
        self.assertEqual(carbon.intensity_at("a", 0, 60), 100)
        self.assertEqual(carbon.intensity_at("a", 60, 60), 900)
        self.assertEqual(carbon.intensity_at("a", 120, 60), 500)

    def test_region_specific_execution_speed(self):
        regions = [Region("a", Resources(2, 8, 16), 400, execution_speed=1),
                   Region("b", Resources(2, 8, 16), 200, execution_speed=2),
                   Region("c", Resources(2, 8, 16), 300, execution_speed=.5)]
        result = CloudEnvironment(regions).run([self.task()], GreedyCarbonScheduler())
        self.assertEqual(result["allocations"]["t"], "b")
        record = next(r for r in result["records"] if r["action"] != "defer")
        self.assertAlmostEqual(record["execution_seconds"], 30)

    def test_formal_agent_observation_and_action_validation(self):
        resources = Resources(4, 16, 64)
        obs = make_observation(2, "a", self.task(), resources, ("a", "b"), 123)
        self.assertTrue(obs.local_feasible)
        self.assertEqual(obs.carbon_intensity_gco2e_kwh, 123)
        self.assertEqual(RegionAction("a", ActionType.EXECUTE_LOCAL).action,
                         ActionType.EXECUTE_LOCAL)
        with self.assertRaises(ValueError):
            RegionAction("a", ActionType.MIGRATE)
        with self.assertRaises(ValueError):
            RegionAction("a", ActionType.MIGRATE, "a")

    def test_simultaneous_proposals_resolve_once_and_respect_capacity(self):
        env = self.environment()
        tasks = [self.task(task_id=f"t{i}", arrival_slot=0) for i in range(3)]
        result = env.run(tasks, GreedyCarbonScheduler())
        executions = [r for r in result["records"] if r["action"] in ("execute_local", "migrate")]
        self.assertEqual(len(executions), 3)
        self.assertEqual(len(result["allocations"]), 3)
        self.assertEqual(len({r["task_id"] for r in executions}), 3)
        self.assertTrue(all(env.regions[name].resources.used_gpus == 0 for name in env.region_names))

    def test_completion_and_greedy_carbon(self):
        result = self.environment().run([self.task()], GreedyCarbonScheduler())
        self.assertEqual(result["totals"]["completed"], 1)
        self.assertEqual(result["allocations"]["t"], "b")

    def test_fcfs_local_and_deadline_rejection(self):
        env = self.environment()
        result = env.run([self.task()], FCFSScheduler())
        self.assertEqual(result["allocations"]["t"], "a")
        impossible = self.task(task_id="late", deadline_seconds=1)
        result = self.environment().run([impossible], FCFSScheduler())
        self.assertEqual(result["totals"]["rejected"], 1)

    def test_defer_is_bounded(self):
        env = self.environment()
        task = self.task(gpu_count=9)
        result = env.run([task], FCFSScheduler())
        self.assertEqual(result["totals"]["rejected"], 1)
        self.assertEqual(sum(r["action"] == "defer" for r in result["records"]), 2)


if __name__ == "__main__":
    unittest.main()
