"""Versioned two-method A-MARL-derived IPPO research comparison.

Validation selects the proposed method's latency allowance; held-out test data
are evaluated only once after selection. Historical results are never written.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

import torch
import yaml

from environment.task_generator import (generate_variable_workload,
                                        generate_diverse_workload,
                                        generate_phase25_workload)
from experiments.evaluate_baselines import make_phase25_environment
from experiments.train_ippo import ROOT, train, build_scheduler


METHODS = ("A-MARL-derived IPPO", "Proposed Carbon-Aware SPT")
METRICS = ("carbon_gco2e", "carbon_gco2e_per_completed", "energy_kwh",
           "completion_rate", "rejection_rate", "sla_violations",
           "mean_latency_seconds", "deferrals", "spt_interventions")
GENERATORS = {"variable": generate_variable_workload,
              "diverse": generate_diverse_workload,
              "bursty": generate_phase25_workload}


def make_workload(family: str, seed: int, count: int):
    return GENERATORS[family](seed, count)


def method_config(common, method, allowance):
    config = dict(common)
    config["algorithm"] = "ippo"
    config["spt_intervention_probability"] = 1.0
    if method == METHODS[0]:
        config.pop("spt_method", None)
    else:
        config["spt_method"] = "carbon_latency_bounded"
        config["spt_latency_allowance_fraction"] = float(allowance)
    return config


def evaluate(checkpoint, config, workload, policy_seed):
    env = make_phase25_environment(dynamic_carbon=True, profile_slots=512)
    scheduler = build_scheduler(config, policy_seed, deterministic=True)
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    scheduler.load_checkpoint(state["agents"])
    result = env.run(workload, scheduler)
    totals = result["totals"]
    deferred = sum(record["action"] == "defer" for record in result["records"])
    completed = totals["completed"]
    return {"policy_seed": policy_seed, **totals,
            "carbon_gco2e_per_completed": totals["carbon_gco2e"] / completed if completed else None,
            "deferrals": deferred,
            # Inference is deterministic and the source A-MARL method uses SPT
            # as a training exploration intervention. Report zero explicitly.
            "spt_interventions": totals.get("spt_overrides", 0),
            "spt_intervention_rate": 0.0,
            "decisions": result["records"],
            "agent_decisions": result.get("agent_decisions", [])}


def bootstrap_mean(values, seed, replicates):
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return {"n": 0, "mean": None, "sd": None, "ci95": [None, None]}
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(clean, k=len(clean))) for _ in range(replicates))
    return {"n": len(clean), "mean": statistics.mean(clean),
            "sd": statistics.stdev(clean) if len(clean) > 1 else 0.0,
            "ci95": [samples[int(.025 * (replicates - 1))],
                     samples[int(.975 * (replicates - 1))]],
            "ci_method": "percentile bootstrap"}


def crossed_summary(rows, value, seed, replicates):
    """Bootstrap independent policy seeds and workload instances as crossed factors."""
    matrix = {(r["policy_seed"], r["workload_id"]): r[value] for r in rows
              if r.get(value) is not None}
    policy_seeds = sorted({key[0] for key in matrix})
    workloads = sorted({key[1] for key in matrix})
    if not policy_seeds or not workloads:
        return bootstrap_mean([], seed, replicates)
    complete_seeds = [p for p in policy_seeds if all((p, w) in matrix for w in workloads)]
    complete_workloads = [w for w in workloads if all((p, w) in matrix for p in complete_seeds)]
    if not complete_seeds or not complete_workloads:
        return bootstrap_mean([r[value] for r in rows if r.get(value) is not None], seed, replicates)
    flat = [matrix[p, w] for p in complete_seeds for w in complete_workloads]
    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        ps = rng.choices(complete_seeds, k=len(complete_seeds))
        ws = rng.choices(complete_workloads, k=len(complete_workloads))
        samples.append(statistics.mean(matrix[p, w] for p in ps for w in ws))
    samples.sort()
    return {"n": len(flat), "mean": statistics.mean(flat),
            "sd": statistics.stdev(flat) if len(flat) > 1 else 0.0,
            "ci95": [samples[int(.025 * (replicates - 1))],
                     samples[int(.975 * (replicates - 1))]],
            "ci_method": "crossed policy-seed/workload percentile bootstrap"}


def aggregate(rows, replicates, seed_offset=0):
    summary = {}
    for method in METHODS:
        group = [r for r in rows if r["method"] == method]
        summary[method] = {metric: crossed_summary(group, metric, seed_offset + i, replicates)
                           for i, metric in enumerate(METRICS)}
    paired = {}
    for family in sorted({r["family"] for r in rows} | {"all"}):
        subset = rows if family == "all" else [r for r in rows if r["family"] == family]
        index = {(r["method"], r["policy_seed"], r["workload_id"]): r for r in subset}
        diffs = []
        for policy_seed, workload_id in sorted({(r["policy_seed"], r["workload_id"])
                                                 for r in subset}):
            base = index.get((METHODS[0], policy_seed, workload_id))
            prop = index.get((METHODS[1], policy_seed, workload_id))
            if base and prop:
                delta = {"policy_seed": policy_seed, "workload_id": workload_id}
                for metric in METRICS:
                    a, b = prop.get(metric), base.get(metric)
                    delta[metric] = (a - b if a is not None and b is not None else None)
                diffs.append(delta)
        paired[family] = {metric: crossed_summary(diffs, metric, seed_offset + 100 + i, replicates)
                          for i, metric in enumerate(METRICS)}
    return {"per_method": summary, "paired_proposed_minus_base": paired}


def training_diagnostics(log_paths):
    episodes, overrides, decisions = [], 0, 0
    for path in log_paths:
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                episodes.append({"seed": row["seed"], "episode": row["episode"],
                                 "episode_reward": row["reward"],
                                 "carbon_gco2e": row["carbon_gco2e"],
                                 "completion_rate": row["completed"] / max(1, row["completed"] + row["rejected"]),
                                 "spt_interventions": row["spt_overrides"]})
                overrides += row["spt_overrides"]
                decisions += sum(row["action_distribution"]["selected_action_counts"].values())
    by_seed = {}
    for row in episodes:
        by_seed.setdefault(row["seed"], []).append(row)
    convergence = {}
    for seed, curve in by_seed.items():
        curve.sort(key=lambda x: x["episode"])
        width = min(5, max(1, len(curve) // 3))
        convergence[str(seed)] = {
            "episodes": len(curve),
            "initial_window_mean_reward": statistics.mean(x["episode_reward"] for x in curve[:width]),
            "final_window_mean_reward": statistics.mean(x["episode_reward"] for x in curve[-width:]),
            "reward_by_episode": [x["episode_reward"] for x in curve],
            "convergence_claim": "not inferred from this finite learning curve"}
    return {"episodes": episodes, "by_seed": convergence,
            "training_spt_interventions": overrides,
            "training_decisions": decisions,
            "training_spt_intervention_rate": overrides / decisions if decisions else 0.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/research_alignment_v1.yaml"))
    parser.add_argument("--output-dir", default=str(ROOT / "results/research_alignment_v1"))
    parser.add_argument("--smoke", action="store_true", help="one-seed short pipeline; not benchmark evidence")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing results: {output}")
    output.mkdir(parents=True, exist_ok=True)
    seeds = [7] if args.smoke else config["training_seeds"]
    episodes = 1 if args.smoke else config["episodes"]
    validation_seeds = config["validation_seeds"][:1] if args.smoke else config["validation_seeds"]
    test_seeds = config["test_seeds"][:1] if args.smoke else config["test_seeds"]
    allowances = [0.0, 0.10] if args.smoke else config["allowance_candidates"]
    families = config["workload_families"]
    count = config["tasks_per_episode"]
    common = {k: v for k, v in config.items() if k not in {
        "training_seeds", "validation_seeds", "test_seeds", "workload_families",
        "allowance_candidates", "bootstrap_replicates"}}

    # Train base once; train each candidate on identical per-seed episode workloads.
    checkpoints, logs, validation_rows = {}, {}, []
    for method in METHODS:
        candidate_values = [None] if method == METHODS[0] else allowances
        for allowance in candidate_values:
            key = (method, allowance)
            checkpoints[key], logs[key] = {}, []
            for seed in seeds:
                label = "base" if allowance is None else f"proposed_eps_{allowance:.3f}"
                train_dir = output / "training" / label / f"seed_{seed}"
                cfg = method_config(common, method, allowance)
                _, checkpoint, log_path = train(cfg, episodes, seed, train_dir)
                checkpoints[key][seed] = checkpoint
                logs[key].append(log_path)
            # Validation is isolated from training and final test workload seeds.
            for family in families:
                for validation_seed in validation_seeds:
                    workload = make_workload(family, validation_seed, count)
                    workload_id = f"{family}:{validation_seed}"
                    for seed in seeds:
                        row = evaluate(checkpoints[key][seed], method_config(common, method, allowance),
                                       workload, seed)
                        validation_rows.append({k: v for k, v in row.items()
                                                if k not in ("decisions", "agent_decisions")}
                                               | {"method": method, "allowance": allowance,
                                                  "family": family, "workload_id": workload_id})

    # Select only from validation: minimize mean emissions per completed task.
    proposed_validation = [r for r in validation_rows if r["method"] == METHODS[1]]
    validation_scores = {}
    for allowance in allowances:
        vals = [r["carbon_gco2e_per_completed"] for r in proposed_validation
                if r["allowance"] == allowance and r["carbon_gco2e_per_completed"] is not None]
        validation_scores[str(allowance)] = statistics.mean(vals) if vals else float("inf")
    selected_allowance = min(allowances, key=lambda a: (validation_scores[str(a)], a))
    selected_key = (METHODS[1], selected_allowance)

    # Held-out test workloads are first evaluated after the allowance is frozen.
    test_rows = []
    for family in families:
        for test_seed in test_seeds:
            workload = make_workload(family, test_seed, count)
            workload_id = f"{family}:{test_seed}"
            for method, allowance in ((METHODS[0], None), (METHODS[1], selected_allowance)):
                key = (method, allowance)
                for seed in seeds:
                    row = evaluate(checkpoints[key][seed], method_config(common, method, allowance),
                                   workload, seed)
                    test_rows.append({k: v for k, v in row.items()
                                      if k not in ("decisions", "agent_decisions")}
                                     | {"method": method, "allowance": allowance,
                                        "family": family, "workload_seed": test_seed,
                                        "workload_id": workload_id})

    # Store training curves/override rates for the two final configurations only.
    selected_logs = {METHODS[0]: training_diagnostics(logs[(METHODS[0], None)]),
                     METHODS[1]: training_diagnostics(logs[selected_key])}
    validation_payload = {"candidate_mean_carbon_per_completed": validation_scores,
                          "selected_allowance_fraction": selected_allowance,
                          "selection_rule": "minimum validation mean gCO2e per completed task; lower allowance breaks ties",
                          "rows": validation_rows}
    replicates = 500 if args.smoke else config["bootstrap_replicates"]
    summary = aggregate(test_rows, replicates, seed_offset=88000)
    payload = {
        "study": "Research alignment v1: A-MARL-derived IPPO vs Carbon-Aware, Latency-Bounded Entropy-Guided SPT",
        "status": "smoke_not_benchmark" if args.smoke else "held_out_test_complete",
        "command": "python -m experiments.run_research_alignment" +
                   (" --smoke --output-dir " + str(output) if args.smoke else ""),
        "config": config, "training_seeds": seeds, "episodes_per_seed": episodes,
        "validation": validation_payload, "training_diagnostics": selected_logs,
        "summary": summary, "test_runs": test_rows,
        "protocol": {"families": families, "validation_seeds": validation_seeds,
                     "test_seeds": test_seeds,
                     "carbon_profiles": "identical deterministic synthetic 512-slot profile per matched run",
                     "paired_unit": "training seed × workload family/seed",
                     "final_test_used_for_tuning": False,
                     "greedy_role": "auxiliary only; excluded from primary comparison"}}
    (output / "research_alignment_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output / "validation_selection.json").write_text(json.dumps(validation_payload, indent=2), encoding="utf-8")
    (output / "test_runs.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in test_rows), encoding="utf-8")
    (output / "training_diagnostics.json").write_text(json.dumps(selected_logs, indent=2), encoding="utf-8")
    # The UI reads the exact selected policy checkpoints and frozen allowance here.
    ui_index = {"selected_allowance_fraction": selected_allowance,
                "base_checkpoints": {str(seed): str(path.resolve()) for seed, path in checkpoints[(METHODS[0], None)].items()},
                "proposed_checkpoints": {str(seed): str(path.resolve()) for seed, path in checkpoints[selected_key].items()},
                "default_seed": seeds[0], "config": common,
                "training_diagnostics": selected_logs}
    (output / "ui_policy_index.json").write_text(json.dumps(ui_index, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "selected_allowance_fraction": selected_allowance,
                      "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
