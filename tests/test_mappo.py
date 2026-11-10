import copy
import unittest
import torch

from agents.mappo_agent import MAPPOScheduler
from experiments.evaluate_baselines import make_phase25_environment
from environment.task_generator import generate_phase25_workload


class MAPPOTests(unittest.TestCase):
    def setUp(self):
        env = make_phase25_environment()
        self.env = env
        self.config = {"slot_seconds": 60, "hidden_size": 16, "observation_size": 54,
                       "actor_lr": 3e-4, "critic_lr": 1e-3, "device": "cpu",
                       "gamma": .99, "gae_lambda": .95, "clip_epsilon": .2,
                       "entropy_coefficient": .002, "max_grad_norm": .5,
                       "update_epochs": 2, "spt_entropy_fraction": .8,
                       "spt_intervention_probability": 0.0,
                       "terminal_fallback_enabled": True,
                       "lambda_latency": .25, "lambda_sla": .5,
                       "reward_carbon_weight": 1., "carbon_scale_g": 100.,
                       "carbon_clip": 2., "completion_bonus": 1.,
                       "rejection_penalty": 2.5, "defer_penalty": .1,
                       "forced_defer_penalty": 1.5}
        self.capacities = {n: (r.resources.gpus, r.resources.cpu_cores, r.resources.memory_gb)
                           for n, r in env.regions.items()}
        self.scheduler = MAPPOScheduler(env.region_names, self.capacities, self.config, seed=13)

    def test_global_state_contains_all_regions_and_actor_identity(self):
        task = generate_phase25_workload(881, 1)[0]
        result = self.env.run([task], self.scheduler)
        proposal = result["agent_decisions"][0]
        expected_size = len(self.env.region_names) * 54 + len(self.env.region_names)
        self.assertEqual(self.scheduler.global_observation_size, expected_size)
        stored = self.scheduler.agents[task.source_region].buffer.critic_observations
        self.assertTrue(stored)
        self.assertEqual(stored[0].numel(), expected_size)
        self.assertIn("individual_reward", proposal)
        self.assertEqual(sum(result["agent_rewards"].values()), result["episode_reward"])

    def test_central_critic_trains_and_reports_diagnostics(self):
        initial = copy.deepcopy(self.scheduler.central_critic.state_dict())
        self.env.run(generate_phase25_workload(882, 8), self.scheduler)
        stats = self.scheduler.update()
        self.assertEqual(stats["central_critic"]["samples"], sum(
            stats["actors"][name].get("actor_valid_samples", 0) + stats["actors"][name].get("spt_overrides", 0)
            for name in self.scheduler.region_names))
        self.assertGreater(stats["central_critic"]["critic_grad_norm"], 0)
        self.assertTrue(any(not torch.equal(initial[k], self.scheduler.central_critic.state_dict()[k])
                            for k in initial))
        self.assertIn("actor_grad_norm", stats["actors"]["north"])

    def test_action_masking_remains_respected_with_global_critic(self):
        task = generate_phase25_workload(883, 1)[0]
        result = self.env.run([task], self.scheduler)
        decision = result["agent_decisions"][0]
        for valid, probability in zip(decision["mask"], decision["probabilities"]):
            if not valid:
                self.assertEqual(probability, 0.0)

    def test_reward_attribution_is_only_to_controlling_agent(self):
        task = generate_phase25_workload(884, 1)[0]
        result = self.env.run([task], self.scheduler)
        self.assertEqual(set(result["agent_rewards"]), set(self.env.region_names))
        non_owner = set(self.env.region_names) - {task.source_region}
        self.assertTrue(all(result["agent_rewards"][name] == 0.0 for name in non_owner))


if __name__ == "__main__":
    unittest.main()
