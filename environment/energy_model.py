"""GPU energy accounting; outputs kWh."""
from collections.abc import Iterable


def energy_kwh(gpu_count: int, active_watts_per_gpu: float, idle_overhead_watts: float,
               runtime_seconds: float, pue: float) -> float:
    watt_seconds = (gpu_count * active_watts_per_gpu + idle_overhead_watts) * runtime_seconds * pue
    return watt_seconds / 3_600_000.0


def interval_energy_kwh(active_gpu_counts: Iterable[int], active_watts_per_gpu: float,
                        shared_idle_overhead_watts: float, duration_seconds: float,
                        pue: float) -> float:
    """Integrate simultaneous GPU loads with shared idle overhead charged once."""
    gpu_count = sum(active_gpu_counts)
    if gpu_count <= 0 or duration_seconds <= 0:
        return 0.0
    watts = gpu_count * active_watts_per_gpu + shared_idle_overhead_watts
    return watts * duration_seconds * pue / 3_600_000.0
