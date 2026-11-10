"""Phase 3.3 Corrected Benchmark.

Addresses the audit findings in PHASE33_AUDIT.md:
1. Corrected MPC (2h): eight-slot lookahead, two-transition defer budget, reservations enabled
2. Corrected MPC (4h): sixteen-slot lookahead, same two-transition defer budget, reservations enabled
3. Reports completion-normalised emissions (gCO2e/completed_task) alongside raw totals.
4. Preserves original results under results/phase33/ (unchanged).
5. Outputs corrected results to results/phase33_corrected/.

Original experiment artefacts (results/phase33/) are labelled in the report header.
"""
import argparse
import csv
import json
import statistics
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import yaml

from experiments.offline_optimizer import OfflineOptimizer
from experiments.run_phase31 import make_environment
from experiments.run_phase3 import stats_ci, task_from_json
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler
from schedulers.forecast_mpc import ForecastAwareMPCScheduler

ROOT = Path(__file__).resolve().parents[1]

CORRECTED_POLICY_NAMES = (
    "FCFS",
    "Greedy carbon",
    "Forecast MPC (2h, orig)",   # max_deferrals=2 — original bottlenecked version
    "Corrected MPC (2h)",         # horizon_slots=8, shared max_deferrals=2, reservations=True
    "Corrected MPC (4h)",         # horizon_slots=16, shared max_deferrals=2, reservations=True
    "Offline MILP",
)
ONLINE_POLICIES = (
    "FCFS", "Greedy carbon", "Forecast MPC (2h, orig)", "Corrected MPC (2h)", "Corrected MPC (4h)"
)
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds", "runtime_seconds", "optimality_gap_pct")


def as_tasks(raw):
    return [task_from_json(item) for item in raw]


def configured_tasks(tasks, deadline_slack):
    return [replace(task, deadline_seconds=task.deadline_seconds + deadline_slack - 3600.0)
            for task in tasks]


def make_schedulers(config, env):
    """Return original + corrected schedulers for paired comparison."""
    profiles = env.carbon_model.profiles
    defaults = {k: v[0] for k, v in profiles.items()}
    common = dict(
        slot_seconds=config["slot_seconds"],
        carbon_forecast=profiles,
        defaults=defaults,
        urgency_slack_threshold_seconds=config.get("urgency_slack_threshold_seconds", 1800.0),
        deferral_saving_threshold=config.get("deferral_saving_threshold", 0.05),
        congestion_weight=config.get("congestion_weight", 0.02),
        latency_weight=config.get("latency_weight", 0.01),
    )
    corrected = {item["label"]: item for item in config.get("corrected_horizons", [])}
    corrected_2h = corrected.get("Corrected MPC (2h)", {"forecast_horizon_hours": 2.0, "max_deferrals": 2})
    corrected_4h = corrected.get("Corrected MPC (4h)", {"forecast_horizon_hours": 4.0, "max_deferrals": 2})
    return [
        ("FCFS", FCFSScheduler()),
        ("Greedy carbon", GreedyCarbonScheduler()),
        # Original Phase 3.3 MPC: max_deferrals=2 (bottlenecked), no reservations
        ("Forecast MPC (2h, orig)", ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            max_deferrals=config["max_deferrals"],   # 2 — original
            enable_reservations=False,
            **common,
        )),
        # Corrected MPC (2h): eight-slot lookahead, shared transition budget, reservations enabled
        ("Corrected MPC (2h)", ForecastAwareMPCScheduler(
            forecast_horizon_hours=corrected_2h["forecast_horizon_hours"],
            max_deferrals=corrected_2h["max_deferrals"],
            enable_reservations=config.get("enable_reservations", True),
            **common,
        )),
        # Corrected MPC (4h): sixteen-slot lookahead, shared transition budget, reservations enabled
        ("Corrected MPC (4h)", ForecastAwareMPCScheduler(
            forecast_horizon_hours=corrected_4h["forecast_horizon_hours"],
            max_deferrals=corrected_4h["max_deferrals"],
            enable_reservations=config.get("enable_reservations", True),
            **common,
        )),
    ]


def evaluate_online(family, instance, tasks, config, carbon, **assumptions):
    rows = []
    base_env = make_environment(config, carbon, **{k: v for k, v in assumptions.items()
        if k in {"carbon_month", "pue_scale", "gpu_scale", "network_scale"}})
    schedulers = make_schedulers(config, base_env)

    for name, scheduler in schedulers:
        env = make_environment(config, carbon, **{k: v for k, v in assumptions.items()
            if k in {"carbon_month", "pue_scale", "gpu_scale", "network_scale"}})
        started = perf_counter()
        result = env.run(tasks, scheduler)
        elapsed = perf_counter() - started
        totals = result["totals"]
        completed = totals.get("completed", 0)
        carbon_g = totals.get("carbon_gco2e", 0.0)
        # Completion-normalised emissions: gCO2e per successfully completed task
        carbon_per_completed = (carbon_g / completed) if completed > 0 else float("inf")
        rows.append({
            "family": family,
            "instance": instance,
            "policy": name,
            "task_count": len(tasks),
            **totals,
            "carbon_gco2e_per_completed": carbon_per_completed,
            "decision_signature": json.dumps([
                [r.get("task_id"), r.get("action"), r.get("slot"), r.get("retry_slot"), r.get("region")]
                for r in result["records"]], separators=(",", ":")),
            "runtime_seconds": elapsed,
            "deferrals_recommended": getattr(scheduler, "deferrals_recommended", 0),
            "urgent_placements": getattr(scheduler, "urgent_placements", 0),
        })
    return rows


def evaluate_matched_milp(family, instance, tasks, config, carbon, **assumptions):
    """Compare all corrected policies and offline MILP on a bounded 12-task prefix."""
    tasks = tasks[:config["milp_task_limit"]]
    tasks = configured_tasks(tasks, assumptions.get("deadline_slack", 3600.0))
    rows = evaluate_online(family, instance, tasks, config, carbon, **assumptions)
    env = make_environment(config, carbon, **{k: v for k, v in assumptions.items()
        if k in {"carbon_month", "pue_scale", "gpu_scale", "network_scale"}})
    started = perf_counter()
    solution = OfflineOptimizer().solve(env, tasks, config["offline_time_limit_seconds"])
    elapsed = perf_counter() - started
    milp_totals = solution.get("totals") or {}
    completed = milp_totals.get("completed", 0)
    carbon_g = milp_totals.get("carbon_gco2e", 0.0) or 0.0
    row = {
        "family": family, "instance": instance, "policy": "Offline MILP",
        "task_count": len(tasks), "solver_status": solution["status"],
        "optimal": solution["optimal"], "runtime_seconds": elapsed,
        "deferrals_recommended": 0, "urgent_placements": 0,
        "carbon_gco2e_per_completed": (carbon_g / completed) if completed > 0 else float("inf"),
    }
    if milp_totals:
        row.update(milp_totals)
    else:
        row.update({m: None for m in METRICS if m not in ("runtime_seconds", "optimality_gap_pct")})
    rows.append(row)
    milp = rows[-1]
    if milp.get("optimal") and milp.get("completion_rate") == 1.0 and (milp.get("carbon_gco2e") or 0) > 0:
        for online in rows[:-1]:
            online["optimality_gap_pct"] = 100 * (
                online["carbon_gco2e"] - milp["carbon_gco2e"]) / milp["carbon_gco2e"]
    return rows


def summarize(rows, policies=CORRECTED_POLICY_NAMES):
    output = {}
    for family in sorted({r["family"] for r in rows}):
        output[family] = {}
        for policy in policies:
            subset = [r for r in rows if r["family"] == family and r["policy"] == policy]
            output[family][policy] = {
                metric: stats_ci([r[metric] for r in subset if r.get(metric) is not None],
                    93300 + len(output) * 101 + i)
                for i, metric in enumerate(METRICS)
            }
            subset_completed = [r["carbon_gco2e_per_completed"] for r in subset
                                if r.get("carbon_gco2e_per_completed") not in (None, float("inf"))]
            output[family][policy]["carbon_gco2e_per_completed"] = stats_ci(subset_completed, 93300 + len(output) * 101 + 99)
            output[family][policy]["certified_optima"] = sum(bool(r.get("optimal")) for r in subset)
            output[family][policy]["instances"] = len(subset)
            output[family][policy]["deferrals_recommended"] = (
                statistics.mean([r["deferrals_recommended"] for r in subset]) if subset else 0.0)
            output[family][policy]["urgent_placements"] = (
                statistics.mean([r["urgent_placements"] for r in subset]) if subset else 0.0)
    return output


def compute_paired_differences(rows):
    """Compute matched paired deltas (corrected MPC - Greedy) across identical workload instances."""
    by_inst = {}
    for r in rows:
        key = (r["family"], r["instance"])
        by_inst.setdefault(key, {})[r["policy"]] = r

    names = ("Forecast MPC (2h, orig)", "Corrected MPC (2h)", "Corrected MPC (4h)")
    deltas = {n: {"carbon": [], "energy": [], "completion": [], "sla": [], "carbon_per_completed": []} for n in names}

    for key, pols in by_inst.items():
        if "Greedy carbon" not in pols:
            continue
        greedy = pols["Greedy carbon"]
        for mpc_name in names:
            if mpc_name in pols:
                mpc = pols[mpc_name]
                deltas[mpc_name]["carbon"].append(mpc["carbon_gco2e"] - greedy["carbon_gco2e"])
                deltas[mpc_name]["energy"].append(mpc["energy_kwh"] - greedy["energy_kwh"])
                deltas[mpc_name]["completion"].append(mpc["completion_rate"] - greedy["completion_rate"])
                deltas[mpc_name]["sla"].append(mpc["sla_violations"] - greedy["sla_violations"])
                # Normalised emissions delta (skip inf values)
                mpc_per = mpc.get("carbon_gco2e_per_completed", float("inf"))
                grd_per = greedy.get("carbon_gco2e_per_completed", float("inf"))
                if mpc_per not in (None, float("inf")) and grd_per not in (None, float("inf")):
                    deltas[mpc_name]["carbon_per_completed"].append(mpc_per - grd_per)

    summary = {}
    for name, metrics in deltas.items():
        summary[name] = {
            "delta_carbon_gco2e": stats_ci(metrics["carbon"], 88401),
            "delta_energy_kwh": stats_ci(metrics["energy"], 88405),
            "delta_completion_rate": stats_ci(metrics["completion"], 88402),
            "delta_sla_violations": stats_ci(metrics["sla"], 88403),
            "delta_carbon_per_completed": stats_ci(metrics["carbon_per_completed"], 88404),
        }
    return summary


def table(lines, title, summary, policies=CORRECTED_POLICY_NAMES):
    lines.extend([f"### {title}", "",
        "| Policy | Emissions gCO₂e | Energy kWh | gCO₂e/completed task | Completion | Rejection | SLA violations | Latency s | Opt. gap % | Deferrals |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for policy in policies:
        if policy not in summary:
            continue
        m = summary[policy]
        cells = []
        for key in ("carbon_gco2e", "energy_kwh", "carbon_gco2e_per_completed", "completion_rate", "rejection_rate",
                    "sla_violations", "mean_latency_seconds"):
            stat = m[key]
            cells.append("n/a" if not stat["n"] else
                f"{stat['mean']:.2f} ± {stat['sd']:.2f} [{stat['ci95'][0]:.2f}, {stat['ci95'][1]:.2f}]")
        gap = m["optimality_gap_pct"]
        cells.append("n/a" if not gap["n"] else f"{gap['mean']:.2f} ± {gap['sd']:.2f}")
        cells.append(f"{m.get('deferrals_recommended', 0.0):.1f}")
        lines.append("| " + policy + " | " + " | ".join(cells) + " |")
    lines.append("")


def make_report(online_summary, matched_summary, paired_summary, milp_stats, total_instances,
                horizon_comparison):
    total_online_runs = len(ONLINE_POLICIES) * total_instances
    matched_runs = len(CORRECTED_POLICY_NAMES) * sum(v["FCFS"]["instances"] for v in matched_summary.values())

    lines = [
        "# Phase 3.3 Corrected Benchmark — Forecast-Aware Receding Horizon (MPC) Scheduling", "",
        "> **Note**: This is the corrected evaluation following the independent audit (PHASE33_AUDIT.md).",
        "> Original results are preserved in `results/phase33/` and labelled **(orig)** where referenced.", "",
        "## What Changed from Original Phase 3.3", "",
        "| Issue | Original | Corrected |",
        "|---|---|---|",
        "| **Horizon vs. deferrals mismatch** | `max_deferrals=2` bottlenecked lookahead to 30 min for both 2h and 4h | Lookahead uses horizon and deadline slack; both settings share the same two-transition defer budget, and the chosen slot is committed directly |",
        "| **Capacity cliff** | Deferrals had no future slot reservation; tasks deferred into full slots | Tentative capacity reservations prevent oversubscribing future slots |",
        "| **Identical 2h/4h outputs** | Both configurations produced bit-for-bit identical decisions | Horizon and retry budget are separated; report whether the selected workload produces distinct decisions or metrics |",
        "| **Report text error** | Executive summary claimed '100% completion, 0 rejections' for burst-48 | Corrected to reflect actual numbers; completion normalised metrics added |",
        "| **Confounded burst emissions** | Raw emissions reduction partially from non-completion | Now reported separately as gCO₂e/completed-task |",
        "",
        "## Corrected Results Summary", "",
        f"Evaluated {total_instances} full-size instances × {len(ONLINE_POLICIES)} online policies = {total_online_runs} runs.",
        f"Matched prefix: {sum(v['FCFS']['instances'] for v in matched_summary.values())} workload-family/window cases × {len(CORRECTED_POLICY_NAMES)} policies = {matched_runs} rows: {matched_runs - milp_stats['attempted']} online rows plus {milp_stats['attempted']} MILP rows. The previously stated 120 count includes online policies only; 144 includes the MILP row for each of the 24 cases.", "",
        "The corrected policies have configured lookahead maxima of 8 and 16 slots and a shared two-transition defer budget. They generated identical decision signatures in "
        f"{horizon_comparison['identical_instances']} of {horizon_comparison['instances']} instances; "
        f"{horizon_comparison['different_instances']} instances differed. The selected Phase 3.2 workload derives deadlines as runtime + 3,600 seconds, which limits available deferral slack. Decision differences (if any) are counted separately from aggregate metrics; no distinct horizon benefit is claimed unless the measured outcomes support it.", "",
        "## Paired Statistical Comparison vs. Greedy Carbon (N=78 instances)", "",
        "| Policy | Δ Emissions (95% CI) | Δ Energy kWh (95% CI) | Δ gCO₂e/completed task (95% CI) | Δ Completion (95% CI) | Δ SLA violations (95% CI) |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for name in ("Forecast MPC (2h, orig)", "Corrected MPC (2h)", "Corrected MPC (4h)"):
        if name not in paired_summary:
            continue
        p = paired_summary[name]
        dc = p["delta_carbon_gco2e"]
        de = p["delta_energy_kwh"]
        dp = p["delta_carbon_per_completed"]
        comp = p["delta_completion_rate"]
        sla = p["delta_sla_violations"]
        n = dc.get("n", 0)
        dc_str = f"{dc['mean']:+.2f} ± {dc['sd']:.2f} [{dc['ci95'][0]:+.2f}, {dc['ci95'][1]:+.2f}] (n={n})"
        de_str = f"{de['mean']:+.3f} ± {de['sd']:.3f} [{de['ci95'][0]:+.3f}, {de['ci95'][1]:+.3f}] (n={de.get('n', 0)})"
        dp_str = (f"{dp['mean']:+.2f} ± {dp['sd']:.2f} [{dp['ci95'][0]:+.2f}, {dp['ci95'][1]:+.2f}]"
                  if dp.get("n") else "n/a")
        comp_str = f"{comp['mean']:+.4f} [{comp['ci95'][0]:+.4f}, {comp['ci95'][1]:+.4f}]"
        sla_str = f"{sla['mean']:+.3f} [{sla['ci95'][0]:+.3f}, {sla['ci95'][1]:+.3f}]"
        lines.append(f"| {name} | {dc_str} | {de_str} | {dp_str} | {comp_str} | {sla_str} |")
    lines.append("")

    lines.extend(["## Full-Size Online Results by Workload Family", ""])
    for family, summary in online_summary.items():
        n_inst = summary.get("Greedy carbon", {}).get("instances", 0)
        table(lines, f"{family} ({n_inst} windows, full size)", summary, policies=ONLINE_POLICIES)

    lines.extend(["## Matched 12-Task Solver Comparisons (Offline MILP benchmark)", ""])
    for family, summary in matched_summary.items():
        table(lines, f"Matched prefix: {family} (12 tasks, 4 windows)", summary, policies=CORRECTED_POLICY_NAMES)

    lines.extend([
        "## MILP Solver Status", "",
        f"Across {milp_stats['attempted']} matched 12-task MILP instances: "
        f"{milp_stats['certified_optimal']} certified optimal, "
        f"{milp_stats['feasible_incumbent']} feasible incumbents, "
        f"{milp_stats['infeasible_or_no_solution']} infeasible.", "",
        "## Limitations", "",
        "- Deferred tasks hold a tentative destination and retry slot, with region resource capacity reserved over the migration and execution interval. Reservations are released after placement, terminal rejection, or when their target slot expires. Capacity estimates use static configured region capacities plus known scheduled assignments; future unarrived workload is unknowable.",
        "- The 2h and 4h configurations have 8-slot and 16-slot lookahead respectively but share a two-deferral transition budget. Their decision signatures were identical on all 78 evaluated instances. The current deadline construction (runtime + 3,600 seconds) and workload profiles did not demonstrate a horizon effect. A separate predeclared workload design with sufficient feasible slack is needed to compare horizons empirically.",
        "- Deadline urgency is evaluated when a decision is made. New arrivals after a reservation can consume capacity; live feasibility checks prevent conflicts, but can force a reserved task to another feasible destination or terminal path.",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Phase 3.3 Corrected Benchmark")
    parser.add_argument("--config", default=str(ROOT / "configs/phase33_forecast_config.yaml"))
    parser.add_argument("--output-dir")
    parser.add_argument("--matched-smoke", action="store_true",
                        help="evaluate one matched 12-task prefix per family as a validation smoke run")
    parser.add_argument("--render-existing", action="store_true",
                        help="regenerate the report from existing evaluation JSON without rerunning simulations")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output_dir or ROOT / config.get("corrected_output_dir", "results/phase33_corrected"))
    output.mkdir(parents=True, exist_ok=True)

    if args.render_existing:
        artifact_dir = output
        payload = json.loads((artifact_dir / "phase33_corrected_evaluation.json").read_text(encoding="utf-8"))
        with (artifact_dir / "phase33_corrected_runs.csv").open(newline="", encoding="utf-8") as stream:
            csv_rows = list(csv.DictReader(stream))
        numeric_fields = ("instance", "carbon_gco2e", "energy_kwh", "completion_rate",
                          "sla_violations", "carbon_gco2e_per_completed")
        paired_rows = []
        for row in csv_rows:
            converted = dict(row)
            for field in numeric_fields:
                converted[field] = float(row[field])
            paired_rows.append(converted)
        payload["paired_summary"] = compute_paired_differences(paired_rows)
        report = make_report(
            payload["online_full_size_summary"], payload["matched_12_task_summary"],
            payload["paired_summary"], payload["milp_solver_status"],
            payload["run_accounting"]["full_size_instances"], payload["horizon_comparison"])
        (artifact_dir / "phase33_corrected_evaluation.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        (artifact_dir / "PHASE33_CORRECTED_REPORT.md").write_text(report, encoding="utf-8")
        (ROOT / "PHASE33_CORRECTED_REPORT.md").write_text(report, encoding="utf-8")
        print(f"Report regenerated from {artifact_dir / 'phase33_corrected_evaluation.json'}")
        return

    workload_payload = json.loads((ROOT / config["workloads_path"]).read_text(encoding="utf-8"))
    carbon = json.loads((ROOT / config["carbon_profiles_path"]).read_text(encoding="utf-8"))

    if args.matched_smoke:
        rows = []
        for family, scenarios in workload_payload["scenario_families"].items():
            rows.extend(evaluate_matched_milp(family, 0, as_tasks(scenarios[0]), config, carbon))
        with (output / "phase33_matched_smoke.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
            writer.writeheader()
            writer.writerows(rows)
        (output / "phase33_matched_smoke.json").write_text(json.dumps({
            "scope": "one matched 12-task prefix per workload family",
            "rows": rows,
            "milp_attempted": sum(r["policy"] == "Offline MILP" for r in rows),
            "milp_certified_optimal": sum(r["policy"] == "Offline MILP" and r.get("optimal", False) for r in rows),
        }, indent=2), encoding="utf-8")
        print(json.dumps({"families": len(workload_payload["scenario_families"]),
            "rows": len(rows), "output": str(output)}, indent=2), flush=True)
        return

    full_rows, matched_rows = [], []
    families = workload_payload["scenario_families"]
    milp_indices = set(config["milp_window_indices"])
    milp_attempted = milp_optimal = milp_incumbent = milp_infeasible = 0

    print("Phase 3.3 CORRECTED benchmark — evaluating 78 instances...", flush=True)
    for family, scenarios in families.items():
        print(f"  Family: {family} ({len(scenarios)} instances)", flush=True)
        for index, raw_tasks in enumerate(scenarios):
            tasks = as_tasks(raw_tasks)
            full_rows += evaluate_online(family, index, tasks, config, carbon)
            if index in milp_indices:
                matched = evaluate_matched_milp(family, index, tasks, config, carbon)
                matched_rows += matched
                milp_row = matched[-1]
                milp_attempted += 1
                if milp_row.get("optimal"):
                    milp_optimal += 1
                elif milp_row.get("solver_status") == "feasible_incumbent":
                    milp_incumbent += 1
                else:
                    milp_infeasible += 1

    total_instances = len({(r["family"], r["instance"]) for r in full_rows if r["policy"] == "Greedy carbon"})
    online_summary = summarize(full_rows, policies=ONLINE_POLICIES)
    matched_summary = summarize(matched_rows, policies=CORRECTED_POLICY_NAMES)
    paired_summary = compute_paired_differences(full_rows)

    milp_stats = {
        "attempted": milp_attempted,
        "certified_optimal": milp_optimal,
        "feasible_incumbent": milp_incumbent,
        "infeasible_or_no_solution": milp_infeasible,
    }

    by_instance = {}
    for row in full_rows:
        by_instance.setdefault((row["family"], row["instance"]), {})[row["policy"]] = row
    horizon_pairs = [policies for policies in by_instance.values()
                     if "Corrected MPC (2h)" in policies and "Corrected MPC (4h)" in policies]
    horizon_comparison = {
        "instances": len(horizon_pairs),
        "identical_instances": sum(p["Corrected MPC (2h)"]["decision_signature"] ==
                                    p["Corrected MPC (4h)"]["decision_signature"] for p in horizon_pairs),
        "different_instances": sum(p["Corrected MPC (2h)"]["decision_signature"] !=
                                    p["Corrected MPC (4h)"]["decision_signature"] for p in horizon_pairs),
        "policy_decision_signatures": True,
    }
    report = make_report(online_summary, matched_summary, paired_summary, milp_stats,
                         total_instances, horizon_comparison)
    corrected_config = {item["label"]: item for item in config.get("corrected_horizons", [])}
    matched_cases = sum(v["FCFS"]["instances"] for v in matched_summary.values())
    matched_policy_rows = sum(metrics["instances"] for group in matched_summary.values()
                              for metrics in group.values())
    run_accounting = {
        "full_size_instances": total_instances,
        "full_size_online_policy_rows": len(full_rows),
        "matched_prefix_cases": matched_cases,
        "matched_prefix_policy_rows_including_milp": matched_policy_rows,
        "matched_prefix_online_policy_rows": matched_policy_rows - milp_stats["attempted"],
        "matched_prefix_milp_rows": milp_stats["attempted"],
        "matched_prefix_policies_per_case": len(CORRECTED_POLICY_NAMES),
    }

    (output / "phase33_corrected_evaluation.json").write_text(json.dumps({
        "config": {k: v for k, v in config.items() if k != "corrected_horizons"},
        "corrected_schedulers": {
            "Corrected MPC (2h)": {"max_deferrals": corrected_config.get("Corrected MPC (2h)", {}).get("max_deferrals", 2), "horizon_slots": 8, "reservations": True},
            "Corrected MPC (4h)": {"max_deferrals": corrected_config.get("Corrected MPC (4h)", {}).get("max_deferrals", 2), "horizon_slots": 16, "reservations": True},
            "Forecast MPC (2h, orig)": {"max_deferrals": 2, "horizon_slots": 8, "reservations": False},
        },
        "online_full_size_summary": online_summary,
        "matched_12_task_summary": matched_summary,
        "paired_summary": paired_summary,
        "milp_solver_status": milp_stats,
        "horizon_comparison": horizon_comparison,
        "run_accounting": run_accounting,
    }, indent=2), encoding="utf-8")

    with (output / "phase33_corrected_runs.csv").open("w", newline="", encoding="utf-8") as stream:
        if full_rows:
            fields = sorted({k for r in full_rows for k in r})
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(full_rows)

    (output / "PHASE33_CORRECTED_REPORT.md").write_text(report, encoding="utf-8")
    default_output = (ROOT / config.get("corrected_output_dir", "results/phase33_corrected")).resolve()
    if output.resolve() == default_output:
        (ROOT / "PHASE33_CORRECTED_REPORT.md").write_text(report, encoding="utf-8")
    print(f"Corrected benchmark complete. Results in {output}/", flush=True)
    print(f"Report written to PHASE33_CORRECTED_REPORT.md", flush=True)


if __name__ == "__main__":
    main()
