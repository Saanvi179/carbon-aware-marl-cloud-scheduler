# Streamlit Scheduler Demonstration

The UI has separate views for fresh synthetic demonstrations, the saved final v4 research comparison, and historical supporting benchmarks.

## Install and launch

From the project root:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run ui/app.py
```

Streamlit displays a local URL, normally `http://localhost:8501`.

## Primary methods

- **Base — A-MARL-derived IPPO (fastest-feasible SPT):** uses the shared saved IPPO policy; when the entropy gate triggers, chooses the feasible destination with shortest estimated execution time.
- **Proposed — Carbon-Aware, Latency-Bounded Entropy-Guided SPT (20%):** uses the same policy, entropy gate, action mask and simulator. At an SPT intervention, it allows up to 20% estimated migration-plus-execution latency over the fastest feasible destination, then chooses the lowest estimated-carbon candidate. This candidate-level allowance is not a guarantee on measured end-to-end or episode-average latency.

The original A-MARL JobShop/edge experiments are not claimed as reproduced.

## Tabs and result provenance

### Fresh synthetic demo

This tab creates a new synthetic workload and compares scheduling decisions and run metrics for the two primary methods. SPT intervention is active in both. The workload and resulting metrics are an illustrative **fresh demo**, not a held-out research evaluation. Optional Greedy, FCFS and historical scheduler demonstrations appear in a separate auxiliary section and are excluded from the primary research comparison.

### Saved v4 research results

This tab reads `results/research_alignment_v4_final_confirmation/final_summary.json` and charts in `assets/presentation/research_alignment_v4/`. It displays method means, paired differences, confidence intervals, p-values, workload-family outcomes and the service non-inferiority caveat. It does not execute simulations or select/tune parameters. The v4 holdout is synthetic and does not establish real-world generalization.

### Historical benchmark

The Phase 3.3 trace-based benchmark view is historical supporting material. Its data-derived outputs are omitted from the public repository pending source redistribution verification, so the tab displays an unavailable-data message in a public clone. Local copies continue to work when the preserved historical files are present. It is separate from the v4 primary comparison and is never pooled with v4 results.

No tab trains a model. The primary demonstration loads the existing seed-7 proposed-epsilon-zero checkpoint used by the v4 method comparison for both methods, so the fresh run changes only the intervention rule. The public-safe policy index uses repository-relative checkpoint paths; the original machine-specific index remains local-only.
