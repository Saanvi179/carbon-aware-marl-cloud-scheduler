# Implementation walkthrough

This guide follows one task from workload generation to placement, learning, saved evaluation, and the Streamlit interface. It describes the checked-in implementation. The simulator is a research model with synthetic workloads and carbon profiles; it is not a live cloud controller.

## 1. Project map and end-to-end flow

The main execution path is:

```text
task generator -> Task objects -> CloudEnvironment.run()
      -> feasible per-region candidates and observations
      -> source region's IPPO agent proposes an action
      -> entropy gate may replace that proposal with an SPT destination
      -> resolver and allocation ledger -> simulated execution
      -> rewards, rollout buffer, metrics and decision trace
      -> training updates/checkpoints OR evaluation artifacts
      -> Streamlit demo or saved-results view
```

Important files:

| Component | Source | Main entry points |
|---|---|---|
| Workloads | [`environment/task_generator.py`](../environment/task_generator.py) | `Task`, `generate_variable_workload`, `generate_diverse_workload`, `generate_phase25_workload` |
| Simulator and placement loop | [`environment/cloud_environment.py`](../environment/cloud_environment.py) | `Region`, `CloudEnvironment.run`, `_candidate_metrics`, `_integrate_region` |
| Actions and observations | [`environment/agent_api.py`](../environment/agent_api.py) | `ActionType`, `CandidateRegionFeatures`, `RegionObservation`, `make_observation` |
| Capacity and duplicate protection | [`environment/resource_manager.py`](../environment/resource_manager.py) | `Resources`, `AllocationLedger` |
| Network, energy and carbon | [`environment/network_model.py`](../environment/network_model.py), [`environment/energy_model.py`](../environment/energy_model.py), [`environment/carbon_model.py`](../environment/carbon_model.py) | `NetworkModel`, `interval_energy_kwh`, `CarbonModel` |
| IPPO and both primary selectors | [`agents/ippo_agent.py`](../agents/ippo_agent.py) | `observation_vector`, `IPPOAgent`, `IPPOScheduler`, `CarbonAwareSPTIPPOScheduler` |
| Networks and buffer | [`agents/actor.py`](../agents/actor.py), [`agents/critic.py`](../agents/critic.py), [`agents/rollout_buffer.py`](../agents/rollout_buffer.py) | `Actor`, `Critic`, `RolloutBuffer` |
| Reward | [`agents/reward.py`](../agents/reward.py) | `execution_reward`, `deferral_reward`, `terminal_rejection_reward` |
| Environment and scheduler construction | [`experiments/evaluate_baselines.py`](../experiments/evaluate_baselines.py), [`experiments/train_ippo.py`](../experiments/train_ippo.py) | `make_phase25_environment`, `environment_for_config`, `build_scheduler`, `train` |
| Final evaluation | [`experiments/run_research_alignment_v4_confirmation.py`](../experiments/run_research_alignment_v4_confirmation.py) | `generate_and_save_manifest`, `evaluate_condition`, `summarize`, `main` |
| UI | [`ui/runner.py`](../ui/runner.py), [`ui/app.py`](../ui/app.py) | `make_workload`, `make_scheduler`, `run_comparison`, `simulation_tab`, `research_results_tab` |

The research-method details and evidence boundary are also recorded in [`RESEARCH_METHOD_SPECIFICATION.md`](RESEARCH_METHOD_SPECIFICATION.md), and the confirmed outcomes are in [`results/research_alignment_v4_final_confirmation/FINAL_REPORT.md`](../results/research_alignment_v4_final_confirmation/FINAL_REPORT.md).

## 2. Workloads and task representation

`Task` in `environment/task_generator.py` is an immutable record with task ID, arrival slot, GPU count, CPU cores, memory, dataset size, deadline, runtime, and source region. It does not contain a real container image, measured model graph, or trace-derived execution profile by default.

Three seeded generators are used in the final v4 experiment:

- `generate_variable_workload(seed, task_count, ...)` samples arrival slots from 0–12, sources, discrete resource demands, uniform dataset size/runtime, and a sampled deadline slack.
- `generate_diverse_workload(...)` spans arrival slots 0–60 and wider resource, data-volume, runtime, and slack ranges.
- `generate_phase25_workload(...)` uses normalized exponential gaps for bursty arrivals and weighted GPU choices; runtime and dataset size are bounded log-normal samples. Its deadline slack depends on runtime and data size.

Each uses its own `random.Random(seed)`, making a workload repeatable from its generator and seed. Tasks are returned sorted by arrival slot and task ID. `synthetic_workload()` is a small fixed illustrative six-task demo, not the v4 holdout.

**Approximation:** all three v4 workload families are synthetic scenario generators. They are not observations from production cloud traces. The ranges, arrivals, and task demands encode assumptions in code.

## 3. Environment, regions, resources, network, energy, carbon

### Regions and environment construction

`experiments/evaluate_baselines.py:make_phase25_environment` creates exactly three `Region` objects and a `CloudEnvironment` with 60-second slots, two maximum deferrals, a default network model, and synthetic carbon profiles. The regions differ in GPU/CPU/memory capacity, GPU and idle watt assumptions, PUE, baseline carbon intensity, and relative execution speed:

| Region | Capacity (GPU, CPU cores, GB RAM) | GPU W | Idle W | PUE | Speed multiplier |
|---|---:|---:|---:|---:|---:|
| north | (8, 64, 256) | 300 | 100 | 1.20 | 1.00 |
| west | (6, 48, 192) | 280 | 90 | 1.15 | 1.15 |
| east | (10, 80, 384) | 330 | 110 | 1.25 | 0.90 |

These are configured simulator values, not provider inventory or measured hardware. `execution_speed` is a multiplier: `runtime_seconds / execution_speed` gives estimated execution time.

### Feasibility and task lifecycle

`CloudEnvironment.run` sorts tasks and advances slots. It releases resources for jobs whose rounded finish slot has arrived, finds tasks newly arriving or due for retry, then estimates each region candidate. Candidate feasibility requires:

1. `Resources.can_fit` says GPUs, CPU, and memory fit.
2. Estimated end time is no later than the task deadline.
3. Any scheduler reservation permits the region.
4. Any scheduler-specific reservation rule permits the candidate.

The task is allocated at most once through `AllocationLedger`. The region resources are reserved until the candidate's finish slot (rounded up). If a task defers, it is retried later; after the allowed deferrals, it may be rejected. If configured, the terminal safety resolver can force a feasible execution when the agent's final action is defer. That fallback is a safety mechanism, not either SPT selector.

### Network latency

`NetworkModel.migration_latency(source, destination, dataset_gb)` returns zero for local placement. Remote placement uses:

\[
T_{migration}=\frac{8\,D_{GB}}{B_{Gb/s}}+RTT.
\]

The default link assumption is 2.0 Gbit/s and 0.08 seconds RTT for each direction pair not explicitly configured. The model does not simulate packet contention or a changing WAN.

Candidate execution and total task latency are:

\[
T_{execution}=\frac{T_{runtime}}{speed_{region}},\qquad
L=T_{migration}+T_{execution}.
\]

The task starts after migration, at `slot * slot_seconds + migration`. The scheduler's proposed 20% rule uses this candidate-level `L` estimate.

### Energy and carbon

`CloudEnvironment._integrate_region` splits activity intervals at task boundaries and 60-second carbon slots, charges shared idle overhead once per active interval, and integrates energy. `interval_energy_kwh` computes:

\[
E_{kWh}=\frac{(N_{GPU}P_{GPU}+P_{idle})\,\Delta t\,PUE}{3{,}600{,}000}.
\]

`emissions_gco2e` multiplies energy by the regional intensity:

\[
CO_2e=E_{kWh}\times I_{gCO_2e/kWh}.
\]

`synthetic_carbon_profiles` builds nonnegative smooth, region-specific time series from fixed base intensities and sine components. These represent scenario inputs, not observed or forecast grid data. For candidate decisions, the environment computes the incremental region energy and estimated carbon. In generated v4 conditions, the synthetic profile is known to candidate estimation. When the model is configured with unknown candidate forecasts, the estimate uses the current observed intensity held flat; this branch avoids using future trace values as online information. The final reported total is recomputed from all assignments and the profile over their active intervals.

## 4. How the agents meet the environment

The environment constructs an observation for each region. With `owner_controlled=True`, which `IPPOScheduler` declares, only the task's `source_region` agent proposes a placement. This means there are three independent regional policies, but one source-region owner makes each task's decision; the IPPO path does not collect three simultaneous competing actions for one task. The environment API also supports non-owner-controlled schedulers that may submit one proposal per region.

`RegionObservation` includes current slot and region, the task, available local resources, local feasibility, feasible destination names, local carbon intensity, and candidate features for all three regions. Candidate features contain feasibility, intensity, speed, execution and migration seconds, energy and emissions estimates, available capacity, queue length, and queued work.

The adapter `observation_vector` in `agents/ippo_agent.py` turns this into numbers for the networks. The configured v4 observation has 54 values: 12 normalized task/owner-region values plus 14 values for each of three region candidates. Normalization constants are explicit in code (for example, GPU demand divided by 16, runtime by 1000 seconds, intensity by 1000 gCO₂e/kWh). This is a fixed feature vector, not an image or learned state encoder.

The four categorical actions are ordered as:

0. defer;
1. execute in the task's source/local region;
2. migrate to the first other region in `region_names` order;
3. migrate to the second other region.

`IPPOScheduler._mask` always permits defer and permits a placement action only if that destination is in the environment's feasible destination set. `masked_distribution` assigns invalid logits the smallest representable value before constructing a categorical distribution. Thus policy sampling and entropy are over legal actions only.

## 5. IPPO implementation

### Policy and value networks

`Actor` outputs four action logits from two 64-unit `Tanh` hidden layers. `Critic` has the same two-hidden-layer MLP shape but outputs one scalar value. Each region owns an independent `IPPOAgent`; weights are not shared. Initialization seeds are offset by region (`seed + i*997`).

At a decision, `IPPOAgent.act` samples from the masked categorical distribution during stochastic operation, or chooses the maximum-probability action in deterministic mode. It also returns that action's log probability, the critic's value estimate, and distribution entropy.

### Reward

For an executed task, `execution_reward` forms:

\[
r=b_{complete}-w_C\min(\max(C,0)/S_C,C_{clip})
-\lambda_L\min(\max(L,0)/\max(D_{remaining},1),1).
\]

Here `C` is the environment candidate's estimated marginal emissions at the decision; `L` is migration plus execution latency; and `D_remaining` is deadline minus the original arrival time in seconds, bounded below by one. Reward coefficients and scales are in the selected config, not derived from the physical simulator. Deferral incurs `-defer_penalty`; terminal rejection incurs `-(lambda_sla + rejection_penalty)`; a forced execution after deferring to the limit incurs `-forced_defer_penalty`. The simulator reports `sla_violations` as its rejection count; it does not implement a separate soft SLA violation classifier.

### Rollouts and PPO updates

At episode end, `IPPOScheduler.end_episode` computes the reward for each recorded decision and adds it to that region agent's `RolloutBuffer`, grouped by task trajectory ID. The buffer computes discounted returns and generalized advantage estimates (GAE) using configured `gamma` and `gae_lambda`; episode trajectories end on terminal task outcomes.

For each update epoch, `IPPOAgent.update` recomputes masked action log probabilities and uses PPO's clipped surrogate:

\[
L_{actor}=-\mathbb E[\min(\rho_t A_t,\;clip(\rho_t,1-\epsilon,1+\epsilon)A_t)]
-\beta H(\pi_t),
\quad \rho_t=\exp(\log\pi_{new}-\log\pi_{old}).
\]

The critic minimizes mean squared error between value predictions and returns. Actor and critic gradients are clipped to the configured maximum norm. In the frozen research config, `include_spt_actor_updates: true`; for SPT-overridden transitions the selected SPT action is assigned its current policy log probability and participates in actor updates. This is an implementation choice recorded by the project; it is not a claim about an unverified paper detail.

### Training and checkpoints

`experiments/train_ippo.py:train` seeds Python and Torch, builds the environment and scheduler, generates one seeded workload per episode, runs the simulator, updates the agent, logs metrics/decision traces, and writes checkpoints at the configured cadence. Checkpoints store episode, seed, config, and each region's actor, critic, and optimizer states. `load_checkpoint` restores those states.

The frozen shared configuration in `configs/research_alignment_v1.yaml` specifies 16 episodes, 24 tasks per training episode, 54 observation values, hidden size 64, 8 update epochs, actor/critic learning rates 0.0003/0.001, gamma 0.99, GAE lambda 0.95, PPO clip 0.2, entropy coefficient 0.002, max gradient norm 0.5, entropy fraction 0.8, and intervention probability 1.0. The final confirmation itself did **not** call `train` or update weights.

## 6. Base entropy-guided SPT

`IPPOScheduler._propose` first samples a masked policy action and calculates its entropy `H`. It counts valid actions `n_legal` and checks:

\[
H > \alpha\ln(\max(1,n_{legal})),\qquad \alpha=0.8.
\]

If the scheduler is stochastic, at least one feasible candidate exists, the threshold is exceeded, and the intervention-probability draw passes, it replaces the sampled action with the result of `_spt_destination`. In v4 the intervention probability is 1.0, but only decisions over the entropy threshold trigger.

For the base IPPO class, `_spt_destination` selects the feasible candidate with minimum `execution` seconds; configured region order breaks ties. This is the project's cloud mapping of A-MARL's SPT idea: there is already one arriving task, so the selector ranks destinations for that task. It is not a reproduction of the original JobShop operation-selection environment. The base selector's objective is execution time, not migration-plus-execution latency.

The chosen SPT action index is decoded into local or remote placement. Its log probability is recomputed under the same masked policy distribution. The decision trace records the selected action, action mask, proposed policy probabilities, pre-intervention entropy, policy-valid flag, and whether SPT intervened.

**Paper boundary:** A-MARL (2025) is the primary methodological reference. The accessible author repository supports the high-entropy SPT-guided intervention and PPO-derived action-selection pattern. The repository's model and environment are cloud-specific adaptations. The IEEE full paper details not verifiable from available local records are not inferred here; see [`RESEARCH_METHOD_SPECIFICATION.md`](RESEARCH_METHOD_SPECIFICATION.md) for the source/evidence boundary. Exact A-MARL JobShop/edge experiments are not claimed.

## 7. Proposed carbon-aware, latency-bounded SPT

`CarbonAwareSPTIPPOScheduler` subclasses the base scheduler and overrides only `_spt_destination`. It receives the same already-feasible candidates, policy weights, entropy gate, action mask, reward and simulator.

For feasible destinations \(\mathcal F\), calculate estimated candidate latency and emissions:

\[
L_r=T_{migration,r}+T_{execution,r},\quad C_r=\widehat{\Delta E_r}\times I_r.
\]

Find the fastest candidate's latency \(L_{min}=\min_{r\in\mathcal F}L_r\). With the frozen allowance \(\epsilon=0.20\), form:

\[
\mathcal F_{20\%}=\{r\in\mathcal F:L_r\le1.20L_{min}+10^{-9}\}.
\]

Choose the eligible destination minimizing `(estimated carbon, total latency, region order)`. The small numeric tolerance is in the code. If eligibility were unexpectedly empty, it falls back to the fastest candidate, which is necessarily in the set mathematically. The configured allowance is validated between 0 and 2; the final experiment explicitly freezes it to 0.20.

The 20% is a local selector allowance relative to the fastest feasible estimated candidate latency at that decision. It is **not** an episode latency guarantee or a bound on actual aggregate latency. Resource capacity and task deadline checks happen before selection and remain in force. Candidate carbon is an estimate; final outcome emissions are separately integrated by the simulator.

## 8. Training and evaluation flow

The normal training path is `python -m experiments.train_ippo --config configs/research_alignment_v1.yaml ...`. It reads the YAML config, constructs an `IPPOScheduler` (or configured variant), trains episode-by-episode, and writes logs/checkpoints under the configured output directory. This guide does not ask you to rerun it.

Validation selected the allowance before the final holdout. The v4 script, `experiments/run_research_alignment_v4_confirmation.py`, is an evaluation-only runner. It:

1. Requires a frozen protocol amendment and checks the output directory against overwriting prior results.
2. Audits existing seed references, generates six fresh 32-bit workload seeds using Python's OS-backed `secrets.randbits`, and writes a manifest before evaluation.
3. Uses three generators (variable, diverse, bursty), each on the six seeds, for 18 synthetic workload instances of 24 tasks each.
4. Crosses them with five policy seeds (7, 19, 42, 73, 101), yielding 90 paired comparisons / 180 method runs.
5. Loads the same existing checkpoint for each policy seed into each method condition. It does not train or update weights. Both use stochastic inference so the entropy-triggered SPT remains active, probability 1.0, and the same dynamic synthetic 512-slot carbon profile and environment settings.
6. Saves task outcomes and decision traces, aggregates metrics, and calculates paired differences with two-factor crossed percentile bootstrap 95% intervals (10,000 replicates) and two-way wild-cluster bootstrap p-values (9,999 draws).

The workload and policy-seed factors are paired/crossed to account for variation along both dimensions. There are only five policy-seed clusters, so the wild-cluster p-values are approximate and must be read with the intervals and the sample limitations. The final seed manifest has a no-overlap audit and provenance records.

## 9. Authoritative v4 results

The complete authoritative result directory is [`results/research_alignment_v4_final_confirmation/`](../results/research_alignment_v4_final_confirmation/):

- `FINAL_REPORT.md`: protocol, results, interpretation and limits.
- `final_summary.json`: per-method and paired metric summaries, intervals and tests.
- `frozen_evaluation_config.json`: shared and method-specific settings.
- `seed_manifest.json`: generated seeds and audit scope.
- `run_metadata.json`: hashes, versions, counts and integrity checks.
- `run_metrics.jsonl`, `task_outcomes.jsonl`, `decision_traces.jsonl`: per-run and per-task evidence.
- `PROTOCOL_AMENDMENT.md`: frozen evaluation protocol.

Selected paired results (proposed minus base):

| Metric | Base mean | Proposed mean | Paired difference [95% CI] | Test p |
|---|---:|---:|---:|---:|
| Total carbon (gCO₂e/run) | 749.36 | 713.57 | -35.80 [-56.89, -15.27] | 0.0029 |
| Carbon/completed task (gCO₂e) | 33.113 | 31.222 | -1.890 [-3.087, -0.930] | 0.0044 |
| Energy (kWh/run) | 2.3385 | 2.4211 | +0.0825 [+0.0425, +0.1368] | 0.0010 |
| Completion rate | 0.9583 | 0.9648 | +0.0065 [-0.0009, +0.0157] | 0.1600 |
| Rejection/SLA violations per run | 1.000 | 0.844 | -0.156 [-0.389, +0.022] | 0.1653 |
| Mean latency (s) | 328.94 | 333.85 | +4.90 [+3.11, +7.02] | 0.0004 |
| Deferrals/run | 3.178 | 3.200 | +0.022 [-0.689, +0.733] | 0.9190 |
| SPT interventions/run | 14.16 | 14.19 | +0.03 [-0.38, +0.39] | 0.8315 |

These outcomes support a carbon reduction within this synthetic evaluation, alongside higher modeled energy and latency. Completion and rejection/SLA evidence is inconclusive; formal service non-inferiority is not robustly established at the zero-increase margin. Therefore the results do not establish unqualified overall superiority or real-world cloud generalization.

## 10. Streamlit connection and controls

Launch from the repository root with `python -m streamlit run ui/app.py` (dependencies are listed in `requirements.txt`). `ui/app.py` defines three tabs:

### Fresh synthetic demo

- **Workload family** chooses the fixed six-task demo, variable, diverse, or bursty synthetic generator.
- **Workload seed** controls the seeded synthetic generator and stochastic policy sampling seed used by the runner.
- **Optional auxiliary scheduler demos** can add Greedy, FCFS, or historical methods. They appear in a separate expandable table, not the primary comparison. A forecast horizon control applies only to the historical Forecast MPC auxiliary scheduler.
- **Run comparison** calls `ui.runner.run_comparison`; it creates a fresh 512-slot synthetic-carbon environment for each selected scheduler, runs the same task list on each, then shows metrics, regional placements, task decisions and policy diagnostics.
- **Compare primary scheduling decisions** switches the trace shown for the Base or Proposed method. Diagnostic action probabilities, masks, entropies and interventions are expandable.

Fresh demo values are illustrative runs, not final v4 evidence. The runner loads the saved IPPO checkpoint from `results/research_alignment_v1/ui_policy_index.json`; it does not train from the UI.

### Saved v4 research results

`research_results_tab` reads `results/research_alignment_v4_final_confirmation/final_summary.json`, the seed manifest, and the five saved chart files under `assets/presentation/research_alignment_v4/`. It displays per-method means and intervals, paired changes and p-values, workload-family effects, the service non-inferiority caveat, and provenance. This tab does not run a simulation.

### Historical benchmark

`saved_tab` reads preserved Phase 3.3 corrected CSV/JSON artifacts and summarizes that historical trace-based benchmark by workload family. It is explicitly separate from the primary two-method comparison and does not include its rows in v4.

## 11. One-task walkthrough (illustrative numbers)

Suppose a task arrives in north with a 1 GB dataset, a 300-second runtime, and a deadline that leaves ample slack. Assume all regions pass the environment's capacity and deadline checks. These candidate values are hypothetical to explain the code, not recorded v4 measurements:

| Candidate | Migration | Execution | Total latency | Estimated carbon |
|---|---:|---:|---:|---:|
| north | 0 s | 300 s | 300 s | 120 gCO₂e |
| west | 4.08 s | 260.87 s | 264.95 s | 75 gCO₂e |
| east | 4.08 s | 333.33 s | 337.41 s | 58 gCO₂e |

West is fastest at 264.95 seconds. A 20% allowance gives a limit of about 317.94 seconds, so north and west are eligible; east is not. The proposed SPT picks west because it has the lowest estimated carbon among eligible regions. The base SPT picks west too because west has the shortest execution time. If north instead had lower eligible estimated emissions than west, proposed SPT could choose north within the 20% bound. The environment then reserves west/north resources, records actual modeled energy and integrated emissions, and the owner agent receives the reward based on the selected candidate estimate and latency. A task that fails feasibility is never made feasible by carbon ranking.

## 12. Glossary

- **Agent:** a policy instance that observes a state and selects an action. Here, one independent policy is maintained per region.
- **IPPO:** Independent Proximal Policy Optimization; each agent updates its own policy with PPO-style clipped policy gradients.
- **Actor / critic:** network predicting action logits / network estimating state value.
- **Action mask:** per-decision filter that removes infeasible placement actions before sampling.
- **Entropy:** uncertainty of a categorical action distribution, `-Σ p(a) log p(a)`.
- **SPT:** shortest processing time heuristic. Here, it is adapted to choose a destination for the current task.
- **Intervention:** replacing the sampled policy action with the SPT-selected placement when the entropy gate triggers.
- **Feasible candidate:** destination that passes capacity, deadline and reservation checks in the simulator.
- **Latency allowance:** proposed selector's tolerated fraction above the fastest candidate's estimated migration-plus-execution latency; frozen at 20%.
- **PUE:** power usage effectiveness multiplier applied to IT energy in the energy formula.
- **Carbon intensity:** emissions per kWh, here in gCO₂e/kWh.
- **Marginal/estimated carbon:** additional emissions estimated if a candidate is added to the current region schedule.
- **Integrated emissions:** energy integrated over assignment intervals multiplied by carbon intensity over time.
- **GAE:** generalized advantage estimation, a discounted estimate of how much better an action performed than expected.
- **Checkpoint:** saved policy/value weights and optimizer state, plus training metadata.
- **Matched pair:** base and proposed runs on the same workload and policy-seed condition.
- **Crossed bootstrap:** resampling both workload and policy-seed dimensions for an uncertainty interval.
- **Synthetic holdout:** generated workload set reserved for the one-time final evaluation; synthetic evidence is not production validation.

## 13. Likely viva questions

**Q: Is this an exact reproduction of A-MARL?**  
A: No. It implements an A-MARL-derived IPPO/SPT pattern in a three-region cloud simulator. The source task, actions, state, reward, constraints, and network architecture are project-specific. The original JobShop/edge experiments are not claimed as reproduced.

**Q: What does “multi-agent” mean here if only one proposal is used?**  
A: There are three independent regional IPPO policies, and the task's source region owns its placement decision. The simulator has an API for simultaneous region proposals for other schedulers, but this IPPO scheduler marks itself owner-controlled and asks only the source-region agent.

**Q: What exactly causes SPT to override the policy?**  
A: Stochastic inference must be active, there must be a feasible destination, and masked-distribution entropy must exceed `0.8 × ln(number of legal actions)`; then the intervention probability draw must pass. It is set to 1.0 in final evaluation.

**Q: What is the difference between base and proposed?**  
A: Only the SPT destination selector. Base minimizes estimated execution seconds. Proposed minimizes estimated carbon among destinations whose migration-plus-execution latency is at most 1.20 times the fastest candidate's latency. They share checkpoint, policy, entropy gate, mask, reward and environment in v4.

**Q: Does 20% cap actual latency?**  
A: No. It constrains the selector's estimated candidate-level latency at an intervention. It is not a task-level or episode-level actual latency guarantee.

**Q: How is carbon computed?**  
A: Modeled energy is integrated from GPU and shared idle watt assumptions with PUE, then multiplied by synthetic regional carbon intensity. Candidate emissions are estimated incremental values; total outcomes are integrated over all assignments and the configured profile.

**Q: Why use the same checkpoint for the two v4 methods?**  
A: The final experiment asks whether changing the intervention selector changes outcomes at inference time. Reusing the same weights within each policy seed controls for checkpoint differences; it does not test retraining a dedicated policy for the 20% method.

**Q: What is the main v4 finding?**  
A: In the synthetic holdout, proposed SPT lowered modeled carbon by about 35.8 g/run and 1.89 g per completed task, while energy rose by about 0.083 kWh/run and mean latency by about 4.9 seconds. Completion and service evidence is inconclusive; no overall superiority or robust service non-inferiority is claimed.

**Q: What does the 95% interval describe?**  
A: The paired difference interval uses crossed resampling over 18 workload instances and five policy seeds. The wild-cluster p-values are approximate with only five policy-seed clusters, so uncertainty and limited synthetic sample size matter.

**Q: Is a rejection a distinct SLA event in these results?**  
A: The simulator sets `sla_violations` equal to rejected tasks. It has hard deadline feasibility for placement, not a separate operational SLA-monitoring model.

**Q: Does the UI show confirmatory outcomes when I run a fresh demo?**  
A: No. Fresh demo runs are new illustrative simulations. The separate Saved v4 tab reads the one-time v4 summary, provenance, and saved charts; the historical benchmark tab is separate again.

**Q: What are the main limitations?**  
A: Workloads and carbon profiles are synthetic; region hardware, network, power, and PUE are assumptions; the model has three regions and simplified resource scheduling; the holdout is limited; and the method trades lower modeled carbon for higher energy and latency without robust service non-inferiority evidence. Real cloud measurements are outside the current implementation.
