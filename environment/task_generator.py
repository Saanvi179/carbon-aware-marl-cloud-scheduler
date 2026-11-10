"""Task schema and reproducible synthetic workload."""
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Task:
    task_id: str
    arrival_slot: int
    gpu_count: float
    cpu_cores: float
    memory_gb: float
    dataset_gb: float
    deadline_seconds: float
    runtime_seconds: float
    source_region: str


def synthetic_workload() -> list[Task]:
    """A small illustrative workload; values are assumptions, not measured traces."""
    specs = [
        (0, 1, 4, 16, 0.2, 180, 600, "north"),
        (0, 2, 8, 32, 0.5, 240, 720, "north"),
        (1, 1, 2, 8, 0.1, 180, 720, "west"),
        (2, 1, 4, 16, 0.4, 300, 900, "east"),
        (3, 2, 8, 64, 1.0, 360, 1080, "west"),
        (4, 1, 2, 8, 0.05, 150, 900, "east"),
    ]
    return [Task(f"task-{i+1}", a, g, c, m, d, deadline, runtime, source)
            for i, (a, g, c, m, d, runtime, deadline, source) in enumerate(specs)]


def generate_variable_workload(seed: int, task_count: int = 18,
                               regions=("north", "west", "east")) -> list[Task]:
    """Generate reproducible synthetic episodes independent of the demo trace."""
    rng = random.Random(seed)
    tasks = []
    for index in range(task_count):
        arrival = rng.randint(0, 12)
        source = rng.choice(regions)
        gpu_count = rng.choice((1, 1, 2, 2, 4))
        cpu_cores = rng.choice((2, 4, 8, 16))
        memory_gb = rng.choice((8.0, 16.0, 32.0, 64.0))
        dataset_gb = round(rng.uniform(0.05, 1.5), 4)
        runtime_seconds = round(rng.uniform(45.0, 480.0), 2)
        slack_seconds = rng.uniform(300.0, 900.0)
        deadline_seconds = arrival * 60 + runtime_seconds + slack_seconds
        tasks.append(Task(f"w{seed}-task-{index+1:03d}", arrival, gpu_count, cpu_cores,
                          memory_gb, dataset_gb, deadline_seconds, runtime_seconds, source))
    return sorted(tasks, key=lambda task: (task.arrival_slot, task.task_id))


def generate_diverse_workload(seed: int, task_count: int = 24,
                              regions=("north", "west", "east")) -> list[Task]:
    """Expanded reproducible synthetic family for Phase 2.4 generalization checks.

    Arrival, accelerator/CPU/memory demand, runtime, data volume and deadline slack
    vary independently within explicit illustrative ranges. Values are synthetic.
    """
    rng = random.Random(seed)
    tasks = []
    for index in range(task_count):
        # Spread a 24-task episode across a longer horizon so increased task
        # size/runtime diversity does not silently turn every trace into overload.
        arrival = rng.randint(0, 60)
        source = rng.choice(regions)
        gpu_count = rng.choice((1, 1, 2, 2, 4, 8))
        cpu_cores = rng.choice((2, 4, 8, 16, 32, 64))
        memory_gb = rng.choice((8.0, 16.0, 32.0, 64.0, 128.0))
        dataset_gb = round(rng.uniform(0.02, 5.0), 4)
        runtime_seconds = round(rng.uniform(30.0, 900.0), 2)
        slack_seconds = rng.uniform(180.0, 1800.0)
        deadline_seconds = arrival * 60 + runtime_seconds + slack_seconds
        tasks.append(Task(f"d{seed}-task-{index+1:03d}", arrival, gpu_count, cpu_cores,
                          memory_gb, dataset_gb, deadline_seconds, runtime_seconds, source))
    return sorted(tasks, key=lambda task: (task.arrival_slot, task.task_id))


def generate_phase25_workload(seed: int, task_count: int = 24,
                              regions=("north", "west", "east")) -> list[Task]:
    """Reproducible synthetic workload with bursty arrivals and varied AI jobs."""
    rng = random.Random(seed)
    gaps = [rng.expovariate(1.0) for _ in range(task_count)]
    total_gap = sum(gaps) or 1.0
    cumulative = 0.0
    tasks = []
    for index, gap in enumerate(gaps):
        cumulative += gap
        arrival = min(60, int(round(60.0 * cumulative / total_gap)))
        source = rng.choice(regions)
        gpu_count = rng.choices((1, 2, 4, 8), weights=(0.22, 0.40, 0.28, 0.10))[0]
        cpu_cores = min(64, gpu_count * rng.choice((4, 8)))
        memory_gb = rng.choice((8.0, 16.0, 32.0, 64.0, 128.0))
        runtime = min(900.0, max(30.0, rng.lognormvariate(5.3, 0.7)))
        dataset_gb = round(min(5.0, max(0.02, rng.lognormvariate(-0.25, 0.9))), 4)
        slack = max(120.0, runtime * rng.uniform(0.18, 0.75) + dataset_gb * 20.0)
        deadline = arrival * 60 + runtime + slack
        tasks.append(Task(f"p25-{seed}-task-{index+1:03d}", arrival, gpu_count, cpu_cores,
                          memory_gb, dataset_gb, deadline, runtime, source))
    return sorted(tasks, key=lambda task: (task.arrival_slot, task.task_id))
