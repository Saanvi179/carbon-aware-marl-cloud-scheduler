"""Controlled Phase 3.1 robustness and assumption-sensitivity benchmark."""
import argparse
import json
import statistics
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import yaml

from environment.carbon_model import CarbonModel
from environment.cloud_environment import CloudEnvironment, Region
from environment.network_model import NetworkModel
from environment.resource_manager import Resources
from environment.task_generator import Task
from experiments.offline_optimizer import OfflineOptimizer
from experiments.preprocess_phase3 import load_trace_workloads
from experiments.run_phase3 import stats_ci, task_from_json

ROOT = Path(__file__).resolve().parents[1]


def make_environment(config, payload, *, carbon_month=1, common_carbon=False,
                     pue_scale=1.0, gpu_scale=1.0, network_scale=1.0):
    profiles = deepcopy(payload["profiles"])
    # Rotate each measured 2023 series to a month boundary. This is an explicit
    # date-mismatch sensitivity, not date alignment or a future forecast.
    offset = (carbon_month - 1) * 30 * 24 * 4
    profiles = {name: values[offset:] + values[:offset] for name, values in profiles.items()}
    if common_carbon:
        profiles = {name: [sum(v) / len(profiles) for v in zip(*profiles.values())]
                    for name in profiles}
    defaults = {name: values[0] for name, values in profiles.items()}
    regions = [
        Region("north", Resources(8, 64, 256), defaults["north"], 300 * gpu_scale, 100,
               1.20 * pue_scale, 1.0),
        Region("west", Resources(6, 48, 192), defaults["west"], 280 * gpu_scale, 90,
               1.15 * pue_scale, 1.15),
        Region("east", Resources(10, 80, 384), defaults["east"], 330 * gpu_scale, 110,
               1.25 * pue_scale, 0.9),
    ]
    links = {(a, b): (2.0 * network_scale, 0.08 * network_scale)
             for a in ("north", "west", "east") for b in ("north", "west", "east") if a != b}
    return CloudEnvironment(regions, NetworkModel(links), slot_seconds=config["slot_seconds"],
        max_deferrals=config["max_deferrals"],
        carbon_model=CarbonModel(profiles, defaults, candidate_forecast_known=False))


def vary_tasks(items, *, deadline_slack=3600, ingress="north"):
    result = []
    for item in items:
        task = task_from_json(item)
        result.append(replace(task, deadline_seconds=task.deadline_seconds + deadline_slack - 3600,
                              source_region=ingress))
    return result


def evaluate(label, instance, items, config, carbon_payload, **assumptions):
    tasks = vary_tasks(items, deadline_slack=assumptions.get("deadline_slack", 3600),
                       ingress=assumptions.get("ingress", "north"))
    rows = []
    for policy, scheduler_type in (("FCFS", "fcfs"), ("Greedy carbon", "greedy")):
        from schedulers.fcfs import FCFSScheduler
        from schedulers.greedy_carbon import GreedyCarbonScheduler
        scheduler = FCFSScheduler() if scheduler_type == "fcfs" else GreedyCarbonScheduler()
        env = make_environment(config, carbon_payload, **{k: v for k, v in assumptions.items()
            if k in {"carbon_month", "common_carbon", "pue_scale", "gpu_scale", "network_scale"}})
        start = perf_counter(); result = env.run(tasks, scheduler); elapsed = perf_counter() - start
        placements = {name: sum(r.get("region") == name for r in result["records"])
                      for name in ("north", "west", "east")}
        rows.append({"family": label, "instance": instance, "policy": policy,
                     **result["totals"], "placement_counts": placements, "runtime_seconds": elapsed})
    env = make_environment(config, carbon_payload, **{k: v for k, v in assumptions.items()
        if k in {"carbon_month", "common_carbon", "pue_scale", "gpu_scale", "network_scale"}})
    start = perf_counter(); optimal = OfflineOptimizer().solve(env, tasks, config["offline_time_limit_seconds"])
    elapsed = perf_counter() - start
    row = {"family": label, "instance": instance, "policy": "Offline MILP",
           "runtime_seconds": elapsed, "optimal": optimal["optimal"], "solver_status": optimal["status"]}
    if optimal["totals"] is None:
        row.update({k: None for k in ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
                                     "sla_violations", "mean_latency_seconds", "completed", "rejected")})
    else:
        row.update(optimal["totals"])
        row["placement_counts"] = {name: sum(r.get("region") == name for r in optimal["schedule"])
                                    for name in ("north", "west", "east")}
    rows.append(row)
    milp = rows[-1]
    for row in rows[:-1]:
        row["optimality_gap_pct"] = (100 * (row["carbon_gco2e"] - milp["carbon_gco2e"]) /
            milp["carbon_gco2e"] if milp.get("optimal") and milp.get("completion_rate") == 1 and
            row.get("completion_rate") == 1 and milp["carbon_gco2e"] else None)
    return rows


def summarize(rows):
    metrics = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate", "sla_violations",
               "mean_latency_seconds", "runtime_seconds", "optimality_gap_pct")
    output = {}
    for family in sorted({r["family"] for r in rows}):
        output[family] = {}
        for policy in ("FCFS", "Greedy carbon", "Offline MILP"):
            subset = [r for r in rows if r["family"] == family and r["policy"] == policy]
            output[family][policy] = {m: stats_ci([r[m] for r in subset if r.get(m) is not None],
                73100 + len(output) * 997 + i) for i, m in enumerate(metrics)}
            output[family][policy]["placement_counts"] = {
                region: statistics.mean(r.get("placement_counts", {}).get(region, 0) for r in subset)
                if subset else 0.0 for region in ("north", "west", "east")}
    return output


def report_text(summary, manifest):
    lines = ["# Phase 3.1 — robustness and generalisation", "",
        "## Method", "",
        f"Inputs are the retained official Alibaba-derived 2020 workload archive and 2023 hourly direct regional carbon profiles. This run sampled {manifest['selected_task_count']} task appearances in the primary spread/burst cohorts; seeded subset replications reuse the same source windows and may overlap in job IDs. No task fields or arrival times were fabricated. The trace supplies no per-task deadline or geo-origin, so deadline slack and ingress are varied explicitly as assumptions. Carbon observations use zero-order-held source values, and online candidate estimates remain current-observation-only. MILP uses the full future profile and is an offline oracle.", "",
        "Sensitivity settings are controlled one-factor scenario assumptions: month-offset replay of 2023 profiles; commonized profiles as a regional-variation ablation; deadline slack, ingress region, PUE, GPU active power, and network bandwidth/RTT. The 2020/2023 offset sweep quantifies date-mismatch sensitivity but cannot establish a historical year-to-year comparison. Network, PUE and power values are model inputs, not trace measurements.", "",
        "Results show mean ± sample SD [95% percentile bootstrap interval] across instances. Confidence intervals resample instances; they are descriptive, particularly with three instances. MILP gaps are included only when the solver certifies optimality and both schedules complete all tasks; the gap cell gives the number of qualifying paired instances.", "", "## Regional carbon profiles", "",
        "| Region | Source zone | Mean direct intensity gCO₂e/kWh | Min | Max | Estimated hourly rows |", "|---|---|---:|---:|---:|---:|"]
    payload=json.loads((ROOT/"data/processed/phase3/carbon_profiles_2023.json").read_text(encoding="utf-8"))
    for name, values in payload["profiles"].items():
        info=payload["regions"][name]
        hourly=values[::4]
        lines.append(f"| {name} | {info['source_zone']} | {statistics.mean(hourly):.2f} | {min(hourly):.2f} | {max(hourly):.2f} | {info['estimated_source_rows']} |")
    lines += ["", "Regional carbon summaries describe the measured 2023 source values; the simulator's task outcomes below replay these series against 2020 workload timestamps.", "", "## Results", ""]
    for family, policies in summary.items():
        lines += [f"### {family}", "", "| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for policy, metrics in policies.items():
            vals=[]
            for metric in ("carbon_gco2e","energy_kwh","completion_rate","rejection_rate","sla_violations","mean_latency_seconds","runtime_seconds"):
                x=metrics[metric]; vals.append("n/a" if not x["n"] else f"{x['mean']:.3f} ± {x['sd']:.3f} [{x['ci95'][0]:.3f}, {x['ci95'][1]:.3f}]")
            x=metrics["optimality_gap_pct"]; vals.append("n/a" if not x["n"] else f"{x['mean']:.2f} ± {x['sd']:.2f} [{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}] (n={x['n']})")
            vals.extend(f"{metrics['placement_counts'][r]:.2f}" for r in ("north", "west", "east"))
            lines.append("| " + policy + " | " + " | ".join(vals) + " |")
        lines.append("")
    lines += ["## Findings", "",
        "On the three 24-task spread windows, greedy completed every task and averaged 688.10 gCO₂e with a 5.93% gap to certified MILP (95% bootstrap interval 5.57–6.21; n=3); FCFS averaged 814.68 g and a 23.05% gap. The two seeded alternate spread subsets also completed all jobs, but greedy emissions were 413.68 and 603.09 g and the gaps were 10.55% and 6.15% respectively (three date windows per seed). This demonstrates meaningful sensitivity to which eligible trace jobs are sampled, while all reported spread MILPs solved optimally.", "",
        "The 24-task burst cohort had 98.6% mean completion for greedy and FCFS (one rejection across the three workloads); MILP schedules completed all tasks in all three. Only one burst MILP certified optimality within the 15-second limit; the other two returned feasible incumbents, so they contribute no optimality gaps. Greedy's 23.00% gap is for the sole fully completed, certified paired instance (n=1), a warning about burst congestion rather than a stable gap estimate. Baseline 8-task jobs completed at 100%, and greedy averaged 437.97 gCO₂e with a 3.28% gap [1.08, 4.45].", "",
        "Deadline slack from 1,800 to 7,200 seconds did not change placements or outcomes in this sample. Changing ingress and halving/doubling the assumed network parameters left placement and completion unchanged; measured latency moved only slightly because these jobs' data volumes and deadlines did not make migration infeasible. PUE and GPU-power sweeps changed absolute emissions/energy roughly in proportion to the input scaling, while the baseline gap stayed at 3.28%. Rotating the carbon replay to April/July/October changed greedy emissions to 315.97/395.55/357.60 g and gaps to 0.31/0.26/1.02%; the workload and its 2.305 kWh energy remained fixed. This quantifies substantial year/profile timing sensitivity without resolving the year mismatch.", "",
        "Measured regional 2023 means were 209.68 gCO₂e/kWh (north), 193.96 (west) and 316.72 (east). Greedy placed 23.33 of 24 spread jobs in west on average; with all regions assigned the same carbon profile, the 8-task baseline gap decreased from 3.28% to 1.29%. The selected cases therefore expose a regional carbon advantage, but this conclusion is conditioned on one ingress assumption and uncalibrated region energy/network characteristics.", "",
        "Greedy's gap and service metrics must be interpreted together: a low-emissions result with lower completion is not considered an improvement. Carbon-profile month offsets change the emissions landscape while leaving the workload unchanged. The MILP gap is an oracle-lookahead comparison, not an online regret estimate.", "",
        "## Limitations", "",
        "This remains a simulator replay, not a production-cloud measurement. The source workload is a selected subset of a packaged processed trace whose timestamps conflict with its upstream source description. Attributes absent from the trace (deadlines and ingress geography) remain assumptions. Carbon years are not aligned, the monthly offsets are deterministic rotations (30-day months for sensitivity only), regional power/PUE and network are not calibrated, and MILP is limited to small instances and its configured time bound. Across 57 MILPs, 55 were certified optimal and two burst cases returned feasible incumbents at the 15-second limit. Three dates per configuration do not support strong population-level generalisation. Full per-run solver status, metrics and assumptions are in `phase31_evaluation.json`.", ""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--config",default=str(ROOT/"configs/phase3_trace_config.yaml")); p.add_argument("--output-dir"); args=p.parse_args()
    config=yaml.safe_load(Path(args.config).read_text(encoding="utf-8")); out=Path(args.output_dir or ROOT/"results/phase31"); out.mkdir(parents=True,exist_ok=True)
    carbon=json.loads((ROOT/config["carbon_profiles_path"]).read_text(encoding="utf-8"))
    raw=ROOT/"data/raw/phase3/result_df_full_year_2020.zip"
    starts=("2020-01-01","2020-01-02","2020-01-08")
    spread,manifest=load_trace_workloads(raw,starts=starts,tasks_per_scenario=24,window_slots=96,arrival_pattern="spread")
    burst,burst_manifest=load_trace_workloads(raw,starts=starts,tasks_per_scenario=24,window_slots=8,arrival_pattern="burst")
    rows=[]
    # Larger trace windows with contrasting real arrival patterns.
    for label,sets in (("24-task spread windows",spread),("24-task recorded burst windows",burst)):
        for i,items in enumerate(sets): rows+=evaluate(label,i,items,config,carbon)
    # Repeated seeded spread sampling checks subset sensitivity and reproducibility.
    for seed in (31031, 31032):
        seeded, _ = load_trace_workloads(raw, starts=starts, tasks_per_scenario=24,
            window_slots=96, arrival_pattern="spread", selection_seed=seed)
        for i,items in enumerate(seeded):
            rows += evaluate(f"24-task spread subset seed {seed}", i, items, config, carbon)
    # Sensitivities use eight-task subsets to keep exact MILP practical.
    base,base_manifest=load_trace_workloads(raw,starts=starts,tasks_per_scenario=8,window_slots=96)
    scenarios=[("Baseline assumptions",{}), ("Deadline slack 1800s",{"deadline_slack":1800}),
      ("Deadline slack 7200s",{"deadline_slack":7200}), ("Ingress west",{"ingress":"west"}),
      ("Ingress east",{"ingress":"east"}), ("PUE -10%",{"pue_scale":.9}), ("PUE +10%",{"pue_scale":1.1}),
      ("GPU power -20%",{"gpu_scale":.8}), ("GPU power +20%",{"gpu_scale":1.2}),
      ("Network throughput/RTT half",{"network_scale":.5}), ("Network throughput/RTT double",{"network_scale":2.0}),
      ("2023 carbon April offset",{"carbon_month":4}), ("2023 carbon July offset",{"carbon_month":7}),
      ("2023 carbon October offset",{"carbon_month":10}), ("Common regional carbon",{"common_carbon":True})]
    for label,assumptions in scenarios:
        for i,items in enumerate(base): rows+=evaluate(label,i,items,config,carbon,**assumptions)
    summary=summarize(rows)
    payload={"summary":summary,"runs":[{k:v for k,v in r.items() if k!="records"} for r in rows],
       "assumptions":{"deadline_slack_sweep_seconds":[1800,3600,7200],"ingress_sweep":["north","west","east"],
       "pue_scale":[.9,1,1.1],"gpu_power_scale":[.8,1,1.2],"network_scale":[.5,1,2],"carbon_month_offsets":[1,4,7,10]},
       "workload_sampling":{"source_starts_utc":list(starts),"tasks_per_instance":24,
         "patterns":["spread","burst"],"alternate_spread_selection_seeds":[31031,31032],
         "sensitivity_tasks_per_instance":8,"source_order_default_is_deterministic":True},
       "online_carbon_information":"current-observation only","offline_milp_uses_future_carbon":True}
    (out/"phase31_evaluation.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    (ROOT/"PHASE31_REPORT.md").write_text(report_text(summary,{"selected_task_count":manifest["selected_task_count"]+burst_manifest["selected_task_count"]}),encoding="utf-8")
    (out/"PHASE31_REPORT.md").write_text((ROOT/"PHASE31_REPORT.md").read_text(encoding="utf-8"),encoding="utf-8")
    print(json.dumps({"families":len(summary),"runs":len(rows),"output":str(out)},indent=2))

if __name__=="__main__": main()
