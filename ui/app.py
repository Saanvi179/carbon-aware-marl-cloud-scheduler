"""Local Streamlit demo for the existing carbon-aware cloud simulator."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ui.runner import (AUXILIARY_METHODS, EXPLANATIONS, PRIMARY_METHODS,
                       WORKLOADS, ROOT, run_comparison)


st.set_page_config(page_title="Cloud Scheduler Demo", page_icon="☁️", layout="wide")


def metric_cards(row):
    columns = st.columns(6)
    values = (
        ("Energy", f"{row['Energy (kWh)']:.3f} kWh"),
        ("Emissions", f"{row['Carbon (gCO₂e)']:.1f} gCO₂e"),
        ("Per completed task", "—" if row["gCO₂e / completed task"] is None else
         f"{row['gCO₂e / completed task']:.2f} gCO₂e"),
        ("Completion", f"{100 * row['Completion rate']:.1f}%"),
        ("SLA violations", f"{int(row['SLA violations'])}"),
        ("Mean latency", f"{row['Mean latency (s)']:.1f} s"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)


def simulation_tab():
    st.subheader("Fresh synthetic demonstration")
    st.info("This creates a new illustrative synthetic workload. Its outcomes are not part of the saved v4 confirmatory evaluation and must not be read as research evidence.")
    with st.form("simulation_form"):
        left, mid, right = st.columns((2, 2, 1))
        with left:
            workload_name = st.selectbox("Workload family", list(WORKLOADS))
            st.markdown("**Primary comparison**")
            st.caption("Both frozen research methods run on the same fresh tasks, with active SPT intervention.")
        with mid:
            seed = st.number_input("Workload seed", min_value=0, max_value=2_147_483_647,
                                   value=7, step=1)
            with st.expander("Optional auxiliary scheduler demos"):
                st.caption("Auxiliary outputs are displayed separately and are not part of the primary research comparison.")
                auxiliary = st.multiselect("Auxiliary demos", AUXILIARY_METHODS, default=[])
                horizon = st.select_slider("Forecast MPC horizon", options=[2, 4], value=2,
                                           format_func=lambda value: f"{value} hours")
        with right:
            st.markdown("**Frozen methods**")
            st.caption("A-MARL-derived IPPO SPT vs. carbon-aware SPT with a fixed 20% latency allowance.")
        submitted = st.form_submit_button("Run comparison", type="primary", use_container_width=True)
    if submitted:
        try:
            with st.spinner("Running the fresh synthetic demonstration…"):
                st.session_state["demo_result"] = run_comparison(
                    workload_name, [*PRIMARY_METHODS, *auxiliary], int(seed), float(horizon))
        except Exception as exc:
            st.exception(exc)
    result = st.session_state.get("demo_result")
    if not result:
        st.info("Choose a synthetic workload and run the two primary methods to compare their task decisions.")
        return

    st.markdown(f"**Fresh demo only** · {result['workload_name']} · seed {result['seed']} · {result['task_count']} tasks")
    primary_rows = [row for row in result["rows"] if row["Algorithm"] in PRIMARY_METHODS]
    auxiliary_rows = [row for row in result["rows"] if row["Algorithm"] in AUXILIARY_METHODS]
    st.markdown("**Primary method outcomes for this synthetic demonstration**")
    st.dataframe(pd.DataFrame(primary_rows).set_index("Algorithm").style.format({
        "Energy (kWh)": "{:.3f}", "Carbon (gCO₂e)": "{:.1f}",
        "gCO₂e / completed task": "{:.2f}", "Completion rate": "{:.1%}",
        "Mean latency (s)": "{:.1f}",
    }), use_container_width=True)

    selected = st.selectbox("Compare primary scheduling decisions", PRIMARY_METHODS, key="inspect_algorithm")
    trace = result["traces"][selected]
    st.info(trace["explanation"])
    st.markdown("**Regional task placements**")
    placement_df = pd.DataFrame([{"Region": key, "Completed tasks": value}
                                 for key, value in trace["placements"].items()])
    st.bar_chart(placement_df.set_index("Region"))
    st.markdown("**Task-by-task outcomes**")
    st.dataframe(pd.DataFrame(trace["decisions"]), hide_index=True, use_container_width=True)
    agent_decisions = trace.get("agent_decisions", [])
    if agent_decisions:
        with st.expander("Agent policy diagnostics"):
            st.caption("Fresh demo proposals, entropy values, masks and intervention outcomes. Not confirmatory test observations.")
            st.dataframe(pd.DataFrame(agent_decisions), hide_index=True, use_container_width=True)

    if auxiliary_rows:
        with st.expander("Auxiliary and historical demo outcomes"):
            st.caption("These algorithms are supporting demonstrations only and are excluded from the primary research comparison.")
            st.dataframe(pd.DataFrame(auxiliary_rows).set_index("Algorithm"), use_container_width=True)


def saved_tab():
    st.subheader("Saved Phase 3.3 benchmark")
    st.caption("These are historical trace-based benchmark outputs loaded from the preserved Phase 3.3 corrected CSV. Opening this view does not run a simulation.")
    csv_path = ROOT / "results/phase33_corrected_v5/phase33_corrected_runs.csv"
    json_path = ROOT / "results/phase33_corrected_v5/phase33_corrected_evaluation.json"
    if not csv_path.exists() or not json_path.exists():
        st.error("Saved Phase 3.3 v5 outputs were not found in the expected results folder.")
        return
    rows = pd.read_csv(csv_path)
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    family = st.selectbox("Saved workload family", sorted(rows["family"].unique()))
    family_rows = rows.loc[rows["family"] == family]
    policies = ["FCFS", "Greedy carbon", "Forecast MPC (2h, orig)",
                "Corrected MPC (2h)", "Corrected MPC (4h)"]
    grouped = family_rows.groupby("policy").agg(
        instances=("instance", "nunique"), energy_kwh=("energy_kwh", "mean"),
        carbon_gco2e=("carbon_gco2e", "mean"),
        carbon_per_completed=("carbon_gco2e_per_completed", "mean"),
        completion_rate=("completion_rate", "mean"),
        sla_violations=("sla_violations", "mean"),
        mean_latency_seconds=("mean_latency_seconds", "mean"),
    ).reindex(policies).dropna(how="all")
    st.markdown(f"**Saved benchmark result** · {family} · {int(grouped['instances'].max())} windows")
    st.caption("Values are arithmetic means calculated from the saved run-level rows for this family; the corrected report contains the benchmark's uncertainty intervals.")
    st.dataframe(grouped.style.format({
        "energy_kwh": "{:.3f}", "carbon_gco2e": "{:.1f}",
        "carbon_per_completed": "{:.2f}", "completion_rate": "{:.1%}",
        "sla_violations": "{:.2f}", "mean_latency_seconds": "{:.1f}",
    }), use_container_width=True)
    st.bar_chart(grouped[["carbon_gco2e"]])
    with st.expander("Accounting and provenance"):
        st.json({"run_accounting": metadata["run_accounting"],
                 "horizon_comparison": metadata["horizon_comparison"],
                 "milp_solver_status": metadata["milp_solver_status"]})
        st.caption("Historical benchmark rows are supporting experiments only. They are not pooled into the current two-method primary comparison.")


def research_results_tab():
    st.subheader("Primary research comparison")
    json_path = ROOT / "results/research_alignment_v4_final_confirmation/final_summary.json"
    if not json_path.exists():
        st.error("The authoritative v4 final results are missing. The UI will not substitute a fresh simulation or historical benchmark.")
        return
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if payload.get("status") != "complete_synthetic_confirmatory_evaluation":
        st.error(f"Unexpected saved-results status: {payload.get('status')}")
        return
    st.success("Saved v4 confirmatory evaluation · fresh synthetic holdout · 90 matched pairs · 20% allowance frozen")
    st.caption("These values are loaded from results/research_alignment_v4_final_confirmation/final_summary.json. They are separate from the fresh synthetic demonstrations and do not imply real-world generalization.")
    method_columns = st.columns(2)
    method_columns[0].markdown("**Base: A-MARL-derived IPPO with fastest-feasible SPT**")
    method_columns[0].write("The same saved IPPO policy uses active entropy-guided SPT to choose the feasible destination with the shortest execution time. This is a cloud adaptation; the original A-MARL JobShop/edge experiments are not claimed as reproduced.")
    method_columns[1].markdown("**Proposed: Carbon-Aware, Latency-Bounded Entropy-Guided SPT (20%)**")
    method_columns[1].write("Under the same policy and entropy gate, find the fastest feasible destination by migration plus execution latency, allow candidates up to 20% slower, and select the eligible destination with lowest estimated carbon.")
    metric_keys = (
        ("Total carbon (gCO₂e/run)", "carbon_gco2e"),
        ("Carbon per completed task (gCO₂e)", "carbon_gco2e_per_completed"),
        ("Energy (kWh/run)", "energy_kwh"),
        ("Completion rate", "completion_rate"),
        ("Rejection rate", "rejection_rate"),
        ("SLA violations/run", "sla_violations"),
        ("Mean latency (s)", "mean_latency_seconds"),
        ("Deferrals/run", "deferrals"),
        ("SPT interventions/run", "intervention_count"),
        ("SPT intervention rate", "intervention_rate"),
    )
    rows = []
    for method, values in payload["summary"]["per_method"].items():
        row = {"Method": method}
        for label, key in metric_keys:
            stat = values[key]
            row[label] = ("n/a" if stat["mean"] is None else
                          f"{stat['mean']:.3f} [{stat['ci95'][0]:.3f}, {stat['ci95'][1]:.3f}]")
        rows.append(row)
    st.markdown("**Saved v4 method means [crossed-bootstrap 95% CI]**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    paired_rows = []
    for label, key in metric_keys:
        stat = payload["summary"]["paired_proposed_minus_base"][key]
        paired_rows.append({"Outcome": label,
                            "Proposed − base": stat["mean"],
                            "95% CI low": stat["ci95"][0],
                            "95% CI high": stat["ci95"][1],
                            "Wild-cluster p": stat["wild_cluster_test_two_sided"]["p_value"]})
    st.markdown("**Paired differences (proposed − base), 95% crossed-bootstrap intervals**")
    st.dataframe(pd.DataFrame(paired_rows).style.format({
        "Proposed − base": "{:+.4f}", "95% CI low": "{:+.4f}", "95% CI high": "{:+.4f}",
        "Wild-cluster p": "{:.4f}",
    }), hide_index=True, use_container_width=True)

    rejection = payload["summary"]["paired_proposed_minus_base"]["rejection_rate"]
    st.warning("Service non-inferiority is not claimed: the prespecified zero-increase margin's one-sided bootstrap bound is at 0, but the wild-cluster test is not significant and the two-sided interval extends above zero. Mean latency increases; the simulator has no separate aggregate latency tolerance.")
    st.caption(f"One-sided rejection-rate upper bound: {rejection['one_sided_service_noninferiority_upper_95']:.4f}; non-inferiority test p={rejection['wild_cluster_test_noninferiority']['p_value']:.4f}. SLA violations equal rejections in this simulator.")

    st.markdown("### Saved-result visual comparisons")
    chart_dir = ROOT / "assets/presentation/research_alignment_v4"
    chart_files = [
        ("Total carbon emissions", "carbon_emissions.png"),
        ("Emissions per completed task", "carbon_per_completed_task.png"),
        ("Energy consumption", "energy_consumption.png"),
        ("Completion and SLA outcomes", "completion_sla.png"),
        ("Latency trade-off", "latency_tradeoff.png"),
    ]
    for title, filename in chart_files:
        chart_path = chart_dir / filename
        if chart_path.is_file():
            st.markdown(f"**{title}**")
            st.image(str(chart_path), use_container_width=True)
        else:
            st.warning(f"Saved chart not found: {filename}")

    by_family = payload["summary"]["paired_by_family"]
    family_rows = []
    for family in ("variable", "diverse", "bursty"):
        group = by_family[family]
        stat = group["carbon_gco2e"]
        family_rows.append({"Workload family": family,
                            "Δ CO₂e (g)": stat["mean"],
                            "95% CI": f"[{stat['ci95'][0]:.2f}, {stat['ci95'][1]:.2f}]",
                            "Δ g/task": group["carbon_gco2e_per_completed"]["mean"],
                            "Δ latency (s)": group["mean_latency_seconds"]["mean"]})
    st.markdown("**Paired emissions by workload family**")
    st.dataframe(pd.DataFrame(family_rows).style.format({"Δ CO₂e (g)": "{:+.2f}", "Δ g/task": "{:+.3f}", "Δ latency (s)": "{:+.2f}"}),
                 hide_index=True, use_container_width=True)
    manifest_path = ROOT / "results/research_alignment_v4_final_confirmation/seed_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    with st.expander("Saved evaluation provenance"):
        st.json({"status": payload["status"], "matched_pairs": payload["matched_pairs"],
                 "synthetic_workload_seeds": manifest.get("workload_seeds", []),
                 "workload_families": manifest.get("workload_families", []),
                 "policy_seeds": manifest.get("policy_seeds", []),
                 "allowance_fraction": payload["allowance_fraction"],
                 "training_launched": payload["training_launched"],
                 "heldout_data_synthetic": payload["heldout_data_synthetic"]})


def main():
    st.title("Carbon-Aware Cloud Scheduler")
    st.write("Explore fresh synthetic scheduling decisions, review the saved v4 confirmation, and browse historical supporting benchmarks.")
    fresh, research, saved = st.tabs(["Fresh synthetic demo", "Saved v4 research results", "Historical benchmark"])
    with fresh:
        simulation_tab()
    with research:
        research_results_tab()
    with saved:
        saved_tab()
    with st.sidebar:
        st.header("About this demo")
        st.caption("The primary comparison uses the frozen v4 methods and 20% proposed latency allowance. Fresh demos are not confirmatory results. No training starts in the UI.")
        st.caption("Greedy and historical schedulers appear only as optional auxiliary demos or in the separate historical benchmark view.")


if __name__ == "__main__":
    main()
