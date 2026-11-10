"""Slot-based three-region simulator with simultaneous region-agent proposals."""
from dataclasses import dataclass
from math import ceil
from .resource_manager import Resources, AllocationLedger
from .energy_model import interval_energy_kwh
from .carbon_model import CarbonModel, emissions_gco2e
from .network_model import NetworkModel
from .agent_api import ActionType, RegionAction, CandidateRegionFeatures, make_observation


@dataclass
class Region:
    name: str
    resources: Resources
    carbon_intensity: float
    gpu_watts: float = 300.0
    idle_watts: float = 100.0
    pue: float = 1.2
    execution_speed: float = 1.0  # relative to task runtime; >1 executes faster


class CloudEnvironment:
    def __init__(self, regions, network=None, slot_seconds=60, max_deferrals=2,
                 lambda_latency=0.2, lambda_sla=2.0, carbon_model=None):
        if len(regions) != 3:
            raise ValueError("exactly three regions are required")
        if len({r.name for r in regions}) != 3:
            raise ValueError("region names must be unique")
        self.regions = {r.name: r for r in regions}
        self.region_names = list(self.regions)
        self.network = network or NetworkModel()
        self.slot_seconds, self.max_deferrals = slot_seconds, max_deferrals
        self.lambda_latency, self.lambda_sla = lambda_latency, lambda_sla
        self.carbon_model = carbon_model or CarbonModel({}, {n: r.carbon_intensity for n, r in self.regions.items()})

    def _integrate_region(self, region_name, assignments, include_carbon=True):
        """Return total region energy and carbon, counting shared overhead once per active interval."""
        region = self.regions[region_name]
        local = [a for a in assignments if a["region"] == region_name]
        if not local:
            return 0.0, 0.0
        start = min(a["start"] for a in local)
        end = max(a["end"] for a in local)
        boundaries = {start, end}
        for item in local:
            boundaries.update((item["start"], item["end"]))
        first_slot = int(start // self.slot_seconds)
        last_slot = int(end // self.slot_seconds) + 1
        boundaries.update(i * self.slot_seconds for i in range(first_slot + 1, last_slot + 1)
                          if start < i * self.slot_seconds < end)
        points = sorted(boundaries)
        total_energy = total_carbon = 0.0
        for left, right in zip(points, points[1:]):
            active = [a for a in local if a["start"] < right and a["end"] > left]
            if not active:
                continue
            energy = interval_energy_kwh((a["task"].gpu_count for a in active), region.gpu_watts,
                                         region.idle_watts, right - left, region.pue)
            total_energy += energy
            if include_carbon:
                intensity = self.carbon_model.intensity_at(region_name, left, self.slot_seconds)
                total_carbon += emissions_gco2e(energy, intensity)
        return total_energy, total_carbon

    def _candidate_metrics(self, region_name, task, slot, existing):
        region = self.regions[region_name]
        migration = self.network.migration_latency(task.source_region, region_name, task.dataset_gb)
        execution = task.runtime_seconds / region.execution_speed
        start = slot * self.slot_seconds + migration
        end = start + execution
        proposed = existing + [{"task": task, "region": region_name, "start": start, "end": end}]
        need_forecast = self.carbon_model.candidate_forecast_known
        before_energy, before_carbon = self._integrate_region(
            region_name, existing, include_carbon=need_forecast)
        after_energy, after_carbon = self._integrate_region(
            region_name, proposed, include_carbon=need_forecast)
        observed_intensity = self.carbon_model.intensity_at(
            region_name, slot * self.slot_seconds, self.slot_seconds)
        if self.carbon_model.candidate_forecast_known:
            estimated_carbon = after_carbon - before_carbon
            candidate_intensity = self.carbon_model.intensity_at(
                region_name, start, self.slot_seconds)
        else:
            # In trace replay, future carbon values are outcome data only. The
            # online scheduler's estimate uses the latest observation held flat.
            estimated_carbon = (after_energy - before_energy) * observed_intensity
            candidate_intensity = observed_intensity
        return {"region": region_name, "migration": migration, "execution": execution,
                "start": start, "end": end, "finish": ceil(end / self.slot_seconds),
                "energy": after_energy - before_energy, "carbon": estimated_carbon,
                "carbon_intensity": candidate_intensity,
                "execution_speed": region.execution_speed}

    def run(self, tasks, scheduler):
        ledger = AllocationLedger()
        records, deferred, assignments, decision_events = [], {}, [], []
        busy = {name: [] for name in self.region_names}  # (finish slot, task)
        tasks = sorted(tasks, key=lambda t: (t.arrival_slot, t.task_id))
        effective_max_deferrals = getattr(scheduler, "max_deferrals", self.max_deferrals)
        if effective_max_deferrals is None:
            effective_max_deferrals = self.max_deferrals
        effective_retry_horizon = max(0, int(getattr(scheduler, "horizon_slots", 0)))
        last_slot = max((t.arrival_slot for t in tasks), default=0)
        final_slot = last_slot + effective_retry_horizon + effective_max_deferrals + 2
        for slot in range(final_slot):
            for name in self.region_names:
                finished = [(end, task) for end, task in busy[name] if end <= slot]
                for _, task in finished:
                    self.regions[name].resources.release(task)
                busy[name] = [(end, task) for end, task in busy[name] if end > slot]
            ready = [t for t in tasks if t.arrival_slot == slot]
            ready += [t for t in tasks if deferred.get(t.task_id) == slot]
            for task in ready:
                defer_count = sum(1 for r in records if r["task_id"] == task.task_id and r["action"] == "defer")
                candidates, candidate_features = [], []
                reserved_region = (scheduler.reserved_region(task.task_id, slot)
                    if hasattr(scheduler, "reserved_region") else None)
                for name, region in self.regions.items():
                    candidate = self._candidate_metrics(name, task, slot, assignments)
                    resources = region.resources
                    available = resources.can_fit(task)
                    candidate["region_capacity"] = {
                        "gpus": resources.gpus, "cpu_cores": resources.cpu_cores,
                        "memory_gb": resources.memory_gb}
                    # ResourceManager holds a placement until its rounded finish slot,
                    # so reservations must use the same conservative interval.
                    candidate["resource_start"] = slot * self.slot_seconds
                    candidate["resource_end"] = candidate["finish"] * self.slot_seconds
                    candidate["scheduled_assignments"] = assignments
                    feasible = (available and candidate["end"] <= task.deadline_seconds and
                        (reserved_region is None or name == reserved_region) and
                        (not hasattr(scheduler, "candidate_respects_reservations") or
                         scheduler.candidate_respects_reservations(task, candidate)))
                    candidate["feasible"] = feasible
                    candidate["available_gpus"] = resources.gpus - resources.used_gpus
                    candidate["available_cpu_cores"] = resources.cpu_cores - resources.used_cpu_cores
                    candidate["available_memory_gb"] = resources.memory_gb - resources.used_memory_gb
                    candidate["queue_length"] = len(busy[name])
                    candidate["queued_work_seconds"] = sum(
                        max(0.0, a["end"] - slot * self.slot_seconds)
                        for a in assignments if a["region"] == name and a["end"] > slot * self.slot_seconds)
                    candidate_features.append(CandidateRegionFeatures(
                        name, feasible, candidate["carbon_intensity"], candidate["execution_speed"],
                        candidate["execution"], candidate["migration"], candidate["energy"], candidate["carbon"],
                        candidate["available_gpus"], candidate["available_cpu_cores"],
                        candidate["available_memory_gb"], candidate["queue_length"],
                        candidate["queued_work_seconds"]))
                    if feasible:
                        candidates.append(candidate)
                observations = {name: make_observation(
                    slot, name, task, self.regions[name].resources,
                    tuple(c["region"] for c in candidates),
                    self.carbon_model.intensity_at(name, slot * self.slot_seconds, self.slot_seconds),
                    tuple(candidate_features)) for name in self.region_names}
                if getattr(scheduler, "owner_controlled", False):
                    if getattr(scheduler, "centralized_critic", False):
                        proposals = [scheduler.propose_global(
                            observations[task.source_region],
                            tuple(observations[name] for name in self.region_names),
                            candidates, self.region_names)]
                    else:
                        proposals = [scheduler.propose(observations[task.source_region], candidates, self.region_names)]
                else:
                    proposals = [scheduler.propose(observations[name], candidates, self.region_names)
                                 for name in self.region_names]
                choice = scheduler.resolve(task, proposals, candidates, self.region_names,
                                           force=(defer_count >= effective_max_deferrals))
                if choice is None:
                    if defer_count < effective_max_deferrals:
                        retry_slot = (scheduler.retry_slot(task.task_id, slot)
                            if hasattr(scheduler, "retry_slot") else slot + 1)
                        if retry_slot <= slot:
                            raise RuntimeError("scheduler requested a non-forward retry slot")
                        deferred[task.task_id] = retry_slot
                        record = {"task_id": task.task_id, "slot": slot, "retry_slot": retry_slot,
                                  "action": "defer"}
                        records.append(record)
                    else:
                        if hasattr(scheduler, "release_reservation"):
                            scheduler.release_reservation(task.task_id)
                        record = {"task_id": task.task_id, "slot": slot, "action": "reject"}
                        records.append(record)
                    decision_events.append({"task": task, "proposals": proposals, "outcome": record["action"],
                                            "choice": None,
                                            "resolver_intervention": getattr(scheduler, "last_resolver_intervention", False)})
                    continue
                forced_execution = getattr(scheduler, "last_resolver_intervention", False)
                name = choice["region"]
                if not self.regions[name].resources.can_fit(task):
                    raise RuntimeError(f"safety check rejected over-capacity allocation in {name}")
                if not ledger.claim(task.task_id, name):
                    raise RuntimeError(f"duplicate allocation for {task.task_id}")
                region = self.regions[name]
                region.resources.reserve(task)
                busy[name].append((choice["finish"], task))
                assignments.append({"task": task, "region": name, "start": choice["start"], "end": choice["end"],
                                    "resource_start": slot * self.slot_seconds,
                                    "resource_end": choice["finish"] * self.slot_seconds})
                record = {"task_id": task.task_id, "slot": slot,
                                "action": "execute_local" if name == task.source_region else "migrate",
                                "owner_region": task.source_region,
                                "region": name, "energy_kwh": choice["energy"],
                                "carbon_gco2e": choice["carbon"], "migration_seconds": choice["migration"],
                                "latency_seconds": choice["migration"] + choice["execution"],
                                "execution_seconds": choice["execution"], "finish_slot": choice["finish"]}
                records.append(record)
                decision_events.append({"task": task, "proposals": proposals,
                                        "outcome": "forced_execute" if forced_execution else record["action"],
                                        "choice": choice,
                                        "resolver_intervention": forced_execution})
                deferred.pop(task.task_id, None)
        # Recompute additive marginal values as total integrated region energy/emissions.
        region_totals = {n: self._integrate_region(n, assignments) for n in self.region_names}
        for name in self.region_names:
            self.regions[name].resources.used_gpus = 0
            self.regions[name].resources.used_cpu_cores = 0
            self.regions[name].resources.used_memory_gb = 0.0
        completed = sum(r["action"] in ("execute_local", "migrate") for r in records)
        rejected = sum(r["action"] == "reject" for r in records)
        if completed + rejected != len(tasks):
            raise RuntimeError(
                f"task lifecycle did not terminate for every task: {completed} completed + "
                f"{rejected} rejected of {len(tasks)}"
            )
        latency_values = [r["latency_seconds"] for r in records if "latency_seconds" in r]
        result = {"records": records, "allocations": ledger.allocations,
                "totals": {"energy_kwh": sum(v[0] for v in region_totals.values()),
                           "carbon_gco2e": sum(v[1] for v in region_totals.values()),
                           "completed": completed, "rejected": rejected,
                           "rejection_rate": rejected / len(tasks) if tasks else 0.0,
                           "sla_violations": rejected,
                           "total_latency_seconds": sum(latency_values),
                           "mean_latency_seconds": sum(latency_values) / len(latency_values) if latency_values else 0.0,
                           "completion_rate": completed / len(tasks) if tasks else 0.0}}
        if hasattr(scheduler, "end_episode"):
            result["episode_reward"] = scheduler.end_episode(decision_events, result)
        return result
