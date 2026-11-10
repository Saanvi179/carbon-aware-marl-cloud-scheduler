"""Capacity checks and duplicate-safe allocation ledger."""
from dataclasses import dataclass
from .task_generator import Task


@dataclass
class Resources:
    gpus: float
    cpu_cores: float
    memory_gb: float
    used_gpus: float = 0.0
    used_cpu_cores: float = 0.0
    used_memory_gb: float = 0.0

    def can_fit(self, task: Task) -> bool:
        return (self.used_gpus + task.gpu_count <= self.gpus and
                self.used_cpu_cores + task.cpu_cores <= self.cpu_cores and
                self.used_memory_gb + task.memory_gb <= self.memory_gb)

    def reserve(self, task: Task) -> None:
        if not self.can_fit(task):
            raise ValueError("task exceeds available region capacity")
        self.used_gpus += task.gpu_count
        self.used_cpu_cores += task.cpu_cores
        self.used_memory_gb += task.memory_gb

    def release(self, task: Task) -> None:
        self.used_gpus -= task.gpu_count
        self.used_cpu_cores -= task.cpu_cores
        self.used_memory_gb -= task.memory_gb


class AllocationLedger:
    def __init__(self):
        self.allocations: dict[str, str] = {}

    def claim(self, task_id: str, region: str) -> bool:
        if task_id in self.allocations:
            return False
        self.allocations[task_id] = region
        return True
