# Final confirmatory comparison on a fresh synthetic holdout

**Conclusion scope:** this is a confirmatory comparison on newly generated synthetic workloads. It does not establish real-world generalization.

## Protocol

Six post-protocol workload seeds: `[2440927432, 2803977861, 3843001411, 204599743, 2733690354, 543108715]`; families: `variable, diverse, bursty`; 24 tasks per workload.
Five policy seeds `[7, 19, 42, 73, 101]` crossed with 18 workload instances produced 90 matched pairs (180 method runs). Both methods used the same existing checkpoint per policy seed, stochastic action sampling, entropy fraction 0.8, intervention probability 1.0, same environment and carbon profile; no training or weight updates occurred. Proposed allowance was fixed at 20%.
Fresh workload seeds were drawn from Python's OS-backed `secrets.randbits(32)` after the protocol amendment was frozen. The seed manifest records the audit scope, previous seed values, no-overlap result, source paths and hashes. The held-out workloads were evaluated once per method condition.
The reference selects the feasible destination with minimum execution time. The proposed selector admits destinations no slower than 1.20 times the minimum migration-plus-execution latency and then selects the lowest estimated carbon candidate. Simulator resource/deadline masks and reward remain unchanged.

## Paired results

Differences are proposed minus reference. Intervals are 95% two-factor crossed percentile-bootstrap intervals across workload instances and policy seeds (10,000 replicates). The table reports the paired wild-cluster bootstrap test p-value where available.

| Metric | Reference mean | Proposed mean | Paired difference [95% CI] | Two-way wild-bootstrap p |
|---|---:|---:|---:|---:|
| Total emissions (gCO₂e/run) | 749.36 | 713.57 | -35.80 [-56.89, -15.27] | 0.0029 |
| Emissions per completed task (gCO₂e) | 33.113 | 31.222 | -1.890 [-3.087, -0.930] | 0.0044 |
| Energy (kWh/run) | 2.3385 | 2.4211 | 0.0825 [0.0425, 0.1368] | 0.0010 |
| Completion rate | 0.9583 | 0.9648 | 0.0065 [-0.0009, 0.0157] | 0.1600 |
| Rejections/run | 1.000 | 0.844 | -0.156 [-0.389, 0.022] | 0.1653 |
| Rejection rate | 0.0417 | 0.0352 | -0.0065 [-0.0157, 0.0009] | 0.1559 |
| SLA violations/run | 1.000 | 0.844 | -0.156 [-0.389, 0.022] | 0.1640 |
| Mean latency (seconds) | 328.94 | 333.85 | 4.90 [3.11, 7.02] | 0.0004 |
| Deferrals/run | 3.178 | 3.200 | 0.022 [-0.689, 0.733] | 0.9190 |
| SPT interventions/run | 14.16 | 14.19 | 0.03 [-0.38, 0.39] | 0.8315 |
| SPT intervention rate | 0.5295 | 0.5301 | 0.0006 [-0.0234, 0.0203] | 0.9286 |

Family-specific paired effects show the same energy and latency cost direction in every family. Carbon-per-completed-task reduction was strongest in `diverse`; the `variable` family interval includes zero.

| Family | Emissions/completed task Δ [95% CI] (gCO₂e) | Energy Δ [95% CI] (kWh/run) | Mean latency Δ [95% CI] (s) | Completion-rate Δ [95% CI] |
|---|---:|---:|---:|---:|
| variable | -0.907 [-1.922, +0.298] | +0.067 [+0.033, +0.125] | +4.24 [+1.82, +7.95] | +0.0056 [0.0000, +0.0167] |
| diverse | -3.522 [-5.803, -1.618] | +0.120 [+0.018, +0.251] | +7.60 [+3.94, +11.53] | +0.0139 [-0.0056, +0.0375] |
| bursty | -1.242 [-2.419, -0.024] | +0.061 [+0.032, +0.094] | +2.88 [+1.57, +4.25] | 0.0000 [0.0000, 0.0000] |

## Service non-inferiority

The prespecified service margin was zero additional rejections/SLA violations per task (0 percentage points), based on the simulator's hard per-task deadline feasibility rule and its mapping of SLA violations to rejections. The one-sided 95% crossed-bootstrap upper bound for the rejection-rate difference is **0.000000**, exactly at the margin. However, the one-sided two-way wild-cluster test gives p=0.0777, and the two-sided 95% interval extends slightly above zero. The interval criterion meets its boundary, but the independent test does not corroborate it; we therefore do **not** claim robust formal service non-inferiority. There is also a measurable mean-latency increase. The simulator defines no separate aggregate mean-latency tolerance, so latency is reported as a secondary outcome.

## Interpretation and limitations

The proposed method reduced total emissions by 35.80 g/run (4.78%) and emissions per completed task by 1.890 g (5.71%), while energy increased by 0.083 kWh/run (3.53%) and mean latency increased by 4.90 s (1.49%). Completion was 0.65 percentage points higher on average, but its interval includes no change. Rejections/SLA violations were lower on average, but the evidence does not robustly establish non-inferiority at the strict zero-increase margin. These outcomes do not support an unqualified overall superiority claim.

Interpret carbon, energy, latency, completion, rejection/SLA, deferrals and intervention frequency together. The carbon metric is simulated with synthetic regional profiles, not measured operational emissions. Candidate carbon values are estimates; total episode emissions are integrated simulator outcomes. Checkpoint reuse isolates the inference-time selector on existing weights; it does not estimate the effect of retraining a policy specifically for the 20% rule. Five policy seeds and 18 synthetic workload instances provide limited population evidence. Wild-cluster p-values are approximate with only five policy-seed clusters and are not multiplicity-adjusted; treat them alongside intervals and outcomes. No real-world generalization claim is made.

## Reproducibility

The paired wild-bootstrap test uses 9,999 draws, centering paired cell differences under the zero-mean null and applying independent Rademacher cluster weights for policy seed and workload instance with multiplier `w_policy + w_workload − w_policy × w_workload`; p-values are empirical tail probabilities. These are approximate with few policy-seed clusters.

Command: `python -m experiments.run_research_alignment_v4_confirmation`. The full test suite ran beforehand with `python -m unittest discover -s tests` and passed 77 tests. The exact seed manifest, config snapshot (including effective method-specific settings), checkpoint hashes, runner hash, run metadata, per-run metrics, decision traces and task outcomes are saved beside this report. The evaluation runner refuses to overwrite prior artifacts. Reproducibility metadata, no-overlap, unique matched run keys, and hashes were checked after the single evaluation pass; the test workloads were not rerun.
