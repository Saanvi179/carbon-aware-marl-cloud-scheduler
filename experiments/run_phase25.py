"""Controlled feature study under time-varying synthetic regional carbon."""
import argparse
import json
import random
import statistics
from pathlib import Path

import torch
import yaml

from experiments.train_ippo import ROOT, train, build_scheduler
from experiments.evaluate_baselines import make_phase25_environment
from experiments.run_phase24 import mean_ci, summarize_actions, write_learning_curves
from environment.task_generator import generate_phase25_workload
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


VARIANTS = {
    "IPPO + SPT / dynamic": {"spt_intervention_probability": 0.5,
                             "carbon_profile_mode": "dynamic_synthetic",
                             "observation_ablation": "none"},
    "IPPO no SPT / dynamic": {"spt_intervention_probability": 0.0,
                              "carbon_profile_mode": "dynamic_synthetic",
                              "observation_ablation": "none"},
    "IPPO no-carbon-observation / dynamic": {"spt_intervention_probability": 0.0,
                                             "carbon_profile_mode": "dynamic_synthetic",
                                             "observation_ablation": "no_carbon"},
    "IPPO no SPT / static carbon": {"spt_intervention_probability": 0.0,
                                    "carbon_profile_mode": "static_control",
                                    "observation_ablation": "none"},
}


def write_summaries(rows, seeds, workload_seeds, config):
    metrics = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
               "sla_violations", "mean_latency_seconds")
    summary = {}
    for policy in sorted({row["policy"] for row in rows}):
        group = [row for row in rows if row["policy"] == policy]
        summary[policy] = {metric: mean_ci(group, metric, 25001 + i)
                           for i, metric in enumerate(metrics)}
        diagnostic_rows = [row for row in group if row.get("action_distribution")]
        if diagnostic_rows:
            summary[policy]["action_distribution"] = {
                "selected_actions": {action: sum(row["action_distribution"]["selected_action_counts"][action]
                    for row in diagnostic_rows) for action in ("defer", "execute_local", "migrate")},
                "mean_masked_probabilities": {action: statistics.mean(
                    row["action_distribution"]["mean_masked_probabilities"][action]
                    for row in diagnostic_rows) for action in
                    ("defer", "execute_local", "migrate_remote_1", "migrate_remote_2")},
                "mean_entropy": statistics.mean(row["action_distribution"]["mean_entropy"]
                                                for row in diagnostic_rows),
                "mean_spt_override_rate": statistics.mean(row["action_distribution"]["spt_override_rate"]
                                                           for row in diagnostic_rows),
                "mean_resolver_intervention_rate": statistics.mean(
                    row["action_distribution"]["resolver_intervention_rate"] for row in diagnostic_rows),
                "forced_execution_count": sum(row["action_distribution"]["forced_execution_count"]
                                               for row in diagnostic_rows),
                "legal_action_counts": {str(n): sum(
                    row["action_distribution"]["legal_action_count_distribution"][str(n)]
                    for row in diagnostic_rows) for n in range(1, 5)},
            }

    comparator = {
        "IPPO + SPT / dynamic": "Greedy carbon / dynamic",
        "IPPO no SPT / dynamic": "Greedy carbon / dynamic",
        "IPPO no-carbon-observation / dynamic": "Greedy carbon / dynamic",
        "IPPO no SPT / static carbon": "Greedy carbon / static",
        "IPPO + SPT / dynamic (fallback off)": "Greedy carbon / dynamic",
        "IPPO no SPT / dynamic (fallback off)": "Greedy carbon / dynamic",
    }
    for policy, greedy_name in comparator.items():
        group = [row for row in rows if row["policy"] == policy]
        greedy = {row["workload_seed"]: row for row in rows if row["policy"] == greedy_name}
        if group and greedy:
            paired = [{"policy_seed": row["policy_seed"], "workload_seed": row["workload_seed"],
                       "carbon_delta": row["carbon_gco2e"] - greedy[row["workload_seed"]]["carbon_gco2e"],
                       "completion_delta": row["completion_rate"] - greedy[row["workload_seed"]]["completion_rate"],
                       "sla_delta": row["sla_violations"] - greedy[row["workload_seed"]]["sla_violations"]}
                      for row in group]
            summary[policy]["paired_delta_vs_greedy"] = {
                metric: mean_ci(paired, metric, 26001 + i)
                for i, metric in enumerate(("carbon_delta", "completion_delta", "sla_delta"))}

    controlled_pairs = (
        ("IPPO + SPT / dynamic", "IPPO no SPT / dynamic", "paired_spt_effect"),
        ("IPPO no-carbon-observation / dynamic", "IPPO no SPT / dynamic",
         "paired_no_carbon_observation_effect"),
        ("IPPO no SPT / dynamic", "IPPO no SPT / static carbon", "paired_dynamic_carbon_effect"),
        ("IPPO + SPT / dynamic (fallback off)", "IPPO + SPT / dynamic",
         "paired_fallback_disabled_effect"),
    )
    for left_name, right_name, result_name in controlled_pairs:
        left = {(row["policy_seed"], row["workload_seed"]): row for row in rows
                if row["policy"] == left_name}
        right = {(row["policy_seed"], row["workload_seed"]): row for row in rows
                 if row["policy"] == right_name}
        shared = sorted(set(left) & set(right))
        if shared:
            differences = [{"policy_seed": seed, "workload_seed": workload,
                            "carbon_delta": left[(seed, workload)]["carbon_gco2e"] -
                                            right[(seed, workload)]["carbon_gco2e"],
                            "completion_delta": left[(seed, workload)]["completion_rate"] -
                                               right[(seed, workload)]["completion_rate"],
                            "sla_delta": left[(seed, workload)]["sla_violations"] -
                                         right[(seed, workload)]["sla_violations"]}
                           for seed, workload in shared]
            summary[left_name][result_name] = {
                metric: mean_ci(differences, metric, 27001 + i)
                for i, metric in enumerate(("carbon_delta", "completion_delta", "sla_delta"))}

    for dynamic_name, static_name in (("Greedy carbon / dynamic", "Greedy carbon / static"),
                                     ("FCFS / dynamic", "FCFS / static")):
        dynamic = {row["workload_seed"]: row for row in rows if row["policy"] == dynamic_name}
        static = {row["workload_seed"]: row for row in rows if row["policy"] == static_name}
        shared = sorted(set(dynamic) & set(static))
        differences = [{"policy_seed": None, "workload_seed": seed,
                        "carbon_delta": dynamic[seed]["carbon_gco2e"] - static[seed]["carbon_gco2e"],
                        "completion_delta": dynamic[seed]["completion_rate"] - static[seed]["completion_rate"],
                        "sla_delta": dynamic[seed]["sla_violations"] - static[seed]["sla_violations"]}
                       for seed in shared]
        summary[dynamic_name]["paired_dynamic_profile_effect"] = {
            metric: mean_ci(differences, metric, 28001 + i)
            for i, metric in enumerate(("carbon_delta", "completion_delta", "sla_delta"))}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "phase25_training_config.yaml"))
    parser.add_argument("--seeds", default="7,19,42")
    parser.add_argument("--workload-seeds", default="25101,25102,25103,25104,25105,25106,25107,25108,25109,25110,25111,25112")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase25_final"))
    parser.add_argument("--skip-training", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.episodes is not None:
        config["episodes"] = args.episodes
    seeds = [int(value) for value in args.seeds.split(",")]
    workload_seeds = [int(value) for value in args.workload_seeds.split(",")]
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    checkpoint_index, seed_logs = {}, {}
    for variant, override in VARIANTS.items():
        seed_logs[variant] = {}
        for seed in seeds:
            run_dir = output / "training" / variant.replace(" ", "_").replace("/", "") / f"seed_{seed}"
            checkpoint = run_dir / "checkpoints" / f"ippo_seed{seed}.pt"
            log = run_dir / f"training_seed{seed}.jsonl"
            if args.skip_training:
                if not checkpoint.exists() or not log.exists():
                    raise FileNotFoundError(f"missing saved checkpoint or training log: {run_dir}")
            else:
                _, checkpoint, log = train({**config, **override}, config["episodes"], seed, run_dir)
            checkpoint_index[(variant, seed)] = checkpoint
            seed_logs[variant][seed] = log

    rows = []
    for workload_seed in workload_seeds:
        workload = generate_phase25_workload(workload_seed, config["tasks_per_episode"])
        for mode, dynamic in (("dynamic", True), ("static", False)):
            env = make_phase25_environment(dynamic_carbon=dynamic)
            for name, scheduler in ((f"FCFS / {mode}", FCFSScheduler()),
                                    (f"Greedy carbon / {mode}", GreedyCarbonScheduler())):
                result = env.run(workload, scheduler)
                rows.append({"policy": name, "policy_seed": None, "workload_seed": workload_seed,
                             "carbon_mode": mode, **result["totals"]})
        for variant, override in VARIANTS.items():
            dynamic = override["carbon_profile_mode"] == "dynamic_synthetic"
            for seed in seeds:
                scheduler_config = {**config, **override}
                scheduler = build_scheduler(scheduler_config, seed, deterministic=True)
                state = torch.load(checkpoint_index[(variant, seed)], map_location="cpu", weights_only=False)
                scheduler.load_checkpoint(state["agents"])
                result = make_phase25_environment(dynamic_carbon=dynamic).run(workload, scheduler)
                rows.append({"policy": variant, "policy_seed": seed, "workload_seed": workload_seed,
                             "carbon_mode": "dynamic" if dynamic else "static",
                             **result["totals"],
                             "action_distribution": summarize_actions(result["agent_decisions"])})
                if dynamic and variant in ("IPPO + SPT / dynamic", "IPPO no SPT / dynamic"):
                    fallback_config = {**scheduler_config, "terminal_fallback_enabled": False}
                    unassisted = build_scheduler(fallback_config, seed, deterministic=True)
                    unassisted.load_checkpoint(state["agents"])
                    diagnostic = make_phase25_environment(dynamic_carbon=True).run(workload, unassisted)
                    rows.append({"policy": variant + " (fallback off)", "policy_seed": seed,
                                 "workload_seed": workload_seed, "carbon_mode": "dynamic",
                                 **diagnostic["totals"],
                                 "action_distribution": summarize_actions(diagnostic["agent_decisions"])})

    summary = write_summaries(rows, seeds, workload_seeds, config)
    payload = {"training_seeds": seeds, "heldout_workload_seeds": workload_seeds,
               "episodes_per_seed_variant": config["episodes"],
               "tasks_per_workload": config["tasks_per_episode"],
               "feature_controls": {name: value for name, value in VARIANTS.items()},
               "profile_generation": "synthetic deterministic 96-slot sinusoidal regional profiles",
               "settings": config, "summary": summary, "runs": rows}
    (output / "phase25_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output / "phase25_evaluation.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    write_learning_curves(output, seed_logs, VARIANTS)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
