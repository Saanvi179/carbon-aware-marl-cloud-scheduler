# Reproducibility and artifact guide

## Frozen final evidence

The authoritative results are in `results/research_alignment_v4_final_confirmation/`. Do not combine these files with earlier `phase*`, `research_alignment_v1`, smoke, diagnostic or validation folders. The final directory preserves the one-pass synthetic holdout, protocol amendment digest, frozen configuration, seed provenance and overlap audit, checkpoint/config hashes, per-run metrics, task outcomes, decision traces, summary and final report.

The final protocol crossed three workload families and six new workload seeds with five policy seeds (`7, 19, 42, 73, 101`), producing 90 matched method pairs. Both methods reuse the same existing checkpoint within each policy seed and use active SPT under the same stochastic inference and environment conditions. The final comparison does not retrain a separate 20% policy. No future run should be treated as a replacement for v4 without a separately frozen protocol and new versioned output directory.

The v4 confirmation driver is `experiments/run_research_alignment_v4_confirmation.py`; it was used for the saved one-pass evaluation. Its output path is the existing final-confirmation directory. **Do not rerun it against this checkout**, since doing so would collide with the authoritative results and would generate new seeds. Preserve the result directory before any deliberate reproduction attempt and direct any future run to a new versioned destination using a reviewed copy of the driver. This guidance does not change the frozen methodology.

## Environment setup and checks

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python -c "import ui.app; print('UI import OK')"
python -m streamlit run ui/app.py
```

The saved-results tab reads `results/research_alignment_v4_final_confirmation/final_summary.json`. Presentation charts are in `assets/presentation/research_alignment_v4/`; their `chart_manifest.json` names the source summary and its SHA-256. The charts can be regenerated from the existing summary without running an experiment:

```powershell
python tools/render_final_confirmation_charts.py
```

The chart utility only reads the saved v4 summary and writes chart files plus the chart manifest. It does not train or evaluate policies.

## Checkpoints and data

V4 identifies the `proposed_eps_0.000` checkpoint index under `results/research_alignment_v1/` and records the policy seeds and checkpoint hashes in its frozen evaluation configuration and run metadata. These checkpoints were trained under a common configuration specifying 16 episodes and 24 tasks per episode. Keep those historical checkpoint files alongside v4. Do not replace a checkpoint with one from a later or unrelated experiment.

The public repository intentionally excludes third-party raw/derived datasets and trace-derived Phase 3–3.3 run outputs while redistribution rights remain unverified. To reproduce those historical data experiments, obtain the sources from their official providers, confirm their terms, then place them at the paths documented in `docs/DATA_SOURCES.md` before running the relevant preprocessing commands. This does not affect v4: it uses synthetic workloads and synthetic dynamic carbon profiles. The v4 `seed_manifest.json` records workload seed provenance; `run_metrics.jsonl`, `task_outcomes.jsonl`, and `decision_traces.jsonl` retain its evaluated outputs.

The public-safe checkpoint index is `results/research_alignment_v1/ui_policy_index.public.json`. The original local index is excluded because it contains absolute machine paths. For the final v4 runner in a fresh clone, copy this path-safe index to the expected local filename before running the evaluation command:

```powershell
Copy-Item results/research_alignment_v1/ui_policy_index.public.json results/research_alignment_v1/ui_policy_index.json
```

The saved final v4 artifacts are already present; this command is only needed to restore the runner's expected local index path. Do not rerun the final confirmation as part of ordinary project setup.

## Statistical procedure

The saved summary reports paired proposed-minus-base effects, 95% crossed percentile bootstrap intervals (10,000 replicates across workload instances and policy seeds), and two-way crossed wild-cluster tests (9,999 replicates). With five policy-seed clusters, p-values are approximate and unadjusted for multiple outcomes. The service non-inferiority test did not establish a robust conclusion. Consult `docs/FINAL_PROJECT_REPORT.md` for metric interpretation and all reported trade-offs.

## Provenance limits

The holdout and carbon profiles are synthetic. Seed provenance and artifact hashes support auditability of this saved run, but this project does not claim production-cloud generalization. The reports also state that complete A-MARL IEEE paper details were not verified and that exact JobShop/edge reproduction is not claimed.
