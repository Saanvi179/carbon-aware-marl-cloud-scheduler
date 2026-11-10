"""Episode-scaling IPPO study on expanded reproducible synthetic workloads."""
import argparse
import csv
import json
import random
import statistics
from pathlib import Path

import torch
import yaml

from experiments.train_ippo import ROOT, train, build_scheduler
from experiments.evaluate_baselines import make_environment
from environment.task_generator import generate_diverse_workload
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


def mean_ci(rows, metric, seed=9241, replicates=4000):
    values = [float(row[metric]) for row in rows]
    mean = statistics.mean(values) if values else 0.0
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    rng = random.Random(seed)
    policy_seeds = sorted({r["policy_seed"] for r in rows if r["policy_seed"] is not None})
    workloads = sorted({r["workload_seed"] for r in rows})
    samples = []
    if policy_seeds:
        matrix = {(r["policy_seed"], r["workload_seed"]): float(r[metric]) for r in rows}
        for _ in range(replicates):
            ps = [rng.choice(policy_seeds) for _ in policy_seeds]
            ws = [rng.choice(workloads) for _ in workloads]
            samples.append(statistics.mean(matrix[p, w] for p in ps for w in ws))
    else:
        by_workload = {r["workload_seed"]: float(r[metric]) for r in rows}
        for _ in range(replicates):
            samples.append(statistics.mean(by_workload[rng.choice(workloads)] for _ in workloads))
    samples.sort()
    return {"n": len(values), "mean": mean, "sd": sd,
            "ci95_low": samples[int(.025 * (len(samples) - 1))] if samples else mean,
            "ci95_high": samples[int(.975 * (len(samples) - 1))] if samples else mean,
            "ci_method": "crossed policy/workload percentile bootstrap" if policy_seeds
                         else "workload percentile bootstrap"}


def summarize_actions(decisions):
    counts = {name: 0 for name in ("defer", "execute_local", "migrate")}
    probs = [0.0] * 4
    entropies = []
    spt_count = resolver_count = forced_count = 0
    legal_counts = {str(i): 0 for i in range(1, 5)}
    for decision in decisions:
        key = decision["selected_action"]
        counts[key] = counts.get(key, 0) + 1
        for i, value in enumerate(decision["probabilities"]):
            probs[i] += value
        entropies.append(decision["entropy"])
        spt_count += int(decision["spt_override"])
        resolver_count += int(decision["resolver_intervention"])
        forced_count += int(decision["outcome"] == "forced_execute")
        legal_counts[str(sum(decision["mask"]))] += 1
    total = max(1, len(decisions))
    return {"decision_count": len(decisions), "selected_action_counts": counts,
            "selected_action_rates": {key: value / total for key, value in counts.items()},
            "mean_masked_probabilities": {
                name: probs[i] / total for i, name in enumerate(
                    ("defer", "execute_local", "migrate_remote_1", "migrate_remote_2"))},
            "mean_entropy": statistics.mean(entropies) if entropies else 0.0,
            "legal_action_count_distribution": legal_counts,
            "forced_execution_count": forced_count,
            "spt_override_rate": spt_count / total,
            "resolver_intervention_rate": resolver_count / total}


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_learning_curves(output, seed_logs, variants):
    records = []
    for variant in variants:
        for seed, path in seed_logs[variant].items():
            for row in read_jsonl(path):
                updates = row["updates"]
                if "actors" in updates:  # MAPPO: actors are independent; critic is centralized.
                    actor_values = list(updates["actors"].values())
                    critic_values = [updates["central_critic"]]
                else:
                    actor_values = critic_values = list(updates.values())
                actor_losses = [x["actor_loss"] for x in actor_values]
                critic_losses = [x["critic_loss"] for x in critic_values if "critic_loss" in x]
                entropy = [x["entropy"] for x in actor_values]
                records.append({"variant": variant, "seed": seed, "episode": row["episode"],
                                "reward": row["reward"], "carbon_gco2e": row["carbon_gco2e"],
                                "mean_policy_entropy": statistics.mean(entropy) if entropy else 0.0,
                                "actor_loss": statistics.mean(actor_losses) if actor_losses else 0.0,
                                "critic_loss": statistics.mean(critic_losses) if critic_losses else 0.0,
                                "action_distribution": row["action_distribution"]})
    csv_path = output / "learning_curves.csv"
    fields = ("variant", "seed", "episode", "reward", "carbon_gco2e", "mean_policy_entropy",
              "actor_loss", "critic_loss", "action_distribution")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "action_distribution": json.dumps(row["action_distribution"], sort_keys=True)})

    groups = sorted(variants)
    curve = {}
    for variant in groups:
        episodes = sorted({r["episode"] for r in records if r["variant"] == variant})
        curve[variant] = {}
        for episode in episodes:
            rows = [r for r in records if r["variant"] == variant and r["episode"] == episode]
            curve[variant][episode] = {metric: statistics.mean(r[metric] for r in rows)
                                       for metric in ("reward", "carbon_gco2e", "mean_policy_entropy")}
    (output / "learning_curves.json").write_text(json.dumps(curve, indent=2), encoding="utf-8")
    write_curve_svg(output / "learning_curves.svg", curve, groups)


def write_curve_svg(path, curves, variants):
    width, height = 960, 780
    panels = (("reward", "Mean training episode reward"),
              ("carbon_gco2e", "Training emissions (gCO2e)"),
              ("mean_policy_entropy", "Policy entropy (max ln(4) = 1.386"))
    colors = ("#1769aa", "#d1495b", "#2a9d8f", "#e9c46a", "#7b2cbf", "#f77f00")
    max_episode = max((max(values) for values in curves.values() if values), default=1)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Segoe UI,Arial,sans-serif;font-size:14px}.title{font-size:17px;font-weight:bold}</style>']
    for pi, (metric, title) in enumerate(panels):
        top = 25 + pi * 245
        left, chart_w, chart_h = 90, 790, 170
        vals = [values[metric] for variant in variants
                for values in curves[variant].values() if metric in values]
        lows, highs = min(vals), max(vals)
        pad = max((highs - lows) * .08, .02)
        lows, highs = lows - pad, highs + pad
        svg.append(f'<text x="{left}" y="{top}" class="title">{title}</text>')
        svg.append(f'<line x1="{left}" y1="{top+25}" x2="{left}" y2="{top+chart_h}" stroke="#555"/>')
        svg.append(f'<line x1="{left}" y1="{top+chart_h}" x2="{left+chart_w}" y2="{top+chart_h}" stroke="#555"/>')
        for vi, variant in enumerate(variants):
            items = sorted(curves[variant].items())
            coords = []
            for episode, vals_at_episode in items:
                x = left + chart_w * (episode - 1) / max(1, max_episode - 1)
                y = top + 25 + chart_h * (1 - (vals_at_episode[metric] - lows) / (highs - lows))
                coords.append(f"{x:.1f},{y:.1f}")
            svg.append(f'<polyline fill="none" stroke="{colors[vi]}" stroke-width="2" points="{" ".join(coords)}"/>')
            svg.append(f'<text x="{left+chart_w-150}" y="{top+42+vi*20}" fill="{colors[vi]}">{variant}</text>')
        svg.append(f'<text x="{left}" y="{top+chart_h+20}">Episode 1</text><text x="{left+chart_w-60}" y="{top+chart_h+20}">32</text>')
    svg.append('</svg>')
    path.write_text("\n".join(svg), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "phase24_training_config.yaml"))
    parser.add_argument("--seeds", default="7,19,42")
    parser.add_argument("--workload-seeds", default="9101,9102,9103,9104,9105,9106,9107,9108")
    parser.add_argument("--episode-counts", default="4,12,32")
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "phase24"))
    parser.add_argument("--skip-training", action="store_true",
                        help="reuse existing checkpoints/logs under the output directory")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    seeds = [int(x) for x in args.seeds.split(",")]
    workload_seeds = [int(x) for x in args.workload_seeds.split(",")]
    episode_counts = sorted({int(x) for x in args.episode_counts.split(",")})
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    variants = {"IPPO + SPT": {}, "IPPO no SPT": {"spt_intervention_probability": 0.0}}
    checkpoint_index = {}
    seed_logs = {name: {} for name in variants}
    for variant, override in variants.items():
        for episodes in episode_counts:
            for seed in seeds:
                run_dir = output / "training" / variant.replace(" ", "_") / f"episodes_{episodes:02d}" / f"seed_{seed}"
                checkpoint = run_dir / "checkpoints" / f"ippo_seed{seed}.pt"
                log = run_dir / f"training_seed{seed}.jsonl"
                if args.skip_training:
                    if not checkpoint.exists() or not log.exists():
                        raise FileNotFoundError(f"missing reusable checkpoint/log in {run_dir}")
                else:
                    _, checkpoint, log = train({**config, **override}, episodes, seed, run_dir)
                checkpoint_index[(variant, episodes, seed)] = checkpoint
                if episodes == max(episode_counts):
                    seed_logs[variant][seed] = log

    rows = []
    for workload_seed in workload_seeds:
        workload = generate_diverse_workload(workload_seed, config["tasks_per_episode"])
        for name, scheduler in (("FCFS", FCFSScheduler()),
                                ("Greedy carbon", GreedyCarbonScheduler())):
            result = make_environment().run(workload, scheduler)
            rows.append({"policy": name, "training_episodes": None, "policy_seed": None,
                         "workload_seed": workload_seed, **result["totals"]})
        for variant in variants:
            for episodes in episode_counts:
                for seed in seeds:
                    scheduler = build_scheduler({**config, **variants[variant]}, seed, deterministic=True)
                    state = torch.load(checkpoint_index[(variant, episodes, seed)],
                                       map_location="cpu", weights_only=False)
                    scheduler.load_checkpoint(state["agents"])
                    result = make_environment().run(workload, scheduler)
                    rows.append({"policy": variant, "training_episodes": episodes, "policy_seed": seed,
                                 "workload_seed": workload_seed, **result["totals"],
                                 "action_distribution": summarize_actions(result["agent_decisions"]),
                                 "agent_rewards": result.get("agent_rewards")})

    metrics = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
               "sla_violations", "mean_latency_seconds")
    summary = {}
    for policy in ("FCFS", "Greedy carbon"):
        group = [r for r in rows if r["policy"] == policy]
        summary[policy] = {m: mean_ci(group, m, 9241 + i) for i, m in enumerate(metrics)}
    for variant in variants:
        greedy_workloads = {r["workload_seed"]: r for r in rows if r["policy"] == "Greedy carbon"}
        for episodes in episode_counts:
            group = [r for r in rows if r["policy"] == variant and r["training_episodes"] == episodes]
            key = f"{variant} ({episodes} episodes)"
            summary[key] = {m: mean_ci(group, m, 9241 + i) for i, m in enumerate(metrics)}
            summary[key]["action_distribution"] = {
                    "selected_actions": {action: sum(row["action_distribution"]["selected_action_counts"][action]
                        for row in group) for action in ("defer", "execute_local", "migrate")},
                    "mean_masked_probabilities": {action: statistics.mean(
                        row["action_distribution"]["mean_masked_probabilities"][action] for row in group)
                        for action in ("defer", "execute_local", "migrate_remote_1", "migrate_remote_2")},
                    "mean_entropy": statistics.mean(row["action_distribution"]["mean_entropy"] for row in group),
                    "legal_action_count_distribution": {str(n): sum(
                        row["action_distribution"]["legal_action_count_distribution"][str(n)]
                        for row in group) for n in range(1, 5)},
                    "forced_execution_count": sum(row["action_distribution"]["forced_execution_count"]
                                                   for row in group),
                    "spt_override_rate": statistics.mean(row["action_distribution"]["spt_override_rate"] for row in group),
                    "resolver_intervention_rate": statistics.mean(row["action_distribution"]["resolver_intervention_rate"] for row in group)}
            paired = []
            for row in group:
                baseline = greedy_workloads[row["workload_seed"]]
                paired.append({"policy_seed": row["policy_seed"], "workload_seed": row["workload_seed"],
                               "carbon_delta": row["carbon_gco2e"] - baseline["carbon_gco2e"],
                               "completion_delta": row["completion_rate"] - baseline["completion_rate"],
                               "sla_delta": row["sla_violations"] - baseline["sla_violations"]})
            summary[key]["paired_delta_vs_greedy"] = {
                metric: mean_ci(paired, metric, 9641 + i)
                for i, metric in enumerate(("carbon_delta", "completion_delta", "sla_delta"))}
    result_obj = {"training_seeds": seeds, "heldout_workload_seeds": workload_seeds,
                  "episode_counts": episode_counts, "tasks_per_episode": config["tasks_per_episode"],
                  "workload_profile": config["workload_profile"], "settings": config,
                  "summary": summary, "runs": rows}
    (output / "phase24_evaluation.json").write_text(json.dumps(result_obj, indent=2), encoding="utf-8")
    with (output / "phase24_evaluation.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    write_learning_curves(output, seed_logs, variants)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
