"""One-shot final confirmation on a post-protocol fresh synthetic holdout.

The script refuses to overwrite results, audits previous seed metadata, saves a
random post-protocol seed manifest before evaluation, and performs no training.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import secrets
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml

from agents.ippo_agent import IPPOScheduler, CarbonAwareSPTIPPOScheduler
from environment.task_generator import (generate_variable_workload,
                                        generate_diverse_workload,
                                        generate_phase25_workload)
from experiments.diagnose_spt_allowances import TracedIPPO, TracedCarbonSPT
from experiments.evaluate_baselines import make_phase25_environment
from experiments.train_ippo import ROOT


OUTPUT = ROOT / "results/research_alignment_v4_final_confirmation"
PROTOCOL = OUTPUT / "PROTOCOL_AMENDMENT.md"
POLICY_INDEX = ROOT / "results/research_alignment_v1/ui_policy_index.json"
CONFIG_PATH = ROOT / "configs/research_alignment_v1.yaml"
ALLOWANCE = 0.20
FAMILIES = {"variable": generate_variable_workload,
            "diverse": generate_diverse_workload,
            "bursty": generate_phase25_workload}
BASE_LABEL = "A-MARL-derived IPPO (fastest-execution SPT)"
PROPOSED_LABEL = "Carbon-aware latency-bounded SPT (20%)"
POLICY_SEEDS = (7, 19, 42, 73, 101)
BOOTSTRAP_REPLICATES = 10000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_ints(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for part in value for item in _as_ints(part)]
    if isinstance(value, dict):
        return []
    return []


def _walk_seed_fields(value, source, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if "seed" in str(key).lower():
                values = _as_ints(item)
                if values:
                    found.update(values)
                    source.add(str(key))
            _walk_seed_fields(item, source, found)
    elif isinstance(value, list):
        for item in value:
            _walk_seed_fields(item, source, found)


SEED_LINE = re.compile(r"\b(?:workload[_ -]?seeds?|heldout[_ -]?seeds?|validation[_ -]?seeds?|test[_ -]?seeds?|training[_ -]?seeds?|policy[_ -]?seeds?|seed)\b", re.I)
INTEGER_OR_RANGE = re.compile(r"(?<![A-Za-z0-9_])(\d{1,10})(?:\s*[–—-]\s*(\d{1,10}))?(?![A-Za-z0-9_])")


def audit_existing_seeds(excluded_dir: Path):
    """Collect seed-key values from prior structured records and seed lines."""
    used: set[int] = set()
    source_paths: set[str] = set()
    sources = [ROOT / "configs", ROOT / "results", ROOT / "experiments", ROOT / "tests"]
    allowed_suffixes = {".yaml", ".yml", ".json", ".jsonl", ".csv", ".md", ".txt", ".py"}
    for base in sources:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
                continue
            try:
                resolved = path.resolve()
                if excluded_dir == resolved or excluded_dir in resolved.parents:
                    continue
                content = path.read_text(encoding="utf-8-sig", errors="ignore")
            except OSError:
                continue
            local: set[int] = set()
            suffix = path.suffix.lower()
            if suffix in (".yaml", ".yml"):
                try:
                    parsed = yaml.safe_load(content)
                    _walk_seed_fields(parsed, set(), local)
                except yaml.YAMLError:
                    pass
            elif suffix == ".json":
                try:
                    _walk_seed_fields(json.loads(content), set(), local)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif suffix == ".jsonl":
                for line in content.splitlines():
                    try:
                        _walk_seed_fields(json.loads(line), set(), local)
                    except (json.JSONDecodeError, TypeError):
                        continue
            elif suffix == ".csv":
                try:
                    for row in csv.DictReader(content.splitlines()):
                        for key, value in row.items():
                            if key and "seed" in key.lower() and value:
                                try:
                                    local.add(int(float(value)))
                                except ValueError:
                                    continue
                except csv.Error:
                    pass
            # Human reports and source scripts often record seed lists that
            # predate structured artifacts. Parse only lines mentioning seeds.
            if suffix in {".md", ".txt", ".py"}:
                for line in content.splitlines():
                    if not SEED_LINE.search(line):
                        continue
                    for first, last in INTEGER_OR_RANGE.findall(line):
                        start = int(first)
                        end = int(last) if last else start
                        if start <= end and end - start <= 10000:
                            local.update(range(start, end + 1))
            if local:
                used.update(local)
                source_paths.add(str(path.relative_to(ROOT)))
    return sorted(used), sorted(source_paths)


def generate_and_save_manifest(output: Path, config: dict, policy_index: dict, runner_path: Path):
    if not PROTOCOL.is_file():
        raise FileNotFoundError(f"Frozen protocol amendment is required first: {PROTOCOL}")
    protocol_hash = sha256(PROTOCOL)
    audited_values, audit_sources = audit_existing_seeds(output.resolve())
    audited = set(audited_values)
    seeds: list[int] = []
    while len(seeds) < 6:
        candidate = secrets.randbits(32)
        if candidate not in audited and candidate not in seeds:
            seeds.append(candidate)
    generated = datetime.now(timezone.utc).isoformat()
    protocol_frozen = datetime.fromtimestamp(PROTOCOL.stat().st_mtime, timezone.utc).isoformat()
    manifest = {
        "manifest_id": "research_alignment_v4_fresh_holdout",
        "generated_utc": generated,
        "protocol_frozen_utc_file_mtime": protocol_frozen,
        "protocol_sha256": protocol_hash,
        "seed_generator": "Python secrets.randbits(32), backed by the operating-system cryptographic random source",
        "python_version": sys.version,
        "workload_seeds": seeds,
        "workload_families": config["workload_families"],
        "workload_instances": [f"{family}:{seed}" for family in config["workload_families"] for seed in seeds],
        "tasks_per_workload": config["tasks_per_episode"],
        "policy_seeds": list(POLICY_SEEDS),
        "audited_prior_seed_values": audited_values,
        "audited_prior_seed_value_count": len(audited_values),
        "audit_source_paths": audit_sources,
        "seed_overlap": sorted(set(seeds) & audited),
        "audit_scope": "structured seed-key values in prior configs/results; seed-mentioned integer values/ranges in prior reports, scripts and tests; current v4 output directory excluded",
        "test_workload_outcomes_previewed_before_manifest": False,
        "previous_holdout_seed_sets_not_reused": [75101, 75102, 75103, 75104, 75105, 75106],
        "runner_sha256": sha256(runner_path),
        "policy_index_sha256": sha256(POLICY_INDEX),
        "training_config_sha256": sha256(CONFIG_PATH),
    }
    if manifest["seed_overlap"]:
        raise RuntimeError(f"Seed collision detected; do not evaluate: {manifest['seed_overlap']}")
    target = output / "seed_manifest.json"
    if target.exists():
        raise FileExistsError(f"Seed manifest already exists; refusing to redraw or overwrite: {target}")
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def crossed_bootstrap(values_by_pair, workload_ids, policy_seeds, seed, replicates=BOOTSTRAP_REPLICATES):
    complete = [(p, w) for p in policy_seeds for w in workload_ids
                if (p, w) in values_by_pair and values_by_pair[p, w] is not None]
    if not complete:
        return {"n_pairs": 0, "mean": None, "ci95": [None, None]}
    vals = [float(values_by_pair[p, w]) for p, w in complete]
    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        pdraw = rng.choices(policy_seeds, k=len(policy_seeds))
        wdraw = rng.choices(workload_ids, k=len(workload_ids))
        sample = [values_by_pair[p, w] for p in pdraw for w in wdraw
                  if (p, w) in values_by_pair and values_by_pair[p, w] is not None]
        samples.append(statistics.mean(sample))
    samples.sort()
    return {"n_pairs": len(vals), "mean": statistics.mean(vals),
            "ci95": [samples[int(.025 * (replicates - 1))], samples[int(.975 * (replicates - 1))]],
            "upper_one_sided_95": samples[int(.95 * (replicates - 1))],
            "ci_method": "two-factor crossed percentile bootstrap over workload instances and policy seeds",
            "bootstrap_replicates": replicates}


def wild_cluster_p(values_by_pair, workload_ids, policy_seeds, seed, alternative="two-sided", replicates=9999):
    pairs = [(p, w) for p in policy_seeds for w in workload_ids
             if (p, w) in values_by_pair and values_by_pair[p, w] is not None]
    observed = statistics.mean(values_by_pair[p, w] for p, w in pairs)
    centered = {(p, w): values_by_pair[p, w] - observed for p, w in pairs}
    rng = random.Random(seed)
    null_stats = []
    for _ in range(replicates):
        wp = {p: rng.choice((-1.0, 1.0)) for p in policy_seeds}
        ww = {w: rng.choice((-1.0, 1.0)) for w in workload_ids}
        weighted = [centered[p, w] * (wp[p] + ww[w] - wp[p] * ww[w]) for p, w in pairs]
        null_stats.append(statistics.mean(weighted))
    if alternative == "less":
        exceed = sum(value <= observed for value in null_stats)
    elif alternative == "greater":
        exceed = sum(value >= observed for value in null_stats)
    else:
        exceed = sum(abs(value) >= abs(observed) for value in null_stats)
    return {"mean_paired_difference": observed,
            "p_value": (exceed + 1) / (replicates + 1),
            "test": "two-way crossed wild-cluster bootstrap under zero-mean null (policy seed and workload instance clusters)",
            "alternative": alternative, "replicates": replicates}


def summarize(run_rows, replicates=BOOTSTRAP_REPLICATES):
    labels = (BASE_LABEL, PROPOSED_LABEL)
    metrics = ("carbon_gco2e", "carbon_gco2e_per_completed", "energy_kwh",
               "completion_rate", "rejections", "rejection_rate", "sla_violations",
               "mean_latency_seconds", "total_latency_seconds", "deferrals",
               "intervention_count", "intervention_rate")
    workload_ids = sorted({row["workload_id"] for row in run_rows})
    output = {"per_method": {}, "paired_proposed_minus_base": {}}
    lookup = {(row["condition"], row["policy_seed"], row["workload_id"]): row for row in run_rows}
    for ci, label in enumerate(labels):
        group = [r for r in run_rows if r["condition"] == label]
        output["per_method"][label] = {}
        for mi, metric in enumerate(metrics):
            matrix = {(r["policy_seed"], r["workload_id"]): r.get(metric) for r in group}
            output["per_method"][label][metric] = crossed_bootstrap(
                matrix, workload_ids, POLICY_SEEDS, 910000 + ci * 100 + mi, replicates)
    deltas = []
    for policy_seed in POLICY_SEEDS:
        for workload_id in workload_ids:
            b = lookup[(BASE_LABEL, policy_seed, workload_id)]
            p = lookup[(PROPOSED_LABEL, policy_seed, workload_id)]
            diff = {"policy_seed": policy_seed, "workload_id": workload_id}
            for metric in metrics:
                bv, pv = b.get(metric), p.get(metric)
                diff[metric] = pv - bv if bv is not None and pv is not None else None
            deltas.append(diff)
    output["paired_proposed_minus_base"] = {}
    for mi, metric in enumerate(metrics):
        matrix = {(r["policy_seed"], r["workload_id"]): r[metric] for r in deltas}
        summary = crossed_bootstrap(matrix, workload_ids, POLICY_SEEDS, 920000 + mi, replicates)
        summary["wild_cluster_test_two_sided"] = wild_cluster_p(
            matrix, workload_ids, POLICY_SEEDS, 930000 + mi, "two-sided")
        if metric in ("rejection_rate", "sla_violations"):
            summary["one_sided_service_noninferiority_upper_95"] = crossed_bootstrap(
                matrix, workload_ids, POLICY_SEEDS, 940000 + mi, replicates)["upper_one_sided_95"]
            summary["noninferiority_margin"] = 0.0
            summary["noninferiority_established_by_ci"] = (
                summary["one_sided_service_noninferiority_upper_95"] <= 0.0)
            summary["wild_cluster_test_noninferiority"] = wild_cluster_p(
                matrix, workload_ids, POLICY_SEEDS, 950000 + mi, "less")
        output["paired_proposed_minus_base"][metric] = summary
    by_family = {}
    for family in sorted({r["family"] for r in run_rows}):
        family_rows = [r for r in run_rows if r["family"] == family]
        base_ix = {(r["policy_seed"], r["workload_id"]): r for r in family_rows if r["condition"] == BASE_LABEL}
        proposed_ix = {(r["policy_seed"], r["workload_id"]): r for r in family_rows if r["condition"] == PROPOSED_LABEL}
        by_family[family] = {}
        for mi, metric in enumerate(metrics):
            matrix = {}
            for key, b in base_ix.items():
                p = proposed_ix[key]
                matrix[key] = p.get(metric) - b.get(metric) if p.get(metric) is not None and b.get(metric) is not None else None
            by_family[family][metric] = crossed_bootstrap(
                matrix, sorted({r["workload_id"] for r in family_rows}), POLICY_SEEDS,
                960000 + len(by_family) * 100 + mi, replicates)
    output["paired_by_family"] = by_family
    return output


def evaluate_condition(workload, family, workload_seed, policy_seed, condition, common, checkpoint_path):
    env = make_phase25_environment(dynamic_carbon=True, profile_slots=512)
    config = dict(common)
    config["algorithm"] = "ippo"
    config["spt_intervention_probability"] = 1.0
    if condition == BASE_LABEL:
        config.pop("spt_method", None)
        scheduler_cls = TracedIPPO
    else:
        config["spt_method"] = "carbon_latency_bounded"
        config["spt_latency_allowance_fraction"] = ALLOWANCE
        scheduler_cls = TracedCarbonSPT
    random.seed(policy_seed)
    torch.manual_seed(policy_seed)
    capacities = {name: (r.resources.gpus, r.resources.cpu_cores, r.resources.memory_gb)
                  for name, r in env.regions.items()}
    scheduler = scheduler_cls(env.region_names, capacities, config, policy_seed,
                              deterministic=False, condition=condition)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    scheduler.load_checkpoint(checkpoint["agents"])
    result = env.run(workload, scheduler)
    totals = result["totals"]
    trace = scheduler.decision_trace
    interventions = [d for d in trace if d["intervention"]]
    if len(interventions) != totals.get("spt_overrides", 0):
        raise RuntimeError("Traced and simulator SPT intervention counts disagree")
    completed = totals["completed"]
    return {
        "condition": condition, "family": family, "workload_seed": workload_seed,
        "workload_id": f"{family}:{workload_seed}", "policy_seed": policy_seed,
        "tasks": len(workload), "carbon_gco2e": totals["carbon_gco2e"],
        "carbon_gco2e_per_completed": totals["carbon_gco2e"] / completed if completed else None,
        "energy_kwh": totals["energy_kwh"], "completed": completed,
        "completion_rate": totals["completion_rate"], "rejections": totals["rejected"],
        "rejection_rate": totals["rejection_rate"], "sla_violations": totals["sla_violations"],
        "mean_latency_seconds": totals["mean_latency_seconds"],
        "total_latency_seconds": totals["total_latency_seconds"],
        "deferrals": sum(r["action"] == "defer" for r in result["records"]),
        "intervention_count": len(interventions),
        "decision_count": len(trace),
        "intervention_rate": len(interventions) / max(1, len(trace)),
        "actual_integrated_region_emissions_gco2e": totals["carbon_gco2e"],
        "task_outcomes": result["records"],
        "decision_trace": trace,
    }


def main():
    if OUTPUT.exists():
        allowed = {"PROTOCOL_AMENDMENT.md"}
        unexpected = [p.name for p in OUTPUT.iterdir() if p.name not in allowed]
        if unexpected:
            raise FileExistsError(f"Refusing to overwrite prior v4 outputs: {unexpected}")
    else:
        OUTPUT.mkdir(parents=True)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    policy_index = json.loads(POLICY_INDEX.read_text(encoding="utf-8"))
    if config["test_seeds"] != [75101, 75102, 75103, 75104, 75105, 75106]:
        raise RuntimeError("Frozen historical seed list changed; inspect protocol and stop")
    if policy_index.get("selected_allowance_fraction") != 0.0:
        raise RuntimeError("Expected existing proposed-epsilon-zero checkpoints for the frozen shared policy")
    common = dict(policy_index["config"])
    common["tasks_per_episode"] = config["tasks_per_episode"]
    common["spt_entropy_fraction"] = config["spt_entropy_fraction"]
    common["spt_intervention_probability"] = 1.0
    manifest = generate_and_save_manifest(OUTPUT, config, policy_index, Path(__file__).resolve())
    print(f"Saved new seed manifest before evaluation: {OUTPUT / 'seed_manifest.json'}", flush=True)

    checkpoint_paths = {seed: Path(policy_index["proposed_checkpoints"][str(seed)]) for seed in POLICY_SEEDS}
    for path in checkpoint_paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    checkpoint_hashes = {str(seed): sha256(path) for seed, path in checkpoint_paths.items()}
    config_snapshot = {
        "source_config": str(CONFIG_PATH.relative_to(ROOT)),
        "policy_index": str(POLICY_INDEX.relative_to(ROOT)),
        "common_scheduler_config": common,
        "test_conditions": [BASE_LABEL, PROPOSED_LABEL],
        "proposed_allowance_fraction": ALLOWANCE,
        "policy_seeds": list(POLICY_SEEDS),
        "workload_seeds": manifest["workload_seeds"],
        "workload_families": config["workload_families"],
        "tasks_per_workload": config["tasks_per_episode"],
        "profile": "dynamic synthetic, 512 slots; make_phase25_environment",
        "checkpoint_sha256_by_policy_seed": checkpoint_hashes,
        "python_version": sys.version,
        "torch_version": torch.__version__,
        "pyyaml_version": yaml.__version__,
        "full_test_suite": "77 passed before seed generation/evaluation",
        "seed_manifest_sha256": sha256(OUTPUT / "seed_manifest.json"),
        "runner_sha256": sha256(Path(__file__).resolve()),
    }
    (OUTPUT / "frozen_evaluation_config.json").write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")

    generated_workloads = {}
    for family in config["workload_families"]:
        for workload_seed in manifest["workload_seeds"]:
            generated_workloads[(family, workload_seed)] = FAMILIES[family](
                workload_seed, config["tasks_per_episode"])
    rows = []
    trace_path = OUTPUT / "decision_traces.jsonl"
    outcomes_path = OUTPUT / "task_outcomes.jsonl"
    with trace_path.open("w", encoding="utf-8") as trace_file, outcomes_path.open("w", encoding="utf-8") as outcomes_file:
        for family in config["workload_families"]:
            for workload_seed in manifest["workload_seeds"]:
                canonical = generated_workloads[(family, workload_seed)]
                for policy_seed in POLICY_SEEDS:
                    pair_workload_id = f"{family}:{workload_seed}"
                    for condition in (BASE_LABEL, PROPOSED_LABEL):
                        from copy import deepcopy
                        run = evaluate_condition(deepcopy(canonical), family, workload_seed,
                                                 policy_seed, condition, common,
                                                 checkpoint_paths[policy_seed])
                        trace = run.pop("decision_trace")
                        outcomes = run.pop("task_outcomes")
                        for decision in trace:
                            trace_file.write(json.dumps({
                                "condition": condition, "family": family,
                                "workload_seed": workload_seed, "policy_seed": policy_seed,
                                **decision}, sort_keys=True) + "\n")
                        for outcome in outcomes:
                            outcomes_file.write(json.dumps({
                                "condition": condition, "family": family,
                                "workload_seed": workload_seed, "policy_seed": policy_seed,
                                **outcome}, sort_keys=True) + "\n")
                        rows.append(run)
                        print(f"Completed {condition} | {pair_workload_id} | policy {policy_seed}", flush=True)
    expected = len(config["workload_families"]) * len(manifest["workload_seeds"]) * len(POLICY_SEEDS) * 2
    if len(rows) != expected:
        raise RuntimeError(f"Expected {expected} method runs, got {len(rows)}")
    metrics_path = OUTPUT / "run_metrics.jsonl"
    metrics_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    summary = summarize(rows)
    result = {
        "study": "Research alignment v4: final confirmation on fresh synthetic holdout",
        "status": "complete_synthetic_confirmatory_evaluation",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_amendment_sha256": manifest["protocol_sha256"],
        "seed_manifest": "seed_manifest.json",
        "frozen_config": "frozen_evaluation_config.json",
        "methods": [BASE_LABEL, PROPOSED_LABEL],
        "allowance_fraction": ALLOWANCE,
        "training_launched": False,
        "test_workloads_evaluated_once_per_condition": True,
        "heldout_data_synthetic": True,
        "real_world_generalization_claim": False,
        "runs": len(rows),
        "matched_pairs": len(rows) // 2,
        "summary": summary,
        "artifact_paths": {"run_metrics": "run_metrics.jsonl",
                           "decision_traces": "decision_traces.jsonl",
                           "task_outcomes": "task_outcomes.jsonl"},
    }
    (OUTPUT / "final_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    report = write_report(result, manifest, rows)
    (OUTPUT / "FINAL_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": result["status"], "output_dir": str(OUTPUT.resolve()),
                      "matched_pairs": result["matched_pairs"],
                      "paired_summary": summary["paired_proposed_minus_base"]}, indent=2))


def write_report(result, manifest, rows):
    summary = result["summary"]
    paired = summary["paired_proposed_minus_base"]
    per_method = summary["per_method"]
    def m(label, metric):
        return per_method[label][metric]["mean"]
    lines = [
        "# Final confirmatory comparison on a fresh synthetic holdout", "",
        "**Conclusion scope:** this is a confirmatory comparison on newly generated synthetic workloads. It does not establish real-world generalization.", "",
        "## Protocol", "",
        f"Six post-protocol workload seeds: `{manifest['workload_seeds']}`; families: `{', '.join(manifest['workload_families'])}`; 24 tasks per workload.",
        f"Five policy seeds `{list(POLICY_SEEDS)}` crossed with 18 workload instances produced {result['matched_pairs']} matched pairs ({result['runs']} method runs). Both methods used the same existing checkpoint per policy seed, stochastic action sampling, entropy fraction 0.8, intervention probability 1.0, same environment and carbon profile; no training or weight updates occurred. Proposed allowance was fixed at 20%.",
        "Fresh workload seeds were drawn from Python's OS-backed `secrets.randbits(32)` after the protocol amendment was frozen. The seed manifest records the audit scope, previous seed values, no-overlap result, source paths and hashes. The held-out workloads were evaluated once per method condition.",
        "The reference selects the feasible destination with minimum execution time. The proposed selector admits destinations no slower than 1.20 times the minimum migration-plus-execution latency and then selects the lowest estimated carbon candidate. Simulator resource/deadline masks and reward remain unchanged.",
        "",
        "## Paired results", "",
        "Differences are proposed minus reference. Intervals are 95% two-factor crossed percentile-bootstrap intervals across workload instances and policy seeds (10,000 replicates). The table reports the paired wild-cluster bootstrap test p-value where available.",
        "",
        "| Metric | Reference mean | Proposed mean | Paired difference [95% CI] | Two-way wild-bootstrap p |", "|---|---:|---:|---:|---:|"
    ]
    metric_names = {
        "carbon_gco2e": ("Total emissions (gCO₂e/run)", 2),
        "carbon_gco2e_per_completed": ("Emissions per completed task (gCO₂e)", 3),
        "energy_kwh": ("Energy (kWh/run)", 4),
        "completion_rate": ("Completion rate", 4),
        "rejections": ("Rejections/run", 3),
        "rejection_rate": ("Rejection rate", 4),
        "sla_violations": ("SLA violations/run", 3),
        "mean_latency_seconds": ("Mean latency (seconds)", 2),
        "deferrals": ("Deferrals/run", 3),
        "intervention_count": ("SPT interventions/run", 2),
        "intervention_rate": ("SPT intervention rate", 4),
    }
    for metric, (name, digits) in metric_names.items():
        stat = paired[metric]
        ci = stat["ci95"]
        p = stat["wild_cluster_test_two_sided"]["p_value"]
        lines.append(f"| {name} | {m(BASE_LABEL, metric):.{digits}f} | {m(PROPOSED_LABEL, metric):.{digits}f} | {stat['mean']:.{digits}f} [{ci[0]:.{digits}f}, {ci[1]:.{digits}f}] | {p:.4f} |")
    ni = paired["rejection_rate"]
    ni_upper = ni["one_sided_service_noninferiority_upper_95"]
    lines += [
        "", "## Service non-inferiority", "",
        "The prespecified service margin was zero additional rejections/SLA violations per task (0 percentage points), based on the simulator's hard per-task deadline feasibility rule and its mapping of SLA violations to rejections. The one-sided 95% upper bound for the rejection-rate difference is ",
        f"**{ni_upper:.6f}** (one-sided two-way wild-cluster bootstrap p={ni['wild_cluster_test_noninferiority']['p_value']:.4f}). Service non-inferiority is {'established under this simulator endpoint' if ni_upper <= 0 else 'not established'} by the prespecified interval criterion. The simulator defines no separate aggregate mean-latency tolerance; latency is reported as a secondary outcome.",
        "", "## Interpretation and limitations", "",
        "Interpret carbon, energy, latency, completion, rejection/SLA, deferrals and intervention frequency together. The carbon metric is simulated with synthetic regional profiles, not measured operational emissions. Candidate carbon values are estimates; total episode emissions are integrated simulator outcomes. Checkpoint reuse isolates the inference-time selector on existing weights; it does not estimate the effect of retraining a policy specifically for the 20% rule. Five policy seeds and 18 synthetic workload instances provide limited population evidence. Wild-cluster p-values are approximate with only five policy-seed clusters and are not multiplicity-adjusted; treat them alongside intervals and outcomes. No real-world generalization claim is made.",
        "", "## Reproducibility", "",
        "The exact seed manifest, config snapshot, checkpoint hashes, runner hash, command, test-suite result, per-run metrics, decision traces and task outcomes are saved beside this report. The evaluation runner refuses to overwrite prior artifacts.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
