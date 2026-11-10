import unittest

from agents.reward import (execution_reward, deferral_reward, terminal_rejection_reward,
                           forced_defer_reward, minimum_feasible_execution_reward,
                           validate_reward_config)


class RewardDesignTests(unittest.TestCase):
    def setUp(self):
        self.config = {"carbon_scale_g": 100., "carbon_clip": 2., "completion_bonus": 1.,
                       "reward_carbon_weight": 1., "lambda_latency": .25, "lambda_sla": .5,
                       "rejection_penalty": 2.5, "defer_penalty": .1,
                       "forced_defer_penalty": 1.5}

    def test_components_are_normalized_and_carbon_is_bounded(self):
        reward, parts = execution_reward(10000, 10000, 10, self.config)
        self.assertEqual(parts["carbon"], -2.0)
        self.assertEqual(parts["latency"], -self.config["lambda_latency"])
        self.assertEqual(parts["completion"], self.config["completion_bonus"])
        self.assertAlmostEqual(reward, sum(parts.values()))

    def test_rejection_is_worse_than_worst_feasible_execution(self):
        accepted, _ = execution_reward(200, 100, 100, self.config)
        rejected, _ = terminal_rejection_reward(self.config)
        self.assertGreaterEqual(accepted, minimum_feasible_execution_reward(self.config))
        self.assertLess(rejected, minimum_feasible_execution_reward(self.config))

    def test_deferral_has_strict_cost_and_no_completion_credit(self):
        deferred, parts = deferral_reward(self.config)
        executed, _ = execution_reward(0, 0, 100, self.config)
        self.assertEqual(deferred, -self.config["defer_penalty"])
        self.assertEqual(parts["completion"], 0)
        self.assertLess(deferred, executed)
        self.assertLess(2 * deferred, deferred)

    def test_invalid_reward_that_favors_rejection_is_rejected(self):
        self.config["rejection_penalty"] = 0
        with self.assertRaises(ValueError):
            validate_reward_config(self.config)

    def test_forced_deferral_cost_is_worse_than_feasible_completion(self):
        forced, components = forced_defer_reward(self.config)
        feasible, _ = execution_reward(0, 0, 100, self.config)
        self.assertLess(forced, feasible)
        self.assertEqual(components["completion"], 0)


if __name__ == "__main__":
    unittest.main()
