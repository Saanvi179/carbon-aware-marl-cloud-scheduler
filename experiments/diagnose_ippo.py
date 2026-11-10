"""Read-only policy diagnostics over reproducible synthetic workload variations."""
import argparse
import csv
import json
import random
from dataclasses import replace
from pathlib import Path

import torch
import yaml

from agents.ippo_agent import IPPOScheduler
from experiments.train_ippo import ROOT, build_scheduler
from experiments.evaluate_baselines import make_environment
from environment.task_generator import synthetic_workload, generate_variable_workload
from schedulers.greedy_carbon import GreedyCarbonScheduler


class CapturingIPPOScheduler(IPPOScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_proposals = {}
        self.decisions = []

    def propose(self, observation, candidates, region_names):
        proposal = super().propose(observation, candidates, region_names)
        agent = self.agents[proposal.agent_region]
        with torch.no_grad():
            dist = agent.masked_distribution(agent.actor(torch.tensor(proposal.observation)), proposal.mask)
            probabilities = [round(float(value), 6) for value in dist.probs.tolist()]
        self.current_proposals.setdefault(observation.task.task_id, []).append({
            "agent": proposal.agent_region, "action": proposal.action.value,
            "target": proposal.target_region, "action_index": proposal.action_index,
            "mask": list(proposal.mask), "probabilities": probabilities,
            "entropy": round(proposal.entropy, 6), "policy_valid": proposal.policy_valid,
        })
        return proposal

    def resolve(self, task, proposals, candidates, region_names, force=False):
        chosen = super().resolve(task, proposals, candidates, region_names, force)
        offered = set()
        for proposal in proposals:
            if proposal.action.value == "execute_local":
                offered.add(proposal.agent_region)
            elif proposal.action.value == "migrate" and proposal.target_region:
                offered.add(proposal.target_region)
        self.decisions.append({
            "task_id": task.task_id,
            "proposals": self.current_proposals.pop(task.task_id, []),
            "candidates": [{"region": c["region"], "carbon_gco2e": round(c["carbon"], 6),
                            "energy_kwh": round(c["energy"], 8),
                            "execution_seconds": round(c["execution"], 4),
                            "migration_seconds": round(c["migration"], 4)} for c in candidates],
            "offered_destinations": sorted(offered),
            "all_feasible_min_carbon_region": min(candidates, key=lambda c: c["carbon"])["region"] if candidates else None,
            "selected_region": chosen["region"] if chosen else None,
        })
        return chosen


def varied_synthetic_workload(seed):
    """Create deterministic, explicitly synthetic held-out variants of the six-task example."""
    if seed == 0:
        return synthetic_workload()
    rng = random.Random(seed)
    varied = []
    for task in synthetic_workload():
        arrival = task.arrival_slot + rng.choice((0, 1, 2))
        runtime = round(task.runtime_seconds * rng.uniform(0.75, 1.35), 2)
        dataset = round(task.dataset_gb * rng.uniform(0.6, 1.4), 4)
        deadline = max(task.deadline_seconds + (arrival - task.arrival_slot) * 60,
                       arrival * 60 + runtime + 360)
        varied.append(replace(task, arrival_slot=arrival, runtime_seconds=runtime,
                              dataset_gb=dataset, deadline_seconds=deadline))
    return varied


def final_task_choices(result):
    final = {}
    for row in result["records"]:
        final[row["task_id"]] = row.get("region") if row["action"] in ("execute_local", "migrate") else row["action"]
    return final


def load_capture(config, checkpoint_path, seed):
    scheduler = build_scheduler(config, seed, deterministic=True)
    scheduler.__class__ = CapturingIPPOScheduler
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    scheduler.load_checkpoint(state["agents"])
    scheduler.current_proposals = {}
    scheduler.decisions = []
    return scheduler


def decision_diagnostics(config, checkpoints, workload_seeds):
    rows, run_summaries = [], []
    for policy_seed, checkpoint in checkpoints.items():
        for workload_seed in workload_seeds:
            workload = generate_variable_workload(workload_seed, config["tasks_per_episode"])
            greedy_result = make_environment().run(workload, GreedyCarbonScheduler())
            scheduler = load_capture(config, checkpoint, policy_seed)
            ippo_result = make_environment().run(workload, scheduler)
            greedy, ippo = final_task_choices(greedy_result), final_task_choices(ippo_result)
            matches = [greedy.get(t.task_id) == ippo.get(t.task_id) for t in workload]
            run_summaries.append({"policy_seed": policy_seed, "workload_seed": workload_seed,
                                  "decision_match_rate": sum(matches) / len(matches),
                                  "greedy": greedy_result["totals"], "ippo": ippo_result["totals"]})
            for task in workload:
                rows.append({"policy_seed": policy_seed, "workload_seed": workload_seed,
                             "task_id": task.task_id, "greedy_decision": greedy.get(task.task_id),
                             "ippo_decision": ippo.get(task.task_id),
                             "match": greedy.get(task.task_id) == ippo.get(task.task_id),
                             "ippo_decision_trace": [d for d in scheduler.decisions
                                                      if d["task_id"] == task.task_id]})
    return rows, run_summaries


def training_curve_summary(training_logs):
    summary, curves = [], []
    for seed, path in training_logs.items():
        episodes = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
        actor = [r["updates"][region]["actor_loss"] for r in episodes for region in r["updates"]]
        critic = [r["updates"][region]["critic_loss"] for r in episodes for region in r["updates"]]
        entropy = [r["updates"][region]["entropy"] for r in episodes for region in r["updates"]]
        summary.append({"seed": int(seed), "episodes": len(episodes),
                        "mean_actor_loss": sum(actor) / len(actor),
                        "mean_critic_loss": sum(critic) / len(critic),
                        "mean_policy_entropy": sum(entropy) / len(entropy),
                        "mean_spt_overrides": sum(r["spt_overrides"] for r in episodes) / len(episodes),
                        "nonzero_actor_updates": sum(abs(x) > 1e-10 for x in actor),
                        "actor_update_count": len(actor)})
        for row in episodes:
            curves.append({"seed": int(seed), "episode": row["episode"],
                           "actor_loss": sum(v["actor_loss"] for v in row["updates"].values()) / len(row["updates"]),
                           "critic_loss": sum(v["critic_loss"] for v in row["updates"].values()) / len(row["updates"]),
                           "policy_entropy": sum(v["entropy"] for v in row["updates"].values()) / len(row["updates"]),
                           "spt_overrides": row["spt_overrides"], "reward": row["reward"]})
    return summary, curves


def proposal_summary(task_rows):
    proposals = [p for row in task_rows for trace in row["ippo_decision_trace"] for p in trace["proposals"]]
    decisions = [trace for row in task_rows for trace in row["ippo_decision_trace"]]
    counts, probability_sums, mask_counts = {}, [0.0] * 4, [0] * 4
    for proposal in proposals:
        key = proposal["action"] + (":" + proposal["target"] if proposal["target"] else "")
        counts[key] = counts.get(key, 0) + 1
        for i, (probability, legal) in enumerate(zip(proposal["probabilities"], proposal["mask"])):
            probability_sums[i] += probability
            mask_counts[i] += int(legal)
    n = max(1, len(proposals))
    selected_global_min = [d["selected_region"] == d["all_feasible_min_carbon_region"]
                          for d in decisions if d["selected_region"]]
    return {"proposal_count": len(proposals), "action_counts": counts,
            "mean_action_probabilities_by_index": [round(x / n, 6) for x in probability_sums],
            "legal_action_rate_by_index": [round(x / n, 6) for x in mask_counts],
            "mean_policy_entropy": round(sum(p["entropy"] for p in proposals) / n, 6),
            "policy_valid_fraction": round(sum(p["policy_valid"] for p in proposals) / n, 6),
            "decision_event_count": len(decisions),
            "all_agents_deferred_fraction": round(sum(not d["offered_destinations"] for d in decisions) /
                                                    max(1, len(decisions)), 6),
            "mean_offered_destinations": round(sum(len(d["offered_destinations"]) for d in decisions) /
                                               max(1, len(decisions)), 6),
            "resolver_selected_global_min_carbon_fraction": round(sum(selected_global_min) /
                                                                   max(1, len(selected_global_min)), 6)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "training_config.yaml"))
    parser.add_argument("--variant", default="ippo_spt_full_reward")
    parser.add_argument("--workload-seeds", default="901,902,903,904,905")
    parser.add_argument("--policy-seeds", default="7,19,42")
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase22" / "diagnostics"))
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    seeds = [int(item) for item in args.policy_seeds.split(",")]
    checkpoints = {seed: ROOT / "results" / "phase22" / args.variant / f"seed{seed}" /
                   "checkpoints" / f"ippo_seed{seed}.pt"
                   for seed in seeds}
    for seed, checkpoint in checkpoints.items():
        if not checkpoint.exists():
            raise FileNotFoundError(f"Train policy seed {seed} first; expected {checkpoint}")
    logs = {seed: ROOT / "results" / "phase22" / args.variant / f"seed{seed}" /
            f"training_seed{seed}.jsonl"
            for seed in seeds}
    workload_seeds = [int(x) for x in args.workload_seeds.split(",")]
    task_rows, workload_results = decision_diagnostics(config, checkpoints, workload_seeds)
    curve_summary, curves = training_curve_summary(logs)
    result = {"variant": args.variant, "workload_seeds": workload_seeds,
              "policy_seeds": seeds,
              "decision_comparison": task_rows,
              "workload_results": workload_results,
              "proposal_summary": proposal_summary(task_rows),
              "training_curve_summary": curve_summary}
    matches = [r["match"] for r in task_rows]
    result["aggregate"] = {"task_decisions_compared": len(matches),
                           "greedy_decision_match_rate": sum(matches) / len(matches) if matches else None}
    path = output / "ippo_diagnostics.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    with (output / "training_curves.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(curves[0]))
        writer.writeheader(); writer.writerows(curves)
    with (output / "training_curve_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result["training_curve_summary"][0]))
        writer.writeheader(); writer.writerows(result["training_curve_summary"])
    print(json.dumps(result["aggregate"], indent=2))
    print(json.dumps(result["training_curve_summary"], indent=2))


if __name__ == "__main__":
    main()
