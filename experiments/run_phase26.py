"""Small matched IPPO/MAPPO comparison with held-out synthetic workloads."""
import argparse
import json
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
    "IPPO no SPT": {"algorithm": "ippo", "spt_intervention_probability": 0.0},
    "MAPPO no SPT": {"algorithm": "mappo", "spt_intervention_probability": 0.0},
    "MAPPO with SPT": {"algorithm": "mappo", "spt_intervention_probability": 0.5},
}
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds")


def summarize(rows):
    output = {}
    for name in sorted({r["policy"] for r in rows}):
        subset = [r for r in rows if r["policy"] == name]
        output[name] = {metric: mean_ci(subset, metric, 26900+i) for i, metric in enumerate(METRICS)}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "phase26_training_config.yaml"))
    parser.add_argument("--seeds", default="7,19,42")
    parser.add_argument("--workload-seeds", default="26101,26102,26103,26104")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase26_final"))
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.episodes is not None:
        config["episodes"] = args.episodes
    seeds = [int(x) for x in args.seeds.split(",")]
    workload_seeds = [int(x) for x in args.workload_seeds.split(",")]
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    checkpoints, logs = {}, {}
    for variant, override in VARIANTS.items():
        logs[variant] = {}
        for seed in seeds:
            run_dir = output / "training" / variant.replace(" ", "_") / f"seed_{seed}"
            scheduler, checkpoint, log = train({**config, **override}, config["episodes"], seed, run_dir)
            checkpoints[(variant, seed)] = checkpoint
            logs[variant][seed] = log
    rows = []
    for workload_seed in workload_seeds:
        workload = generate_phase25_workload(workload_seed, config["tasks_per_episode"])
        for name, scheduler in (("FCFS", FCFSScheduler()),
                                ("Greedy carbon", GreedyCarbonScheduler())):
            result = make_phase25_environment().run(workload, scheduler)
            rows.append({"policy": name, "policy_seed": None, "workload_seed": workload_seed,
                         **result["totals"]})
        for variant, override in VARIANTS.items():
            for seed in seeds:
                cfg = {**config, **override}
                scheduler = build_scheduler(cfg, seed, deterministic=True)
                state = torch.load(checkpoints[(variant, seed)], map_location="cpu", weights_only=False)
                scheduler.load_checkpoint(state["agents"])
                result = make_phase25_environment().run(workload, scheduler)
                rows.append({"policy": variant, "policy_seed": seed, "workload_seed": workload_seed,
                             **result["totals"],
                             "action_distribution": summarize_actions(result["agent_decisions"])})
    payload = {"training_seeds": seeds, "heldout_workload_seeds": workload_seeds,
               "episodes_per_seed": config["episodes"], "tasks_per_workload": config["tasks_per_episode"],
               "settings": config, "summary": summarize(rows), "runs": rows}
    (output / "phase26_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output / "phase26_evaluation.jsonl").open("w", encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row, sort_keys=True) + "\n")
    write_learning_curves(output, logs, VARIANTS)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
