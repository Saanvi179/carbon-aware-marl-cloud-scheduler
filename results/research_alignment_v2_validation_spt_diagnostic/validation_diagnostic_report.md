# Validation-only SPT allowance diagnostic

**Status:** validation diagnostic only. The 20% allowance is frozen as a candidate for a separate held-out confirmation; this report does not establish superiority.

## Method

The run used the existing proposed-epsilon-zero IPPO checkpoint for each of five policy seeds (`7, 19, 42, 73, 101`). Each checkpoint was loaded unchanged for the A-MARL-derived reference and all four proposed allowances. Training was not run. The scheduler ran in stochastic inference mode so the entropy gate and SPT override were active; `spt_intervention_probability` remained 1.0. We reset Python and PyTorch RNGs to the same policy seed for each matched condition.

The workload set was exactly the existing validation set: `variable`, `diverse`, and `bursty`, each with workload seeds `74101–74104`, 24 tasks per workload. This gives 12 workload instances, five policy seeds, and 60 matched run pairs per condition. Each replay used the same cloud simulator configuration and deterministic synthetic 512-slot carbon profile. No held-out test workload was accessed.

The reference invokes the repository's `IPPOScheduler._spt_destination`, which selects the feasible destination with minimum execution time (the project's cloud adaptation of shortest processing time). Proposed settings invoke `CarbonAwareSPTIPPOScheduler._spt_destination`: find the minimum total migration-plus-execution latency; admit feasible candidates whose latency is at most `fastest × (1 + allowance)`; select the lowest estimated carbon candidate among them. Existing resource/deadline feasibility and categorical action masks remain in force. Both rules are triggered by the same entropy condition and share the same policy checkpoint, PPO weights, observations, reward, and environment.

For each scheduling decision, `candidate_decisions.jsonl` stores the feasible destination list, candidate estimated carbon and latency, entropy, intervention flag, selected SPT destination, and resulting placement. `run_metrics.jsonl` stores episode outcomes. Episode `carbon_gco2e` is the simulator's final integrated emissions over region assignments. A per-placement carbon value is the simulator's candidate marginal estimate at placement time; it is not represented as a separately measured realized task emission.

Paired differences are proposed minus reference. Intervals are 95% two-factor crossed percentile bootstrap intervals (10,000 replicates), resampling policy seeds and workload instances. The 60 rows are matched pairs, not 60 independent workload populations.

## Results

Means below are per 24-task run. Confidence intervals shown are for the paired difference from the A-MARL-derived reference, not for absolute means.

| Proposed allowance | Total emissions Δ (gCO₂e/run), 95% CI | Emissions/completed task Δ (gCO₂e), 95% CI | Energy Δ (kWh/run), 95% CI | Mean latency Δ (s), 95% CI | Completion-rate Δ, 95% CI | SLA-violation count Δ, 95% CI |
|---:|---:|---:|---:|---:|---:|---:|
| 0% | +0.150 [0.000, +0.676] | +0.006 [+0.000, +0.028] | +0.0001 [+0.0000, +0.0004] | −0.008 [−0.037, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| 5% | +0.150 [0.000, +0.676] | +0.006 [+0.000, +0.028] | +0.0001 [+0.0000, +0.0004] | −0.008 [−0.037, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| 10% | +2.052 [−20.383, +31.292] | −0.018 [−0.870, +0.944] | +0.056 [−0.013, +0.204] | +1.173 [−0.555, +4.133] | +0.0028 [0.0000, +0.0104] | −0.067 [−0.250, 0.000] |
| 20% | −32.311 [−65.866, +6.786] | −1.376 [−2.651, −0.044] | +0.097 [+0.022, +0.235] | +4.950 [+2.203, +8.287] | 0.000 [−0.0076, +0.0083] | 0.000 [−0.200, +0.183] |

Additional paired differences (proposed minus reference), with 95% crossed-bootstrap intervals:

| Allowance | Rejection-rate Δ | Deferrals/run Δ | Intervention-rate Δ |
|---:|---:|---:|---:|
| 0% | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.0000 [0.0000, 0.0000] |
| 5% | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.0000 [0.0000, 0.0000] |
| 10% | −0.0028 [−0.0104, 0.0000] | −0.017 [−0.250, +0.150] | +0.0040 [−0.0036, +0.0152] |
| 20% | 0.0000 [−0.0083, +0.0076] | +0.367 [−0.233, +1.067] | −0.0085 [−0.0335, +0.0166] |

Reference means were 607.63 gCO₂e total, 25.684 gCO₂e/completed task, 1.953 kWh, 98.61% completion, 0.333 SLA violations, and 307.48 seconds mean task latency per run. The 20% setting's corresponding means were 575.32 gCO₂e, 24.308 gCO₂e/completed task, 2.050 kWh, 98.61% completion, 0.333 SLA violations, and 312.43 seconds.

SPT override rates were 62.57% for the reference, 62.57% at 0% and 5%, 62.97% at 10%, and 61.72% at 20%. There were 940 reference overrides; the proposed conditions had 940, 940, 946, and 937 respectively. Of the override decisions, the selected destination had lower estimated carbon than the reference fastest-execution choice 0 times at 0% and 5%, 38 times at 10%, and 222 times at 20%. These counts reflect the trajectories generated under each condition; later candidate sets can differ after earlier choices diverge.

An illustrative validation decision at 20% had north at 25.15 gCO₂e and 109.56 s versus east at 11.80 gCO₂e and 121.55 s; east was selected. Its estimated carbon reduction was 13.35 g for 11.99 s additional latency, inside the 20% allowance. Candidate-level estimates and outcomes for all decisions are in the JSONL trace.

## Interpretation and frozen candidate

The 0% and 5% settings were effectively indistinguishable in this replay and did not select a lower-carbon option than the reference. At 10%, carbon per completed task improved by only 0.018 g on average; its paired interval includes no effect. At 20%, emissions per completed task decreased by 1.376 g (about 5.36% of the reference mean), with the paired interval narrowly below zero. Total episode emissions also decreased on average, but its interval includes zero. Energy increased by about 0.097 kWh/run (about 4.97%), and mean latency increased by 4.95 seconds (about 1.61%); completion and SLA counts showed no clear paired change. Thus 20% presents a measurable validation carbon/latency/energy trade-off, not an unqualified improvement. The latency increase is within the method's per-intervention allowance by construction. This simulator study did not predefine a service non-inferiority margin, so acceptability must be judged against a margin specified before the final test.

**Frozen selection:** `spt_latency_allowance_fraction: 0.20` for the next, separate held-out evaluation. Rationale: among the tested candidates, only 20% showed a paired reduction in emissions per completed task whose 95% interval excluded zero, while completion and SLA differences were not clearly worse; the associated latency and energy costs are explicitly retained. This choice is not to be retuned using held-out results. A final test may confirm or fail to confirm this validation finding; no superiority claim is made now.

## Reproduction and limitations

Command: `python -m experiments.diagnose_spt_allowances`

The script reads `configs/research_alignment_v1.yaml` and `results/research_alignment_v1/ui_policy_index.json`; it writes only to this new versioned directory and refuses to overwrite a nonempty output directory. No training, reward changes, test-set changes, or test-set access occurred.

Limitations: this is a synthetic cloud simulator; five learned policy seeds and 12 validation workloads are a modest sample; the same stochastic seeds provide matched random-number streams but policy/environment trajectories diverge after decisions change; crossed bootstrap intervals do not remove model or workload-generation bias. The reference is an A-MARL-derived SPT adaptation in this cloud environment, not an exact reproduction of A-MARL's original JobShop experiments. The existing v1 checkpoint was trained with its historical setup; this validation replay isolates the inference-time intervention rule on those fixed weights and does not estimate retraining each method under a new frozen allowance.
