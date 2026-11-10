"""Compare FCFS, greedy carbon and a trained IPPO checkpoint on identical tasks."""
import argparse
import json
from pathlib import Path
import torch
import yaml

from agents.ippo_agent import IPPOScheduler
from environment.task_generator import synthetic_workload
from experiments.evaluate_baselines import make_environment
from experiments.train_ippo import build_scheduler, ROOT
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


def evaluate(config, checkpoint, episodes=1, seed=None):
    seed = config["seed"] if seed is None else seed
    policies = [("FCFS", FCFSScheduler()), ("Greedy carbon", GreedyCarbonScheduler())]
    ippo = build_scheduler(config, seed, deterministic=True)
    if checkpoint:
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        ippo.load_checkpoint(state["agents"])
        policies.append(("IPPO", ippo))
    results = {}
    for name, scheduler in policies:
        rows = []
        for _ in range(episodes):
            result = make_environment().run(synthetic_workload(), scheduler)
            rows.append(result["totals"])
        keys = ("carbon_gco2e", "energy_kwh", "mean_latency_seconds", "sla_violations",
                "completed", "rejected", "completion_rate")
        results[name] = {key: sum(row[key] for row in rows) / len(rows) for key in keys}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "training_config.yaml"))
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output")
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    result = evaluate(config, args.checkpoint, args.episodes, args.seed)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
