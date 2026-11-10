import unittest
from experiments.diagnose_ippo import varied_synthetic_workload
from environment.task_generator import (generate_variable_workload, generate_diverse_workload,
                                        generate_phase25_workload)
from experiments.run_phase24 import summarize_actions
from experiments.evaluate_baselines import make_phase25_environment


class IPPODiagnosticTests(unittest.TestCase):
    def test_held_out_synthetic_variants_are_reproducible_and_distinct(self):
        first = varied_synthetic_workload(101)
        repeated = varied_synthetic_workload(101)
        other = varied_synthetic_workload(202)
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other)
        self.assertEqual(len(first), 6)

    def test_zero_workload_seed_is_original_reference_trace(self):
        from environment.task_generator import synthetic_workload
        self.assertEqual(varied_synthetic_workload(0), synthetic_workload())

    def test_training_workloads_are_variable_reproducible_and_distinct_from_demo(self):
        first = generate_variable_workload(17001, 18)
        self.assertEqual(first, generate_variable_workload(17001, 18))
        self.assertNotEqual(first, generate_variable_workload(17002, 18))
        self.assertEqual(len(first), 18)
        self.assertTrue(all(task.task_id.startswith("w17001-") for task in first))

    def test_expanded_training_workloads_vary_all_requested_dimensions(self):
        first = generate_diverse_workload(2401, 120)
        self.assertEqual(first, generate_diverse_workload(2401, 120))
        self.assertNotEqual(first, generate_diverse_workload(2402, 120))
        self.assertGreater(max(t.arrival_slot for t in first), 12)
        self.assertGreater(max(t.runtime_seconds for t in first), 480)
        self.assertIn(8, {t.gpu_count for t in first})
        self.assertGreater(max(t.dataset_gb for t in first), 1.5)
        self.assertGreater(len({round(t.deadline_seconds - t.arrival_slot * 60 - t.runtime_seconds)
                                for t in first}), 100)

    def test_phase25_workload_is_reproducible_and_varies_task_dimensions(self):
        first = generate_phase25_workload(25101, 100)
        self.assertEqual(first, generate_phase25_workload(25101, 100))
        self.assertNotEqual(first, generate_phase25_workload(25102, 100))
        self.assertEqual(min(t.arrival_slot for t in first), 0)
        self.assertEqual(max(t.arrival_slot for t in first), 60)
        self.assertGreater(len({t.runtime_seconds for t in first}), 90)
        self.assertIn(8, {t.gpu_count for t in first})
        self.assertGreater(max(t.dataset_gb for t in first), 1.0)
        self.assertGreater(len({round(t.deadline_seconds - t.arrival_slot * 60 - t.runtime_seconds)
                                for t in first}), 30)

    def test_action_diagnostics_distinguish_proposal_from_resolver(self):
        decision = {"selected_action": "defer", "outcome": "forced_execute",
                    "mask": [True, True, False, False],
                    "probabilities": [0.6, 0.4, 0.0, 0.0], "entropy": 0.673,
                    "spt_override": False, "resolver_intervention": True}
        summary = summarize_actions([decision])
        self.assertEqual(summary["selected_action_counts"]["defer"], 1)
        self.assertEqual(summary["forced_execution_count"], 1)
        self.assertEqual(summary["legal_action_count_distribution"]["2"], 1)
        self.assertAlmostEqual(sum(summary["mean_masked_probabilities"].values()), 1.0)

    def test_observation_exposes_carbon_changes_at_predicted_execution_time(self):
        from agents.ippo_agent import observation_vector
        from environment.task_generator import Task
        from environment.agent_api import make_observation, CandidateRegionFeatures
        from environment.resource_manager import Resources
        env = make_phase25_environment(dynamic_carbon=True)
        task = Task("carbon-observation", 0, 1, 4, 16.0, 0.5, 10000.0, 180.0, "north")
        capacities = {name: (r.resources.gpus, r.resources.cpu_cores, r.resources.memory_gb)
                      for name, r in env.regions.items()}
        vectors = []
        masked_vector = None
        for slot in (8, 30):
            features = []
            for name in env.region_names:
                candidate = env._candidate_metrics(name, task, slot, [])
                region = env.regions[name]
                features.append(CandidateRegionFeatures(name, True, candidate["carbon_intensity"],
                    candidate["execution_speed"], candidate["execution"], candidate["migration"],
                    candidate["energy"], candidate["carbon"], region.resources.gpus,
                    region.resources.cpu_cores, region.resources.memory_gb, 0, 0.0))
            observation = make_observation(slot, "north", task, Resources(8, 64, 256),
                tuple(env.region_names), env.carbon_model.intensity_at("north", slot * 60, 60),
                tuple(features))
            vectors.append(observation_vector(observation, capacities, 60, 54))
            if slot == 8:
                masked_vector = observation_vector(observation, capacities, 60, 54, "no_carbon")
        self.assertNotEqual(vectors[0][10], vectors[1][10])
        self.assertNotEqual(vectors[0][13], vectors[1][13])
        self.assertEqual(masked_vector[10], 0.0)
        self.assertEqual([masked_vector[i] for i in (13, 18, 27, 32, 41, 46)], [0.0] * 6)
        self.assertNotEqual(masked_vector[15], 0.0)  # execution-duration information remains available


if __name__ == "__main__":
    unittest.main()
