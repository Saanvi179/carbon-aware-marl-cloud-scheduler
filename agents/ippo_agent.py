"""Independent PPO agents and their simultaneous-action scheduler adapter."""
from dataclasses import dataclass
import math
import random
import torch
from torch.distributions import Categorical
from torch.nn import functional as F
from torch.optim import Adam

from .actor import Actor
from .critic import Critic
from .rollout_buffer import RolloutBuffer
from .reward import (validate_reward_config, deferral_reward,
                     terminal_rejection_reward, execution_reward, forced_defer_reward)
from environment.agent_api import ActionType


@dataclass(frozen=True)
class PolicyProposal:
    agent_region: str
    action: ActionType
    target_region: str | None
    action_index: int
    observation: tuple[float, ...]
    mask: tuple[bool, ...]
    log_probability: float
    value: float
    policy_valid: bool
    entropy: float
    action_probabilities: tuple[float, ...]
    critic_observation: tuple[float, ...] | None = None


def observation_vector(observation, region_capacities, slot_seconds, observation_size=54,
                       observation_ablation="none"):
    """Normalized task state plus 12 (legacy) or 14 (expanded) values per candidate."""
    task = observation.task
    remaining_deadline = max(1.0, task.deadline_seconds - observation.slot * slot_seconds)
    core = [
        observation.slot / 100.0,
        task.gpu_count / 16.0,
        task.cpu_cores / 128.0,
        task.memory_gb / 512.0,
        task.dataset_gb / 10.0,
        task.runtime_seconds / 1000.0,
        max(0.0, task.deadline_seconds - observation.slot * slot_seconds) / 2000.0,
        observation.available_gpus / max(1, region_capacities[observation.region][0]),
        observation.available_cpu_cores / max(1, region_capacities[observation.region][1]),
        observation.available_memory_gb / max(1.0, region_capacities[observation.region][2]),
        observation.carbon_intensity_gco2e_kwh / 1000.0,
        float(observation.local_feasible),
    ]
    if observation_ablation == "no_carbon":
        core[10] = 0.0
    candidate_values = []
    for feature in observation.candidate_features:
        fields = [
              float(feature.feasible), feature.carbon_intensity_gco2e_kwh / 1000.0,
              feature.execution_speed / 2.0, feature.execution_seconds / 1000.0,
              feature.migration_seconds / 100.0, feature.energy_kwh,
              feature.emissions_gco2e / 100.0,
              feature.available_gpus / max(1, region_capacities[feature.region][0]),
              feature.available_cpu_cores / max(1, region_capacities[feature.region][1]),
              feature.available_memory_gb / max(1.0, region_capacities[feature.region][2]),
              feature.queue_length / 16.0, feature.queued_work_seconds / 2000.0]
        if observation_size >= 54:
            total_latency = feature.migration_seconds + feature.execution_seconds
            fields.extend((min(1.0, total_latency / remaining_deadline),
                           feature.migration_seconds / max(1.0, total_latency)))
        if observation_ablation == "no_carbon":
            fields[1] = 0.0  # candidate grid intensity
            fields[6] = 0.0  # candidate emissions estimate
        candidate_values.extend(fields)
    return tuple(core) + tuple(candidate_values)


class IPPOAgent:
    def __init__(self, observation_size=48, action_count=4, hidden_size=64,
                 actor_lr=3e-4, critic_lr=1e-3, device="cpu", seed=0):
        torch.manual_seed(seed)
        self.device = torch.device(device)
        self.actor = Actor(observation_size, action_count, hidden_size).to(self.device)
        self.critic = Critic(observation_size, hidden_size).to(self.device)
        self.actor_optimizer = Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = Adam(self.critic.parameters(), lr=critic_lr)
        self.buffer = RolloutBuffer()

    @staticmethod
    def masked_distribution(logits, mask):
        mask = torch.as_tensor(mask, dtype=torch.bool, device=logits.device)
        if not bool(mask.any()):
            raise ValueError("at least one action must be valid")
        return Categorical(logits=logits.masked_fill(~mask, torch.finfo(logits.dtype).min))

    def act(self, observation, mask, deterministic=False):
        obs = torch.as_tensor(observation, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            distribution = self.masked_distribution(self.actor(obs), mask)
            action = distribution.probs.argmax(-1) if deterministic else distribution.sample()
            value = self.critic(obs)
            return int(action.item()), float(distribution.log_prob(action).item()), \
                float(value.item()), float(distribution.entropy().item())

    def update(self, config):
        if len(self.buffer) == 0:
            return {"actor_loss": 0.0, "critic_loss": 0.0, "entropy": 0.0}
        returns, advantages = self.buffer.compute_returns_and_advantages(
            config["gamma"], config["gae_lambda"])
        obs = torch.stack(self.buffer.observations).to(self.device)
        masks = torch.stack(self.buffer.masks).to(self.device)
        actions = torch.tensor(self.buffer.actions, dtype=torch.long, device=self.device)
        old_logp = torch.tensor(self.buffer.log_probabilities, dtype=torch.float32, device=self.device)
        returns, advantages = returns.to(self.device), advantages.to(self.device)
        # The A-MARL-derived research config stores PPO log probabilities for
        # entropy-triggered SPT actions and updates on those transitions too,
        # matching the author learner. Older experiment configs retain their
        # original policy-only actor update unless they opt in explicitly.
        policy_sample = torch.tensor(self.buffer.policy_valid, dtype=torch.bool, device=self.device)
        valid = (torch.ones(len(self.buffer), dtype=torch.bool, device=self.device)
                 if config.get("include_spt_actor_updates", False) else policy_sample)
        raw_advantages = advantages.detach().clone()
        value_before = self.critic(obs).detach()
        returns_var = torch.var(returns, unbiased=False)
        explained_variance = (1.0 - torch.var(returns - value_before, unbiased=False) /
                              returns_var.clamp_min(1e-8))
        actor_before = torch.cat([parameter.detach().flatten() for parameter in self.actor.parameters()])
        valid_advantages = raw_advantages[policy_sample] if bool(policy_sample.any()) else raw_advantages
        if bool(valid.any()):
            selected = advantages[valid]
            advantages = advantages.clone()
            advantages[valid] = (selected - selected.mean()) / (selected.std(unbiased=False) + 1e-8)
        clip = config["clip_epsilon"]
        actor_losses, critic_losses, entropies = [], [], []
        actor_grad_norms, critic_grad_norms, approximate_kls = [], [], []
        for _ in range(config["update_epochs"]):
            logits = self.actor(obs)
            distributions = [self.masked_distribution(logits[i], masks[i]) for i in range(len(obs))]
            logp = torch.stack([d.log_prob(actions[i]) for i, d in enumerate(distributions)])
            entropy = torch.stack([d.entropy() for d in distributions])
            if bool(valid.any()):
                ratio = torch.exp(logp[valid] - old_logp[valid])
                surr1 = ratio * advantages[valid]
                surr2 = torch.clamp(ratio, 1 - clip, 1 + clip) * advantages[valid]
                actor_loss = -torch.minimum(surr1, surr2).mean() - config["entropy_coefficient"] * entropy[valid].mean()
                self.actor_optimizer.zero_grad(); actor_loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(self.actor.parameters(), config["max_grad_norm"])
                actor_grad_norms.append(float(grad_norm.detach().cpu()))
                self.actor_optimizer.step()
                actor_losses.append(float(actor_loss.detach().cpu()))
                entropies.append(float(entropy[valid].mean().detach().cpu()))
                with torch.no_grad():
                    refreshed = self.actor(obs)
                    refreshed_distributions = [self.masked_distribution(refreshed[i], masks[i])
                                                for i in range(len(obs))]
                    refreshed_logp = torch.stack([d.log_prob(actions[i])
                                                  for i, d in enumerate(refreshed_distributions)])
                    approximate_kls.append(float((old_logp[valid] - refreshed_logp[valid]).mean().cpu()))
            value = self.critic(obs)
            critic_loss = F.mse_loss(value, returns)
            self.critic_optimizer.zero_grad(); critic_loss.backward()
            value_grad_norm = torch.nn.utils.clip_grad_norm_(self.critic.parameters(), config["max_grad_norm"])
            critic_grad_norms.append(float(value_grad_norm.detach().cpu()))
            self.critic_optimizer.step()
            critic_losses.append(float(critic_loss.detach().cpu()))
        actor_after = torch.cat([parameter.detach().flatten() for parameter in self.actor.parameters()])
        stats = {"actor_loss": sum(actor_losses) / max(1, len(actor_losses)),
                 "critic_loss": sum(critic_losses) / len(critic_losses),
                 "entropy": sum(entropies) / max(1, len(entropies)),
                 "actor_samples": len(self.buffer),
                 "actor_valid_samples": int(policy_sample.sum().item()),
                 "spt_overrides": len(self.buffer) - int(policy_sample.sum().item()),
                 "actor_grad_norm": sum(actor_grad_norms) / max(1, len(actor_grad_norms)),
                 "critic_grad_norm": sum(critic_grad_norms) / max(1, len(critic_grad_norms)),
                 "approx_kl": sum(approximate_kls) / max(1, len(approximate_kls)),
                 "mean_return": float(returns.mean().cpu()),
                 "return_std": float(returns.std(unbiased=False).cpu()),
                 "mean_value_estimate_before_update": float(value_before.mean().cpu()),
                 "value_estimate_std_before_update": float(value_before.std(unbiased=False).cpu()),
                 "critic_explained_variance_before_update": float(explained_variance.cpu()),
                 "mean_raw_advantage": float(valid_advantages.mean().cpu()),
                 "raw_advantage_std": float(valid_advantages.std(unbiased=False).cpu()),
                 "actor_update_l2": float(torch.linalg.vector_norm(actor_after - actor_before).cpu())}
        self.buffer.clear()
        return stats

    def checkpoint(self):
        return {"actor": self.actor.state_dict(), "critic": self.critic.state_dict(),
                "actor_optimizer": self.actor_optimizer.state_dict(),
                "critic_optimizer": self.critic_optimizer.state_dict()}

    def load_checkpoint(self, state):
        self.actor.load_state_dict(state["actor"]); self.critic.load_state_dict(state["critic"])
        if "actor_optimizer" in state: self.actor_optimizer.load_state_dict(state["actor_optimizer"])
        if "critic_optimizer" in state: self.critic_optimizer.load_state_dict(state["critic_optimizer"])


class IPPOScheduler:
    """Source-region-owned IPPO decisions with a feasibility-only safety resolver."""
    owner_controlled = True
    def __init__(self, region_names, capacities, config, seed=7, deterministic=False):
        self.region_names, self.capacities, self.config = list(region_names), capacities, config
        validate_reward_config(config)
        self.slot_seconds = config["slot_seconds"]
        self.deterministic = deterministic
        self.agents = {name: IPPOAgent(hidden_size=config["hidden_size"],
                                       observation_size=config.get("observation_size", 48),
                                       actor_lr=config["actor_lr"], critic_lr=config["critic_lr"],
                                       device=config.get("device", "cpu"),
                                       seed=seed + i * 997)
                       for i, name in enumerate(self.region_names)}
        self.spt_overrides = 0
        self.resolver_interventions = 0
        self.last_resolver_intervention = False

    def _spt_destination(self, candidates, region_names):
        """Return the project adaptation of SPT for the current task.

        A-MARL's JobShop selects a shortest operation among schedulable jobs.
        This simulator has already fixed the arriving task, so the base mapping
        selects its fastest feasible destination. Subclasses/configured variants
        may alter only this selector.
        """
        return min(candidates, key=lambda c: (c["execution"], region_names.index(c["region"])))

    def _mask(self, observation):
        feasible = set(observation.feasible_destinations)
        remotes = [name for name in self.region_names if name != observation.region]
        return [True, observation.region in feasible,
                *(name in feasible for name in remotes)]

    def _decode(self, region, index):
        if index == 0:
            return ActionType.DEFER, None
        if index == 1:
            return ActionType.EXECUTE_LOCAL, None
        remotes = [name for name in self.region_names if name != region]
        return ActionType.MIGRATE, remotes[index - 2]

    def propose(self, observation, candidates, region_names):
        return self._propose(observation, candidates, region_names, None)

    def _propose(self, observation, candidates, region_names, all_observations):
        region = observation.region
        obs = observation_vector(observation, self.capacities, self.slot_seconds,
                                 self.config.get("observation_size", 48),
                                 self.config.get("observation_ablation", "none"))
        mask = self._mask(observation)
        agent = self.agents[region]
        index, logp, value, entropy = agent.act(obs, mask, self.deterministic)
        with torch.no_grad():
            initial_dist = agent.masked_distribution(agent.actor(torch.tensor(obs, dtype=torch.float32)), mask)
            action_probabilities = tuple(float(x) for x in initial_dist.probs.tolist())
        legal_count = sum(mask)
        # The original A-MARL code uses alpha*log(action-count). Since this
        # cloud adaptation masks infeasible actions, use the effective support
        # size of the masked categorical distribution.
        threshold = self.config["spt_entropy_fraction"] * math.log(max(1, legal_count))
        override = (not self.deterministic and entropy > threshold and bool(candidates)
                    and random.random() < self.config.get("spt_intervention_probability", 1.0))
        if override:
            best = self._spt_destination(candidates, region_names)
            target = best["region"]
            if target == region:
                index = 1
            else:
                remotes = [name for name in self.region_names if name != region]
                index = 2 + remotes.index(target)
            self.spt_overrides += 1
            with torch.no_grad():
                dist = agent.masked_distribution(agent.actor(torch.tensor(obs, dtype=torch.float32)), mask)
                logp = float(dist.log_prob(torch.tensor(index)).item())
        action, target = self._decode(region, index)
        critic_observation = None
        if all_observations is not None:
            critic_observation = tuple(x for name in self.region_names
                                       for x in observation_vector(
                                           all_observations[name], self.capacities, self.slot_seconds,
                                           self.config.get("observation_size", 48),
                                           self.config.get("observation_ablation", "none"))) + tuple(
                                               float(name == region) for name in self.region_names)
            value = float(self.central_critic(torch.tensor(
                critic_observation, dtype=torch.float32, device=self.central_device)).item())
        return PolicyProposal(region, action, target, index, tuple(obs), tuple(mask), logp,
                              value, not override, entropy, action_probabilities,
                              critic_observation)

    def resolve(self, task, proposals, candidates, region_names, force=False):
        self.last_resolver_intervention = False
        if len(proposals) != 1 or proposals[0].agent_region != task.source_region:
            raise ValueError("IPPO placement must be decided by exactly the task's source-region agent")
        proposal = proposals[0]
        if proposal.action == ActionType.DEFER:
            if force and candidates and self.config.get("terminal_fallback_enabled", True):
                # Deadline/resource safety only: local first, then stable region order.
                by_region = {c["region"]: c for c in candidates}
                target = proposal.agent_region if proposal.agent_region in by_region else next(
                    name for name in region_names if name in by_region)
                self.resolver_interventions += 1
                self.last_resolver_intervention = True
                return by_region[target]
            return None
        target = proposal.agent_region if proposal.action == ActionType.EXECUTE_LOCAL else proposal.target_region
        by_region = {c["region"]: c for c in candidates}
        if target not in by_region:
            self.resolver_interventions += 1
            self.last_resolver_intervention = True
            return None
        return by_region[target]

    def end_episode(self, decision_events, result):
        episode_reward = 0.0
        agent_rewards = {name: 0.0 for name in self.region_names}
        trace = []
        for event_index, event in enumerate(decision_events):
            outcome, choice = event["outcome"], event["choice"]
            if outcome == "defer":
                reward, reward_components = deferral_reward(self.config)
            elif outcome == "forced_execute":
                reward, reward_components = forced_defer_reward(self.config)
            elif outcome == "reject":
                reward, reward_components = terminal_rejection_reward(self.config)
            else:
                task = event["task"]
                available_deadline = max(1.0, task.deadline_seconds - task.arrival_slot * self.slot_seconds)
                reward, reward_components = execution_reward(
                    choice["carbon"], choice["migration"] + choice["execution"],
                    available_deadline, self.config)
            episode_reward += reward
            for proposal in event["proposals"]:
                agent_rewards[proposal.agent_region] += reward
                self.agents[proposal.agent_region].buffer.add(
                    proposal.observation, proposal.mask, proposal.action_index,
                    proposal.log_probability, proposal.value, reward,
                    outcome != "defer", proposal.policy_valid,
                    trajectory_id=event["task"].task_id,
                    critic_observation=proposal.critic_observation)
                trace.append({"task_id": event["task"].task_id, "agent": proposal.agent_region,
                              "selected_action": proposal.action.value,
                              "target_region": proposal.target_region,
                              "mask": list(proposal.mask),
                              "probabilities": list(proposal.action_probabilities),
                              "entropy": proposal.entropy, "value_estimate": proposal.value,
                              "log_probability": proposal.log_probability,
                              "policy_valid": proposal.policy_valid,
                              "spt_override": not proposal.policy_valid,
                              "outcome": outcome, "individual_reward": reward,
                              "reward_components": reward_components,
                              "resolver_intervention": event.get("resolver_intervention", False),
                              "terminal": outcome != "defer"})
        result["totals"]["episode_reward"] = episode_reward
        result["totals"]["spt_overrides"] = self.spt_overrides
        result["totals"]["resolver_interventions"] = self.resolver_interventions
        result["agent_rewards"] = agent_rewards
        result["agent_decisions"] = trace
        self.spt_overrides = 0
        self.resolver_interventions = 0
        return episode_reward

    def update(self):
        return {name: agent.update(self.config) for name, agent in self.agents.items()}

    def checkpoint(self):
        return {name: agent.checkpoint() for name, agent in self.agents.items()}

    def load_checkpoint(self, state):
        for name in self.region_names:
            self.agents[name].load_checkpoint(state[name])


class CarbonAwareSPTIPPOScheduler(IPPOScheduler):
    """IPPO with carbon selection among destinations close to fastest latency.

    The only behavior change from IPPOScheduler is the entropy-triggered SPT
    destination selector. Feasible candidates have already passed the same
    simulator resource/deadline checks and categorical action mask.
    """
    def _spt_destination(self, candidates, region_names):
        allowance = float(self.config.get("spt_latency_allowance_fraction", 0.10))
        if not 0.0 <= allowance <= 2.0:
            raise ValueError("spt_latency_allowance_fraction must be between 0 and 2")
        fastest = min(candidates, key=lambda c: (
            c["migration"] + c["execution"], region_names.index(c["region"])))
        fastest_latency = fastest["migration"] + fastest["execution"]
        latency_limit = fastest_latency * (1.0 + allowance)
        eligible = [c for c in candidates
                    if c["migration"] + c["execution"] <= latency_limit + 1e-9]
        if not eligible:
            # Defensive fallback; fastest is necessarily feasible.
            eligible = [fastest]
        return min(eligible, key=lambda c: (
            c["carbon"], c["migration"] + c["execution"], region_names.index(c["region"])))
