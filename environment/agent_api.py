"""Formal per-region observation and three-way placement action API."""
from dataclasses import dataclass
from enum import Enum
from .resource_manager import Resources
from .task_generator import Task


class ActionType(str, Enum):
    DEFER = "defer"
    EXECUTE_LOCAL = "execute_local"
    MIGRATE = "migrate"


@dataclass(frozen=True)
class CandidateRegionFeatures:
    region: str
    feasible: bool
    carbon_intensity_gco2e_kwh: float
    execution_speed: float
    execution_seconds: float
    migration_seconds: float
    energy_kwh: float
    emissions_gco2e: float
    available_gpus: float
    available_cpu_cores: float
    available_memory_gb: float
    queue_length: int
    queued_work_seconds: float


@dataclass(frozen=True)
class RegionObservation:
    slot: int
    region: str
    task: Task
    available_gpus: float
    available_cpu_cores: float
    available_memory_gb: float
    local_feasible: bool
    feasible_destinations: tuple[str, ...]
    carbon_intensity_gco2e_kwh: float
    candidate_features: tuple[CandidateRegionFeatures, ...] = ()


@dataclass(frozen=True)
class RegionAction:
    agent_region: str
    action: ActionType
    target_region: str | None = None

    def __post_init__(self):
        if self.action == ActionType.MIGRATE and not self.target_region:
            raise ValueError("migrate action requires a destination")
        if self.action == ActionType.MIGRATE and self.target_region == self.agent_region:
            raise ValueError("migrate action must target another region")
        if self.action != ActionType.MIGRATE and self.target_region is not None:
            raise ValueError("only migrate actions can name a destination")


def make_observation(slot: int, agent_region: str, task: Task, resources: Resources,
                     feasible_destinations: tuple[str, ...], carbon_intensity: float,
                     candidate_features: tuple[CandidateRegionFeatures, ...] = ()) -> RegionObservation:
    return RegionObservation(slot, agent_region, task,
                            resources.gpus - resources.used_gpus,
                            resources.cpu_cores - resources.used_cpu_cores,
                            resources.memory_gb - resources.used_memory_gb,
                            agent_region in feasible_destinations, feasible_destinations,
                            carbon_intensity, candidate_features)
