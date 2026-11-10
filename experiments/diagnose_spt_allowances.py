"""Validation-only matched replay of entropy-guided SPT allowance rules.

Loads the already-trained proposed-epsilon-zero IPPO checkpoints and evaluates
the same weights with the A-MARL-derived fastest-execution SPT rule and each
carbon/latency allowance. No training or held-out workload is used.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml

from agents.ippo_agent import IPPOScheduler, CarbonAwareSPTIPPOScheduler
from environment.task_generator import (generate_variable_workload,
                                        generate_diverse_workload,
                                        generate_phase25_workload)
from experiments.evaluate_baselines import make_phase25_environment
from experiments.train_ippo import ROOT, build_scheduler


FAMILIES = {"variable": generate_variable_workload,
            "diverse": generate_diverse_workload,
            "bursty": generate_phase25_workload}
ALLOWANCES = (0.0, 0.05, 0.10, 0.20)
BASE = "A-MARL-derived SPT (fastest execution)"


class TracedIPPO(IPPOScheduler):
    def __init__(self, *args, condition, **kwargs):
        super().__init__(*args, **kwargs)
        self.condition = condition
        self.decision_trace = []

    def propose(self, observation, candidates, region_names):
        proposal = super().propose(observation, candidates, region_names)
        self.decision_trace.append(self._trace_record(observation, candidates, proposal))
        return proposal

    def _trace_record(self, observation, candidates, proposal):
        return {
            "task_id": observation.task.task_id,
            "slot": observation.slot,
            "agent_region": observation.region,
            "condition": self.condition,
            "entropy": proposal.entropy,
            "entropy_threshold": self.config["spt_entropy_fraction"]
                * math.log(max(1, sum(proposal.mask))),
            "intervention": not proposal.policy_valid,
            "proposal_action": proposal.action.value,
            "proposal_target": proposal.target_region,
            "selected_spt_destination": ((proposal.target_region or observation.region)
                                         if not proposal.policy_valid else None),
            "feasible_candidates": [
                {"region": c["region"],
                 "estimated_carbon_gco2e": c["carbon"],
                 "estimated_energy_kwh": c["energy"],
                 "estimated_migration_seconds": c["migration"],
                 "estimated_execution_seconds": c["execution"],
                 "estimated_latency_seconds": c["migration"] + c["execution"],
                 "deadline_finish_seconds": c["end"]}
                for c in candidates],
        }


class TracedCarbonSPT(CarbonAwareSPTIPPOScheduler):
    def __init__(self, *args, condition, **kwargs):
        super().__init__(*args, **kwargs)
        self.condition = condition
        self.decision_trace = []

    def propose(self, observation, candidates, region_names):
        proposal = super().propose(observation, candidates, region_names)
        self.decision_trace.append({
            "task_id": observation.task.task_id,
            "slot": observation.slot,
            "agent_region": observation.region,
            "condition": self.condition,
            "entropy": proposal.entropy,
            "entropy_threshold": self.config["spt_entropy_fraction"]
                * math.log(max(1, sum(proposal.mask))),
            "intervention": not proposal.policy_valid,
            "proposal_action": proposal.action.value,
            "proposal_target": proposal.target_region,
            "selected_spt_destination": ((proposal.target_region or observation.region)
                                         if not proposal.policy_valid else None),
            "feasible_candidates": [
                {"region": c["region"],
                 "estimated_carbon_gco2e": c["carbon"],
                 "estimated_energy_kwh": c["energy"],
                 "estimated_migration_seconds": c["migration"],
                 "estimated_execution_seconds": c["execution"],
                 "estimated_latency_seconds": c["migration"] + c["execution"],
                 "deadline_finish_seconds": c["end"]}
                for c in candidates],
        })
        return proposal


def _checkpoint(index, seed):
    path = Path(index["proposed_checkpoints"][str(seed)])
    if not path.is_file():
        raise FileNotFoundError(f"Required existing checkpoint not found: {path}")
    return path


def _condition_configs(common, allowance):
    config = dict(common)
    config["algorithm"] = "ippo"
    config["spt_intervention_probability"] = 1.0
    if allowance is None:
        config.pop("spt_method", None)
        return config
    config["spt_method"] = "carbon_latency_bounded"
    config["spt_latency_allowance_fraction"] = allowance
    return config


def run_one(index, common, family, workload_seed, policy_seed, label, allowance):
    workload = FAMILIES[family](workload_seed, common["tasks_per_episode"])
    config = _condition_configs(common, allowance)
    env = make_phase25_environment(dynamic_carbon=True, profile_slots=512)
    scheduler_type = TracedIPPO if allowance is None else TracedCarbonSPT
    # Reinitialize each condition's sampler from the same seed. Checkpoint load
    # then replaces weights while preserving matched stochastic action draws.
    random.seed(policy_seed)
    torch.manual_seed(policy_seed)
    scheduler = scheduler_type(env.region_names,
        {name: (r.resources.gpus, r.resources.cpu_cores, r.resources.memory_gb)
         for name, r in env.regions.items()}, config, policy_seed,
        deterministic=False, condition=label)
    state = torch.load(_checkpoint(index, policy_seed), map_location="cpu", weights_only=False)
    scheduler.load_checkpoint(state["agents"])
    result = env.run(workload, scheduler)
    totals = result["totals"]
    trace = scheduler.decision_trace
    interventions = [d for d in trace if d["intervention"]]
    selected = {d["task_id"]: d["selected_spt_destination"] for d in trace
                if d.get("intervention")}
    # Attach selected per-task simulated outcome to every matching decision
    # record, retaining the episode totals as the authoritative integrated CO2.
    outcomes = {r["task_id"]: r for r in result["records"]
                if r.get("action") in ("execute_local", "migrate")}
    for decision in trace:
        outcome = outcomes.get(decision["task_id"])
        decision["actual_selected_destination"] = outcome.get("region") if outcome else None
        decision["selected_record_marginal_carbon_estimate_gco2e"] = (
            outcome.get("carbon_gco2e") if outcome else None)
        decision["selected_record_latency_seconds"] = (
            outcome.get("latency_seconds") if outcome else None)
    n_tasks = len(workload)
    completed = totals["completed"]
    row = {"condition": label, "allowance_fraction": allowance,
           "family": family, "workload_seed": workload_seed,
           "workload_id": f"{family}:{workload_seed}", "policy_seed": policy_seed,
           "tasks": n_tasks, "carbon_gco2e": totals["carbon_gco2e"],
           "carbon_gco2e_per_completed": totals["carbon_gco2e"] / completed if completed else None,
           "energy_kwh": totals["energy_kwh"], "completed": completed,
           "completion_rate": totals["completion_rate"], "rejected": totals["rejected"],
           "rejection_rate": totals["rejection_rate"],
           "sla_violations": totals["sla_violations"],
           "mean_latency_seconds": totals["mean_latency_seconds"],
           "total_latency_seconds": totals["total_latency_seconds"],
           "deferrals": sum(r["action"] == "defer" for r in result["records"]),
           "intervention_count": len(interventions),
           "decision_count": len(trace),
           "intervention_rate": len(interventions) / max(1, len(trace)),
           "intervention_multicandidate_count": sum(len(d["feasible_candidates"]) > 1 for d in interventions),
           "decision_trace": trace,
           "task_outcomes": result["records"],
           "actual_integrated_region_emissions_gco2e": totals["carbon_gco2e"]}
    return row


def crossed_bootstrap(rows, metric, rng, replicates=10000):
    matrix = {(r["policy_seed"], r["workload_id"]): r.get(metric) for r in rows}
    ps, ws = sorted({k[0] for k in matrix}), sorted({k[1] for k in matrix})
    if not ps or not ws or any(matrix.get((p, w)) is None for p in ps for w in ws):
        return {"n_pairs": len([v for v in matrix.values() if v is not None]),
                "mean": None, "ci95": [None, None], "method": "crossed bootstrap unavailable: incomplete pairs"}
    vals = [matrix[p, w] for p in ps for w in ws]
    samples = []
    for _ in range(replicates):
        pdraw = rng.choices(ps, k=len(ps))
        wdraw = rng.choices(ws, k=len(ws))
        samples.append(statistics.mean(matrix[p, w] for p in pdraw for w in wdraw))
    samples.sort()
    return {"n_pairs": len(vals), "mean": statistics.mean(vals),
            "ci95": [samples[int(.025 * (replicates - 1))], samples[int(.975 * (replicates - 1))]],
            "method": "two-factor crossed percentile bootstrap over policy seeds and validation workloads"}


def summaries(rows, comparison_labels, replicates):
    metrics = ("carbon_gco2e", "carbon_gco2e_per_completed", "energy_kwh",
               "completion_rate", "rejection_rate", "sla_violations",
               "mean_latency_seconds", "deferrals", "intervention_rate")
    output = {"by_condition": {}, "paired_differences_vs_base": {}}
    baseline = [r for r in rows if r["condition"] == BASE]
    for label in comparison_labels:
        group = [r for r in rows if r["condition"] == label]
        output["by_condition"][label] = {
            metric: crossed_bootstrap(group, metric, random.Random(60100 + i), replicates)
            for i, metric in enumerate(metrics)}
        base_ix = {(r["policy_seed"], r["workload_id"]): r for r in baseline}
        diffs = []
        for row in group:
            b = base_ix[(row["policy_seed"], row["workload_id"])]
            diff = dict(row)
            for metric in metrics:
                a, bv = row.get(metric), b.get(metric)
                diff[metric] = a - bv if a is not None and bv is not None else None
            diffs.append(diff)
        output["paired_differences_vs_base"][label] = {
            metric: crossed_bootstrap(diffs, metric, random.Random(60200 + i), replicates)
            for i, metric in enumerate(metrics)}
    return output


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/research_alignment_v1.yaml"))
    parser.add_argument("--policy-index", default=str(ROOT / "results/research_alignment_v1/ui_policy_index.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "results/research_alignment_v2_validation_spt_diagnostic"))
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    args = parser.parse_args()
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output}")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    index = json.loads(Path(args.policy_index).read_text(encoding="utf-8"))
    common = dict(index["config"])
    common["tasks_per_episode"] = config["tasks_per_episode"]
    seeds = sorted(int(s) for s in index["proposed_checkpoints"])
    conditions = [(BASE, None)] + [(f"Carbon-aware SPT, allowance={a:.0%}", a) for a in ALLOWANCES]
    rows = []
    for family in config["workload_families"]:
        for workload_seed in config["validation_seeds"]:
            for policy_seed in seeds:
                for label, allowance in conditions:
                    print(f"Replay: {family} workload={workload_seed}, policy={policy_seed}, {label}", flush=True)
                    rows.append(run_one(index, common, family, workload_seed, policy_seed, label, allowance))
    output.mkdir(parents=True, exist_ok=False)
    decision_rows = []
    for row in rows:
        for decision in row.pop("decision_trace"):
            decision_rows.append({"condition": row["condition"], "family": row["family"],
                                  "workload_seed": row["workload_seed"],
                                  "policy_seed": row["policy_seed"], **decision})
    # task_outcomes is retained in the summary rows; candidate decision detail
    # lives in its own line-oriented file to make the evidence auditable.
    (output / "candidate_decisions.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in decision_rows), encoding="utf-8")
    (output / "run_metrics.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    labels = [x[0] for x in conditions]
    summary = summaries(rows, labels, args.bootstrap_replicates)
    payload = {
        "study": "Validation-only matched intervention replay: A-MARL-derived IPPO SPT vs carbon-aware latency-bounded SPT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "validation_diagnostic_only_not_final_test_evidence",
        "method": {
            "checkpoint_source": "existing proposed_epsilon_0 checkpoints from research_alignment_v1, one checkpoint per policy seed reused unchanged across all conditions",
            "same_conditions": "same validation family/seed workload, dynamic synthetic 512-slot carbon profile, environment parameters, policy checkpoint, entropy threshold, intervention probability and stochastic action seed within each matched pair",
            "inference": "stochastic policy actions enabled; SPT entropy trigger active; no optimizer updates",
            "base_rule": "existing IPPOScheduler._spt_destination: minimum execution time among feasible destinations; this is the repository's cloud mapping of shortest processing time",
            "proposed_rule": "minimum total migration plus execution latency among feasible destinations, then minimum estimated carbon among candidates within allowance",
            "allowance_candidates": list(ALLOWANCES),
            "workload_families": config["workload_families"],
            "validation_seeds": config["validation_seeds"],
            "policy_seeds": seeds,
            "runs_per_condition": len(rows) // len(conditions),
            "heldout_test_used": False,
            "training_launched": False,
            "actual_emissions_definition": "episode totals are final integrated region emissions from simulator assignments; each placement's candidate carbon is a pre-assignment marginal estimate, not a separately measured realized task emission",
        },
        "summary": summary,
        "files": {"run_metrics": "run_metrics.jsonl", "candidate_decisions": "candidate_decisions.jsonl"},
    }
    (output / "diagnostic_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output.resolve()), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
