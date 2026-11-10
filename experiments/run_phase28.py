"""Compare exact small-instance offline MILP with online FCFS/greedy."""
import argparse
import csv
import json
import random
import statistics
from pathlib import Path
from time import perf_counter

from environment.task_generator import generate_phase25_workload
from experiments.evaluate_baselines import make_phase25_environment
from experiments.offline_optimizer import OfflineOptimizer
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler

ROOT = Path(__file__).resolve().parents[1]
POLICY_NAMES = ("Offline MILP", "Greedy carbon", "FCFS")
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds", "runtime_seconds")


def mean_sd_ci(values, seed):
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95": [None, None]}
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    rng = random.Random(seed)
    boot = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000)]
    boot.sort()
    return {"n": len(values), "mean": mean, "sd": sd,
            "ci95": [boot[int(.025 * (len(boot)-1))], boot[int(.975 * (len(boot)-1))]]}


def run_instance(task_count, seed, output, time_limit):
    tasks = generate_phase25_workload(seed, task_count)
    optimizer_environment = make_phase25_environment(dynamic_carbon=True)
    offline = OfflineOptimizer().solve(optimizer_environment, tasks, time_limit)
    rows = []
    if offline["totals"] is not None:
        rows.append({"policy": "Offline MILP", "instance_seed": seed,
                     "task_count": task_count, "optimal": offline["optimal"],
                     "solver_status": offline["status"],
                     **offline["totals"], "runtime_seconds": offline["runtime_seconds"],
                     "mip_gap": offline.get("mip_gap"), "message": offline["message"]})
    for policy, scheduler in (("Greedy carbon", GreedyCarbonScheduler()),
                              ("FCFS", FCFSScheduler())):
        environment = make_phase25_environment(dynamic_carbon=True)
        started = perf_counter()
        result = environment.run(tasks, scheduler)
        elapsed = perf_counter() - started
        rows.append({"policy": policy, "instance_seed": seed, "task_count": task_count,
                     "optimal": False, "solver_status": "online_heuristic",
                     **result["totals"], "runtime_seconds": elapsed,
                     "mip_gap": None, "message": "online; no future workload information"})
    offline_row = next((row for row in rows if row["policy"] == "Offline MILP" and row["optimal"]), None)
    greedy_row = next((row for row in rows if row["policy"] == "Greedy carbon"), None)
    for row in rows:
        row["optimality_gap_pct"] = None
    if offline_row and greedy_row and offline_row["completion_rate"] == 1.0 and greedy_row["completion_rate"] == 1.0:
        greedy_row["optimality_gap_pct"] = (greedy_row["carbon_gco2e"] - offline_row["carbon_gco2e"])
        greedy_row["optimality_gap_pct"] *= 100.0 / max(offline_row["carbon_gco2e"], 1e-12)
    return rows, offline


def make_report(output, rows, seeds, sizes, config):
    groups = {}
    for size in sizes:
        groups[str(size)] = {}
        for policy in POLICY_NAMES:
            subset = [r for r in rows if r["task_count"] == size and r["policy"] == policy]
            groups[str(size)][policy] = {metric: mean_sd_ci(
                [row[metric] for row in subset], 28000 + size * 101 + mi)
                for mi, metric in enumerate(METRICS)}
            if policy == "Greedy carbon":
                gap_values = [r["optimality_gap_pct"] for r in subset
                              if r.get("optimality_gap_pct") is not None]
                groups[str(size)][policy]["optimality_gap_pct"] = mean_sd_ci(
                    gap_values, 28900 + size)
    payload = {"config": config, "seeds": seeds, "task_sizes": sizes,
               "groups": groups, "runs": rows}
    (output / "phase28_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output / "phase28_evaluation.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    if rows:
        with (output / "phase28_runs.csv").open("w", newline="", encoding="utf-8") as stream:
            fields = sorted({key for row in rows for key in row})
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    lines = ["# Phase 2.8 — Offline optimisation benchmark", "",
             "## Method", "",
             "SciPy/HiGHS MILP chooses exactly one region and dispatch slot for every task. It minimizes total CO2e from the same GPU active-power and once-per-active-interval idle-power model used by the simulator. Constraints enforce GPU, CPU and memory reservations through the simulator's finish slot, migration latency, absolute deadlines, complete task assignment, and the simulator's two-slot maximum deferral. The offline optimizer is given the entire workload and full carbon profiles; Greedy carbon and FCFS run online with their existing candidate information only.", "",
             "An `optimal` row is an exact MILP optimum to solver tolerance. A `feasible_incumbent` is not certified optimal and is excluded from optimality-gap averages. Offline schedules require 100% completion; infeasible cases remain explicit. Greedy's gap is reported only when both it and the certified offline schedule complete every task:", "",
             "`Gap (%) = (Greedy emissions - Optimal emissions) / Optimal emissions × 100`", "",
             "Metrics are mean ± sample SD [95% bootstrap CI] across workload seeds. Confidence intervals are descriptive for this small seed count. Runtime measures optimizer construction/solve or baseline simulation wall time on this host; do not compare as a hardware-independent performance claim.", "",
             "## Results by workload size", ""]
    for size in sizes:
        lines.append(f"### {size} tasks per instance")
        lines.extend(["", "| Policy | Emissions gCO2e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Greedy optimality gap |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for policy in POLICY_NAMES:
            stats = groups[str(size)][policy]
            cells = []
            for metric in METRICS:
                x = stats[metric]
                cells.append("n/a" if x["n"] == 0 else
                             f'{x["mean"]:.4f} ± {x["sd"]:.4f} [{x["ci95"][0]:.4f}, {x["ci95"][1]:.4f}]')
            gap = stats.get("optimality_gap_pct")
            gap_cell = "n/a" if not gap or not gap["n"] else (
                f'{gap["mean"]:.2f}% ± {gap["sd"]:.2f} [{gap["ci95"][0]:.2f}, {gap["ci95"][1]:.2f}]')
            lines.append(f"| {policy} | " + " | ".join(cells[:6]) +
                         f" | {cells[6]} | {gap_cell} |")
        lines.append("")
    offline_rows = [r for r in rows if r["policy"] == "Offline MILP"]
    gaps = [r["optimality_gap_pct"] for r in rows if r["policy"] == "Greedy carbon" and
            r.get("optimality_gap_pct") is not None]
    all_complete = all(r["completion_rate"] == 1.0 for r in rows if r["policy"] == "Greedy carbon")
    gap_mean = statistics.mean(gaps) if gaps else None
    if gap_mean is None:
        conclusion = "No certified comparable optimality gaps were available; the experiment does not support an algorithm go/no-go conclusion."
    elif gap_mean < 5.0 and all_complete:
        conclusion = (f"Across certified, fully completed comparisons, mean greedy gap was {gap_mean:.2f}%. "
                      "For these bounded synthetic instances greedy is already near the offline benchmark; retain it and do not justify learning from this gap alone.")
    else:
        conclusion = (f"Mean certified greedy gap was {gap_mean:.2f}%. This indicates measurable offline headroom on these instances, but it does not by itself justify a contextual bandit: first determine whether the gap comes from future carbon knowledge, limited two-slot deferral, or capacity interactions, then validate on larger held-out/trace workloads.")
    lines.extend(["## Assessment", "", conclusion, "",
                  f"Certified optimal solves: {sum(r['optimal'] for r in offline_rows)} / {len(offline_rows)}. Greedy completed every task in every run: {all_complete}.", "",
                  "## Limitations", "",
                  "- This is an exact MILP for the simulator's modeled placement/energy semantics, not for real cloud hardware. It uses synthetic workload and carbon inputs.",
                  "- Offline has future knowledge of all tasks and the complete carbon profile; online schedulers do not. Gap therefore measures the combined value of lookahead and placement optimization under the specified wait limit, not a fair online algorithm race.",
                  "- All-completion is a hard MILP constraint. A case with no feasible complete schedule is reported as infeasible, not silently compared as lower-carbon rejection.",
                  "- SciPy/HiGHS solves to proven optimality only when status is `optimal`; any time-limited incumbent is identified separately and excluded from certified gaps.",
                  "- MILP models resource occupancy in the same integer finish-slot intervals as the simulator and energy on exact execution intervals partitioned at carbon slot boundaries. Shared idle power is represented by binary active-interval variables. This structure is exact for the current additive GPU power + shared idle overhead model; startup energy, host power state transitions, network energy, and uncertain runtimes are absent from both models.",
                  "- Only a few seeds and workload sizes are tested; confidence intervals are descriptive. A larger trace-calibrated evaluation and sensitivity analysis are required before interpreting the gap as general.", "",
                  "## Reproduction", "",
                  "`python -m experiments.run_phase28 --output-dir results/phase28_final`", "",
                  "The run-level JSON/JSONL/CSV and solver statuses are stored beside this report.", ""])
    (output / "PHASE28_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="28101,28102,28103")
    parser.add_argument("--task-sizes", default="4,8,12")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase28_final"))
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]
    sizes = [int(x) for x in args.task_sizes.split(",")]
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    rows, solver_details = [], []
    for size in sizes:
        for seed in seeds:
            instance_rows, offline = run_instance(size, seed, output, args.time_limit)
            rows.extend(instance_rows)
            solver_details.append({"task_count": size, "seed": seed,
                                   "status": offline["status"], "optimal": offline["optimal"],
                                   "runtime_seconds": offline["runtime_seconds"],
                                   "mip_gap": offline.get("mip_gap"), "message": offline.get("message")})
    config = {"time_limit_seconds": args.time_limit, "max_wait_slots": 2,
              "carbon_profiles": "synthetic dynamic 96-slot; no profile fitting",
              "workload_generator": "generate_phase25_workload",
              "offline_has_future_workload_and_carbon_knowledge": True,
              "resource_finish_semantics": "simulator ceil(end / slot_seconds) reservation"}
    payload = make_report(output, rows, seeds, sizes, config)
    payload["solver_runs"] = solver_details
    (output / "phase28_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["groups"], indent=2))


if __name__ == "__main__":
    main()
