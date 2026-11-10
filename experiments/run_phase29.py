"""Train/evaluate a safety-gated contextual bandit against baselines and MILP."""
import argparse
import json
import random
import statistics
from pathlib import Path
from time import perf_counter
import numpy as np
import yaml

from agents.contextual_bandit import ContextualBanditScheduler
from environment.task_generator import generate_phase25_workload
from experiments.evaluate_baselines import make_phase25_environment
from experiments.offline_optimizer import OfflineOptimizer
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds", "runtime_seconds", "fallback_rate")


def stats_ci(values, seed):
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95": [None, None]}
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    return {"n": len(values), "mean": mean, "sd": sd,
            "ci95": [samples[int(.025*(len(samples)-1))], samples[int(.975*(len(samples)-1))]]}


def build_bandit(seed, learning=True, deterministic=False, alpha=.8):
    env = make_phase25_environment(dynamic_carbon=True)
    caps = {name: (region.resources.gpus, region.resources.cpu_cores, region.resources.memory_gb)
            for name, region in env.regions.items()}
    return ContextualBanditScheduler(env.region_names, caps, alpha=alpha,
                                     deterministic=deterministic, learning_enabled=learning)


def train_bandit(seed, episodes, tasks_per_episode, output, workload_seed_base, alpha):
    output.mkdir(parents=True, exist_ok=True)
    scheduler = build_bandit(seed, learning=True, deterministic=False, alpha=alpha)
    log_path = output / f"training_seed{seed}.jsonl"
    with log_path.open("w", encoding="utf-8") as log:
        for episode in range(1, episodes + 1):
            workload_seed = workload_seed_base + seed * 1000 + episode
            workload = generate_phase25_workload(workload_seed, tasks_per_episode)
            result = make_phase25_environment(dynamic_carbon=True).run(workload, scheduler)
            theta_norms = {name: float(np.linalg.norm(np.linalg.solve(scheduler.A[name],
                                     scheduler.b[name])))
                           for name in scheduler.region_names}
            row = {"episode": episode, "training_seed": seed,
                   "workload_seed": workload_seed, "totals": result["totals"],
                   "episode_reward": result["episode_reward"],
                   "decision_trace": result["agent_decisions"],
                   "arm_counts": dict(scheduler.arm_counts), "theta_l2": theta_norms,
                   "mean_payoff": result["totals"]["mean_observed_payoff"]}
            log.write(json.dumps(row, sort_keys=True) + "\n")
            log.flush()
    checkpoint = output / f"bandit_seed{seed}.json"
    checkpoint.write_text(json.dumps(scheduler.checkpoint(), indent=2), encoding="utf-8")
    return checkpoint, log_path


def evaluate(seed, heldout_seed, workload, tasks, checkpoint, alpha):
    scheduler = build_bandit(seed, learning=False, deterministic=True, alpha=alpha)
    scheduler.load_checkpoint(json.loads(checkpoint.read_text(encoding="utf-8")))
    env = make_phase25_environment(dynamic_carbon=True)
    started = perf_counter(); result = env.run(workload, scheduler); elapsed = perf_counter()-started
    return {"policy": "Contextual bandit", "policy_seed": seed,
            "workload_seed": heldout_seed, "task_count": tasks,
            **result["totals"], "runtime_seconds": elapsed,
            "decision_trace": result["agent_decisions"]}


def run_baseline(name, scheduler, seed, workload_seed, workload, tasks):
    env = make_phase25_environment(dynamic_carbon=True)
    started = perf_counter(); result = env.run(workload, scheduler); elapsed = perf_counter()-started
    return {"policy": name, "policy_seed": seed, "workload_seed": workload_seed,
            "task_count": tasks, **result["totals"], "runtime_seconds": elapsed,
            "fallback_rate": 0.0, "decision_trace": []}


def summarize(rows, sizes, seeds, heldout_seeds):
    grouped = {}
    for policy in sorted({row["policy"] for row in rows}):
        subset = [row for row in rows if row["policy"] == policy]
        grouped[policy] = {metric: stats_ci([row[metric] for row in subset if row.get(metric) is not None], 29001+i)
                           for i, metric in enumerate(METRICS)}
    by_workload = {row["workload_seed"]: row for row in rows
                   if row["policy"] == "Offline MILP" and row.get("optimal")}
    for policy in ("Greedy carbon", "FCFS", "Contextual bandit"):
        comparisons = [row for row in rows if row["policy"] == policy]
        gaps, paired_deltas, completion_deltas, sla_deltas = [], [], [], []
        for row in comparisons:
            offline = by_workload.get(row["workload_seed"])
            if offline is None:
                continue
            if (offline.get("optimal") and offline["completion_rate"] == 1.0 and
                    row["completion_rate"] == 1.0 and offline["carbon_gco2e"] > 0):
                gaps.append(100.0 * (row["carbon_gco2e"] - offline["carbon_gco2e"]) /
                            offline["carbon_gco2e"])
        grouped[policy]["optimality_gap_pct"] = stats_ci(gaps, 29200)
        greedy = {r["workload_seed"]: r for r in rows if r["policy"] == "Greedy carbon"}
        for row in comparisons:
            key = row["workload_seed"]
            if key in greedy:
                baseline = greedy[key]
                completion_deltas.append(row["completion_rate"] - baseline["completion_rate"])
                sla_deltas.append(row["sla_violations"] - baseline["sla_violations"])
                if (row["completion_rate"] == baseline["completion_rate"] and
                        row["sla_violations"] == baseline["sla_violations"]):
                    paired_deltas.append(row["carbon_gco2e"] - baseline["carbon_gco2e"])
        if policy != "Greedy carbon":
            grouped[policy]["paired_carbon_delta_vs_greedy_g"] = stats_ci(paired_deltas, 29300)
            grouped[policy]["paired_completion_delta_vs_greedy"] = stats_ci(completion_deltas, 29400)
            grouped[policy]["paired_sla_delta_vs_greedy"] = stats_ci(sla_deltas, 29500)
    return grouped


def write_report(output, summary, rows, seeds, heldout, episodes, task_count):
    lines = ["# Phase 2.9 — Contextual bandit evaluation", "",
             "## Method", "",
             f"LinUCB uses one disjoint linear model per destination and features available in the current task observation: candidate carbon intensity, estimated incremental emissions and energy, execution/migration time, available GPU/CPU/memory, queue state, and deadline fraction. It receives feedback only for the region actually committed. Training uses {len(seeds)} seeds × {episodes} episodes × {task_count} synthetic tasks; held-out workloads are distinct from training workload seeds.", "",
             "A hard feasibility mask is applied before selection. The resolver revalidates the selected destination against the current feasible candidate set and task deadline; invalid or numerically unsafe decisions fall back to the existing greedy carbon rule. If no feasible candidate exists, the task defers under the simulator's original bounded lifecycle; the bandit cannot create a feasible placement. The online policy sees no future tasks or future carbon values. Offline MILP rows are an oracle with full workload/carbon lookahead and are not pooled with online-policy comparisons.", "",
             "Metrics are mean ± sample SD [95% percentile bootstrap CI]. For learned policy, runs cross training seeds and held-out workloads. With this pilot's small sample the intervals are descriptive. The required success condition is a negative paired bandit-minus-greedy emissions interval while completion and SLA outcomes are not worse.", "",
             "## Held-out results", "",
             "| Policy | Emissions gCO2e | Energy kWh | Completion | Rejection rate | SLA violations | Latency s | Fallback rate | Runtime s | Gap to offline |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for policy in ("Contextual bandit", "Greedy carbon", "FCFS", "Offline MILP"):
        group = summary[policy]
        vals = []
        for metric in ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate", "sla_violations",
                       "mean_latency_seconds", "fallback_rate", "runtime_seconds"):
            s = group[metric]
            vals.append("n/a" if not s["n"] else f'{s["mean"]:.4f} ± {s["sd"]:.4f} [{s["ci95"][0]:.4f}, {s["ci95"][1]:.4f}]')
        gap = group.get("optimality_gap_pct", {"n": 0})
        gap_text = "n/a" if not gap["n"] else f'{gap["mean"]:.2f}% [{gap["ci95"][0]:.2f}, {gap["ci95"][1]:.2f}]'
        lines.append(f"| {policy} | " + " | ".join(vals) + f" | {gap_text} |")
    bandit = summary["Contextual bandit"]
    paired = bandit["paired_carbon_delta_vs_greedy_g"]
    completion_pair = bandit["paired_completion_delta_vs_greedy"]
    sla_pair = bandit["paired_sla_delta_vs_greedy"]
    lines.extend(["", "Paired bandit-minus-greedy differences on workload runs with equal completion and SLA outcomes: "
                  f"emissions {paired['mean']:.3f} g [{paired['ci95'][0]:.3f}, {paired['ci95'][1]:.3f}] (n={paired['n']}), "
                  f"completion {completion_pair['mean']:.4f}, SLA count {sla_pair['mean']:.4f}.", "",
                  "## Decision", ""])
    if not paired["n"]:
        lines.append("The pilot did not produce complete paired comparisons, so it cannot establish an emissions improvement.")
    elif (paired["ci95"][1] < 0 and
          bandit["paired_completion_delta_vs_greedy"]["mean"] >= 0 and
          bandit["paired_sla_delta_vs_greedy"]["mean"] <= 0):
        lines.append("The paired emissions interval is below zero and service metrics are not worse in this pilot. This is preliminary evidence only; it requires validation on more workload families and seeds.")
    else:
        lines.append("The bandit did not demonstrate the required held-out improvement over greedy while preserving completion and SLA outcomes. No improvement claim is made; retain greedy as the operational scheduler.")
    lines.extend(["", "## Training and safety diagnostics", "",
             f"Training used seeds {seeds} and held-out workload seeds {heldout}. Per-episode action, candidate, payoff, arm-count, parameter and fallback logs plus checkpoints are stored under `training/`. Evaluation decision traces and all run-level metrics are stored in the JSON/JSONL/CSV artifacts. Offline MILP infeasibility is recorded explicitly; only certified optimal feasible instances contribute an optimality gap.", "",
                  "Completion/SLA are hard comparison criteria: a lower carbon mean caused by rejected tasks is not an improvement. The greedy fallback is used when an alternative's confidence bound does not clear the known immediate greedy reward, for missing/invalid model output, or when a decision fails the immediate safety gate; it cannot guarantee future admission under later contention. No feasibility, deadline or rejection rule was relaxed.", "",
                  "## Limitations", "",
                  "- Synthetic 96-slot carbon profiles and synthetic workloads are illustrative, not trace-calibrated. Only one workload family is used.",
                  "- LinUCB models each region separately and updates from chosen-action feedback; it does not model the downstream effects of consuming capacity on future tasks.",
                  "- The offline MILP knows future tasks and the full carbon profile. The online-to-offline gap includes this information advantage and must not be described as learnable policy headroom without further ablations.",
                  "- The safety layer guarantees a selected action is feasible at commitment time. No online algorithm can guarantee all future tasks will complete under arbitrary overload; the report compares actual completion and SLA metrics with greedy.",
                  "- Small seed counts make intervals descriptive. A positive result would not establish production effectiveness.", "",
                  "## Reproduction", "",
                  "`python -m experiments.run_phase29 --episodes 12 --tasks 12`", ""])
    (output / "PHASE29_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "phase29_bandit_config.yaml"))
    parser.add_argument("--seeds")
    parser.add_argument("--workload-seeds")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--tasks", type=int)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    seeds = [int(v) for v in (args.seeds or ",".join(map(str, config["training_seeds"]))).split(",")]
    heldout = [int(v) for v in (args.workload_seeds or ",".join(map(str, config["heldout_workload_seeds"]))).split(",")]
    episodes = args.episodes if args.episodes is not None else config["episodes_per_seed"]
    task_count = args.tasks if args.tasks is not None else config["tasks_per_episode"]
    alpha = args.alpha if args.alpha is not None else config["linucb_alpha"]
    workload_seed_base = config["training_workload_seed_base"]
    output = Path(args.output_dir or ROOT / config["output_dir"]); output.mkdir(parents=True, exist_ok=True)
    checkpoints = {}
    for seed in seeds:
        checkpoint, log = train_bandit(seed, episodes, task_count,
                                       output / "training" / f"seed_{seed}", workload_seed_base, alpha)
        checkpoints[seed] = checkpoint
    rows = []
    for workload_seed in heldout:
        workload = generate_phase25_workload(workload_seed, task_count)
        opt = OfflineOptimizer().solve(make_phase25_environment(dynamic_carbon=True), workload, 30.0)
        if opt["totals"] is not None:
            rows.append({"policy": "Offline MILP", "policy_seed": None,
                         "workload_seed": workload_seed, "task_count": task_count,
                         **opt["totals"], "runtime_seconds": opt["runtime_seconds"],
                         "fallback_rate": 0.0, "optimal": opt["optimal"],
                         "solver_status": opt["status"], "decision_trace": []})
        else:
            rows.append({"policy": "Offline MILP", "policy_seed": None,
                         "workload_seed": workload_seed, "task_count": task_count,
                         "carbon_gco2e": None, "energy_kwh": None, "completed": None,
                         "rejected": None, "completion_rate": None, "rejection_rate": None,
                         "sla_violations": None, "mean_latency_seconds": None,
                         "runtime_seconds": opt["runtime_seconds"], "fallback_rate": None,
                         "optimal": False, "solver_status": opt["status"],
                         "decision_trace": [], "message": opt["message"]})
        for policy_name, scheduler in (("Greedy carbon", GreedyCarbonScheduler()),
                                       ("FCFS", FCFSScheduler())):
            rows.append(run_baseline(policy_name, scheduler, None, workload_seed, workload, task_count))
        for seed in seeds:
            rows.append(evaluate(seed, workload_seed, workload, task_count,
                                 checkpoints[seed], alpha))
    summary = summarize(rows, [task_count], seeds, heldout)
    payload = {"training_seeds": seeds, "heldout_workload_seeds": heldout,
               "episodes_per_seed": episodes, "tasks_per_workload": task_count,
               "alpha": alpha, "online_observation_only": True,
               "summary": summary, "runs": rows}
    (output / "phase29_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output / "phase29_evaluation.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows: stream.write(json.dumps(row, sort_keys=True) + "\n")
    with (output / "phase29_runs.csv").open("w", newline="", encoding="utf-8") as stream:
        import csv
        fields = sorted({key for row in rows for key in row if key != "decision_trace"})
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows([{k:v for k,v in row.items() if k != "decision_trace"} for row in rows])
    write_report(output, summary, rows, seeds, heldout, episodes, task_count)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
