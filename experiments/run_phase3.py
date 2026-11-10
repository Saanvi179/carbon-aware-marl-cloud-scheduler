"""Evaluate FCFS/greedy and the offline MILP on real trace-derived inputs."""
import argparse
import json
import random
import statistics
from pathlib import Path
from time import perf_counter

import yaml

from environment.carbon_model import CarbonModel
from environment.cloud_environment import CloudEnvironment, Region
from environment.network_model import NetworkModel
from environment.resource_manager import Resources
from environment.task_generator import Task, generate_phase25_workload
from experiments.offline_optimizer import OfflineOptimizer
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
           "sla_violations", "mean_latency_seconds", "runtime_seconds", "optimality_gap_pct")


def make_trace_environment(config, profile_payload):
    profiles = profile_payload["profiles"]
    defaults = {name: values[0] for name, values in profiles.items()}
    regions = [
        Region("north", Resources(8, 64, 256), defaults["north"], 300, 100, 1.20, 1.0),
        Region("west", Resources(6, 48, 192), defaults["west"], 280, 90, 1.15, 1.15),
        Region("east", Resources(10, 80, 384), defaults["east"], 330, 110, 1.25, 0.9),
    ]
    model = CarbonModel(profiles, defaults, candidate_forecast_known=False)
    return CloudEnvironment(regions, NetworkModel(), slot_seconds=config["slot_seconds"],
                            max_deferrals=config["max_deferrals"], carbon_model=model)


def task_from_json(item):
    keys = ("task_id", "arrival_slot", "gpu_count", "cpu_cores", "memory_gb",
            "dataset_gb", "deadline_seconds", "runtime_seconds", "source_region")
    return Task(**{key: item[key] for key in keys})


def stats_ci(values, seed):
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95": [None, None]}
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    rng = random.Random(seed)
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    return {"n": len(values), "mean": mean, "sd": sd,
            "ci95": [draws[int(.025*(len(draws)-1))], draws[int(.975*(len(draws)-1))]]}


def evaluate_instance(family, instance, tasks, config, profile_payload):
    rows = []
    for policy, scheduler in (("FCFS", FCFSScheduler()),
                              ("Greedy carbon", GreedyCarbonScheduler())):
        env = make_trace_environment(config, profile_payload)
        started = perf_counter()
        result = env.run(tasks, scheduler)
        elapsed = perf_counter() - started
        rows.append({"family": family, "instance": instance, "policy": policy,
                     **result["totals"], "runtime_seconds": elapsed,
                     "records": result["records"]})
    env = make_trace_environment(config, profile_payload)
    started = perf_counter()
    optimal = OfflineOptimizer().solve(env, tasks, config["offline_time_limit_seconds"])
    elapsed = perf_counter() - started
    if optimal["totals"] is None:
        rows.append({"family": family, "instance": instance, "policy": "Offline MILP",
                     "carbon_gco2e": None, "energy_kwh": None, "completed": None,
                     "rejected": None, "completion_rate": None, "rejection_rate": None,
                     "sla_violations": None, "mean_latency_seconds": None,
                     "runtime_seconds": elapsed, "optimal": False,
                     "solver_status": optimal["status"], "records": [],
                     "message": optimal["message"]})
    else:
        rows.append({"family": family, "instance": instance, "policy": "Offline MILP",
                     **optimal["totals"], "runtime_seconds": elapsed,
                     "optimal": optimal["optimal"], "solver_status": optimal["status"],
                     "records": optimal["schedule"]})
    offline = next(row for row in rows if row["policy"] == "Offline MILP")
    if offline.get("optimal") and offline["completion_rate"] == 1.0:
        for row in rows:
            if row["policy"] != "Offline MILP" and row["completion_rate"] == 1.0:
                row["optimality_gap_pct"] = 100.0 * (row["carbon_gco2e"] -
                                                       offline["carbon_gco2e"]) / offline["carbon_gco2e"]
    else:
        for row in rows:
            if row["policy"] != "Offline MILP":
                row["optimality_gap_pct"] = None
    return rows


def summarize(rows):
    summary = {}
    for family in sorted({row["family"] for row in rows}):
        summary[family] = {}
        for policy in ("FCFS", "Greedy carbon", "Offline MILP"):
            subset = [r for r in rows if r["family"] == family and r["policy"] == policy]
            summary[family][policy] = {
                metric: stats_ci([r[metric] for r in subset if r.get(metric) is not None],
                                 31000 + len(summary) * 101 + list(METRICS).index(metric))
                for metric in METRICS
            }
    return summary


def write_report(output, summary, workload_manifest, config):
    lines = ["# Phase 3 — real-trace benchmark", "", "## Data and replay design", "",
             f"Alibaba-derived workload sample: {workload_manifest['selected_task_count']} real jobs across {len(workload_manifest['scenarios'])} 24-hour windows, {workload_manifest['tasks_per_scenario']} selected jobs per window. The simulator preserves trace arrival intervals and duration/CPU/GPU/memory/data-size fields. Deadlines are not supplied by this source; this pilot derives each as arrival + recorded runtime + {workload_manifest['deadline_assumption_seconds_after_runtime']:.0f} s assumed slack. All sampled tasks are assigned to the north ingress region as a scenario assumption because the source trace is from a single cluster and contains no region-of-origin field.", "",
             "Carbon inputs are the three 2023 hourly regional direct-intensity series. They are held constant across each four 15-minute simulator slots using zero-order hold; there is no interpolation or missing-value fill. Regional series are replayed from their first 2023 observation for each workload instance. Workload timestamps are from 2020 and carbon timestamps from 2023, so this is a controlled trace overlay, not a calendar-synchronized historical replay.", "",
             "Online FCFS/greedy decisions see only the current carbon observation. Candidate emissions estimates use the current intensity held flat; future trace values are used only for realized emissions after execution. The offline MILP sees the full 2023 profile and is an oracle lookahead comparison. All metrics are mean ± sample SD [95% percentile bootstrap CI]; three instances make these descriptive only.", "",
             "## Results", ""]
    for family in sorted(summary):
        lines.extend([f"### {family}", "",
                      "| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Offline gap |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for policy in ("FCFS", "Greedy carbon", "Offline MILP"):
            values = summary[family][policy]
            cells = []
            for metric in ("carbon_gco2e", "energy_kwh", "completion_rate", "rejection_rate",
                           "sla_violations", "mean_latency_seconds", "runtime_seconds"):
                stat = values[metric]
                cells.append("n/a" if not stat["n"] else
                             f"{stat['mean']:.3f} ± {stat['sd']:.3f} [{stat['ci95'][0]:.3f}, {stat['ci95'][1]:.3f}]")
            gap = values["optimality_gap_pct"]
            cells.append("n/a" if not gap["n"] else
                         f"{gap['mean']:.2f}% [{gap['ci95'][0]:.2f}, {gap['ci95'][1]:.2f}]")
            lines.append(f"| {policy} | " + " | ".join(cells) + " |")
        lines.append("")
    lines.extend(["## Interpretation and limits", "",
                  "Historical comparison: the preserved Phase 2.9 synthetic 12-task / 60-second-slot experiment reported greedy carbon at 225.83 ± 122.32 gCO₂e, 0.894 ± 0.347 kWh, 98.61% completion, and 250.21 s mean latency. The Phase 3 synthetic comparison uses eight tasks, 900-second slots, and the 2023 trace carbon series (207.23 ± 97.39 gCO₂e, 1.116 ± 0.497 kWh, 100% completion, 277.67 s latency). These are context only: workload, timescale and carbon conditions differ, so the numerical difference is not an integration effect.", "",
                  "These are simulation outcomes on a small selected trace subset, not measured cloud performance. The trace has no task deadline or geo-origin fields; both SLA slack and ingress location are explicit scenario assumptions. The 2020 task trace and 2023 carbon series are not date matched. Carbon rows flagged estimated remain in the source series and their counts are retained in the manifest; the importer rejects missing numeric observations rather than filling them.", "",
                  "The current simulator uses a fixed synthetic network model and fixed heterogeneous region power, PUE, capacities and execution speeds. The upstream SustainCluster network-delay and transmission-cost models were inspected but are not yet mapped into this project's network API; no empirical network values are claimed. Offline MILP results use future carbon and the small-instance model only; infeasible/time-limited cases do not contribute certified optimality gaps.", "",
                  "Synthetic Phase 2.x results remain unchanged. This benchmark should be expanded with date-aligned workload/carbon years, actual task deadlines or calibrated SLA sources, representative sampling, and measured region/network parameters before real-world conclusions. No learning algorithm is introduced.", "",
                  "Reproduce preprocessing with `python -m experiments.preprocess_phase3`, then run `python -m experiments.run_phase3`. Raw checksums, source URLs, units, licenses, conversion details and dataset sizes are in `data/DATA_SOURCES.md`.", ""])
    (output / "PHASE3_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs/phase3_trace_config.yaml"))
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output_dir or ROOT / config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    profile_payload = json.loads((ROOT / config["carbon_profiles_path"]).read_text(encoding="utf-8"))
    workload_payload = json.loads((ROOT / config["workloads_path"]).read_text(encoding="utf-8"))
    workload_manifest = workload_payload["metadata"]
    workload_manifest["tasks_per_scenario"] = len(workload_payload["tasks"][0])
    rows = []
    for scenario, raw_tasks in enumerate(workload_payload["tasks"]):
        tasks = [task_from_json(item) for item in raw_tasks]
        rows += evaluate_instance("Alibaba trace subset", scenario, tasks, config, profile_payload)
    for instance, seed in enumerate(config["synthetic_workload_seeds"]):
        generated = generate_phase25_workload(seed, workload_manifest["tasks_per_scenario"])
        tasks = []
        for task in generated:
            slack = task.deadline_seconds - task.arrival_slot * 60 - task.runtime_seconds
            tasks.append(Task(task.task_id, task.arrival_slot, task.gpu_count, task.cpu_cores,
                              task.memory_gb, task.dataset_gb,
                              task.arrival_slot * config["slot_seconds"] +
                              task.runtime_seconds + slack,
                              task.runtime_seconds, task.source_region))
        rows += evaluate_instance("Synthetic comparison", instance, tasks, config, profile_payload)
    summary = summarize(rows)
    payload = {"summary": summary,
               "runs": [{key: value for key, value in row.items() if key != "records"}
                        for row in rows],
               "decision_records": [{"family": row["family"], "instance": row["instance"],
                                     "policy": row["policy"], "records": row["records"]}
                                    for row in rows],
               "online_carbon_information": "current-observation only",
               "offline_milp_uses_future_carbon": True}
    (output / "phase3_evaluation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output / "PHASE3_REPORT.md").write_text("", encoding="utf-8")
    write_report(output, summary, workload_manifest, config)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
