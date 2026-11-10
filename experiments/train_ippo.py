"""Train independent regional PPO policies on the synthetic cloud workload."""
import argparse
import json
import random
from pathlib import Path
import torch
import yaml

from agents.ippo_agent import IPPOScheduler, CarbonAwareSPTIPPOScheduler
from agents.mappo_agent import MAPPOScheduler
from environment.task_generator import (generate_variable_workload, generate_diverse_workload,
                                        generate_phase25_workload)
from experiments.evaluate_baselines import make_environment, environment_for_config


ROOT = Path(__file__).resolve().parents[1]


def read_config(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def build_scheduler(config, seed, deterministic=False):
    env = environment_for_config(config)
    capacities = {name: (region.resources.gpus, region.resources.cpu_cores,
                         region.resources.memory_gb) for name, region in env.regions.items()}
    agent_config = dict(config)
    agent_config["slot_seconds"] = env.slot_seconds
    if config.get("algorithm", "ippo") == "mappo":
        scheduler_type = MAPPOScheduler
    elif config.get("spt_method") == "carbon_latency_bounded":
        scheduler_type = CarbonAwareSPTIPPOScheduler
    else:
        scheduler_type = IPPOScheduler
    return scheduler_type(env.region_names, capacities, agent_config, seed, deterministic)


def train(config, episodes=None, seed=None, output_dir=None, workload_seed_base=None):
    seed = config["seed"] if seed is None else seed
    episodes = config["episodes"] if episodes is None else episodes
    output = Path(output_dir or ROOT / config["output_dir"])
    checkpoint_dir = output / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    random.seed(seed); torch.manual_seed(seed)
    scheduler = build_scheduler(config, seed)
    workload_seed_base = (config["training_workload_seed_base"] if workload_seed_base is None
                          else workload_seed_base)
    log_path = output / f"training_seed{seed}.jsonl"
    with log_path.open("w", encoding="utf-8") as log:
        for episode in range(1, episodes + 1):
            workload_seed = workload_seed_base + seed * 1000 + episode
            generator = {"expanded_v1": generate_diverse_workload,
                         "phase25_bursty": generate_phase25_workload}.get(
                             config.get("workload_profile"), generate_variable_workload)
            workload = generator(workload_seed, config["tasks_per_episode"])
            result = environment_for_config(config).run(workload, scheduler)
            update_stats = scheduler.update()
            totals = result["totals"]
            action_counts = {name: 0 for name in ("defer", "execute_local", "migrate")}
            probability_sums = [0.0] * 4
            probability_count = 0
            entropy_values = []
            per_agent = {}
            reward_components = {name: 0.0 for name in
                                 ("completion", "carbon", "latency", "sla", "rejection", "defer")}
            for decision in result["agent_decisions"]:
                action_counts[decision["selected_action"]] += 1
                entropy_values.append(decision["entropy"])
                probabilities = decision["probabilities"]
                if len(probabilities) == 4:
                    for index, value in enumerate(probabilities):
                        probability_sums[index] += value
                    probability_count += 1
                region = per_agent.setdefault(decision["agent"], {
                    "counts": {name: 0 for name in ("defer", "execute_local", "migrate")},
                    "probabilities": [0.0] * 4, "entropy": [], "values": []})
                region["counts"][decision["selected_action"]] += 1
                for index, value in enumerate(probabilities):
                    region["probabilities"][index] += value
                region["entropy"].append(decision["entropy"])
                region["values"].append(decision["value_estimate"])
                for component, value in decision["reward_components"].items():
                    reward_components[component] += value
            for state in per_agent.values():
                count = max(1, len(state["entropy"]))
                state["mean_probabilities"] = [x / count for x in state.pop("probabilities")]
                state["mean_entropy"] = sum(state.pop("entropy")) / count
                state["mean_value_estimate"] = sum(state.pop("values")) / count
            decision_count = max(1, len(result["agent_decisions"]))
            reward_components = {name: value / decision_count for name, value in reward_components.items()}
            action_distribution = {
                "selected_action_counts": action_counts,
                "mean_masked_action_probabilities": {
                    action: probability_sums[index] / max(1, probability_count)
                    for index, action in enumerate(("defer", "execute_local",
                                                    "migrate_remote_1", "migrate_remote_2"))
                },
                "mean_entropy": sum(entropy_values) / max(1, len(entropy_values)),
                "per_agent": per_agent,
            }
            row = {"episode": episode, "seed": seed,
                   "reward": result["episode_reward"],
                   "carbon_gco2e": totals["carbon_gco2e"],
                   "energy_kwh": totals["energy_kwh"],
                   "mean_latency_seconds": totals["mean_latency_seconds"],
                   "sla_violations": totals["sla_violations"],
                   "completed": totals["completed"], "rejected": totals["rejected"],
                   "spt_overrides": totals["spt_overrides"],
                   "resolver_interventions": totals["resolver_interventions"],
                   "action_distribution": action_distribution,
                   "reward_component_means_per_decision": reward_components,
                   "agent_rewards": result["agent_rewards"],
                   "decision_trace": result["agent_decisions"],
                   "workload_seed": workload_seed, "updates": update_stats}
            log.write(json.dumps(row, sort_keys=True) + "\n"); log.flush()
            if episode % config["checkpoint_every"] == 0 or episode == episodes:
                torch.save({"episode": episode, "seed": seed, "config": config,
                            "agents": scheduler.checkpoint()},
                           checkpoint_dir / f"ippo_seed{seed}.pt")
            print(json.dumps({k: row[k] for k in ("episode", "reward", "carbon_gco2e",
                                                   "energy_kwh", "mean_latency_seconds",
                                                   "sla_violations", "completed")}))
    return scheduler, checkpoint_dir / f"ippo_seed{seed}.pt", log_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "training_config.yaml"))
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--workload-seed-base", type=int)
    parser.add_argument("--spt-probability", type=float)
    parser.add_argument("--carbon-weight", type=float)
    parser.add_argument("--lambda-latency", type=float)
    args = parser.parse_args()
    config = read_config(args.config)
    if args.spt_probability is not None:
        config["spt_intervention_probability"] = args.spt_probability
    if args.carbon_weight is not None:
        config["reward_carbon_weight"] = args.carbon_weight
    if args.lambda_latency is not None:
        config["lambda_latency"] = args.lambda_latency
    train(config, args.episodes, args.seed, args.output_dir, args.workload_seed_base)


if __name__ == "__main__":
    main()
