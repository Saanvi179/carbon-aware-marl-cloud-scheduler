"""Render presentation charts from the saved v4 final confirmation only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/research_alignment_v4_final_confirmation/final_summary.json"
OUT = ROOT / "assets/presentation/research_alignment_v4"
BASE = "A-MARL-derived IPPO (fastest-execution SPT)"
PROPOSED = "Carbon-aware latency-bounded SPT (20%)"
COLORS = {BASE: "#24557A", PROPOSED: "#D97925"}
SHORT = {BASE: "Base A-MARL-derived IPPO", PROPOSED: "Proposed SPT (20%)"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def draw_metric(payload, metric, title, unit, filename, formatter=None):
    summary = payload["summary"]
    fig, (ax_abs, ax_delta) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.25, 1]})
    y = np.array([1, 0])
    labels = [SHORT[BASE], SHORT[PROPOSED]]
    for yi, label in zip(y, (BASE, PROPOSED)):
        stat = summary["per_method"][label][metric]
        mean, low, high = stat["mean"], stat["ci95"][0], stat["ci95"][1]
        ax_abs.errorbar(mean, yi, xerr=[[mean - low], [high - mean]], fmt="o", ms=8,
                        capsize=5, lw=2, color=COLORS[label], label=SHORT[label])
        text = formatter(mean) if formatter else f"{mean:.3f}"
        ax_abs.annotate(text, (mean, yi), xytext=(8, 0), textcoords="offset points",
                        va="center", fontsize=9, color=COLORS[label])
    ax_abs.set_yticks(y, labels)
    ax_abs.set_title("Method means", loc="left", fontsize=11, weight="bold")
    ax_abs.set_xlabel(unit)
    ax_abs.grid(axis="x", alpha=.25)
    ax_abs.spines[["top", "right", "left"]].set_visible(False)
    ax_abs.tick_params(axis="y", length=0)

    diff = summary["paired_proposed_minus_base"][metric]
    mean, low, high = diff["mean"], diff["ci95"][0], diff["ci95"][1]
    ax_delta.axvline(0, color="#444444", lw=1.2, ls="--", zorder=0)
    ax_delta.errorbar(mean, 0, xerr=[[mean - low], [high - mean]], fmt="o", ms=9,
                      capsize=6, lw=2.2, color="#4B7F52")
    delta_text = formatter(mean) if formatter else f"{mean:+.3f}"
    ax_delta.annotate(delta_text, (mean, 0), xytext=(8, 10), textcoords="offset points",
                      fontsize=9, color="#315A37")
    ax_delta.set_yticks([])
    ax_delta.set_title("Paired proposed − base", loc="left", fontsize=11, weight="bold")
    ax_delta.set_xlabel(f"Difference ({unit}) · 95% CI")
    ax_delta.grid(axis="x", alpha=.25)
    ax_delta.spines[["top", "right", "left"]].set_visible(False)
    ax_delta.text(.02, -.22, f"95% crossed-bootstrap intervals · {diff['n_pairs']} matched pairs",
                  transform=ax_delta.transAxes, fontsize=8.5, color="#555555")

    fig.suptitle(title, x=.07, y=.99, ha="left", fontsize=16, weight="bold")
    fig.text(.07, .925, "Fresh synthetic holdout · confirmatory v4 results · no real-world inference",
             fontsize=9.5, color="#555555")
    fig.text(.07, .025, "Intervals resample workload instances and policy seeds as crossed factors (10,000 replicates).",
             fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0.04, .08, .98, .90), w_pad=3.2)
    for extension in ("png", "svg", "pdf"):
        target = OUT / f"{filename}.{extension}"
        fig.savefig(target, dpi=320, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_service(payload):
    summary = payload["summary"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.3), gridspec_kw={"width_ratios": [1.25, 1]})
    items = [("completion_rate", "Completion rate", "Fraction", lambda x: f"{x:.1%}"),
             ("sla_violations", "SLA violations per run", "Tasks / 24-task run", lambda x: f"{x:.2f}")]
    for row, (metric, title, unit, formatter) in enumerate(items):
        ax_abs, ax_delta = axes[row]
        y = np.array([1, 0])
        for yi, label in zip(y, (BASE, PROPOSED)):
            stat = summary["per_method"][label][metric]
            mean, low, high = stat["mean"], stat["ci95"][0], stat["ci95"][1]
            ax_abs.errorbar(mean, yi, xerr=[[mean - low], [high - mean]], fmt="o", ms=8,
                            capsize=5, lw=2, color=COLORS[label])
            ax_abs.annotate(formatter(mean), (mean, yi), xytext=(8, 0), textcoords="offset points",
                            va="center", fontsize=9, color=COLORS[label])
        ax_abs.set_yticks(y, [SHORT[BASE], SHORT[PROPOSED]])
        ax_abs.set_title(f"{title}: method means", loc="left", fontsize=10.5, weight="bold")
        ax_abs.set_xlabel(unit)
        ax_abs.grid(axis="x", alpha=.25)
        ax_abs.spines[["top", "right", "left"]].set_visible(False)
        ax_abs.tick_params(axis="y", length=0)

        diff = summary["paired_proposed_minus_base"][metric]
        mean, low, high = diff["mean"], diff["ci95"][0], diff["ci95"][1]
        ax_delta.axvline(0, color="#444444", lw=1.2, ls="--", zorder=0)
        ax_delta.errorbar(mean, 0, xerr=[[mean - low], [high - mean]], fmt="o", ms=9,
                          capsize=6, lw=2.2, color="#4B7F52")
        ax_delta.annotate(formatter(mean), (mean, 0), xytext=(8, 10), textcoords="offset points",
                          fontsize=9, color="#315A37")
        ax_delta.set_yticks([])
        ax_delta.set_title(f"{title}: paired difference", loc="left", fontsize=10.5, weight="bold")
        ax_delta.set_xlabel(f"Proposed − base ({unit}) · 95% CI")
        ax_delta.grid(axis="x", alpha=.25)
        ax_delta.spines[["top", "right", "left"]].set_visible(False)
    fig.suptitle("Service outcomes", x=.07, y=.99, ha="left", fontsize=16, weight="bold")
    fig.text(.07, .945, "Fresh synthetic holdout · completion and hard-deadline rejection/SLA outcomes",
             fontsize=9.5, color="#555555")
    fig.text(.07, .015, "Zero additional SLA violations is the frozen non-inferiority margin; the report does not claim robust formal non-inferiority.",
             fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(.04, .06, .98, .91), h_pad=2.8, w_pad=3.0)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(OUT / f"completion_sla.{extension}", dpi=320, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    if not RESULTS.is_file():
        raise FileNotFoundError(f"Authoritative v4 results missing: {RESULTS}")
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    if payload.get("status") != "complete_synthetic_confirmatory_evaluation":
        raise ValueError(f"Unexpected final result status: {payload.get('status')}")
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.labelsize": 9.5, "svg.fonttype": "none"})
    draw_metric(payload, "carbon_gco2e", "Total carbon emissions", "gCO₂e per 24-task run", "carbon_emissions")
    draw_metric(payload, "carbon_gco2e_per_completed", "Carbon emissions per completed task", "gCO₂e per completed task", "carbon_per_completed_task")
    draw_metric(payload, "energy_kwh", "Energy consumption", "kWh per 24-task run", "energy_consumption")
    draw_service(payload)
    draw_metric(payload, "mean_latency_seconds", "Execution latency trade-off", "Mean seconds per completed task", "latency_tradeoff")
    files = sorted(p for p in OUT.iterdir() if p.suffix.lower() in {".png", ".svg", ".pdf"})
    manifest = {"source_results": str(RESULTS.relative_to(ROOT)),
                "source_sha256": digest(RESULTS),
                "source_status": payload["status"],
                "chart_files": [p.name for p in files],
                "render_script": str(Path(__file__).relative_to(ROOT)),
                "note": "Charts visualize saved v4 final confirmation only; no fresh simulation or evaluation performed."}
    (OUT / "chart_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
