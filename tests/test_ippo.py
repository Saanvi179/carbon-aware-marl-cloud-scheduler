import unittest
import torch

from agents.actor import Actor
from agents.critic import Critic
from agents.ippo_agent import (IPPOAgent, IPPOScheduler, CarbonAwareSPTIPPOScheduler,
                               PolicyProposal, observation_vector)
from agents.rollout_buffer import RolloutBuffer
from environment.agent_api import make_observation, CandidateRegionFeatures, ActionType
from environment.cloud_environment import CloudEnvironment, Region
from environment.resource_manager import Resources
from environment.task_generator import Task
from experiments.evaluate_baselines import make_environment


SMALL_CONFIG = {"seed": 3, "hidden_size": 16, "actor_lr": 1e-3, "critic_lr": 1e-3,
                "gamma": .99, "gae_lambda": .95, "clip_epsilon": .2,
                "entropy_coefficient": .01, "max_grad_norm": .5, "update_epochs": 2,
                "lambda_latency": .25, "lambda_sla": .5, "carbon_scale_g": 100.,
                "reward_carbon_weight": 1.,
                "carbon_clip": 2., "completion_bonus": 1., "rejection_penalty": 2.5,
                "defer_penalty": .1, "forced_defer_penalty": 1.5,
                "spt_entropy_fraction": .8, "slot_seconds": 60,
                "device": "cpu"}


class IPPOTests(unittest.TestCase):
    def test_actor_critic_shapes(self):
        x = torch.zeros(5, 12)
        self.assertEqual(Actor(12, 4, 16)(x).shape, (5, 4))
        self.assertEqual(Critic(12, 16)(x).shape, (5,))

    def test_action_mask_excludes_invalid_actions(self):
        agent = IPPOAgent(hidden_size=16)
        logits = torch.tensor([0.0, 0.0, 100.0, -100.0])
        dist = agent.masked_distribution(logits, [True, True, False, False])
        self.assertAlmostEqual(float(dist.probs[2]), 0.0)
        with self.assertRaises(ValueError):
            agent.masked_distribution(logits, [False] * 4)

    def test_rollout_buffer_gae_and_clear(self):
        buffer = RolloutBuffer()
        buffer.add([0.] * 12, [True] * 4, 0, 0., .5, 1., False)
        buffer.add([0.] * 12, [True] * 4, 1, 0., .25, 2., True)
        returns, advantages = buffer.compute_returns_and_advantages(gamma=1., gae_lambda=1.)
        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(float(returns[0]), 3.)
        self.assertAlmostEqual(float(advantages[1]), 1.75)
        buffer.clear()
        self.assertEqual(len(buffer), 0)

    def test_gae_does_not_mix_interleaved_task_trajectories(self):
        buffer = RolloutBuffer()
        buffer.add([0.] * 12, [True] * 4, 0, 0., 0., 1., False, trajectory_id="task-a")
        buffer.add([0.] * 12, [True] * 4, 0, 0., 0., 10., True, trajectory_id="task-b")
        buffer.add([0.] * 12, [True] * 4, 0, 0., 0., 2., True, trajectory_id="task-a")
        returns, _ = buffer.compute_returns_and_advantages(gamma=1., gae_lambda=1.)
        self.assertEqual(returns.tolist(), [3., 10., 2.])

    def test_ppo_update_changes_parameters(self):
        agent = IPPOAgent(observation_size=12, hidden_size=16, seed=9)
        before = [p.detach().clone() for p in agent.actor.parameters()]
        for i in range(6):
            obs = [i / 10.] * 12
            mask = [True, True, i % 2 == 0, False]
            action, logp, value, _ = agent.act(obs, mask)
            agent.buffer.add(obs, mask, action, logp, value, float(i % 2), i == 5)
        stats = agent.update({**SMALL_CONFIG, "update_epochs": 2})
        self.assertTrue(any(not torch.equal(a, b) for a, b in zip(before, agent.actor.parameters())))
        self.assertTrue(torch.isfinite(torch.tensor(stats["critic_loss"])))
        self.assertGreater(stats["actor_grad_norm"], 0.0)
        self.assertGreater(stats["critic_grad_norm"], 0.0)
        self.assertGreater(stats["actor_update_l2"], 0.0)
        self.assertIn("critic_explained_variance_before_update", stats)
        self.assertEqual(stats["actor_valid_samples"], stats["actor_samples"])
        self.assertEqual(len(agent.buffer), 0)

    def test_masks_follow_region_feasibility(self):
        task = Task("t", 0, 1, 2, 4., .1, 300., 60., "north")
        resources = Resources(2, 8, 16)
        obs = make_observation(0, "north", task, resources, ("north", "west"), 200)
        capacities = {"north": (2, 8, 16), "west": (2, 8, 16), "east": (2, 8, 16)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 4)
        self.assertEqual(scheduler._mask(obs), [True, True, True, False])

    def test_entropy_guided_spt_marks_intervention(self):
        config = {**SMALL_CONFIG, "spt_entropy_fraction": 0.0}
        capacities = {"north": (2, 8, 16), "west": (2, 8, 16), "east": (2, 8, 16)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, config, 11)
        task = Task("t", 0, 1, 2, 4., .1, 300., 60., "north")
        resources = Resources(2, 8, 16)
        features = tuple(CandidateRegionFeatures(n, True, 100 + i, 1 + i, 60 + i,
                                                 0.0 if i == 0 else 1.0, .01, 2.,
                                                 2, 8, 16., 0, 0.)
                         for i, n in enumerate(("north", "west", "east")))
        obs = make_observation(0, "north", task, resources, ("north", "west", "east"), 200, features)
        candidates = [{"region": "north", "execution": 60.0},
                      {"region": "west", "execution": 30.0},
                      {"region": "east", "execution": 80.0}]
        proposal = scheduler.propose(obs, candidates, ["north", "west", "east"])
        self.assertEqual(proposal.action.value, "migrate")
        self.assertEqual(proposal.target_region, "west")
        self.assertFalse(proposal.policy_valid)

    def test_a_marl_adaptation_spt_uses_fastest_feasible_destination(self):
        config = {**SMALL_CONFIG, "spt_entropy_fraction": 0.0,
                  "spt_intervention_probability": 1.0}
        capacities = {"north": (2, 8, 16), "west": (2, 8, 16), "east": (2, 8, 16)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, config, 11)
        task = Task("t", 0, 1, 2, 4., .1, 300., 60., "north")
        resources = Resources(2, 8, 16)
        features = tuple(CandidateRegionFeatures(n, True, 100., 1., 60., 0., .01, 1.,
                                                 2, 8, 16., 0, 0.)
                         for n in ("north", "west", "east"))
        obs = make_observation(0, "north", task, resources, ("north", "west", "east"), 100., features)
        candidates = [
            {"region": "north", "execution": 90., "migration": 0., "carbon": 100.},
            {"region": "west", "execution": 50., "migration": 20., "carbon": 200.},
            {"region": "east", "execution": 40., "migration": 25., "carbon": 300.},
        ]
        proposal = scheduler.propose(obs, candidates, ["north", "west", "east"])
        self.assertEqual(proposal.target_region, "east")
        self.assertFalse(proposal.policy_valid)

    def test_carbon_aware_spt_selects_lowest_carbon_within_latency_allowance(self):
        config = {**SMALL_CONFIG, "spt_entropy_fraction": 0.0,
                  "spt_intervention_probability": 1.0,
                  "spt_latency_allowance_fraction": .10}
        capacities = {"north": (2, 8, 16), "west": (2, 8, 16), "east": (2, 8, 16)}
        scheduler = CarbonAwareSPTIPPOScheduler(["north", "west", "east"], capacities, config, 11)
        task = Task("t", 0, 1, 2, 4., .1, 300., 60., "north")
        resources = Resources(2, 8, 16)
        features = tuple(CandidateRegionFeatures(n, True, 100., 1., 60., 0., .01, 1.,
                                                 2, 8, 16., 0, 0.)
                         for n in ("north", "west", "east"))
        obs = make_observation(0, "north", task, resources, ("north", "west", "east"), 100., features)
        candidates = [
            {"region": "north", "execution": 100., "migration": 0., "carbon": 30.},
            {"region": "west", "execution": 95., "migration": 10., "carbon": 20.},
            {"region": "east", "execution": 110., "migration": 10., "carbon": 0.},
        ]
        proposal = scheduler.propose(obs, candidates, ["north", "west", "east"])
        # west is at the 10% total-latency boundary; east is slower than the bound.
        self.assertEqual(proposal.target_region, "west")
        self.assertLessEqual(105., 100. * (1. + config["spt_latency_allowance_fraction"]))
        self.assertFalse(proposal.policy_valid)

    def test_spt_intervention_samples_are_included_in_ppo_update(self):
        agent = IPPOAgent(observation_size=12, hidden_size=16, seed=9)
        agent.buffer.add([0.] * 12, [True] * 4, 1, -1.0, 0.0, 1.0, True,
                         policy_valid=False, trajectory_id="spt-task")
        stats = agent.update({**SMALL_CONFIG, "update_epochs": 1,
                              "include_spt_actor_updates": True})
        self.assertEqual(stats["actor_valid_samples"], 0)
        self.assertEqual(stats["spt_overrides"], 1)
        self.assertEqual(stats["actor_samples"], 1)

    def test_simulator_integration_and_team_metrics(self):
        env = make_environment()
        capacities = {n: (r.resources.gpus, r.resources.cpu_cores, r.resources.memory_gb)
                      for n, r in env.regions.items()}
        scheduler = IPPOScheduler(env.region_names, capacities, SMALL_CONFIG, 5)
        result = env.run([Task("tiny", 0, 1, 2, 4., .1, 300., 60., "north")], scheduler)
        self.assertEqual(result["totals"]["completed"], 1)
        self.assertIn("episode_reward", result["totals"])
        self.assertEqual([len(scheduler.agents[name].buffer) for name in ("north", "west", "east")],
                         [1, 0, 0])
        self.assertGreaterEqual(result["totals"]["spt_overrides"], 0)

    def test_owner_action_controls_placement_without_carbon_ranking(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 5)
        proposal = PolicyProposal("north", ActionType.EXECUTE_LOCAL, None, 1,
                                  tuple([0.] * 48), tuple([True] * 4), 0., 0., True, 0.,
                                  (.1, .8, .05, .05))
        candidates = [{"region": "north", "carbon": 99.}, {"region": "west", "carbon": 1.}]
        selected = scheduler.resolve(Task("north-task", 0, 1, 2, 4., .1, 300., 60., "north"),
                                     [proposal], candidates, ["north", "west", "east"])
        self.assertEqual(selected["region"], "north")

    def test_terminal_deferral_fallback_uses_first_feasible_without_carbon_ranking(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 5)
        proposal = PolicyProposal("north", ActionType.DEFER, None, 0,
                                  tuple([0.] * 48), tuple([True] * 4), 0., 0., True, 0.,
                                  (.8, .1, .05, .05))
        candidates = [{"region": "west", "carbon": 90.}, {"region": "east", "carbon": 1.}]
        selected = scheduler.resolve(Task("t", 0, 1, 2, 4., .1, 300., 60., "north"),
                                     [proposal], candidates, ["north", "west", "east"], force=True)
        self.assertEqual(selected["region"], "west")
        self.assertTrue(scheduler.last_resolver_intervention)
        self.assertEqual(scheduler.resolver_interventions, 1)

    def test_fallback_can_be_disabled_for_policy_autonomy_diagnostic(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        config = {**SMALL_CONFIG, "terminal_fallback_enabled": False}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, config, 5)
        proposal = PolicyProposal("north", ActionType.DEFER, None, 0,
                                  tuple([0.] * 48), tuple([True] * 4), 0., 0., True, 0.,
                                  (.8, .1, .05, .05))
        candidates = [{"region": "north"}, {"region": "west"}]
        selected = scheduler.resolve(Task("t", 0, 1, 2, 4., .1, 300., 60., "north"),
                                     [proposal], candidates, ["north", "west", "east"], force=True)
        self.assertIsNone(selected)
        self.assertFalse(scheduler.last_resolver_intervention)

    def test_safety_resolver_rejects_masked_or_stale_destination(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 5)
        proposal = PolicyProposal("north", ActionType.MIGRATE, "east", 3,
                                  tuple([0.] * 48), tuple([True] * 4), 0., 0., True, 0.,
                                  (.1, .1, .1, .7))
        chosen = scheduler.resolve(Task("t", 0, 1, 2, 4., .1, 300., 60., "north"),
                                  [proposal], [{"region": "north"}],
                                  ["north", "west", "east"])
        self.assertIsNone(chosen)
        self.assertEqual(scheduler.resolver_interventions, 1)

    def test_individual_reward_and_defer_terminal_lifecycle(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 5)
        task = Task("chain", 0, 1, 2, 4., .1, 300., 60., "north")
        def proposal(index, action):
            return PolicyProposal("north", action, None, index, tuple([0.] * 48),
                                  tuple([True] * 4), 0., 0., True, 0., (.25,) * 4)
        events = [{"task": task, "proposals": [proposal(0, ActionType.DEFER)],
                   "outcome": "defer", "choice": None},
                  {"task": task, "proposals": [proposal(1, ActionType.EXECUTE_LOCAL)],
                   "outcome": "execute_local", "choice": {"carbon": 5., "migration": 0., "execution": 60.}}]
        scheduler.end_episode(events, {"totals": {}})
        buffer = scheduler.agents["north"].buffer
        self.assertEqual(buffer.trajectory_ids, ["chain", "chain"])
        self.assertEqual(buffer.dones, [False, True])
        self.assertAlmostEqual(buffer.rewards[0], -SMALL_CONFIG["defer_penalty"])
        self.assertEqual(len(scheduler.agents["west"].buffer), 0)
        self.assertEqual(len(scheduler.agents["east"].buffer), 0)

    def test_rejection_ends_owner_trajectory_with_penalty(self):
        capacities = {"north": (8, 64, 256), "west": (6, 48, 192), "east": (10, 80, 384)}
        scheduler = IPPOScheduler(["north", "west", "east"], capacities, SMALL_CONFIG, 5)
        task = Task("rejected", 0, 1, 2, 4., .1, 300., 60., "north")
        proposal = PolicyProposal("north", ActionType.DEFER, None, 0,
                                  tuple([0.] * 48), tuple([True] * 4), 0., 0., True, 0.,
                                  (.25,) * 4)
        scheduler.end_episode([{"task": task, "proposals": [proposal],
                                "outcome": "reject", "choice": None}], {"totals": {}})
        owner_buffer = scheduler.agents["north"].buffer
        self.assertEqual(owner_buffer.dones, [True])
        self.assertAlmostEqual(owner_buffer.rewards[0], -3.0)
        self.assertEqual(len(scheduler.agents["west"].buffer), 0)

    def test_candidate_features_expand_observation_vector(self):
        task = Task("t", 0, 1, 2, 4., .1, 300., 60., "a")
        feature = CandidateRegionFeatures("a", True, 100., 1., 60., 0., .01, 1., 1, 2, 4., 0, 0.)
        obs = make_observation(0, "a", task, Resources(1, 2, 4), ("a",), 100.,
                              (feature, feature, feature))
        caps = {"a": (1, 2, 4), "b": (1, 2, 4), "c": (1, 2, 4)}
        legacy = observation_vector(obs, caps, 60, observation_size=48)
        expanded = observation_vector(obs, caps, 60, observation_size=54)
        self.assertEqual(len(legacy), 48)
        self.assertEqual(len(expanded), 54)
        self.assertAlmostEqual(expanded[-2], min(1.0, 60.0 / 300.0))
        self.assertAlmostEqual(expanded[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
