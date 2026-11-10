from dataclasses import dataclass, field
import torch


@dataclass
class RolloutBuffer:
    observations: list = field(default_factory=list)
    masks: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    log_probabilities: list = field(default_factory=list)
    values: list = field(default_factory=list)
    rewards: list = field(default_factory=list)
    dones: list = field(default_factory=list)
    policy_valid: list = field(default_factory=list)
    trajectory_ids: list = field(default_factory=list)
    critic_observations: list = field(default_factory=list)

    def add(self, observation, mask, action, log_probability, value, reward, done,
            policy_valid=True, trajectory_id=0, critic_observation=None):
        self.observations.append(torch.as_tensor(observation, dtype=torch.float32))
        self.masks.append(torch.as_tensor(mask, dtype=torch.bool))
        self.actions.append(int(action))
        self.log_probabilities.append(float(log_probability))
        self.values.append(float(value))
        self.rewards.append(float(reward))
        self.dones.append(bool(done))
        self.policy_valid.append(bool(policy_valid))
        self.trajectory_ids.append(trajectory_id)
        self.critic_observations.append(torch.as_tensor(
            critic_observation if critic_observation is not None else observation,
            dtype=torch.float32))

    def __len__(self):
        return len(self.actions)

    def compute_returns_and_advantages(self, gamma=0.99, gae_lambda=0.95, bootstrap_value=0.0):
        advantages = [0.0] * len(self)
        trajectory_indices = {}
        for index, trajectory_id in enumerate(self.trajectory_ids):
            trajectory_indices.setdefault(trajectory_id, []).append(index)
        for indices in trajectory_indices.values():
            gae, next_value = 0.0, float(bootstrap_value)
            for i in reversed(indices):
                continuation = 0.0 if self.dones[i] else 1.0
                delta = self.rewards[i] + gamma * next_value * continuation - self.values[i]
                gae = delta + gamma * gae_lambda * continuation * gae
                advantages[i] = gae
                next_value = self.values[i]
        advantages_tensor = torch.tensor(advantages, dtype=torch.float32)
        values_tensor = torch.tensor(self.values, dtype=torch.float32)
        return advantages_tensor + values_tensor, advantages_tensor

    def clear(self):
        self.observations.clear(); self.masks.clear(); self.actions.clear()
        self.log_probabilities.clear(); self.values.clear(); self.rewards.clear()
        self.dones.clear(); self.policy_valid.clear(); self.trajectory_ids.clear()
        self.critic_observations.clear()
