"""MAPPO-style shared centralized value critic with independent regional actors."""
import torch
from torch.nn import functional as F
from torch.optim import Adam

from .critic import Critic
from .ippo_agent import IPPOScheduler, IPPOAgent


class MAPPOScheduler(IPPOScheduler):
    """Source-owned proposals; decentralized actors, shared global-state critic."""
    centralized_critic = True

    def __init__(self, region_names, capacities, config, seed=7, deterministic=False):
        super().__init__(region_names, capacities, config, seed, deterministic)
        self.central_device = torch.device(config.get("device", "cpu"))
        self.global_observation_size = len(region_names) * config.get("observation_size", 54) + len(region_names)
        self.central_critic = Critic(self.global_observation_size, config["hidden_size"]).to(self.central_device)
        self.central_critic_optimizer = Adam(self.central_critic.parameters(), lr=config["critic_lr"])

    def global_state_vector(self, all_observations, acting_region):
        """Concatenate every regional vector and an acting-agent one-hot (fixed region order)."""
        values = tuple(x for name in self.region_names for x in self._vector(all_observations[name]))
        return values + tuple(float(name == acting_region) for name in self.region_names)

    def _vector(self, observation):
        from .ippo_agent import observation_vector
        return observation_vector(observation, self.capacities, self.slot_seconds,
                                 self.config.get("observation_size", 54),
                                 self.config.get("observation_ablation", "none"))

    def propose_global(self, observation, all_observations, candidates, region_names):
        return self._propose(observation, candidates, region_names,
                             {name: all_observations[i] for i, name in enumerate(self.region_names)})

    def update(self):
        cfg = self.config
        actor_stats = {}
        critic_states, critic_returns = [], []
        critic_pre_losses, critic_post_values = [], []
        critic_explained = []
        for name, agent in self.agents.items():
            buffer = agent.buffer
            if not len(buffer):
                actor_stats[name] = {"actor_loss": 0.0, "entropy": 0.0,
                                     "actor_grad_norm": 0.0, "actor_update_l2": 0.0,
                                     "actor_valid_samples": 0}
                continue
            returns, advantages = buffer.compute_returns_and_advantages(cfg["gamma"], cfg["gae_lambda"])
            observations = torch.stack(buffer.observations).to(agent.device)
            masks = torch.stack(buffer.masks).to(agent.device)
            actions = torch.tensor(buffer.actions, dtype=torch.long, device=agent.device)
            old_logp = torch.tensor(buffer.log_probabilities, dtype=torch.float32, device=agent.device)
            valid = torch.tensor(buffer.policy_valid, dtype=torch.bool, device=agent.device)
            returns, advantages = returns.to(agent.device), advantages.to(agent.device)
            critic_states.extend(buffer.critic_observations)
            critic_returns.extend(returns.detach().cpu().tolist())
            with torch.no_grad():
                predicted = self.central_critic(torch.stack(buffer.critic_observations).to(self.central_device))
                variance = torch.var(returns.to(self.central_device), unbiased=False).clamp_min(1e-8)
                critic_explained.append(float((1 - torch.var(returns.to(self.central_device) - predicted,
                                                               unbiased=False) / variance).cpu()))
            before = torch.cat([p.detach().flatten() for p in agent.actor.parameters()])
            losses, entropies, grad_norms = [], [], []
            if bool(valid.any()):
                selected = advantages[valid]
                advantages = advantages.clone()
                advantages[valid] = (selected - selected.mean()) / (selected.std(unbiased=False) + 1e-8)
            for _ in range(cfg["update_epochs"]):
                logits = agent.actor(observations)
                distributions = [IPPOAgent.masked_distribution(logits[i], masks[i]) for i in range(len(actions))]
                logp = torch.stack([d.log_prob(actions[i]) for i, d in enumerate(distributions)])
                entropy = torch.stack([d.entropy() for d in distributions])
                if bool(valid.any()):
                    ratio = torch.exp(logp[valid] - old_logp[valid])
                    clip = cfg["clip_epsilon"]
                    objective = torch.minimum(ratio * advantages[valid],
                                              ratio.clamp(1-clip, 1+clip) * advantages[valid])
                    loss = -objective.mean() - cfg["entropy_coefficient"] * entropy[valid].mean()
                    agent.actor_optimizer.zero_grad(); loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(agent.actor.parameters(), cfg["max_grad_norm"])
                    agent.actor_optimizer.step()
                    losses.append(float(loss.detach().cpu())); entropies.append(float(entropy[valid].mean().detach().cpu()))
                    grad_norms.append(float(norm.detach().cpu()))
            after = torch.cat([p.detach().flatten() for p in agent.actor.parameters()])
            actor_stats[name] = {"actor_loss": sum(losses)/max(1, len(losses)),
                                 "entropy": sum(entropies)/max(1, len(entropies)),
                                 "actor_grad_norm": sum(grad_norms)/max(1, len(grad_norms)),
                                 "actor_update_l2": float(torch.linalg.vector_norm(after-before).cpu()),
                                 "actor_valid_samples": int(valid.sum().item()),
                                 "spt_overrides": len(buffer)-int(valid.sum().item())}
        critic_loss_values, critic_grad_norms = [], []
        if critic_states:
            states = torch.stack(critic_states).to(self.central_device)
            targets = torch.tensor(critic_returns, dtype=torch.float32, device=self.central_device)
            with torch.no_grad():
                before_values = self.central_critic(states)
            for _ in range(cfg["update_epochs"]):
                values = self.central_critic(states)
                loss = F.mse_loss(values, targets)
                self.central_critic_optimizer.zero_grad(); loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(self.central_critic.parameters(), cfg["max_grad_norm"])
                self.central_critic_optimizer.step()
                critic_loss_values.append(float(loss.detach().cpu()))
                critic_grad_norms.append(float(norm.detach().cpu()))
            with torch.no_grad():
                after_values = self.central_critic(states)
                variance = torch.var(targets, unbiased=False).clamp_min(1e-8)
                explained = float((1 - torch.var(targets-before_values, unbiased=False)/variance).cpu())
        else:
            explained = 0.0
        for agent in self.agents.values():
            agent.buffer.clear()
        return {"actors": actor_stats,
                "central_critic": {"critic_loss": sum(critic_loss_values)/max(1, len(critic_loss_values)),
                                   "critic_grad_norm": sum(critic_grad_norms)/max(1, len(critic_grad_norms)),
                                   "explained_variance_before_update": explained,
                                   "explained_variance_by_agent": critic_explained,
                                   "mean_value_before_update": float(before_values.mean().cpu()) if critic_states else 0.0,
                                   "mean_value_after_update": float(after_values.mean().cpu()) if critic_states else 0.0,
                                   "samples": len(critic_states)}}

    def checkpoint(self):
        return {"actors": {name: {"actor": agent.actor.state_dict(),
                                  "actor_optimizer": agent.actor_optimizer.state_dict()}
                            for name, agent in self.agents.items()},
                "central_critic": self.central_critic.state_dict(),
                "central_critic_optimizer": self.central_critic_optimizer.state_dict()}

    def load_checkpoint(self, state):
        for name, saved in state["actors"].items():
            self.agents[name].actor.load_state_dict(saved["actor"])
            if "actor_optimizer" in saved:
                self.agents[name].actor_optimizer.load_state_dict(saved["actor_optimizer"])
        self.central_critic.load_state_dict(state["central_critic"])
        if "central_critic_optimizer" in state:
            self.central_critic_optimizer.load_state_dict(state["central_critic_optimizer"])
