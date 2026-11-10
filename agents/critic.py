from torch import nn


class Critic(nn.Module):
    """Independent scalar state-value estimator."""
    def __init__(self, observation_size: int, hidden_size: int = 64):
        super().__init__()
        self.network = nn.Sequential(nn.Linear(observation_size, hidden_size), nn.Tanh(),
                                     nn.Linear(hidden_size, hidden_size), nn.Tanh(),
                                     nn.Linear(hidden_size, 1))

    def forward(self, observations):
        return self.network(observations).squeeze(-1)
