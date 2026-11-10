import unittest

from agents.contextual_bandit import BanditProposal, ContextualBanditScheduler
from environment.agent_api import ActionType
from environment.task_generator import Task, generate_phase25_workload
from experiments.evaluate_baselines import make_phase25_environment


class ContextualBanditTests(unittest.TestCase):
    def setUp(self):
        self.env = make_phase25_environment(dynamic_carbon=True)
        self.capacities = {name: (region.resources.gpus, region.resources.cpu_cores,
                                  region.resources.memory_gb)
                           for name, region in self.env.regions.items()}

    def make_scheduler(self, deterministic=False, learning=True):
        return ContextualBanditScheduler(self.env.region_names, self.capacities,
                                         deterministic=deterministic,
                                         learning_enabled=learning)

    def test_online_action_is_selected_from_feasible_candidates(self):
        scheduler = self.make_scheduler()
        task = generate_phase25_workload(29201, 1)[0]
        result = self.env.run([task], scheduler)
        trace = result["agent_decisions"]
        self.assertEqual(len(trace), 1)
        self.assertIn(trace[0]["actual_region"], self.env.region_names)
        self.assertIsNone(trace[0]["fallback_reason"])
        self.assertEqual(result["totals"]["completed"], 1)
        self.assertEqual(result["totals"]["sla_violations"], 0)
        self.assertGreater(result["totals"]["bandit_feedback_updates"], 0)

    def test_bandit_learns_only_from_committed_arm_and_roundtrips(self):
        scheduler = self.make_scheduler()
        result = self.env.run(generate_phase25_workload(29202, 6), scheduler)
        self.assertEqual(sum(scheduler.arm_counts.values()), result["totals"]["bandit_feedback_updates"])
        saved = scheduler.checkpoint()
        restored = self.make_scheduler(deterministic=True, learning=False)
        restored.load_checkpoint(saved)
        self.assertEqual(restored.arm_counts, scheduler.arm_counts)
        self.assertTrue(all((restored.A[name] == scheduler.A[name]).all()
                            for name in self.env.region_names))

    def test_invalid_selected_destination_uses_greedy_safety_fallback(self):
        scheduler = self.make_scheduler()
        task = Task("fallback", 0, 1, 2, 8.0, .01, 500.0, 60.0, "north")
        result = self.env.run([task], scheduler)
        # Build a fresh snapshot's feasible candidate list from the simulator's
        # typed observation by calling a single-task run and selecting its record.
        task = Task("bad-target", 0, 1, 2, 8.0, .01, 500.0, 60.0, "north")
        # The environment has reset resources after the prior run.
        candidates = []
        for name, region in self.env.regions.items():
            metrics = self.env._candidate_metrics(name, task, 0, [])
            metrics["feasible"] = (region.resources.can_fit(task) and
                                   metrics["end"] <= task.deadline_seconds)
            if metrics["feasible"]:
                candidates.append(metrics)
        invalid = BanditProposal("north", ActionType.MIGRATE, "unknown", "unknown",
                                 (1.0,) + (0.0,) * 11, 0.0, 0.0,
                                 "north", False, None)
        selected = scheduler.resolve(task, [invalid], candidates, self.env.region_names)
        self.assertIn(selected["region"], {c["region"] for c in candidates})
        self.assertTrue(scheduler.last_resolver_intervention)
        self.assertGreater(scheduler.greedy_fallbacks, 0)

    def test_context_uses_only_current_candidate_features_and_fixed_schema(self):
        scheduler = self.make_scheduler()
        task = generate_phase25_workload(29203, 1)[0]
        result = self.env.run([task], scheduler)
        self.assertEqual(len(scheduler.A[self.env.region_names[0]]), 12)
        self.assertEqual(len(result["agent_decisions"]), 1)
        self.assertIn("upper_confidence_reward", result["agent_decisions"][0])


if __name__ == "__main__":
    unittest.main()
