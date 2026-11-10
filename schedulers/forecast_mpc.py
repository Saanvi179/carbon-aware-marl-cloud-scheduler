"""Forecast-Aware Receding Horizon (MPC) Scheduler.

Uses short-term carbon forecasts over a bounded horizon (2-4 hours), computes task
slack and urgency, accounts for future resource availability and congestion,
selectively defers delay-tolerant tasks to lower-carbon or less-congested windows,
prioritises urgent tasks to prevent deadline and SLA violations, and uses tentative
future capacity reservations to eliminate the capacity cliff in burst workloads.
"""
from dataclasses import dataclass
from math import ceil
from typing import Any, Callable

from environment.agent_api import ActionType, RegionAction


@dataclass
class CarbonForecastProvider:
    """Manages short-term carbon forecasts with strict horizon enforcement.

    Enforces that queries for target_slot at current_slot satisfy:
        current_slot <= target_slot <= current_slot + horizon_slots.
    Queries beyond the configured forecast horizon raise ValueError to prevent
    information leakage.
    """
    profiles: dict[str, list[float]]
    defaults: dict[str, float]
    horizon_slots: int

    def get_forecast(self, region: str, current_slot: int, target_slot: int) -> float:
        """Return forecasted carbon intensity (gCO2e/kWh) for region at target_slot."""
        if target_slot < current_slot:
            raise ValueError(f"Target slot {target_slot} is in the past relative to current slot {current_slot}.")
        if target_slot > current_slot + self.horizon_slots:
            raise ValueError(
                f"Information leakage: target slot {target_slot} exceeds forecast horizon "
                f"{current_slot + self.horizon_slots} (horizon={self.horizon_slots} slots)."
            )
        profile = self.profiles.get(region, [])
        if target_slot < len(profile):
            return profile[target_slot]
        return self.defaults.get(region, 0.0)

    def window_forecast(self, region: str, current_slot: int, window_slots: int) -> list[float]:
        """Return list of forecasted carbon intensities for slots [current_slot, current_slot + window_slots]."""
        clamped_window = min(window_slots, self.horizon_slots)
        return [self.get_forecast(region, current_slot, current_slot + offset)
                for offset in range(clamped_window + 1)]


DEFAULT_REGION_CAPACITIES = {
    "north": {"gpus": 8.0, "cpu_cores": 64.0, "memory_gb": 256.0},
    "west": {"gpus": 6.0, "cpu_cores": 48.0, "memory_gb": 192.0},
    "east": {"gpus": 10.0, "cpu_cores": 80.0, "memory_gb": 384.0},
}


class ForecastAwareMPCScheduler:
    """Forecast-Aware Receding Horizon (MPC) Scheduler.

    Balances immediate emissions, short-term forecasted carbon valleys, task urgency
    (deadline slack), and multi-region capacity congestion to overcome myopic burst
    contention without violating SLA deadlines or hard feasibility constraints.
    Supports tentative future capacity reservations to eliminate the burst capacity cliff.
    """
    def __init__(self,
                 forecast_horizon_hours: float = 4.0,
                 slot_seconds: int = 900,
                 carbon_forecast: CarbonForecastProvider | dict[str, list[float]] | None = None,
                 defaults: dict[str, float] | None = None,
                 urgency_slack_threshold_seconds: float = 1800.0,
                 deferral_saving_threshold: float = 0.05,
                 latency_weight: float = 0.01,
                 congestion_weight: float = 0.02,
                 max_deferrals: int | None = None,
                 enable_reservations: bool = True,
                 region_capacities: dict[str, dict[str, float]] | None = None):
        self.forecast_horizon_hours = float(forecast_horizon_hours)
        self.slot_seconds = int(slot_seconds)
        self.horizon_slots = max(1, int(round(self.forecast_horizon_hours * 3600.0 / self.slot_seconds)))
        self.urgency_slack_threshold_seconds = float(urgency_slack_threshold_seconds)
        self.deferral_saving_threshold = float(deferral_saving_threshold)
        self.latency_weight = float(latency_weight)
        self.congestion_weight = float(congestion_weight)
        # If max_deferrals is not specified, default to matching the full forecast horizon
        self.max_deferrals = int(max_deferrals) if max_deferrals is not None else self.horizon_slots
        self.enable_reservations = bool(enable_reservations)
        self.region_capacities = region_capacities or DEFAULT_REGION_CAPACITIES

        if isinstance(carbon_forecast, CarbonForecastProvider):
            self.forecast_provider = carbon_forecast
        elif isinstance(carbon_forecast, dict):
            fallback_defaults = defaults or {k: (v[0] if v else 0.0) for k, v in carbon_forecast.items()}
            self.forecast_provider = CarbonForecastProvider(carbon_forecast, fallback_defaults, self.horizon_slots)
        else:
            self.forecast_provider = None

        self.task_deferrals: dict[str, int] = {}
        self.future_reservations: dict[tuple[str, int], dict[str, float]] = {}
        self.task_reserved_slot: dict[str, dict[str, Any]] = {}
        self.decisions_made: int = 0
        self.deferrals_recommended: int = 0
        self.urgent_placements: int = 0

    def set_forecast(self, profiles: dict[str, list[float]], defaults: dict[str, float] | None = None):
        fallback_defaults = defaults or {k: (v[0] if v else 0.0) for k, v in profiles.items()}
        self.forecast_provider = CarbonForecastProvider(profiles, fallback_defaults, self.horizon_slots)

    def clean_elapsed_reservations(self, current_slot: int):
        """Remove reservations for past slots."""
        for task_id, reservation in list(self.task_reserved_slot.items()):
            if reservation["slot"] < current_slot:
                self.release_reservation(task_id)
        self.future_reservations = {
            k: v for k, v in self.future_reservations.items() if k[1] >= current_slot
        }

    def has_tentative_capacity(self, task, region: str, future_slot: int,
                               candidate: dict | None = None) -> bool:
        """Check full execution-interval capacity against committed and tentative work."""
        candidate = candidate or {}
        migration = candidate["migration"] if candidate else 0.0
        execution = candidate["execution"] if candidate else task.runtime_seconds
        start = future_slot * self.slot_seconds
        end = ceil((start + migration + execution) / self.slot_seconds) * self.slot_seconds
        cap = (candidate or {}).get("region_capacity", self.region_capacities.get(
            region, {"gpus": 8.0, "cpu_cores": 64.0, "memory_gb": 256.0}))
        occupants = [r for task_id, r in self.task_reserved_slot.items()
                     if task_id != task.task_id and r["region"] == region
                     and start < r["resource_end"] and end > r["resource_start"]]
        assignments = (candidate or {}).get("scheduled_assignments", [])
        occupants.extend({"resource_start": a.get("resource_start", (a["start"] // self.slot_seconds) * self.slot_seconds),
                          "resource_end": a.get("resource_end", ceil(a["end"] / self.slot_seconds) * self.slot_seconds),
                          "gpus": a["task"].gpu_count,
                          "cpu_cores": a["task"].cpu_cores,
                          "memory_gb": a["task"].memory_gb}
                         for a in assignments if a["region"] == region
                         and start < a.get("resource_end", ceil(a["end"] / self.slot_seconds) * self.slot_seconds)
                         and end > a.get("resource_start", (a["start"] // self.slot_seconds) * self.slot_seconds))
        points = {start, end}
        for other in occupants:
            points.update((max(start, other["resource_start"]), min(end, other["resource_end"])))
        points = sorted(points)
        for left, right in zip(points, points[1:]):
            if left >= right:
                continue
            active = [r for r in occupants if r["resource_start"] < right and r["resource_end"] > left]
            if (sum(r["gpus"] for r in active) + task.gpu_count > cap["gpus"] + 1e-9 or
                sum(r["cpu_cores"] for r in active) + task.cpu_cores > cap["cpu_cores"] + 1e-9 or
                sum(r["memory_gb"] for r in active) + task.memory_gb > cap["memory_gb"] + 1e-9):
                return False
        return True

    def tentatively_reserve(self, task, region: str, future_slot: int,
                            migration: float = 0.0, execution: float | None = None):
        """Register tentative capacity reservation for a deferred task."""
        self.release_reservation(task.task_id)
        execution = task.runtime_seconds if execution is None else execution
        start = future_slot * self.slot_seconds
        end = ceil((start + migration + execution) / self.slot_seconds) * self.slot_seconds
        res = self.future_reservations.setdefault(
            (region, future_slot),
            {"gpus": 0.0, "cpu_cores": 0.0, "memory_gb": 0.0}
        )
        res["gpus"] += task.gpu_count
        res["cpu_cores"] += task.cpu_cores
        res["memory_gb"] += task.memory_gb
        self.task_reserved_slot[task.task_id] = {
            "region": region, "slot": future_slot,
            "start": start, "end": start + migration + execution,
            "resource_start": start, "resource_end": end,
            "gpus": task.gpu_count, "cpu_cores": task.cpu_cores,
            "memory_gb": task.memory_gb,
        }

    def retry_slot(self, task_id: str, current_slot: int) -> int:
        """Return the committed retry slot, falling back to one-slot deferral."""
        reservation = self.task_reserved_slot.get(task_id)
        if reservation and reservation["slot"] > current_slot:
            return reservation["slot"]
        return current_slot + 1

    def reserved_region(self, task_id: str, slot: int) -> str | None:
        """Return the reserved destination only at its committed start slot."""
        reservation = self.task_reserved_slot.get(task_id)
        if reservation and reservation["slot"] == slot:
            return reservation["region"]
        return None

    def candidate_respects_reservations(self, task, candidate: dict) -> bool:
        """Reject a placement that would consume resources promised to another task."""
        region = candidate["region"]
        capacity = candidate.get("region_capacity", self.region_capacities.get(region, {}))
        candidate_start = candidate.get("resource_start", candidate["start"])
        candidate_end = candidate.get("resource_end", candidate["end"])
        overlapping = [r for task_id, r in self.task_reserved_slot.items()
                       if task_id != task.task_id and r["region"] == region
                       and candidate_start < r["resource_end"] and candidate_end > r["resource_start"]]
        if not overlapping:
            return True
        points = {candidate_start, candidate_end}
        for reservation in overlapping:
            points.update((max(candidate_start, reservation["resource_start"]),
                          min(candidate_end, reservation["resource_end"])))
        ordered_points = sorted(points)
        for left, right in zip(ordered_points, ordered_points[1:]):
            if left >= right:
                continue
            active = [r for r in overlapping if r["resource_start"] < right and r["resource_end"] > left]
            if (sum(r["gpus"] for r in active) + task.gpu_count > capacity.get("gpus", 8.0) + 1e-9 or
                sum(r["cpu_cores"] for r in active) + task.cpu_cores > capacity.get("cpu_cores", 64.0) + 1e-9 or
                sum(r["memory_gb"] for r in active) + task.memory_gb > capacity.get("memory_gb", 256.0) + 1e-9):
                return False
        return True

    def release_reservation(self, task_id: str):
        """Release tentative reservation when a task is scheduled or dropped."""
        if task_id in self.task_reserved_slot:
            reservation = self.task_reserved_slot.pop(task_id)
            region, future_slot = reservation["region"], reservation["slot"]
            if (region, future_slot) in self.future_reservations:
                r = self.future_reservations[(region, future_slot)]
                r["gpus"] = max(0.0, r["gpus"] - reservation["gpus"])
                r["cpu_cores"] = max(0.0, r["cpu_cores"] - reservation["cpu_cores"])
                r["memory_gb"] = max(0.0, r["memory_gb"] - reservation["memory_gb"])

    def calculate_slack(self, task, candidate: dict, slot: int) -> float:
        """Calculate remaining deadline slack in seconds for a specific candidate placement."""
        start_time = slot * self.slot_seconds + candidate["migration"]
        finish_time = start_time + candidate["execution"]
        return task.deadline_seconds - finish_time

    def is_urgent(self, task, candidates: list[dict], slot: int, force: bool) -> tuple[bool, float]:
        """Determine whether the task is urgent and cannot safely defer to the next slot."""
        if force:
            return True, 0.0
        defer_count = self.task_deferrals.get(task.task_id, 0)
        if defer_count >= self.max_deferrals:
            return True, 0.0

        slacks = [self.calculate_slack(task, c, slot) for c in candidates]
        max_slack = max(slacks) if slacks else 0.0

        # Check if deferring 1 slot makes finish_time exceed deadline in all currently feasible regions
        next_slot_slacks = [task.deadline_seconds - ((slot + 1) * self.slot_seconds + c["migration"] + c["execution"])
                            for c in candidates]
        can_defer_safely = any(s >= 0.0 for s in next_slot_slacks)

        if not can_defer_safely:
            return True, max_slack

        # If slack is below the configured safety threshold, treat as urgent
        if max_slack < self.urgency_slack_threshold_seconds:
            return True, max_slack

        return False, max_slack

    def evaluate_forecast_opportunity(self, task, candidates: list[dict], slot: int, max_slack: float) -> bool:
        """Determine if deferring to a future slot offers significant savings and has capacity."""
        if self.forecast_provider is None or not candidates:
            return False

        defer_count = self.task_deferrals.get(task.task_id, 0)
        remaining_deferrals = self.max_deferrals - defer_count
        if remaining_deferrals <= 0:
            return False

        # A deferral is one transition even when its committed retry slot lies
        # several slots ahead. The retry budget limits transitions; it must not
        # silently shorten the separate forecast horizon.
        slots_from_slack = max(0, int(max_slack // self.slot_seconds))
        lookahead_slots = min(self.horizon_slots, slots_from_slack)
        if lookahead_slots <= 0:
            return False

        current_best_candidate = min(candidates, key=lambda c: c["carbon"])
        current_best_carbon = current_best_candidate["carbon"]

        best_deferral_target: tuple[str, int] | None = None

        # Check future slots in the allowable window for significant carbon savings
        for offset in range(1, lookahead_slots + 1):
            future_slot = slot + offset
            for c in candidates:
                region = c["region"]
                try:
                    future_intensity = self.forecast_provider.get_forecast(region, slot, future_slot)
                except ValueError:
                    continue
                # Expected incremental emissions at future slot
                future_carbon = c["energy"] * future_intensity
                # Significant carbon reduction threshold
                if future_carbon < current_best_carbon * (1.0 - self.deferral_saving_threshold):
                    if not self.enable_reservations or self.has_tentative_capacity(task, region, future_slot, c):
                        best_deferral_target = (region, future_slot)
                        break
            if best_deferral_target is not None:
                break

        # Check for burst congestion relief: if all feasible regions are highly congested
        if best_deferral_target is None:
            is_congested = all(c.get("available_gpus", 8.0) <= 2.0 or c.get("queue_length", 0) > 0 for c in candidates)
            if is_congested and max_slack >= (self.slot_seconds * 3):
                # Search up to min(lookahead_slots, 2) slots for a feasible, unreserved future slot
                for offset in range(1, min(lookahead_slots, 2) + 1):
                    future_slot = slot + offset
                    for c in sorted(candidates, key=lambda c: c.get("queue_length", 0)):
                        region = c["region"]
                        if not self.enable_reservations or self.has_tentative_capacity(task, region, future_slot, c):
                            best_deferral_target = (region, future_slot)
                            break
                    if best_deferral_target is not None:
                        break

        if best_deferral_target is not None:
            if self.enable_reservations:
                self.tentatively_reserve(task, best_deferral_target[0], best_deferral_target[1],
                    next(c["migration"] for c in candidates if c["region"] == best_deferral_target[0]),
                    next(c["execution"] for c in candidates if c["region"] == best_deferral_target[0]))
            return True

        return False

    def rank_candidate(self, candidate: dict, region_names: list[str]) -> tuple[float, int]:
        """Rank feasible candidate by carbon, latency, and regional congestion."""
        latency = candidate["migration"] + candidate["execution"]
        queue_len = candidate.get("queue_length", 0)
        queued_work = candidate.get("queued_work_seconds", 0.0)
        avail_gpus = candidate.get("available_gpus", 8.0)

        # Congestion metric penalizes overloaded queues and near-zero available capacity
        congestion = (queue_len / 8.0) + (queued_work / 1000.0) + max(0.0, (2.0 - avail_gpus) / 2.0)
        score = candidate["carbon"] + self.latency_weight * latency + self.congestion_weight * congestion
        return score, region_names.index(candidate["region"])

    def propose(self, observation, candidates, region_names):
        """Propose an action from the perspective of an observation."""
        if not candidates:
            return RegionAction(observation.region, ActionType.DEFER)

        task = observation.task
        slot = observation.slot
        self.clean_elapsed_reservations(slot)
        defer_count = self.task_deferrals.get(task.task_id, 0)
        force = (defer_count >= self.max_deferrals)

        urgent, max_slack = self.is_urgent(task, candidates, slot, force)
        if not urgent:
            should_defer = self.evaluate_forecast_opportunity(task, candidates, slot, max_slack)
            if should_defer:
                return RegionAction(observation.region, ActionType.DEFER)

        best_candidate = min(candidates, key=lambda c: self.rank_candidate(c, region_names))
        if best_candidate["region"] == observation.region:
            return RegionAction(observation.region, ActionType.EXECUTE_LOCAL)
        if observation.region == task.source_region:
            return RegionAction(observation.region, ActionType.MIGRATE, best_candidate["region"])
        return RegionAction(observation.region, ActionType.DEFER)

    def resolve(self, task, proposals, candidates, region_names, force=False):
        """Resolve proposals into a single candidate placement or deferral."""
        self.decisions_made += 1
        if not candidates:
            # If rejected or cannot place, release reservation
            if self.enable_reservations:
                self.release_reservation(task.task_id)
            return None

        slot = int(round(candidates[0]["start"] - candidates[0]["migration"])) // self.slot_seconds
        self.clean_elapsed_reservations(slot)
        reservation = self.task_reserved_slot.get(task.task_id)
        if reservation and slot < reservation["slot"]:
            self.deferrals_recommended += 1
            self.task_deferrals[task.task_id] = self.task_deferrals.get(task.task_id, 0) + 1
            return None
        if reservation and slot > reservation["slot"]:
            self.release_reservation(task.task_id)
            reservation = None
        honoring_reservation = bool(reservation and slot == reservation["slot"])
        if honoring_reservation:
            candidates = [c for c in candidates if c["region"] == reservation["region"]]
            if not candidates:
                self.release_reservation(task.task_id)
                return None
        urgent, max_slack = (True, 0.0) if honoring_reservation else self.is_urgent(task, candidates, slot, force)

        if not urgent and not honoring_reservation:
            should_defer = self.evaluate_forecast_opportunity(task, candidates, slot, max_slack)
            if should_defer:
                self.deferrals_recommended += 1
                self.task_deferrals[task.task_id] = self.task_deferrals.get(task.task_id, 0) + 1
                return None

        # Task is urgent or execution now is optimal
        self.urgent_placements += int(urgent)
        best_candidate = min(candidates, key=lambda c: self.rank_candidate(c, region_names))
        # Clear task deferral and tentative reservation tracking on placement
        self.task_deferrals.pop(task.task_id, None)
        if self.enable_reservations:
            self.release_reservation(task.task_id)
        return best_candidate

    def choose(self, task, candidates, region_names, force=False):
        """Convenience direct placement interface for baseline callers."""
        return self.resolve(task, [], candidates, region_names, force)
