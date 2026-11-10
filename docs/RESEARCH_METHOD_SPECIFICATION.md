# Frozen Research Method Specification

**Authoritative methods:** A-MARL-derived IPPO with fastest-feasible SPT, compared with Carbon-Aware, Latency-Bounded Entropy-Guided SPT at a fixed 20% latency allowance. **Authoritative results:** `results/research_alignment_v4_final_confirmation/`. No parameter selection is performed in the UI or after v4.

## Evidence and adaptation boundary

A-MARL is described as multi-agent PPO with entropy-guided SPT exploration for soft-real-time edge scheduling ([paper DOI](https://doi.org/10.1109/CASCON66301.2025.00053), [official author repository](https://github.com/AminAvan/a_marl-scheduler)). The author README describes independent edge-server agents, JobShop actions, high-entropy SPT-guided pseudo-action masking, a residual MLP/self-attention actor-critic, and policy-based action selection as entropy falls. The accessible `informed_ff_ippo.py` learner samples a policy action, computes an SPT action, switches to SPT above its entropy threshold, and records the selected action's policy log probability. The IEEE full text was not accessible for verifying every paper equation or experimental detail. This is public repository evidence, not proof that every repository detail is paper-equivalent. Consequently, this project does not claim exact reproduction of A-MARL's JobShop/edge environment, reward, network, or experiments.

SustainDC Sections 4–6 and DCcluster-Opt Sections 3–6 inform environment and benchmark design, especially workload/carbon context, resource/service constraints, energy accounting, and matched multi-objective evaluation. They are not implemented environments or sources of v4 evaluation results. See [SustainDC](https://arxiv.org/abs/2408.07841) and [DCcluster-Opt](https://arxiv.org/abs/2511.00117).

## Shared cloud policy and simulator

- Three heterogeneous regions; tasks arrive sequentially and are controlled by their source-region actor.
- Independent categorical IPPO actors and value critics, each with two 64-unit tanh hidden layers.
- 54-value normalized task and region-candidate observation.
- Four action choices: defer, execute locally, migrate to remote region one, migrate to remote region two.
- Feasibility mask always permits deferral and masks placements that fail current capacity, resource, reservation, or task-deadline checks.
- Shared reward, environment, carbon model, network model, policy weights, entropy threshold, training checkpoint, and evaluation settings for the v4 paired comparison.

## Base method: A-MARL-derived IPPO with fastest-feasible SPT

For a legal-action policy distribution \(\pi_t\), compute categorical entropy \(H(\pi_t)\). The cloud implementation uses the effective legal support size \(A_t^{legal}\):

\[
H(\pi_t)>0.8\log |A_t^{legal}|.
\]

When the threshold is crossed, intervene with probability 1.0. Since each scheduling decision concerns one arriving task, the JobShop SPT dispatch rule is adapted to choose the feasible region with minimum estimated execution time. If the threshold is not crossed, use a stochastic sample from the masked policy. During training, the selected action log probability is recorded and intervention transitions participate in PPO updates. Final v4 evaluation samples actions and keeps this intervention active, but does not update the model.

This is a **cloud adaptation**, not the original JobShop SPT action that chooses among ready operations/jobs. The project uses its own feasibility mask to remove unavailable placements; it does not claim to reproduce the author README's high-entropy pseudo-action masking. The actor/critic are two-layer 64-unit tanh MLPs rather than the architecture described in that README.

## Proposed method: carbon-aware, latency-bounded SPT

Only the destination selector for an entropy-triggered SPT intervention changes. The policy architecture, weights, entropy trigger, action mask, reward, simulator, and random seeds remain matched.

For feasible destinations \(\mathcal F_t\), define estimated total latency \(L_{t,r}=L^{migration}_{t,r}+L^{execution}_{t,r}\) and estimated marginal carbon \(C_{t,r}\). Let \(L_t^*=\min_{r\in\mathcal F_t}L_{t,r}\). With frozen allowance \(\epsilon=0.20\):

\[
\mathcal F_t^{0.20}=\{r\in\mathcal F_t:L_{t,r}\le1.20L_t^*\},
\qquad
r_t^*=\arg\min_{r\in\mathcal F_t^{0.20}}(C_{t,r},L_{t,r},\text{fixed region order}).
\]

The method preserves all resource and task deadline feasibility because the carbon selector only ranks candidates already in the simulator's feasible set. Candidate carbon is an estimate; the reported total emissions are the simulator's final integrated region emissions.

## Training and final evaluation

The v4 final confirmation loads the already-trained `proposed_eps_0.000` checkpoint for each of five policy seeds (`7, 19, 42, 73, 101`) and reuses that exact checkpoint in both methods for that seed. The recorded common training configuration specifies 16 episodes of 24 tasks per policy seed; v4 itself makes no optimizer updates. This isolates the inference-time selector difference and does not estimate training a separate policy specifically for 20%.

The 20% value was selected using validation-only active-intervention results before the final holdout was generated. It is an allowance on estimated candidate-level migration-plus-execution latency at SPT intervention time; it is not a 20% cap on actual end-to-end or episode-average latency. Final evaluation uses 3 workload families × 6 fresh synthetic workload seeds (18 workload instances) × 5 policy seeds = 90 matched pairs. The seed manifest records generation and prior-seed overlap audit. Both methods use stochastic sampling, active SPT, the same carbon profiles and simulator conditions. The methods run once per matched workload/seed condition.

The service margin is zero additional rejection/SLA violations per task: simulator placements must meet task deadlines, and SLA violation count equals rejection count. No average-latency non-inferiority margin is defined. Report crossed bootstrap 95% intervals over workload instances and policy seeds, and interpret carbon, energy, latency, completion, rejections, deferrals, and intervention frequency jointly. The held-out data are synthetic; no production generalization is claimed.

## Frozen result and limits

The proposed method reduced v4 synthetic total emissions by 35.80 g/run and emissions per completed task by 1.890 g, while increasing energy by 0.0825 kWh/run and mean latency by 4.90 seconds. Completion and SLA differences are statistically inconclusive. The one-sided percentile interval for rejection-rate change reaches the zero margin, but the one-sided wild-cluster test has p=0.0777; robust formal service non-inferiority is not claimed. There is no unqualified superiority claim.

Full result tables, confidence intervals, p-values, limitations, seed provenance, configuration, and run artifacts are in [`FINAL_PROJECT_REPORT.md`](FINAL_PROJECT_REPORT.md) and `../results/research_alignment_v4_final_confirmation/`. Historical experiments remain unchanged and are not pooled with v4.
