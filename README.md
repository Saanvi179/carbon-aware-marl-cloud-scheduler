# Multi-Agent Reinforcement Learning for Carbon-Optimal Distributed AI Workload Scheduling across Heterogeneous Clouds

This repository studies sequential placement of AI workloads across heterogeneous cloud regions. It pairs a cloud-specific **A-MARL-derived IPPO baseline** with a proposed **Carbon-Aware, Latency-Bounded Entropy-Guided SPT** intervention. The final allowance is frozen at **20%**. The authoritative confirmation is the synthetic holdout in [`results/research_alignment_v4_final_confirmation/`](results/research_alignment_v4_final_confirmation/); historical reports are preserved separately and are not combined with it. Third-party trace inputs and trace-derived Phase 3–3.3 results are excluded from the public release pending source-term verification.

## Research objective

The objective is to test whether choosing a lower-carbon feasible region during an entropy-guided SPT intervention can reduce simulated operational emissions while keeping additional latency bounded. The baseline and proposed method use the same IPPO policy checkpoint per policy seed, simulator, observation, action mask, reward, and evaluation settings. Their primary difference is the SPT destination selection rule.

This project is an A-MARL-derived adaptation to a cloud simulator. It does **not** claim exact reproduction of A-MARL's JobShop/edge experiments. See the [method and paper comparison](docs/RESEARCH_AND_IMPLEMENTATION_COMPARISON.md) and [frozen method specification](docs/RESEARCH_METHOD_SPECIFICATION.md) for the source evidence boundary.

## Research references and gap

- **A-MARL (2025), primary methodological reference.** The author repository describes independent agents by edge server, entropy-guided SPT for JobShop actions, and a transition from high-entropy SPT-guided exploration to lower-entropy policy selection. Its README also describes pseudo-action masking and a residual MLP/self-attention architecture; the accessible learner code samples a policy action, selects a JobShop SPT action above its entropy threshold, and records the selected action's policy log probability. The IEEE full paper was not fully accessible for verification of all equations, architecture details, reward, and experiments. These repository descriptions are evidence about the public implementation, not a claim that every detail is verified from the paper. [Paper DOI](https://doi.org/10.1109/CASCON66301.2025.00053) · [Author repository](https://github.com/AminAvan/a_marl-scheduler).
- **SustainDC (2024), supporting environment and benchmark reference.** It provides modular data-center control environments and evaluation methodology. This repository does not run SustainDC or reuse its results. [Paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/b6676756f8a935e208f394a1ba47f0bc-Paper-Datasets_and_Benchmarks_Track.pdf) · [arXiv](https://arxiv.org/abs/2408.07841).
- **DCcluster-Opt (2025), supporting modelling and benchmark reference.** It motivates explicit treatment of geo-distributed workloads, carbon, network and service constraints. Its full multi-site benchmark and facility model are not implemented here. [Paper](https://openreview.net/pdf?id=AgTASkryb6) · [arXiv](https://arxiv.org/abs/2511.00117) · [Author repository](https://github.com/HewlettPackard/sustain-cluster).

The research gap addressed here is a controlled cloud-scheduling comparison of an entropy-guided shortest-processing-time selector with a carbon-aware selector that enforces a stated latency allowance. The contribution is the cloud adaptation and this constrained carbon destination rule, evaluated under matched synthetic conditions.

## Methods

### Base: A-MARL-derived IPPO with fastest-feasible SPT

**What A-MARL describes:** a JobShop agent action assigns a ready operation/job to an edge server. The public author README describes high-entropy SPT-guided exploration plus pseudo-action masking, and a residual MLP/self-attention actor-critic. The accessible `informed_ff_ippo.py` learner uses `0.8 × log(action_count)` as its threshold fraction, samples a policy action, computes a JobShop SPT action, chooses the SPT action above threshold, and evaluates the selected action's policy log probability for PPO. The paper's complete equations and experimental details were not verified from the IEEE full text.

**Cloud adaptation used here:** one arriving task is presented at a time, so the base selector cannot choose among several ready jobs as in JobShop SPT. At an entropy-triggered intervention, it selects the feasible region with shortest estimated execution time for that task. A categorical mask removes infeasible cloud placements throughout action selection; this is the simulator's feasibility mask and is not A-MARL's described high-entropy pseudo-action mask. Our actors/critics are two-layer 64-unit tanh MLPs, not the architecture described in the author README. The legal-action support in the entropy threshold and the region-level meaning of SPT are explicit cloud adaptations. At training time the chosen action's log probability is recorded and SPT transitions participate in PPO updates. At v4 evaluation, the same fixed checkpoints are sampled stochastically with SPT active, without optimizer updates. This is an A-MARL-derived baseline, not an exact reproduction.

### Proposed: Carbon-Aware, Latency-Bounded Entropy-Guided SPT

Only the destination ranking used at an SPT intervention changes. Let `F` be destinations already feasible under current resource, reservation, and deadline checks. For each candidate `r`, estimate total latency `L_r = migration_latency_r + execution_latency_r` and incremental carbon `C_r`. Let `L* = min(L_r for r in F)`. The frozen eligible set is:

```text
F_20 = { r in F : L_r <= 1.20 * L* }
```

Choose the destination in `F_20` with the lowest estimated carbon; ties use estimated latency and the fixed region order. Thus the policy, action feasibility, reward, simulator, and checkpoints are shared, while the SPT selector alone differs. The method preserves existing resource and task-deadline feasibility constraints. The 20% allowance constrains each SPT candidate's **estimated migration-plus-execution latency relative to the fastest currently feasible candidate**; it is not a guarantee that measured episode or mean task latency will remain within 20%.

## System and workflow

The simulator models three heterogeneous regions (`north`, `west`, `east`), sequential task arrivals, candidate placement feasibility, migration delay, energy and regional carbon intensity. The policy observes a 54-value normalized observation with task and destination features. Each region has an independent categorical actor and value critic, implemented as two 64-unit tanh hidden layers. The shared training reward includes completion, bounded carbon and latency costs, deferral and rejection/SLA terms. Full implementation detail is in [the final report](docs/FINAL_PROJECT_REPORT.md) and [system architecture](docs/SYSTEM_ARCHITECTURE.md).

Synthetic workloads and synthetic dynamic carbon profiles are used for the v4 final confirmation. Historical Phase 3 work used third-party trace and regional carbon inputs; raw/derived inputs and trace-derived result folders are intentionally excluded from the public repository while redistribution terms remain unresolved. Existing local copies are not removed. See [data provenance and publication exclusions](docs/DATA_SOURCES.md) and [publication notes](docs/PUBLICATION_NOTES.md).

## Final v4 confirmation

The protocol was frozen before generating six fresh OS-random synthetic workload seeds. The seed manifest records their provenance and non-overlap audit. Three workload families (`variable`, `diverse`, `bursty`) crossed with six workload seeds yield 18 workload instances, each with 24 tasks. Crossing these instances with five policy seeds `[7, 19, 42, 73, 101]` produced 90 matched pairs (180 runs). For each policy seed, both conditions used the same already-trained `proposed_eps_0.000` checkpoint from v1; the recorded common training configuration specifies 16 episodes of 24 tasks per policy seed. V4 itself performs evaluation only. Both conditions used active stochastic SPT under identical simulator and carbon conditions. There was no retraining, test-based tuning, or repeated evaluation. The final data are synthetic and do not establish real-world generalisation.

| Metric | Base mean | Proposed mean | Paired proposed − base (95% CI) | p-value |
|---|---:|---:|---:|---:|
| Total carbon (gCO₂e/run) | 749.36 | 713.57 | −35.80 [−56.89, −15.27] | 0.0029 |
| Carbon per completed task (gCO₂e) | 33.113 | 31.222 | −1.890 [−3.087, −0.930] | 0.0044 |
| Energy (kWh/run) | 2.3385 | 2.4211 | +0.0825 [+0.0425, +0.1368] | 0.0010 |
| Completion rate | 95.83% | 96.48% | +0.65 percentage points [−0.09, +1.57] | 0.1600 |
| Rejection rate | 4.17% | 3.52% | −0.65 percentage points [−1.57, +0.09] | 0.1559 |
| Rejections/run | 1.000 | 0.844 | −0.156 [−0.389, +0.022] | 0.1653 |
| SLA violations/run | 1.000 | 0.844 | −0.156 [−0.389, +0.022] | 0.1640 |
| Mean latency (s) | 328.94 | 333.85 | +4.90 [+3.11, +7.02] | 0.0004 |
| Deferrals/run | 3.178 | 3.200 | +0.022 [−0.689, +0.733] | 0.9190 |
| SPT interventions/run | 14.156 | 14.189 | +0.033 [−0.378, +0.389] | 0.8315 |
| SPT intervention rate | 52.95% | 53.01% | +0.06 percentage points [−2.34, +2.03] | 0.9286 |

Intervals shown are paired proposed-minus-base, two-factor crossed percentile bootstrap 95% intervals (10,000 replicates across workload instances and policy seeds); per-method intervals are also saved in `final_summary.json`. P-values use two-way crossed wild-cluster tests (9,999 replicates); they are approximate with only five policy-seed clusters and are not adjusted for multiple outcomes. The proposed method reduced simulated carbon and carbon per completed task, while energy and mean latency increased. Completion, rejection, and SLA differences are inconclusive. In this simulator, SLA violation counts equal rejection counts. The one-sided zero-margin service bound reaches zero, but the corresponding wild-cluster non-inferiority test was not significant (`p=0.0777`); formal service non-inferiority and unqualified overall superiority are not claimed.

Convergence is not evaluated in v4: the confirmation performs no training and compares frozen checkpoints under an inference-time selector change. Earlier training curves are historical diagnostics, not a v4 confirmatory convergence comparison. See [`final_summary.json`](results/research_alignment_v4_final_confirmation/final_summary.json) and the [complete report](docs/FINAL_PROJECT_REPORT.md).

Presentation charts derived from the saved summary are in [`assets/presentation/research_alignment_v4/`](assets/presentation/research_alignment_v4/), in PNG, SVG and PDF formats. The Streamlit saved-results tab reads the same v4 artifacts. Fresh synthetic UI runs are demonstrations and never presented as confirmation.

## Install, test, and launch

Use Python 3.10 or newer in a virtual environment. From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python -m streamlit run ui/app.py
```

The app opens at the local URL shown by Streamlit (normally `http://localhost:8501`). It provides a fresh synthetic demonstration, saved v4 results with charts and uncertainty intervals, and an explicitly historical supporting-benchmark view. Optional auxiliary algorithms are not part of the primary comparison. No UI tab trains a model. See [UI usage](docs/UI_USAGE.md) and [reproducibility](docs/REPRODUCIBILITY.md).

To render presentation charts from the saved v4 summary (no simulation or training):

```powershell
python tools/render_final_confirmation_charts.py
```

## Repository map

```text
agents/                  IPPO/MAPPO agents, networks, reward and buffers
environment/             Cloud simulator, workload, resource, network, energy, carbon models
agents/ippo_agent.py     IPPO policy, entropy gate, and base/proposed SPT selectors
schedulers/              Supporting FCFS, Greedy, and Forecast MPC schedulers
experiments/             Training, preprocessing, evaluation and historical experiment scripts
configs/                 Simulator and training configurations
data/                     Empty directory markers; third-party datasets are local-only
results/                  Historical outputs and authoritative v4 artifacts
results/research_alignment_v4_final_confirmation/
                          Frozen config, seed provenance, run metrics, traces and final summary
tests/                    Existing automated tests
ui/                       Streamlit application and run interface
docs/                      Final report, methodology, comparison, architecture and usage
assets/presentation/       Final v4 presentation charts and chart manifest
archive/                   Superseded root reports and historical documentation
tools/                     Saved-result chart rendering utility
```

See [`CLEANUP_MANIFEST.md`](CLEANUP_MANIFEST.md) for local cleanup dispositions and [`docs/PUBLICATION_NOTES.md`](docs/PUBLICATION_NOTES.md) for the public file set. Historical reports and selected validation artifacts are available for audit; not every local historical result folder is included. None should be cited as the final v4 comparison.

## Current scope and demonstrated limitations

The current experiments use a synthetic cloud-scheduling simulator, so outcomes depend on its generated workloads, resource settings, and carbon assumptions. In v4 the proposed method reduces simulated emissions while increasing energy and latency; formal service-performance non-inferiority has not been conclusively established. The 20% selector allowance does not guarantee an overall latency cap. The confirmation uses five policy seeds and 18 workload instances; wild-cluster p-values are approximate and unadjusted. A-MARL's full IEEE text was not available for complete methodological verification, and the original JobShop/edge experiments are not reproduced here.

## Future work

Future extensions include deploying and validating the scheduler on real cloud infrastructure and real AI workload traces; extending coverage to providers, regions, and heterogeneous resources; improving the carbon, energy, latency, and SLA trade-off; adding dynamic carbon-intensity forecasting and adaptive scheduling; and evaluating scalability and robustness more broadly. These are extensions beyond the current synthetic study, not claims that the present simulator or research implementation is incomplete.

## Key files

- [Final research report](docs/FINAL_PROJECT_REPORT.md)
- [Method and paper comparison](docs/RESEARCH_AND_IMPLEMENTATION_COMPARISON.md)
- [Frozen method specification](docs/RESEARCH_METHOD_SPECIFICATION.md)
- [System architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Data provenance](docs/DATA_SOURCES.md)
- [UI usage](docs/UI_USAGE.md)
- [Authoritative final v4 result directory](results/research_alignment_v4_final_confirmation/)

## References

1. A. Avan, A. Azim, and Q. H. Mahmoud, “A-MARL: Agile Multi-Agent Reinforcement Learning for Soft Real-Time Task Scheduling in Edge Computing,” IEEE CASCON 2025. [DOI](https://doi.org/10.1109/CASCON66301.2025.00053) · [Author repository](https://github.com/AminAvan/a_marl-scheduler).
2. A. Naug et al., “SustainDC: Benchmarking for Sustainable Data Center Control,” NeurIPS 2024 Datasets and Benchmarks. [Paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/b6676756f8a935e208f394a1ba47f0bc-Paper-Datasets_and_Benchmarks_Track.pdf) · [arXiv](https://arxiv.org/abs/2408.07841).
3. A. Guillen-Perez et al., “DCcluster-Opt: Benchmarking Dynamic Multi-Objective Optimization for Geo-Distributed Data Center Workloads,” 2025. [Paper](https://openreview.net/pdf?id=AgTASkryb6) · [arXiv](https://arxiv.org/abs/2511.00117) · [Repository](https://github.com/HewlettPackard/sustain-cluster).
