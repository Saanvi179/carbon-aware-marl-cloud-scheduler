"""Small multi-seed IPPO ablation and held-out comparison for Phase 2.3."""
import argparse
import json
import statistics
import random
from pathlib import Path
import torch
import yaml

from experiments.train_ippo import ROOT, train, build_scheduler
from experiments.evaluate_baselines import make_environment
from environment.task_generator import generate_variable_workload
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


def mean_ci(rows, metric, bootstrap_seed=5522, replicates=4000):
    values = [row[metric] for row in rows]
    mean = statistics.mean(values) if values else 0.0
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    rng = random.Random(bootstrap_seed)
    boot_means = []
    policy_seeds = sorted({row["policy_seed"] for row in rows if row["policy_seed"] is not None})
    workload_seeds = sorted({row["workload_seed"] for row in rows})
    if policy_seeds:
        matrix = {(row["policy_seed"], row["workload_seed"]): row[metric] for row in rows}
        for _ in range(replicates):
            chosen_policies = [rng.choice(policy_seeds) for _ in policy_seeds]
            chosen_workloads = [rng.choice(workload_seeds) for _ in workload_seeds]
            sample = [matrix[(p, w)] for p in chosen_policies for w in chosen_workloads]
            boot_means.append(statistics.mean(sample))
    elif workload_seeds:
        by_workload = {row["workload_seed"]: row[metric] for row in rows}
        for _ in range(replicates):
            boot_means.append(statistics.mean(by_workload[rng.choice(workload_seeds)]
                                              for _ in workload_seeds))
    boot_means.sort()
    low = boot_means[int(.025 * (len(boot_means) - 1))] if boot_means else mean
    high = boot_means[int(.975 * (len(boot_means) - 1))] if boot_means else mean
    return {"n": len(values), "mean": mean, "sd": sd,
            "ci95_low": low, "ci95_high": high,
            "ci_method": "percentile crossed-cluster bootstrap" if policy_seeds else "percentile workload bootstrap"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "training_config.yaml"))
    parser.add_argument("--seeds", default="7,19,42")
    parser.add_argument("--workload-seeds", default="901,902,903,904,905")
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase23"))
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as stream:
        base = yaml.safe_load(stream)
    seeds = [int(x) for x in args.seeds.split(",")]
    eval_seeds = [int(x) for x in args.workload_seeds.split(",")]
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    variants = {
        "ippo_full_reward_spt": {},
        "ippo_no_spt": {"spt_intervention_probability": 0.0},
        "ippo_carbon_only": {"lambda_latency": 0.0},
        "ippo_latency_only": {"reward_carbon_weight": 0.0},
    }
    checkpoints = {}
    for variant, overrides in variants.items():
        for seed in seeds:
            config = {**base, **overrides}
            run_dir = output / variant / f"seed{seed}"
            _, checkpoint, _ = train(config, args.episodes, seed, run_dir)
            checkpoints[(variant, seed)] = checkpoint

    records = []
    for workload_seed in eval_seeds:
        workload = generate_variable_workload(workload_seed, base["tasks_per_episode"])
        for baseline_name, baseline in (("FCFS", FCFSScheduler()),
                                        ("Greedy carbon", GreedyCarbonScheduler())):
            result = make_environment().run(workload, baseline)
            records.append({"policy": baseline_name, "policy_seed": None,
                            "workload_seed": workload_seed, **result["totals"]})
        for (variant, seed), checkpoint in checkpoints.items():
            config = {**base, **variants[variant]}
            scheduler = build_scheduler(config, seed, deterministic=True)
            state = torch.load(checkpoint, map_location="cpu", weights_only=False)
            scheduler.load_checkpoint(state["agents"])
            result = make_environment().run(workload, scheduler)
            records.append({"policy": variant, "policy_seed": seed,
                            "workload_seed": workload_seed, **result["totals"],
                            "agent_rewards": result["agent_rewards"],
                            "agent_decisions": result["agent_decisions"]})

    metrics = ("carbon_gco2e", "energy_kwh", "mean_latency_seconds", "sla_violations", "rejected", "rejection_rate",
               "completed", "completion_rate")
    groups = {}
    for policy in sorted({r["policy"] for r in records}):
        rows = [r for r in records if r["policy"] == policy]
        groups[policy] = {metric: mean_ci(rows, metric, 5522 + i)
                          for i, metric in enumerate(metrics)}
    greedy_by_seed = {r["workload_seed"]: r for r in records if r["policy"] == "Greedy carbon"}
    for variant in variants:
        deltas = [{**r, "paired_delta": r["carbon_gco2e"] -
                   greedy_by_seed[r["workload_seed"]]["carbon_gco2e"]}
                  for r in records if r["policy"] == variant]
        groups[variant]["paired_emissions_delta_vs_greedy_g"] = mean_ci(deltas, "paired_delta", 6599)
    result = {"training_seeds": seeds, "heldout_workload_seeds": eval_seeds,
              "episodes_per_seed_variant": args.episodes,
              "variant_settings": variants, "summary": groups, "runs": records}
    (output / "phase23_evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (output / "phase23_evaluation.jsonl").open("w", encoding="utf-8") as stream:
        for row in records:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps(groups, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

