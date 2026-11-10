from torch import nn


class Actor(nn.Module):
    """Categorical policy head; invalid actions are masked by the agent."""
    def __init__(self, observation_size: int, action_count: int = 4, hidden_size: int = 64):
        super().__init__()
        self.network = nn.Sequential(nn.Linear(observation_size, hidden_size), nn.Tanh(),
                                     nn.Linear(hidden_size, hidden_size), nn.Tanh(),
                                     nn.Linear(hidden_size, action_count))

    def forward(self, observations):
        return self.network(observations)
