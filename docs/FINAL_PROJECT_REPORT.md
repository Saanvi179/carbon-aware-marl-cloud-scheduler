# Final Project Report: Carbon-Aware Cloud Scheduling with Entropy-Guided SPT

## 1. Research problem and objectives

Cloud schedulers place arriving jobs across heterogeneous regions while balancing task deadlines, resource limits, network transfer, energy use, and grid carbon intensity. The research question is whether a carbon-aware destination choice, applied only when entropy-guided SPT intervenes, improves the carbon/service trade-off over an A-MARL-derived IPPO baseline in the same cloud simulator.

The frozen primary comparison is:

1. **Base:** A-MARL-derived IPPO with entropy-guided selection of the feasible destination with shortest execution time.
2. **Proposed:** Carbon-Aware, Latency-Bounded Entropy-Guided SPT with a fixed 20% latency allowance.

Greedy, FCFS, Forecast MPC, MAPPO, and LinUCB are not part of the primary comparison. Historical experiments remain supporting evidence only.

## 2. Literature review

### A-MARL (2025)

Avan, Azim, and Mahmoud introduce A-MARL for soft-real-time task scheduling in edge computing ([paper DOI](https://doi.org/10.1109/CASCON66301.2025.00053)). The public method description is Multi-Agent PPO with an entropy-triggered SPT action intervention: use a scheduling heuristic at high policy entropy and rely on the policy when entropy is lower. The [official author repository](https://github.com/AminAvan/a_marl-scheduler) documents the high-level algorithm under its README sections **Overview**, **Architecture**, **Entropy Threshold**, and **Method Details**. Its [informed IPPO learner](https://github.com/AminAvan/a_marl-scheduler/blob/develop/mava/systems/ppo/anakin/informed_ff_ippo.py) computes an entropy threshold from `0.8 × log(action_count)`, samples a policy action, selects a JobShop SPT action when the threshold is exceeded, then evaluates the selected action's log probability before PPO updates.

The IEEE full paper text was not available for direct inspection during this project. The exact paper equations, complete model architecture, paper-specific reward, and experiment tables therefore are not independently verified here. The author's repository describes JobShop scheduling; its README advertises residual/self-attention elements, while the active learner path is the feed-forward IPPO implementation. We do not resolve that discrepancy by assumption. The project's work is an A-MARL-derived cloud adaptation, not a reproduction of the original JobShop/edge experiments.

### SustainDC (2024)

SustainDC presents customizable Python environments for multi-agent data-center control. Its **Section 4** describes workload, data-center, and battery environments; **Sections 4.1–4.5** cover workload scheduling, data-center behavior, battery control, the multi-agent problem, and rewards. **Section 5** defines evaluation metrics and experimental settings, and **Section 6** benchmarks algorithms. Its modular treatment of workload, grid carbon, and data-center components informs this project's environment and metric choices, but SustainDC's environment and results are not reused. [NeurIPS paper PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/b6676756f8a935e208f394a1ba47f0bc-Paper-Datasets_and_Benchmarks_Track.pdf), [arXiv record](https://arxiv.org/abs/2408.07841).

### DCcluster-Opt (2025)

DCcluster-Opt is a geo-temporal benchmark for multi-objective scheduling over data centers. **Section 3.1–3.3** covers the global scheduling scenario, simulation loop, and modeling pillars; **Section 4** describes integrated datasets; **Section 5** formalizes the scheduling MDP/API; and **Section 6** describes experimental evaluation. Its workload, grid carbon, weather, network, and facility-energy considerations motivate explicit environment assumptions and matched evaluation conditions here. This project does not implement DCcluster-Opt's 15-minute multi-site simulation, empirical multi-region datasets, or physics-informed IT/HVAC model. [Paper PDF](https://openreview.net/pdf?id=AgTASkryb6), [arXiv record](https://arxiv.org/abs/2511.00117), [author benchmark repository](https://github.com/HewlettPackard/sustain-cluster).

## 3. Base-paper methodology

The author repository describes A-MARL as independent agents for JobShop edge servers, with high-entropy SPT-guided exploration and policy action selection as entropy falls. Its README also describes high-entropy pseudo-action masking and a residual MLP/self-attention actor-critic. In the accessible `informed_ff_ippo.py` learner, a policy action is sampled, a JobShop SPT action is computed, the action is selected using the entropy threshold, and the selected action's policy log probability is recorded for PPO. These details are verified from the public author repository; the IEEE full text was not available here to independently confirm the paper's complete equations, architecture, reward or experimental settings.

Let the policy distribution at time \(t\) have entropy \(H_t\), and let \(A_t^{legal}\) be the legal action support. The cloud implementation intervenes when

\[
H_t > \alpha\log |A_t^{legal}|, \qquad \alpha=0.8.
\]

At an intervention, the base selects the feasible destination with minimum estimated execution time. Otherwise the masked policy action is used. During training, intervention transitions retain the selected action's policy log probability and are included in PPO updates. For the final v4 evaluation, the same fixed policy checkpoint is evaluated with stochastic action sampling and active interventions; no optimizer updates occur.

The cloud implementation does not reproduce the author README's described pseudo-action masking or its residual MLP/self-attention network. It uses a feasibility mask for cloud actions at all times and substitutes the selected action with the cloud SPT choice when the entropy gate triggers. The threshold's effective legal-action count, sequential cloud action semantics, feasibility-mask behavior, and destination-level meaning of SPT are deliberate adaptations. They are not asserted as paper-equivalent details.

## 4. Cloud-specific A-MARL adaptation

The simulator has three heterogeneous regions (`north`, `west`, `east`). Each region has its own independent actor and critic. The actor is a two-hidden-layer 64-unit tanh MLP with a four-action categorical output: defer, execute locally, or migrate to either remote region. The critic is a corresponding MLP with a scalar value output. Each task is controlled by its source-region actor.

The observation has 54 values: normalized task/local state and 14 values per region candidate, including feasibility, carbon intensity, execution speed/time, migration time, estimated energy/emissions, resource availability, queue length, queued work, and latency/deadline terms. The action mask removes infeasible destinations; the simulator preserves resource and per-task deadline checks at placement.

The simulated network migration latency is dataset size divided by configured transfer bandwidth plus a fixed RTT. Region energy is estimated from GPU power, shared idle overhead, interval duration, and PUE. Emissions integrate energy against the region carbon-intensity profile. The reward used during training is shared by both methods: completed execution receives a completion bonus minus bounded normalized carbon and latency costs; deferral receives a fixed penalty; rejection receives SLA and rejection penalties. The v4 evaluation changes neither reward nor policy weights.

## 5. Proposed method and mathematical formulation

The proposed contribution changes only the SPT destination selector. Let (\mathcal F_t) be the simulator's currently feasible region set after resource and deadline checks. For each (r\in\mathcal F_t), define estimated latency and carbon as

\[
L_{t,r}=L^{migration}_{t,r}+L^{execution}_{t,r}, \qquad
C_{t,r}=\widehat{\Delta CO_2e}_{t,r}.
\]

Find the fastest feasible destination and its latency:

\[
L_t^*=\min_{r\in\mathcal F_t}L_{t,r}.
\]

For the frozen (\epsilon=0.20), define the latency-bounded set

\[
\mathcal F_t^{\epsilon}=\{r\in\mathcal F_t:L_{t,r}\le(1+\epsilon)L_t^*\},
\]

then select

\[
r_t^*=\operatorname*{arg\,min}_{r\in\mathcal F_t^{\epsilon}}
\left(C_{t,r},L_{t,r},\operatorname{regionOrder}(r)\right).
\]

Thus carbon is minimized among destinations whose estimated latency stays within 20% of the fastest feasible option. The method cannot select an infeasible, over-capacity, or deadline-violating destination because the eligible set is formed only from (\mathcal F_t). This rule runs only when the shared entropy gate triggers SPT.

## 6. System architecture and implementation

- [`environment/cloud_environment.py`](../environment/cloud_environment.py) generates feasible destination candidates, applies resource/deadline constraints, schedules retries, and integrates episode energy and emissions.
- [`environment/carbon_model.py`](../environment/carbon_model.py) supplies regional carbon profiles; [`environment/network_model.py`](../environment/network_model.py) computes transfer delay.
- [`agents/ippo_agent.py`](../agents/ippo_agent.py) contains the masked IPPO scheduler and the carbon/latency-bounded SPT selector. [`agents/actor.py`](../agents/actor.py) and [`agents/critic.py`](../agents/critic.py) define the MLPs.
- [`experiments/run_research_alignment_v4_confirmation.py`](../experiments/run_research_alignment_v4_confirmation.py) created the fresh seed manifest and ran the one-pass final confirmation. It reuses the same existing checkpoint for both methods within each policy seed.
- [`ui/runner.py`](../ui/runner.py) supplies a separate fresh synthetic demonstration. [`ui/app.py`](../ui/app.py) distinguishes that demonstration from the saved confirmatory results.

## 7. Experimental design and evaluation protocol

The v4 confirmation uses a new independent **synthetic** holdout. Six seeds were generated after the protocol amendment was frozen, using Python's OS-backed `secrets.randbits(32)`, and audited for overlap against prior repository seed metadata before evaluation. The seeds are preserved in [`seed_manifest.json`](../results/research_alignment_v4_final_confirmation/seed_manifest.json). The three workload families (`variable`, `diverse`, `bursty`) used 24 tasks each, yielding 18 workload instances. Five policy seeds `[7, 19, 42, 73, 101]` crossed with workloads produce 90 matched pairs and 180 method runs.

For each policy seed, both methods load the same already-trained `proposed_eps_0.000` checkpoint from v1; the recorded common training configuration specifies 16 episodes of 24 tasks per policy seed. This isolates inference-time SPT rule changes; it does not compare independently retrained policies. Both use stochastic action sampling, the same 0.8 entropy fraction, intervention probability 1.0, observations, action masks, reward, environment, and dynamic synthetic 512-slot carbon profile. SPT is active for both. Each workload/method condition ran once; there was no retraining, allowance tuning, or test reuse.

Metrics are run-level total integrated CO₂e, CO₂e per completed task, energy, completion, rejection/SLA violations, latency, deferrals, and intervention frequency. Paired differences are proposed minus base. 95% confidence intervals use a 10,000-replicate crossed percentile bootstrap over workload instances and policy seeds. P-values use a two-way crossed wild-cluster bootstrap (9,999 draws). With only five policy-seed clusters, the p-values are approximate and are not multiplicity-adjusted.

The service non-inferiority margin is zero additional rejection/SLA violations per task, consistent with the simulator's hard per-task deadline feasibility rule and its definition of SLA violations as rejections. No separate average-latency margin is specified by this project.

## 8. Final held-out results

All values below come from the authoritative [`final_summary.json`](../results/research_alignment_v4_final_confirmation/final_summary.json). Intervals are paired 95% crossed-bootstrap intervals; p-values are from the approximate wild-cluster tests.

| Metric | Base mean | Proposed mean | Paired proposed − base [95% CI] | p-value |
|---|---:|---:|---:|---:|
| Total carbon (gCO₂e/run) | 749.36 | 713.57 | −35.80 [−56.89, −15.27] | 0.0029 |
| Carbon per completed task (gCO₂e) | 33.113 | 31.222 | −1.890 [−3.087, −0.930] | 0.0044 |
| Energy (kWh/run) | 2.3385 | 2.4211 | +0.0825 [+0.0425, +0.1368] | 0.0010 |
| Completion rate | 95.83% | 96.48% | +0.65 pp [−0.09, +1.57] | 0.1600 |
| Rejection rate | 4.17% | 3.52% | −0.65 pp [−1.57, +0.09] | 0.1559 |
| Rejections/run | 1.000 | 0.844 | −0.156 [−0.389, +0.022] | 0.1653 |
| SLA violations/run | 1.000 | 0.844 | −0.156 [−0.389, +0.022] | 0.1640 |
| Mean latency (s) | 328.94 | 333.85 | +4.90 [+3.11, +7.02] | 0.0004 |
| Deferrals/run | 3.178 | 3.200 | +0.022 [−0.689, +0.733] | 0.9190 |
| SPT interventions/run | 14.156 | 14.189 | +0.033 [−0.378, +0.389] | 0.8315 |
| SPT intervention rate | 52.95% | 53.01% | +0.06 pp [−2.34, +2.03] | 0.9286 |

The zero-margin one-sided rejection-rate upper bound is 0.0000, exactly at the margin, but the one-sided wild-cluster non-inferiority test has (p=0.0777) and the two-sided interval extends slightly above zero. Accordingly, robust formal service non-inferiority is not claimed.

## 9. Statistical interpretation

The proposed method lowered total emissions by 35.80 g/run (4.78%) and emissions per completed task by 1.890 g (5.71%). It used 0.0825 kWh more energy per run (3.53%) and increased mean latency by 4.90 seconds (1.49%). Completion was 0.65 percentage points higher on average, but its interval includes no change. Rejection/SLA counts were lower on average, though robust non-inferiority was not established. Deferrals and intervention frequency were similar.

Therefore the result supports a synthetic-holdout carbon reduction accompanied by energy and latency costs. It does not establish unqualified overall superiority. Family results show carbon-per-task effects strongest in `diverse`; `variable` includes zero. The confirmatory summary and per-run data preserve all intervals and family breakdowns.

## 10. Research contributions

1. A documented A-MARL-derived IPPO baseline mapped to feasible cloud destination selection, with the boundary between verified source method and cloud adaptation stated explicitly.
2. A carbon-aware SPT selector constrained by a relative latency allowance, leaving the policy, action mask, reward, and simulator shared with the baseline.
3. A matched, multi-family synthetic holdout comparison using fresh audited seeds, identical checkpoints within policy seed, active SPT interventions, paired effects, and crossed uncertainty estimates.
4. Reproducible run-level, task-level, decision-trace, checkpoint-hash, configuration, and seed-provenance artifacts.

## 11. Current scope and experimentally demonstrated limitations

- The v4 holdout is synthetic and generated by this project's workload/carbon models. It does not demonstrate performance on production traces or real cloud infrastructure.
- A-MARL's full IEEE paper text was unavailable for direct verification. This is explicitly an A-MARL-derived cloud adaptation, not exact reproduction of original JobShop results.
- The simulator is much smaller and less physically detailed than SustainDC or DCcluster-Opt. Carbon estimates and network/resource assumptions are not calibrated operational measurements.
- Five policy seeds and 18 workload instances are limited; wild-cluster tests use few policy-seed clusters and p-values are approximate and unadjusted across outcomes.
- The v4 comparison reuses each proposed-epsilon-zero checkpoint for both conditions to isolate inference-time intervention. It does not estimate retraining the proposed method specifically under 20%.
- The strict service margin is not robustly established, and there is no project-defined average-latency tolerance. The observed latency increase must be considered in any operational interpretation.
- The 20% method allowance is applied to estimated candidate migration-plus-execution latency at each entropy-triggered SPT intervention; it does not cap measured task latency or episode mean latency.
- Convergence is not evaluated in the v4 confirmation because it performs no training. Earlier training curves are historical and are not a confirmatory comparison of the two frozen v4 conditions.

## 12. Future work

Future extensions include deployment and validation on real cloud infrastructure and evaluation using real AI workload traces; extending support to additional providers, regions, and heterogeneous resources; improving the carbon, energy, latency, and SLA trade-off; adding dynamic carbon-intensity forecasting and adaptive scheduling; and assessing scalability and robustness at broader scales. These are extensions beyond the current synthetic study rather than failures of the simulator or completed implementation.

## Presentation assets

Publication-ready PNG, SVG, and PDF charts are in [`assets/presentation/research_alignment_v4/`](../assets/presentation/research_alignment_v4/). They are rendered only from the saved v4 summary; the fresh UI demonstrations are not used as confirmatory evidence.

## References

1. A. Avan, A. Azim, and Q. H. Mahmoud, “A-MARL: Agile Multi-Agent Reinforcement Learning for Soft Real-Time Task Scheduling in Edge Computing,” IEEE CASCON 2025, pp. 275–284. [DOI](https://doi.org/10.1109/CASCON66301.2025.00053); [author repository](https://github.com/AminAvan/a_marl-scheduler).
2. A. Naug et al., “SustainDC: Benchmarking for Sustainable Data Center Control,” NeurIPS 2024 Datasets and Benchmarks. [Paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/b6676756f8a935e208f394a1ba47f0bc-Paper-Datasets_and_Benchmarks_Track.pdf); [arXiv](https://arxiv.org/abs/2408.07841).
3. A. Guillen-Perez et al., “DCcluster-Opt: Benchmarking Dynamic Multi-Objective Optimization for Geo-Distributed Data Center Workloads,” 2025. [Paper](https://openreview.net/pdf?id=AgTASkryb6); [arXiv](https://arxiv.org/abs/2511.00117); [repository](https://github.com/HewlettPackard/sustain-cluster).
