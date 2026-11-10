"""Expanded source-window and arrival-intensity benchmark for Phase 3.2."""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds", "runtime_seconds", "optimality_gap_pct")


def as_tasks(raw):
    return [task_from_json(item) for item in raw]


def configured_tasks(tasks, deadline_slack):
    return [replace(task, deadline_seconds=task.deadline_seconds + deadline_slack - 3600.0)
            for task in tasks]


def evaluate_online(family, instance, tasks, config, carbon, **assumptions):
    rows = []
    for name, scheduler in (("FCFS", FCFSScheduler()),
                            ("Greedy carbon", GreedyCarbonScheduler())):
        env = make_environment(config, carbon, **{k: v for k, v in assumptions.items()
            if k in {"carbon_month", "pue_scale", "gpu_scale", "network_scale"}})
        started = perf_counter()
        result = env.run(tasks, scheduler)
        rows.append({"family": family, "instance": instance, "policy": name,
                     "task_count": len(tasks), **result["totals"],
                     "runtime_seconds": perf_counter() - started})
    return rows


def evaluate_matched_milp(family, instance, tasks, config, carbon, **assumptions):
    """Compare all policies on a bounded 12-task prefix of each cohort."""
    tasks = tasks[:config["milp_task_limit"]]
    tasks = configured_tasks(tasks, assumptions.get("deadline_slack", 3600.0))
    rows = evaluate_online(family, instance, tasks, config, carbon, **assumptions)
    env = make_environment(config, carbon, **{k: v for k, v in assumptions.items()
        if k in {"carbon_month", "pue_scale", "gpu_scale", "network_scale"}})
    started = perf_counter()
    solution = OfflineOptimizer().solve(env, tasks, config["offline_time_limit_seconds"])
    row = {"family": family, "instance": instance, "policy": "Offline MILP",
           "task_count": len(tasks), "solver_status": solution["status"],
           "optimal": solution["optimal"], "runtime_seconds": perf_counter() - started}
    if solution["totals"] is None:
        row.update({m: None for m in METRICS if m != "runtime_seconds" and m != "optimality_gap_pct"})
    else:
        row.update(solution["totals"])
    rows.append(row)
    milp = rows[-1]
    if milp.get("optimal") and milp.get("completion_rate") == 1.0 and milp.get("carbon_gco2e", 0) > 0:
        for online in rows[:-1]:
            online["optimality_gap_pct"] = 100 * (
                online["carbon_gco2e"] - milp["carbon_gco2e"]) / milp["carbon_gco2e"]
    return rows


def summarize(rows):
    output = {}
    for family in sorted({r["family"] for r in rows}):
        output[family] = {}
        for policy in ("FCFS", "Greedy carbon", "Offline MILP"):
            subset = [r for r in rows if r["family"] == family and r["policy"] == policy]
            output[family][policy] = {
                metric: stats_ci([r[metric] for r in subset if r.get(metric) is not None],
                    93200 + len(output) * 101 + i)
                for i, metric in enumerate(METRICS)
            }
            output[family][policy]["certified_optima"] = sum(bool(r.get("optimal")) for r in subset)
            output[family][policy]["instances"] = len(subset)
    return output


def table(lines, title, summary):
    lines.extend([f"### {title}", "",
        "| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for policy in ("FCFS", "Greedy carbon", "Offline MILP"):
        metrics = summary[policy]
        cells = []
        for key in ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
                    "sla_violations", "mean_latency_seconds"):
            stat = metrics[key]
            cells.append("n/a" if not stat["n"] else
                f"{stat['mean']:.3f} ± {stat['sd']:.3f} [{stat['ci95'][0]:.3f}, {stat['ci95'][1]:.3f}] (n={stat['n']})")
        gap = metrics["optimality_gap_pct"]
        cells.append("n/a" if not gap["n"] else
            f"{gap['mean']:.2f} ± {gap['sd']:.2f} [{gap['ci95'][0]:.2f}, {gap['ci95'][1]:.2f}] (n={gap['n']})")
        lines.append("| " + policy + " | " + " | ".join(cells) + " |")
    lines.append("")


def make_report(workloads, online_summary, matched_summary, sensitivity_summary,
                matched_sensitivity_summary, audit, milp_stats):
    full_instances = sum(v["Greedy carbon"]["instances"] for v in online_summary.values())
    full_policy_runs = 2 * full_instances
    matched_policy_runs = 3 * sum(v["FCFS"]["instances"] for v in matched_summary.values())
    sensitivity_online_runs = 2 * sum(v["Greedy carbon"]["instances"] for v in sensitivity_summary.values())
    sensitivity_matched_runs = 3 * sum(v["FCFS"]["instances"] for v in matched_sensitivity_summary.values())
    spread_changes, burst_changes = [], []
    for size in (12, 24, 48):
        spread = online_summary[f"spread_{size}tasks"]
        burst = online_summary[f"burst_2h_{size}tasks"]
        def carbon_change(result):
            return 100 * (result["Greedy carbon"]["carbon_gco2e"]["mean"] /
                          result["FCFS"]["carbon_gco2e"]["mean"] - 1)
        spread_changes.append((size, carbon_change(spread),
            spread["Greedy carbon"]["completion_rate"]["mean"]))
        burst_changes.append((size, carbon_change(burst),
            burst["Greedy carbon"]["completion_rate"]["mean"],
            burst["Greedy carbon"]["rejection_rate"]["mean"]))
    findings = (f"The run evaluated {full_instances} full-size workload instances across six families and 13 package-axis windows: {full_policy_runs} full-size FCFS/greedy runs, {matched_policy_runs} matched 12-task policy runs, {sensitivity_online_runs} online sensitivity runs, and {sensitivity_matched_runs} sensitivity-prefix policy runs. "
        + "Spread greedy carbon changes relative to FCFS were " + "; ".join(
            f"{size} tasks: {change:+.1f}% emissions, {completion:.1%} completion" for size, change, completion in spread_changes) + ". "
        + "Two-hour burst results were " + "; ".join(
            f"{size} tasks: {change:+.1f}% emissions, {completion:.1%} completion, {rejection:.1%} rejection" for size, change, completion, rejection in burst_changes) + ". Lower emissions in burst cases must be read alongside the completion/rejection results. "
        + f"The {milp_stats['attempted'] + milp_stats['sensitivity_attempted']} baseline and sensitivity MILPs yielded {milp_stats['certified_optimal'] + milp_stats['sensitivity_certified_optimal']} certified optima, {milp_stats['feasible_incumbent'] + milp_stats['sensitivity_feasible_incumbent']} feasible incumbents without optimality proof, and {milp_stats['infeasible_or_no_solution'] + milp_stats['sensitivity_infeasible_or_no_solution']} with no feasible solution.")
    lines = ["# Phase 3.2 — dataset expansion and validation", "", "## Executed findings", "", findings, "",
        "## Data validity and provenance", "",
        "The only benchmark workload evaluated here is the retained Alibaba-derived SustainCluster processed trace. Official SustainCluster documentation says the underlying Alibaba PAI 2020 trace covers July–August 2020 and its packaged trace is extended to a simulated year by repeating daily/weekly patterns. This project’s package has 37,552 interval rows (2020-01-01 through 2021-01-26), but the task-level timestamp fields in a 16,720-record deterministic audit sample resolve to surrogate 1970 timestamps and differ from the package interval axis by about 1.58–1.61 billion seconds. Therefore the package axis is a scenario clock, not validated wall-clock observation time. Its 1.30 million task records do not provide 1.30 million independent production observations.", "",
        f"The interval index is monotonic with no duplicate timestamps; {audit['non_15_minute_interval_steps']} of {audit['dataframe_rows']-1} interval steps are 30 minutes instead of 15 minutes. These gaps are retained. The sampled task-field audit found {audit['sampled_malformed_or_invalid_records']} malformed/invalid records under the checked fields; this is a sample check, not a proof that every task field is complete. We preserve source rows and do not fill missing intervals or attributes. Resource conversions remain runtime minutes→seconds, CPU/GPU percent÷100, memory GB as supplied, and `bandwidth_gb` retained as the source's estimated input-volume field.", "",
        "Coverage cohorts use 13 monthly start coordinates across the packaged axis, three sampled task counts (12/24/48), and two recorded-arrival patterns: spread across a 24-hour window and a two-hour busy window. The 15-minute task arrivals and distinct task records are preserved; lower/higher intensity means sampling different counts, not generating jobs. A seeded selector is used, with seeds recorded in the processed payload. Upstream temporal extension means monthly cohorts are not independent raw-trace months; confidence intervals are descriptive across package-axis windows.", "",
        "## Additional source review", "",
        "Alibaba’s official 2023 GPU-sharing trace has 8,152 pod records (~562 KiB) and a 1,214-node GPU inventory (~41 KiB). Its schema provides CPU millicores, memory MiB, GPU count/share, QoS and relative creation/scheduled/deletion times. It does not document a UTC calendar anchor or task input-size field; these omissions block date-matched carbon replay and realistic migration-latency modeling. The source README grants research/study use and requests citation, but no explicit per-data license was found in the inspected dataset subdirectory. It is documented as a follow-up candidate, not mixed into the current simulator or assigned invented values.", "",
        "Other inspected candidates are not compatible as-is: SustainDC Alibaba/Google files are aggregate hourly CPU profiles, not per-task GPU jobs; Google 2019 cluster traces are CPU-centric; the MIT Supercloud GPU workload archive is roughly terabyte-scale and outside this bounded phase. We did not download these datasets.", "",
        "For aligned carbon, the existing 2023 NYISO/CAISO/ERCOT direct-intensity CSVs are complete UTC hourly series with 51 source rows marked estimated (retained). SustainCluster’s current README describes carbon coverage as 2021–2024, while its release overview broadly says environmental data 2020–2024; local Phase 3 files contain 2023 only. WattTime exposes historical MOER in lb CO₂/MWh, but the historical data endpoint is subscriber-restricted. A public CAISO 2019–2020 research dataset reports month-hour regressed AEF/MEF factors (CC BY 4.0), not a full hourly 3-region average-intensity panel. Google’s 2020 regional carbon file is annual lifecycle intensity by Google Cloud region, not hourly ISO data. None is an authentic, compatible hourly 2020 profile for all three simulator regions, so we retain the 2023 signal as a separate unsynchronized carbon replay and do not claim calendar alignment.", "",
        "## Evaluation protocol", "",
        "Every online run compares FCFS and greedy carbon on the full selected workload and uses current-observation-only carbon estimation. FCFS, greedy and offline MILP are compared on the same 12-task prefix from each cohort at four representative package-axis windows; MILP uses the complete future workload and carbon and is an oracle. Gaps are reported only where MILP certifies optimality and all tasks complete. Sensitivity reuses identical 24-task spread/burst cohorts at two package-axis windows for deadline slack (1,800/3,600/7,200 s), PUE (±10%), GPU active power (±20%), network throughput/RTT (half/double), and 2023 carbon replay offsets. Each MILP has a two-second configured limit. Values are mean ± sample SD [95% percentile bootstrap interval] across windows; small n and upstream temporal repetition limit interpretation.", "",
        "## Full-size online results", ""]
    for family, summary in online_summary.items():
        table(lines, f"Workload family: {family} ({summary['Greedy carbon']['instances']} windows; full workload size)", summary)
    lines.extend(["## Matched 12-task FCFS/greedy/MILP results", ""])
    for family, summary in matched_summary.items():
        table(lines, f"Matched prefix: {family}", summary)
    lines.extend(["## Sensitivity results", ""])
    for family, summary in sensitivity_summary.items():
        table(lines, f"Full-size sensitivity: {family}", summary)
    lines.extend(["## Sensitivity matched 12-task solver comparisons", ""])
    for family, summary in matched_sensitivity_summary.items():
        table(lines, f"Sensitivity prefix: {family}", summary)
    lines.extend(["## MILP solver status", "",
        f"Across {milp_stats['attempted']} baseline matched 12-task MILPs, {milp_stats['certified_optimal']} were certified optimal, {milp_stats['feasible_incumbent']} returned a feasible incumbent without a proof of optimality, and {milp_stats['infeasible_or_no_solution']} had no feasible solution. Across {milp_stats['sensitivity_attempted']} sensitivity MILPs, {milp_stats['sensitivity_certified_optimal']} were certified optimal, {milp_stats['sensitivity_feasible_incumbent']} returned feasible incumbents, and {milp_stats['sensitivity_infeasible_or_no_solution']} had no feasible solution. Only certified optimal complete cases contribute gaps.", "",
        "## Interpretation and limitations", "",
        "This expansion increases scenario coverage and tests whether placement results vary with arrival concentration and sampled task count. It does not create new measured trace evidence: official preprocessing repeats a two-month source pattern across the package axis, and the interval timestamps are not validated against task event timestamps. The phase’s 2020/2023 mismatch cannot be repaired from the currently available, compatible all-region data. The 2023 Alibaba trace is a promising independent workload family but lacks a verified absolute timestamp and transfer-size field; adding it requires either an official richer schema or a separately defined no-migration benchmark.", "",
        "Deadlines (runtime + configured slack), north ingress, capacities, execution characteristics, PUE, GPU power, network and transfer sizes remain simulator assumptions or source estimates. The simulator does not represent task failures, GPU-type constraints, multiple instances as gang-scheduled job groups, data locality, or real origin geography. The 12-task MILP is offline and lookahead-aware; its gap is not online regret. Larger workloads are not solved exactly. No claim of production-cloud effectiveness is made. See machine-readable per-run results and solver statuses under `results/phase32/`.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs/phase32_trace_config.yaml"))
    parser.add_argument("--output-dir")
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild markdown from the existing evaluation JSON without rerunning simulations")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output_dir or ROOT / config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    workload_payload = json.loads((ROOT / config["workloads_path"]).read_text(encoding="utf-8"))
    carbon = json.loads((ROOT / config["carbon_profiles_path"]).read_text(encoding="utf-8"))
    audit_path = ROOT / "data/processed/phase32/source_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if args.report_only:
        payload = json.loads((output / "phase32_evaluation.json").read_text(encoding="utf-8"))
        report = make_report(workload_payload, payload["online_full_size_summary"],
            payload["matched_12_task_summary"], payload["sensitivity_full_size_summary"],
            payload["sensitivity_matched_12_task_summary"], audit, payload["milp_solver_status"])
        (ROOT / "PHASE32_REPORT.md").write_text(report, encoding="utf-8")
        (output / "PHASE32_REPORT.md").write_text(report, encoding="utf-8")
        print(f"Report regenerated from {output / 'phase32_evaluation.json'}")
        return
    full_rows, matched_rows = [], []
    families = workload_payload["scenario_families"]
    milp_indices = set(config["milp_window_indices"])
    for family, scenarios in families.items():
        print(f"Evaluating full-size family: {family}", flush=True)
        for index, raw_tasks in enumerate(scenarios):
            tasks = as_tasks(raw_tasks)
            full_rows += evaluate_online(family, index, tasks, config, carbon)
            if index in milp_indices:
                matched_rows += evaluate_matched_milp(family, index, tasks, config, carbon)
    full_summary, matched_summary = summarize(full_rows), summarize(matched_rows)
    sensitivity_full_rows, sensitivity_matched_rows = [], []
    sensitivity = [
        ("baseline", {"deadline_slack": 3600}),
        ("slack_1800s", {"deadline_slack": 1800}),
        ("slack_7200s", {"deadline_slack": 7200}),
        ("pue_minus10pct", {"deadline_slack": 3600, "pue_scale": .9}),
        ("pue_plus10pct", {"deadline_slack": 3600, "pue_scale": 1.1}),
        ("gpu_power_minus20pct", {"deadline_slack": 3600, "gpu_scale": .8}),
        ("gpu_power_plus20pct", {"deadline_slack": 3600, "gpu_scale": 1.2}),
        ("network_half", {"deadline_slack": 3600, "network_scale": .5}),
        ("network_double", {"deadline_slack": 3600, "network_scale": 2.0}),
        ("carbon_april_offset", {"deadline_slack": 3600, "carbon_month": 4}),
        ("carbon_july_offset", {"deadline_slack": 3600, "carbon_month": 7}),
        ("carbon_october_offset", {"deadline_slack": 3600, "carbon_month": 10}),
    ]
    selected_windows = tuple(config["sensitivity_window_indices"])
    for base_family in ("spread_24tasks", "burst_2h_24tasks"):
        for label, assumptions in sensitivity:
            family = f"{base_family}__{label}"
            print(f"Evaluating sensitivity: {family}", flush=True)
            for index in selected_windows:
                raw_tasks = families[base_family][index]
                tasks = configured_tasks(as_tasks(raw_tasks), assumptions["deadline_slack"])
                sensitivity_full_rows += evaluate_online(family, index, tasks, config, carbon,
                    **{k: v for k, v in assumptions.items() if k != "deadline_slack"})
                sensitivity_matched_rows += evaluate_matched_milp(
                    family, index, as_tasks(raw_tasks), config, carbon, **assumptions)
    sensitivity_summary = summarize(sensitivity_full_rows)
    matched_sensitivity_summary = summarize(sensitivity_matched_rows)
    milps = [row for row in matched_rows if row["policy"] == "Offline MILP"]
    milp_stats = {"attempted": len(milps),
                  "certified_optimal": sum(bool(r.get("optimal")) for r in milps),
                  "feasible_incumbent": sum(r.get("solver_status") == "feasible_incumbent" for r in milps),
                  "infeasible_or_no_solution": sum(r.get("completion_rate") is None for r in milps)}
    sensitivity_milps = [r for r in sensitivity_matched_rows if r["policy"] == "Offline MILP"]
    milp_stats.update({"sensitivity_attempted": len(sensitivity_milps),
        "sensitivity_certified_optimal": sum(bool(r.get("optimal")) for r in sensitivity_milps),
        "sensitivity_feasible_incumbent": sum(r.get("solver_status") == "feasible_incumbent" for r in sensitivity_milps),
        "sensitivity_infeasible_or_no_solution": sum(r.get("completion_rate") is None for r in sensitivity_milps)})
    payload = {"online_full_size_summary": full_summary,
        "matched_12_task_summary": matched_summary,
        "sensitivity_full_size_summary": sensitivity_summary,
        "sensitivity_matched_12_task_summary": matched_sensitivity_summary,
        "full_size_runs": full_rows,
        "matched_12_task_runs": matched_rows,
        "sensitivity_full_size_runs": sensitivity_full_rows,
        "sensitivity_matched_12_task_runs": sensitivity_matched_rows,
        "sensitivity_scenarios": [name for name, _ in sensitivity],
        "milp_solver_status": milp_stats,
        "online_carbon_information": "current-observation only",
        "offline_milp_uses_future_workload_and_carbon": True,
        "workload_source_axis_is_not_validated_wall_clock": True}
    (output / "phase32_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = make_report(workload_payload, full_summary, matched_summary,
                         sensitivity_summary, matched_sensitivity_summary, audit, milp_stats)
    (ROOT / "PHASE32_REPORT.md").write_text(report, encoding="utf-8")
    (output / "PHASE32_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"workload_families": len(families), "window_scenarios": sum(map(len, families.values())),
                      "full_size_policy_runs": len(full_rows), "matched_policy_runs": len(matched_rows),
                      "sensitivity_online_runs": len(sensitivity_full_rows),
                      "sensitivity_matched_runs": len(sensitivity_matched_rows),
                      "milp": milp_stats, "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
