"""Small adapter that runs existing schedulers against the existing simulator."""
from __future__ import annotations

import json
import random
from pathlib import Path

import torch
import yaml

from agents.contextual_bandit import ContextualBanditScheduler
from agents.ippo_agent import CarbonAwareSPTIPPOScheduler
from environment.task_generator import (generate_diverse_workload,
                                        generate_phase25_workload,
                                        generate_variable_workload,
                                        synthetic_workload)
from experiments.evaluate_baselines import make_phase25_environment
from experiments.train_ippo import build_scheduler
from schedulers.fcfs import FCFSScheduler
from schedulers.forecast_mpc import ForecastAwareMPCScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_METHODS = ("Base — A-MARL-derived IPPO (fastest-feasible SPT)",
                   "Proposed — Carbon-Aware, Latency-Bounded Entropy-Guided SPT (20%)")
AUXILIARY_METHODS = ("Greedy carbon", "FCFS", "IPPO (historical)",
                     "MAPPO (historical)", "LinUCB (historical)",
                     "Forecast MPC (historical)")
ALGORITHMS = (*PRIMARY_METHODS, *AUXILIARY_METHODS)
WORKLOADS = {
    "Small demo (6 tasks)": lambda _seed: synthetic_workload(),
    "Variable synthetic (18 tasks)": lambda seed: generate_variable_workload(seed, 18),
    "Diverse synthetic (24 tasks)": lambda seed: generate_diverse_workload(seed, 24),
    "Bursty synthetic (24 tasks)": lambda seed: generate_phase25_workload(seed, 24),
}
EXPLANATIONS = {
    PRIMARY_METHODS[0]: "Base method. The same saved IPPO policy is evaluated with stochastic action sampling and active entropy-guided SPT. When entropy exceeds 0.8 × ln(feasible action count), choose the feasible destination with the shortest execution time. This is our cloud adaptation; the original A-MARL JobShop/edge experiments are not claimed as reproduced.",
    PRIMARY_METHODS[1]: "Proposed method. Uses the same policy, entropy gate, action mask, reward and simulator as the base. During an SPT intervention, find the feasible destination with minimum migration-plus-execution latency, keep destinations within 20% of that latency, and select the one with the lowest estimated carbon emissions.",
    "FCFS": "First-fit FCFS: keeps each task local when feasible, otherwise selects a stable feasible destination.",
    "Greedy carbon": "Greedy carbon: chooses the currently feasible region with the lowest estimated emissions, with a small latency tie-breaker.",
    "IPPO (historical)": "Historical Phase 2.6 IPPO policy checkpoint. Shown for continuity only, not part of the primary research comparison.",
    "MAPPO (historical)": "Historical Phase 2.6 MAPPO policy checkpoint. Shown for continuity only, not part of the primary research comparison.",
    "LinUCB (historical)": "Historical Phase 2.9 contextual model, shown for continuity only and not part of the primary research comparison.",
    "Forecast MPC (historical)": "Historical forecast-aware scheduler, shown for continuity only and not part of the primary research comparison.",
}

CHECKPOINTS = {
    "IPPO": ROOT / "results/phase26_final/training/IPPO_no_SPT/seed_7/checkpoints/ippo_seed7.pt",
    "MAPPO": ROOT / "results/phase26_final/training/MAPPO_no_SPT/seed_7/checkpoints/ippo_seed7.pt",
    "LinUCB": ROOT / "results/phase29_final/training/seed_17/bandit_seed17.json",
}
PUBLIC_ALIGNMENT_INDEX = ROOT / "results/research_alignment_v1/ui_policy_index.public.json"
LOCAL_ALIGNMENT_INDEX = ROOT / "results/research_alignment_v1/ui_policy_index.json"
ALIGNMENT_INDEX = (PUBLIC_ALIGNMENT_INDEX if PUBLIC_ALIGNMENT_INDEX.is_file()
                   else LOCAL_ALIGNMENT_INDEX)
FINAL_RESULTS = ROOT / "results/research_alignment_v4_final_confirmation/final_summary.json"
FROZEN_ALLOWANCE = 0.20


def make_workload(name: str, seed: int):
    try:
        return WORKLOADS[name](seed)
    except KeyError as exc:
        raise ValueError(f"Unknown workload family: {name}") from exc


def make_scheduler(name: str, env, seed: int = 7, mpc_horizon_hours: float = 2.0):
    if name == "FCFS":
        return FCFSScheduler()
    if name == "Greedy carbon":
        return GreedyCarbonScheduler()
    if name == "Forecast MPC (historical)":
        return ForecastAwareMPCScheduler(
            forecast_horizon_hours=mpc_horizon_hours,
            slot_seconds=env.slot_seconds,
            carbon_forecast=env.carbon_model.profiles,
            defaults=env.carbon_model.defaults,
            max_deferrals=2,
            enable_reservations=True,
        )
    if name in PRIMARY_METHODS:
        if not ALIGNMENT_INDEX.exists() or not FINAL_RESULTS.exists():
            raise FileNotFoundError("The v4 saved results and existing policy checkpoints are required.")
        index = json.loads(ALIGNMENT_INDEX.read_text(encoding="utf-8"))
        policy_seed = int(index["default_seed"])
        config = dict(index["config"])
        config["slot_seconds"] = env.slot_seconds
        config["spt_entropy_fraction"] = 0.8
        config["spt_intervention_probability"] = 1.0
        if name == PRIMARY_METHODS[1]:
            config["spt_method"] = "carbon_latency_bounded"
            config["spt_latency_allowance_fraction"] = FROZEN_ALLOWANCE
        else:
            config.pop("spt_method", None)
        # v4 reuses one existing checkpoint per policy seed in both conditions.
        checkpoint = Path(index["proposed_checkpoints"][str(policy_seed)])
        if not checkpoint.is_absolute():
            checkpoint = ROOT / checkpoint
        random.seed(seed)
        torch.manual_seed(seed)
        scheduler = build_scheduler(config, policy_seed, deterministic=False)
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        scheduler.load_checkpoint(state["agents"])
        return scheduler
    if name in ("IPPO (historical)", "MAPPO (historical)"):
        config_path = ROOT / "configs/phase26_training_config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["algorithm"] = "mappo" if name.startswith("MAPPO") else "ippo"
        config["slot_seconds"] = env.slot_seconds
        scheduler = build_scheduler(config, seed, deterministic=True)
        checkpoint_name = "MAPPO" if name.startswith("MAPPO") else "IPPO"
        state = torch.load(CHECKPOINTS[checkpoint_name], map_location="cpu", weights_only=False)
        scheduler.load_checkpoint(state["agents"])
        return scheduler
    if name == "LinUCB (historical)":
        capacities = {region: (item.resources.gpus, item.resources.cpu_cores,
                               item.resources.memory_gb)
                      for region, item in env.regions.items()}
        config = yaml.safe_load((ROOT / "configs/phase29_bandit_config.yaml").read_text(encoding="utf-8"))
        scheduler = ContextualBanditScheduler(
            env.region_names, capacities, alpha=config["linucb_alpha"],
            ridge=config["ridge"], carbon_scale_g=config["carbon_scale_g"],
            latency_weight=config["latency_weight"], deterministic=True,
            learning_enabled=False)
        scheduler.load_checkpoint(json.loads(CHECKPOINTS[name].read_text(encoding="utf-8")))
        return scheduler
    raise ValueError(f"Unknown algorithm: {name}")


def run_comparison(workload_name: str, algorithms: list[str], seed: int = 7,
                   mpc_horizon_hours: float = 2.0):
    """Run selected schedulers on identical tasks and fresh environment instances."""
    if not algorithms:
        raise ValueError("Select at least one algorithm")
    tasks = make_workload(workload_name, seed)
    run_rows, traces = [], {}
    for name in algorithms:
        env = make_phase25_environment(dynamic_carbon=True, profile_slots=512)
        scheduler = make_scheduler(name, env, seed, mpc_horizon_hours)
        from copy import deepcopy
        result = env.run(deepcopy(tasks), scheduler)
        totals = result["totals"]
        completed = totals["completed"]
        row = {
            "Algorithm": name,
            "Energy (kWh)": totals["energy_kwh"],
            "Carbon (gCO₂e)": totals["carbon_gco2e"],
            "gCO₂e / completed task": (totals["carbon_gco2e"] / completed) if completed else None,
            "Completion rate": totals["completion_rate"],
            "SLA violations": totals["sla_violations"],
            "Mean latency (s)": totals["mean_latency_seconds"],
            "Completed": completed,
            "Rejected": totals["rejected"],
            "Deferrals": sum(record["action"] == "defer" for record in result["records"]),
            "Active SPT interventions": totals.get("spt_overrides", 0),
            "SPT intervention rate": (totals.get("spt_overrides", 0) /
                                      max(1, len(result.get("agent_decisions", [])))),
        }
        run_rows.append(row)
        placements = {region: 0 for region in env.region_names}
        decision_rows = []
        by_id = {task.task_id: task for task in tasks}
        for record in result["records"]:
            region = record.get("region")
            if region:
                placements[region] += 1
            task = by_id[record["task_id"]]
            decision_rows.append({
                "Slot": record["slot"], "Task": record["task_id"],
                "Arrival slot": task.arrival_slot, "Action": record["action"],
                "Retry slot": record.get("retry_slot"),
                "Source": task.source_region, "Destination": region or "—",
                "Latency (s)": record.get("latency_seconds"),
                "Finish slot": record.get("finish_slot"),
            })
        traces[name] = {"placements": placements, "decisions": decision_rows,
                        "explanation": EXPLANATIONS[name],
                        "agent_decisions": result.get("agent_decisions", []),
                        "totals": totals}
    return {"workload_name": workload_name, "seed": seed, "task_count": len(tasks),
            "mpc_horizon_hours": mpc_horizon_hours, "rows": run_rows, "traces": traces}
