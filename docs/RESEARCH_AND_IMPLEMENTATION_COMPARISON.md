# Research and Implementation Comparison — Final v4 Alignment

This document compares the verified source method with the final cloud implementation and reports the authoritative v4 synthetic holdout. Full report: [`FINAL_PROJECT_REPORT.md`](FINAL_PROJECT_REPORT.md). Machine-readable final results: [`results/research_alignment_v4_final_confirmation/final_summary.json`](../results/research_alignment_v4_final_confirmation/final_summary.json).

## Literature and evidence boundaries

| Source | Relevant published scope | Use in this project |
|---|---|---|
| A-MARL (Avan, Azim, Mahmoud, 2025) | Entropy-guided SPT exploration for soft-real-time edge scheduling with multi-agent PPO; DOI [10.1109/CASCON66301.2025.00053](https://doi.org/10.1109/CASCON66301.2025.00053). The public author repository documents thresholded SPT and IPPO code. | Primary method inspiration and derived baseline. IEEE full text was unavailable for complete equation/configuration verification; this project does not claim exact JobShop reproduction. See [author repository](https://github.com/AminAvan/a_marl-scheduler). |
| SustainDC (NeurIPS 2024) | Sections 4.1–4.5 describe workload, data-center, battery, multi-agent-control, and reward components; Sections 5–6 cover metrics/settings and benchmarks. | Informs environment decomposition and sustainability metrics. We do not run the SustainDC environment or reuse its results. [Paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/b6676756f8a935e208f394a1ba47f0bc-Paper-Datasets_and_Benchmarks_Track.pdf). |
| DCcluster-Opt (2025) | Sections 3–6 describe geo-distributed benchmark design, datasets, an MDP/API, and experimental evaluation. | Informs matched workload/carbon/network/service evaluation design. We do not implement its empirical datasets or high-fidelity IT/HVAC model. [Paper](https://openreview.net/pdf?id=AgTASkryb6). |

## Method-to-code mapping

| Component | A-MARL source evidence | Cloud implementation | Classification |
|---|---|---|---|
| PPO variant | Official author learner is `informed_ff_ippo.py`, a feed-forward IPPO path. | Independent per-region PPO actor and critic in [`agents/ippo_agent.py`](../agents/ippo_agent.py). | Adapted baseline; no MAPPO in the primary pair. |
| Entropy switch | Author code compares policy entropy with a fraction of maximum categorical entropy; README documents 0.8. | `H > 0.8 × ln(legal action count)`; illegal actions are excluded from the effective support. | Explicit cloud adaptation of support size. |
| High-entropy action handling | Author README describes SPT-guided pseudo-action masking; the accessible learner samples a policy action, selects the SPT action above threshold, then records its policy log probability. | Cloud action mask always removes infeasible placements; entropy-triggered SPT substitutes a feasible destination action. | The feasibility mask is not represented as a reproduction of A-MARL's pseudo-action mask. |
| SPT action | JobShop SPT prioritizes a schedulable operation with shortest processing duration. | One task is presented at a time, so base SPT maps to the feasible region with shortest estimated execution time. | Cloud-specific destination adaptation. |
| Proposed action | Not part of A-MARL. | Among destinations within 20% of fastest total migration-plus-execution latency, choose minimum estimated incremental carbon. | Original contribution. |
| Feasibility semantics | The author README describes pseudo-action masking; exact paper-level legality semantics could not be fully checked. | The persistent cloud mask always permits deferral and masks infeasible local/remote placements; the simulator enforces placement constraints. | Shared cloud safety adaptation; not claimed as paper-equivalent masking. |
| Network | Author README advertises residual/self-attention features; active learner details and full paper could not be fully reconciled. | Two-layer 64-unit tanh actor/critic MLPs. | Cloud architecture adaptation, not claimed to reproduce A-MARL network. |
| Reward | Paper-specific reward could not be verified. Public repository uses JobShop objective. | Same bounded carbon/latency/completion/SLA reward in training; no reward edits between methods. | Project-defined objective. |
| Training/evaluation | Author learner samples a policy action, may replace it with SPT, records the selected action probability, then updates PPO. | Existing checkpoint per policy seed reused in both methods; stochastic evaluation activates SPT; no optimizer updates. | Matched inference-time intervention comparison. |

## Final v4 evaluation

The new holdout consists of three workload families × six seeds (18 workload instances) × five policy seeds = **90 matched pairs**. Six workload seeds were generated after the protocol amendment was frozen and audited against prior seed metadata; the manifest is [`seed_manifest.json`](../results/research_alignment_v4_final_confirmation/seed_manifest.json). For each policy seed, both conditions use the same existing `proposed_eps_0.000` checkpoint (trained under the common 16-episode, 24-tasks-per-episode configuration), active SPT, matched stochastic random seeds, the same synthetic carbon profile and simulator. V4 runs evaluation only; each workload/condition ran once.

| Metric | Base | Proposed | Paired difference [95% CI] | Wild-cluster p |
|---|---:|---:|---:|---:|
| Total CO₂e/run (g) | 749.36 | 713.57 | −35.80 [−56.89, −15.27] | 0.0029 |
| CO₂e/completed task (g) | 33.113 | 31.222 | −1.890 [−3.087, −0.930] | 0.0044 |
| Energy/run (kWh) | 2.3385 | 2.4211 | +0.0825 [+0.0425, +0.1368] | 0.0010 |
| Completion rate | 95.83% | 96.48% | +0.65 pp [−0.09, +1.57] | 0.1600 |
| Rejection rate | 4.17% | 3.52% | −0.65 pp [−1.57, +0.09] | 0.1559 |
| SLA violations/run | 1.000 | 0.844 | −0.156 [−0.389, +0.022] | 0.1640 |
| Mean latency (s) | 328.94 | 333.85 | +4.90 [+3.11, +7.02] | 0.0004 |
| Deferrals/run | 3.178 | 3.200 | +0.022 [−0.689, +0.733] | 0.9190 |
| SPT intervention rate | 52.95% | 53.01% | +0.06 pp [−2.34, +2.03] | 0.9286 |

The proposed method reduced simulated carbon while increasing energy and latency. Completion, rejection and SLA differences were inconclusive. The zero-increase service margin's one-sided bootstrap bound meets the boundary, but the one-sided wild-cluster non-inferiority test is not significant (p=0.0777), and the two-sided rejection-rate interval extends slightly above zero. Robust service non-inferiority and unqualified overall superiority are not claimed. V4 has no convergence comparison because it evaluates frozen checkpoints without training; older learning curves are historical.

## Correct interpretation of prior work

Phase 2/3 reports, prior v1 research comparison, and earlier baselines remain preserved as historical supporting experiments. They are not pooled with v4 and do not replace either primary method. The fresh Streamlit simulation is an illustrative new synthetic run; only the v4 saved artifacts represent the final confirmatory evaluation. No result here demonstrates real-world generalization.

## Reproducibility

- Frozen settings and checkpoint hashes: [`frozen_evaluation_config.json`](../results/research_alignment_v4_final_confirmation/frozen_evaluation_config.json).
- Seed provenance and audit: [`seed_manifest.json`](../results/research_alignment_v4_final_confirmation/seed_manifest.json).
- Per-run metrics, task outcomes, and decision traces are stored alongside [`FINAL_REPORT.md`](../results/research_alignment_v4_final_confirmation/FINAL_REPORT.md).
- Full test suite: `python -m unittest discover -s tests` — 77 passed before the one-pass v4 evaluation.
- No new training, tuning, or re-evaluation was performed during final project consolidation.
