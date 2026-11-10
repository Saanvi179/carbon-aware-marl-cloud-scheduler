import itertools
from math import ceil
import unittest

from environment.task_generator import Task, generate_phase25_workload
from experiments.evaluate_baselines import make_phase25_environment
from experiments.offline_optimizer import OfflineOptimizer


class OfflineOptimizerTests(unittest.TestCase):
    def test_single_task_milp_matches_exhaustive_schedule_enumeration(self):
        env = make_phase25_environment(dynamic_carbon=True)
        task = Task("tiny", 0, 1, 2, 8.0, 0.01, 300.0, 45.0, "north")
        solution = OfflineOptimizer().solve(env, [task], time_limit_seconds=10)
        self.assertEqual(solution["status"], "optimal")
        possibilities = []
        for name, region in env.regions.items():
            migration = env.network.migration_latency(task.source_region, name, task.dataset_gb)
            execution = task.runtime_seconds / region.execution_speed
            for slot in range(task.arrival_slot, task.arrival_slot + env.max_deferrals + 1):
                start = slot * env.slot_seconds + migration
                end = start + execution
                if end <= task.deadline_seconds:
                    assignment = {"task": task, "region": name, "start": start, "end": end}
                    carbon = env._integrate_region(name, [assignment])[1]
                    possibilities.append(carbon)
        self.assertAlmostEqual(solution["totals"]["carbon_gco2e"], min(possibilities), places=8)
        self.assertEqual(solution["totals"]["completed"], 1)
        self.assertEqual(solution["totals"]["sla_violations"], 0)

    def test_solution_respects_all_resource_caps_and_task_deadlines(self):
        env = make_phase25_environment(dynamic_carbon=True)
        tasks = generate_phase25_workload(28421, 5)
        solution = OfflineOptimizer().solve(env, tasks, time_limit_seconds=10)
        self.assertTrue(solution["optimal"], solution["message"])
        self.assertEqual(len(solution["schedule"]), len(tasks))
        by_id = {task.task_id: task for task in tasks}
        self.assertEqual(len({row["task_id"] for row in solution["schedule"]}), len(tasks))
        for row in solution["schedule"]:
            task = by_id[row["task_id"]]
            region = env.regions[row["region"]]
            end_time = (row["decision_slot"] * env.slot_seconds + row["migration_seconds"] +
                        row["execution_seconds"])
            self.assertLessEqual(end_time, task.deadline_seconds + 1e-9)
            self.assertLessEqual(row["decision_slot"], task.arrival_slot + env.max_deferrals)
            self.assertLessEqual(task.gpu_count, region.resources.gpus)
            self.assertLessEqual(task.cpu_cores, region.resources.cpu_cores)
            self.assertLessEqual(task.memory_gb, region.resources.memory_gb)
        assignments = [{"task": by_id[row["task_id"]], "region": row["region"],
                        "decision_slot": row["decision_slot"], "finish": row["finish_slot"],
                        "start": row["decision_slot"] * env.slot_seconds + row["migration_seconds"],
                        "end": row["decision_slot"] * env.slot_seconds + row["migration_seconds"] +
                              row["execution_seconds"]}
                       for row in solution["schedule"]]
        for name, region in env.regions.items():
            for slot in range(80):
                active = [a for a in assignments if a["region"] == name and
                          a["decision_slot"] <= slot < a["finish"]]
                self.assertLessEqual(sum(a["task"].gpu_count for a in active), region.resources.gpus)
                self.assertLessEqual(sum(a["task"].cpu_cores for a in active), region.resources.cpu_cores)
                self.assertLessEqual(sum(a["task"].memory_gb for a in active), region.resources.memory_gb)
        exact_energy = sum(env._integrate_region(name, assignments)[0] for name in env.region_names)
        exact_carbon = sum(env._integrate_region(name, assignments)[1] for name in env.region_names)
        self.assertAlmostEqual(solution["totals"]["energy_kwh"], exact_energy, places=9)
        self.assertAlmostEqual(solution["totals"]["carbon_gco2e"], exact_carbon, places=8)

    def test_two_task_milp_matches_exhaustive_capacity_feasible_optimum(self):
        env = make_phase25_environment(dynamic_carbon=True)
        tasks = [Task("a", 0, 6, 12, 32.0, .02, 360.0, 60.0, "north"),
                 Task("b", 0, 6, 12, 32.0, .02, 360.0, 60.0, "west")]
        solution = OfflineOptimizer().solve(env, tasks, time_limit_seconds=10)
        self.assertEqual(solution["status"], "optimal")
        options = []
        for task in tasks:
            task_options = []
            for name, region in env.regions.items():
                migration = env.network.migration_latency(task.source_region, name, task.dataset_gb)
                execution = task.runtime_seconds / region.execution_speed
                for slot in range(task.arrival_slot, task.arrival_slot + env.max_deferrals + 1):
                    start = slot * env.slot_seconds + migration
                    end = start + execution
                    if end <= task.deadline_seconds:
                        task_options.append({"task": task, "region": name, "slot": slot,
                                             "start": start, "end": end, "finish": ceil(end / env.slot_seconds),
                                             "migration": migration, "execution": execution})
            options.append(task_options)
        feasible_costs = []
        for choice in itertools.product(*options):
            legal = True
            for name, region in env.regions.items():
                for slot in range(6):
                    active = [c for c in choice if c["region"] == name and c["slot"] <= slot < c["finish"]]
                    if (sum(c["task"].gpu_count for c in active) > region.resources.gpus or
                        sum(c["task"].cpu_cores for c in active) > region.resources.cpu_cores or
                        sum(c["task"].memory_gb for c in active) > region.resources.memory_gb):
                        legal = False
            if not legal:
                continue
            assignments = [{"task": c["task"], "region": c["region"],
                            "start": c["start"], "end": c["end"]} for c in choice]
            feasible_costs.append(sum(env._integrate_region(name, assignments)[1]
                                      for name in env.region_names))
        self.assertTrue(feasible_costs)
        self.assertAlmostEqual(solution["totals"]["carbon_gco2e"], min(feasible_costs), places=8)


if __name__ == "__main__":
    unittest.main()
