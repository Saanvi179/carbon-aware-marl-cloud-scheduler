"""Safety-gated disjoint LinUCB for online feasible-region selection."""
from dataclasses import dataclass
import math

import numpy as np

from environment.agent_api import ActionType
from schedulers.greedy_carbon import GreedyCarbonScheduler


@dataclass(frozen=True)
class BanditProposal:
    agent_region: str
    action: ActionType
    target_region: str | None
    selected_region: str | None
    context: tuple[float, ...] | None
    predicted_reward: float | None
    upper_confidence_reward: float | None
    greedy_region: str | None
    fallback_used: bool
    fallback_reason: str | None
    candidate_diagnostics: tuple[dict, ...] = ()


class ContextualBanditScheduler:
    """Online contextual region selector; feasibility remains an environment rule.

    Each destination is a disjoint linear arm. Context contains only the current
    task's online candidate metrics, current resources/queue, and current slot.
    The learner receives feedback only for the region actually committed.
    """
    owner_controlled = True

    def __init__(self, region_names, capacities, alpha=0.8, ridge=1.0,
                 carbon_scale_g=100.0, latency_weight=0.25,
                 deterministic=False, learning_enabled=True):
        if alpha < 0 or ridge <= 0 or carbon_scale_g <= 0:
            raise ValueError("alpha must be nonnegative; ridge and carbon scale must be positive")
        self.region_names = list(region_names)
        self.capacities = capacities
        self.alpha, self.ridge = float(alpha), float(ridge)
        self.carbon_scale_g, self.latency_weight = float(carbon_scale_g), float(latency_weight)
        self.deterministic, self.learning_enabled = deterministic, learning_enabled
        self.feature_size = 12
        self.A = {name: np.eye(self.feature_size, dtype=float) * self.ridge
                  for name in self.region_names}
        self.b = {name: np.zeros(self.feature_size, dtype=float) for name in self.region_names}
        self.arm_counts = {name: 0 for name in self.region_names}
        self.last_resolver_intervention = False
        self.decisions = 0
        self.greedy_fallbacks = 0
        self.feedback_count = 0
        self.last_trace = []

    def candidate_context(self, observation, candidate):
        region = candidate["region"]
        region_features = next((feature for feature in observation.candidate_features
                                if feature.region == region), None)
        capacity = self.capacities[region]
        task = observation.task
        available_deadline = max(1.0, task.deadline_seconds - observation.slot * 60.0)
        if region_features is None:
            # Candidate metrics are generated online in the same snapshot. This
            # fallback is for compatible callers with the typed features omitted.
            gpus = candidate.get("available_gpus", capacity[0])
            cpus = candidate.get("available_cpu_cores", capacity[1])
            memory = candidate.get("available_memory_gb", capacity[2])
            carbon_intensity = candidate.get("carbon_intensity", 0.0)
            energy = candidate.get("energy", 0.0)
            emissions = candidate.get("carbon", 0.0)
            execution = candidate["execution"]
            migration = candidate["migration"]
            queue_length = candidate.get("queue_length", 0)
            queued_work = candidate.get("queued_work_seconds", 0.0)
        else:
            gpus, cpus, memory = (region_features.available_gpus,
                                  region_features.available_cpu_cores,
                                  region_features.available_memory_gb)
            carbon_intensity = region_features.carbon_intensity_gco2e_kwh
            energy, emissions = region_features.energy_kwh, region_features.emissions_gco2e
            execution, migration = region_features.execution_seconds, region_features.migration_seconds
            queue_length, queued_work = region_features.queue_length, region_features.queued_work_seconds
        return (1.0, carbon_intensity / 1000.0, emissions / 200.0,
                energy / 2.0, execution / 1000.0, migration / 100.0,
                gpus / max(1, capacity[0]), cpus / max(1, capacity[1]),
                memory / max(1.0, capacity[2]), queue_length / 16.0,
                queued_work / 2000.0, min(1.0, (migration + execution) / available_deadline))

    def _estimate(self, region, context):
        vector = np.asarray(context, dtype=float)
        try:
            theta = np.linalg.solve(self.A[region], self.b[region])
            confidence = math.sqrt(max(0.0, float(vector @ np.linalg.solve(self.A[region], vector))))
            mean = float(theta @ vector)
            return mean, mean + self.alpha * confidence
        except (np.linalg.LinAlgError, FloatingPointError, ValueError):
            return float("nan"), float("nan")

    def _observed_reward(self, choice, task):
        deadline = max(1.0, task.deadline_seconds - task.arrival_slot * 60.0)
        carbon = min(max(0.0, choice["carbon"]) / self.carbon_scale_g, 2.0)
        latency = min(max(0.0, choice["migration"] + choice["execution"]) / deadline, 1.0)
        return 1.0 - carbon - self.latency_weight * latency

    def _greedy_candidate(self, observation, candidates, region_names):
        return GreedyCarbonScheduler().choose(observation.task, candidates, region_names)

    def propose(self, observation, candidates, region_names):
        self.decisions += 1
        owner = observation.task.source_region
        if not candidates:
            return BanditProposal(owner, ActionType.DEFER, None, None, None, None, None,
                                  None, False, "no_feasible_candidate")
        greedy = self._greedy_candidate(observation, candidates, region_names)
        contexts = {candidate["region"]: self.candidate_context(observation, candidate)
                    for candidate in candidates}
        estimates = {name: self._estimate(name, context) for name, context in contexts.items()}
        candidate_diagnostics = tuple({
            "region": candidate["region"], "feasible": bool(candidate.get("feasible", False)),
            "carbon_intensity_gco2e_kwh": candidate.get("carbon_intensity"),
            "carbon_gco2e": candidate["carbon"], "energy_kwh": candidate["energy"],
            "execution_seconds": candidate["execution"], "migration_seconds": candidate["migration"],
            "available_gpus": candidate.get("available_gpus"),
            "available_cpu_cores": candidate.get("available_cpu_cores"),
            "available_memory_gb": candidate.get("available_memory_gb"),
            "linucb_mean": estimates[candidate["region"]][0],
            "linucb_ucb": estimates[candidate["region"]][1],
        } for candidate in candidates)
        if any(not math.isfinite(pair[0]) or not math.isfinite(pair[1]) for pair in estimates.values()):
            selected, mean, upper, fallback, reason = greedy, None, None, True, "invalid_model_estimate"
        else:
            key = (lambda c: estimates[c["region"]][0]) if self.deterministic else (
                lambda c: estimates[c["region"]][1])
            selected = max(candidates, key=key)
            mean, upper = estimates[selected["region"]]
            greedy_context = contexts[greedy["region"]]
            greedy_reward = self._observed_reward(greedy, observation.task)
            greedy_mean, greedy_upper = estimates[greedy["region"]]
            # Online safety gate: an uncertain alternative may be explored only
            # while its UCB clears the known immediate greedy-candidate reward.
            gate_score = mean if self.deterministic else upper
            if selected["region"] != greedy["region"] and gate_score < greedy_reward:
                selected, mean, upper, fallback, reason = greedy, greedy_mean, greedy_upper, True, "below_greedy_reward_bound"
            else:
                fallback, reason = False, None
        if fallback:
            self.greedy_fallbacks += 1
        target = selected["region"]
        action = ActionType.EXECUTE_LOCAL if target == owner else ActionType.MIGRATE
        return BanditProposal(owner, action, None if action == ActionType.EXECUTE_LOCAL else target,
                              target, tuple(contexts[target]), mean, upper, greedy["region"],
                              fallback, reason, candidate_diagnostics)

    def resolve(self, task, proposals, candidates, region_names, force=False):
        self.last_resolver_intervention = False
        if len(proposals) != 1 or proposals[0].agent_region != task.source_region:
            raise ValueError("contextual bandit placement must be decided by the task's source-region owner")
        proposal = proposals[0]
        by_region = {candidate["region"]: candidate for candidate in candidates}
        if proposal.selected_region is None:
            return None
        choice = by_region.get(proposal.selected_region)
        if choice is None or not choice.get("feasible", False) or choice["end"] > task.deadline_seconds:
            if not candidates:
                return None
            self.last_resolver_intervention = True
            self.greedy_fallbacks += 1
            return self._greedy_candidate(type("Obs", (), {"task": task})(), candidates, region_names)
        return choice

    def end_episode(self, decision_events, result):
        trace = []
        rewards = []
        for event in decision_events:
            task, choice = event["task"], event["choice"]
            proposal = event["proposals"][0]
            payoff = self._observed_reward(choice, task) if choice is not None else None
            updated = False
            actual_region = choice["region"] if choice is not None else None
            if (payoff is not None and proposal.context is not None and
                    proposal.selected_region == actual_region):
                x = np.asarray(proposal.context, dtype=float)
                if self.learning_enabled:
                    self.A[actual_region] += np.outer(x, x)
                    self.b[actual_region] += payoff * x
                    self.arm_counts[actual_region] += 1
                    self.feedback_count += 1
                    updated = True
                rewards.append(payoff)
            trace.append({"task_id": task.task_id, "agent": task.source_region,
                          "action": proposal.action.value, "selected_region": proposal.selected_region,
                          "actual_region": actual_region,
                          "greedy_region": proposal.greedy_region,
                          "predicted_reward": proposal.predicted_reward,
                          "upper_confidence_reward": proposal.upper_confidence_reward,
                          "candidate_diagnostics": list(proposal.candidate_diagnostics),
                          "fallback_used": proposal.fallback_used,
                          "fallback_reason": proposal.fallback_reason,
                          "outcome": event["outcome"], "payoff": payoff,
                          "learning_update": updated,
                          "resolver_intervention": event.get("resolver_intervention", False)})
        result["totals"]["bandit_decisions"] = self.decisions
        result["totals"]["greedy_fallbacks"] = self.greedy_fallbacks
        result["totals"]["fallback_rate"] = self.greedy_fallbacks / max(1, self.decisions)
        result["totals"]["bandit_feedback_updates"] = self.feedback_count
        result["totals"]["bandit_arm_counts"] = dict(self.arm_counts)
        result["totals"]["mean_observed_payoff"] = sum(rewards) / max(1, len(rewards))
        result["agent_decisions"] = trace
        result["episode_reward"] = sum(rewards)
        self.last_trace = trace
        self.decisions = self.greedy_fallbacks = self.feedback_count = 0
        return result["episode_reward"]

    def checkpoint(self):
        return {"region_names": list(self.region_names), "feature_size": self.feature_size,
                "alpha": self.alpha, "ridge": self.ridge,
                "carbon_scale_g": self.carbon_scale_g, "latency_weight": self.latency_weight,
                "A": {name: value.tolist() for name, value in self.A.items()},
                "b": {name: value.tolist() for name, value in self.b.items()},
                "arm_counts": dict(self.arm_counts), "feedback_count": self.feedback_count}

    def load_checkpoint(self, state):
        if state["region_names"] != self.region_names or state["feature_size"] != self.feature_size:
            raise ValueError("bandit checkpoint does not match the region/feature schema")
        self.A = {name: np.asarray(state["A"][name], dtype=float) for name in self.region_names}
        self.b = {name: np.asarray(state["b"][name], dtype=float) for name in self.region_names}
        self.arm_counts = {name: int(state["arm_counts"][name]) for name in self.region_names}
        self.feedback_count = int(state.get("feedback_count", sum(self.arm_counts.values())))
