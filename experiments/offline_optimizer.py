"""Exact small-instance MILP benchmark for the simulator's placement model.

The model makes assignment and start-slot decisions with full workload/carbon
knowledge. It uses the simulator's bounded deferral, reservation, migration,
deadline and interval-energy semantics. SciPy/HiGHS is optional at import time
but required to solve.
"""
from math import ceil
from time import perf_counter


class OfflineOptimizer:
    def __init__(self, max_wait_slots=None):
        self.max_wait_slots = max_wait_slots

    def solve(self, environment, tasks, time_limit_seconds=30.0):
        try:
            import numpy as np
            from scipy.optimize import Bounds, LinearConstraint, milp
            from scipy.sparse import coo_matrix
        except ImportError as error:
            raise RuntimeError("Offline MILP requires scipy>=1.11; install project requirements") from error

        start_clock = perf_counter()
        tasks = sorted(tasks, key=lambda t: (t.arrival_slot, t.task_id))
        slot_seconds = environment.slot_seconds
        wait_limit = environment.max_deferrals if self.max_wait_slots is None else self.max_wait_slots
        candidates = []
        by_task = [[] for _ in tasks]
        for ti, task in enumerate(tasks):
            for region_name, region in environment.regions.items():
                migration = environment.network.migration_latency(
                    task.source_region, region_name, task.dataset_gb)
                execution = task.runtime_seconds / region.execution_speed
                final_slot = min(task.arrival_slot + wait_limit,
                                 int((task.deadline_seconds - migration - execution) // slot_seconds))
                for decision_slot in range(task.arrival_slot, final_slot + 1):
                    start = decision_slot * slot_seconds + migration
                    end = start + execution
                    if end > task.deadline_seconds + 1e-9:
                        continue
                    candidate = {"task_index": ti, "task": task, "region": region_name,
                                 "decision_slot": decision_slot, "migration": migration,
                                 "execution": execution, "start": start, "end": end,
                                 "finish": ceil(end / slot_seconds)}
                    candidate["index"] = len(candidates)
                    candidates.append(candidate)
                    by_task[ti].append(candidate)
        if any(not options for options in by_task):
            runtime = perf_counter() - start_clock
            return {"status": "infeasible", "optimal": False, "runtime_seconds": runtime,
                    "schedule": [], "totals": None,
                    "message": "at least one task has no region/start-slot meeting its deadline and wait limit"}

        # Build exact energy intervals from every possible execution boundary,
        # splitting at carbon-slot boundaries as the environment does.
        region_intervals = {}
        candidate_intervals = {candidate["index"]: [] for candidate in candidates}
        interval_idle_cost, interval_idle_energy = [], []
        for region_name, region in environment.regions.items():
            points = set()
            local = [c for c in candidates if c["region"] == region_name]
            for candidate in local:
                points.update((candidate["start"], candidate["end"]))
                lo = int(candidate["start"] // slot_seconds) + 1
                hi = int(candidate["end"] // slot_seconds) + 1
                points.update(k * slot_seconds for k in range(lo, hi)
                              if candidate["start"] < k * slot_seconds < candidate["end"])
            ordered = sorted(points)
            intervals = []
            for left, right in zip(ordered, ordered[1:]):
                if right <= left:
                    continue
                interval_index = len(interval_idle_cost)
                intensity = environment.carbon_model.intensity_at(region_name, left, slot_seconds)
                duration = right - left
                energy_per_watt = duration * region.pue / 3_600_000.0
                interval_idle_cost.append(region.idle_watts * energy_per_watt * intensity)
                interval_idle_energy.append(region.idle_watts * energy_per_watt)
                intervals.append((left, right, interval_index))
            region_intervals[region_name] = intervals
            for candidate in local:
                for left, right, interval_index in intervals:
                    if candidate["start"] < right and candidate["end"] > left:
                        candidate_intervals[candidate["index"]].append(interval_index)

        # Variables: one binary x per (task, region, decision slot), then one
        # binary y per possible region interval indicating shared idle overhead.
        x_count = len(candidates)
        y_count = len(interval_idle_cost)
        variable_count = x_count + y_count
        objective = np.zeros(variable_count, dtype=float)
        energy_gpu_coeff = np.zeros(x_count, dtype=float)
        for candidate in candidates:
            region = environment.regions[candidate["region"]]
            gpu_energy = 0.0
            carbon_cost = 0.0
            for interval_index in candidate_intervals[candidate["index"]]:
                left, right = next((l, r) for l, r, idx in region_intervals[candidate["region"]]
                                   if idx == interval_index)
                e = (candidate["task"].gpu_count * region.gpu_watts * (right-left) * region.pue /
                     3_600_000.0)
                gpu_energy += e
                intensity = environment.carbon_model.intensity_at(candidate["region"], left, slot_seconds)
                carbon_cost += e * intensity
            energy_gpu_coeff[candidate["index"]] = gpu_energy
            objective[candidate["index"]] = carbon_cost
        objective[x_count:] = interval_idle_cost

        rows, cols, data, lower, upper = [], [], [], [], []
        def add_constraint(coefficients, lb=-np.inf, ub=np.inf):
            row = len(lower)
            for col, value in coefficients.items():
                if value:
                    rows.append(row); cols.append(col); data.append(float(value))
            lower.append(lb); upper.append(ub)

        # Complete every task exactly once.
        for options in by_task:
            add_constraint({c["index"]: 1.0 for c in options}, 1.0, 1.0)
        # Capacity is reserved at dispatch time through the simulator's finish
        # slot (migration transfer occupies the reservation as in its ledger).
        for region_name, region in environment.regions.items():
            capacities = (region.resources.gpus, region.resources.cpu_cores,
                          region.resources.memory_gb)
            for slot in sorted({s for c in candidates if c["region"] == region_name
                                for s in range(c["decision_slot"], c["finish"])}):
                active = [c for c in candidates if c["region"] == region_name and
                          c["decision_slot"] <= slot < c["finish"]]
                for attr, capacity in zip(("gpu_count", "cpu_cores", "memory_gb"), capacities):
                    add_constraint({c["index"]: getattr(c["task"], attr) for c in active}, ub=capacity)
        # y >= each selected candidate active in this interval; positive idle
        # power/emissions then makes y exactly the OR of active assignments.
        for candidate in candidates:
            for interval_index in candidate_intervals[candidate["index"]]:
                add_constraint({x_count + interval_index: 1.0, candidate["index"]: -1.0}, lb=0.0)

        matrix = coo_matrix((data, (rows, cols)), shape=(len(lower), variable_count)).tocsr()
        result = milp(objective, integrality=np.ones(variable_count, dtype=int),
                      bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
                      constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
                      options={"time_limit": float(time_limit_seconds), "presolve": True})
        runtime = perf_counter() - start_clock
        if result.x is None:
            return {"status": "infeasible" if result.status == 2 else "no_incumbent",
                    "optimal": False, "runtime_seconds": runtime, "schedule": [],
                    "totals": None, "message": str(result.message)}
        selected = [c for c in candidates if result.x[c["index"]] > 0.5]
        assignments = [{"task": c["task"], "region": c["region"], "start": c["start"],
                        "end": c["end"], "finish": c["finish"],
                        "decision_slot": c["decision_slot"], "migration": c["migration"],
                        "execution": c["execution"]} for c in selected]
        totals_by_region = {name: environment._integrate_region(name, assignments)
                            for name in environment.region_names}
        energy = sum(value[0] for value in totals_by_region.values())
        carbon = sum(value[1] for value in totals_by_region.values())
        latency = sum(a["migration"] + a["execution"] for a in assignments)
        complete = len(assignments)
        schedule = [{"task_id": a["task"].task_id, "region": a["region"],
                     "decision_slot": a["decision_slot"], "migration_seconds": a["migration"],
                     "execution_seconds": a["execution"], "finish_slot": a["finish"]}
                    for a in assignments]
        return {"status": "optimal" if result.status == 0 else "feasible_incumbent",
                "optimal": result.status == 0, "runtime_seconds": runtime,
                "objective_gco2e": float(result.fun), "mip_gap": getattr(result, "mip_gap", None),
                "mip_node_count": getattr(result, "mip_node_count", None),
                "schedule": schedule,
                "totals": {"carbon_gco2e": carbon, "energy_kwh": energy,
                           "completed": complete, "rejected": len(tasks)-complete,
                           "completion_rate": complete / len(tasks) if tasks else 1.0,
                           "rejection_rate": (len(tasks)-complete) / len(tasks) if tasks else 0.0,
                           "sla_violations": len(tasks)-complete,
                           "mean_latency_seconds": latency / complete if complete else 0.0},
                "message": str(result.message)}
