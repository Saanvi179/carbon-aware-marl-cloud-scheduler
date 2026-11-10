# TriSchedRL paper and repository verification

**Scope:** Read-only inspection of the paper and the public GitHub source snapshot. No project code was changed, no dependencies were installed, no scripts/tests/experiments were run, and no reproduction is claimed.

## Executive finding

The paper describes a **guarded DQN** scheduler with replay and a target network. The available repository does **not** implement that algorithm: its agent module implements a stochastic **actor–critic** update, and its advertised training and evaluation entry points are explicit placeholders. The repository contains useful hand-built simulator, guard, predictor-formula, workload, and metric scaffolding, but it is not a complete implementation of the paper or a runnable reproduction pipeline. Treat the paper as a possible source of design ideas, not a verified reproducible baseline, unless a complete matching implementation and run artifacts are obtained.

## Evidence labels

- **Verified—paper:** directly stated in the linked article.
- **Verified—repository:** directly observed in the GitHub source/configuration snapshot inspected.
- **Assessment:** comparison or engineering judgment based on those facts.
- **Unspecified:** not established from the inspected paper/repository. No values are invented to fill these gaps.

## 1. What algorithm does the paper actually use?

**Verified—paper:** The article repeatedly describes TriSchedRL as a guarded **Deep Q-Network (DQN)** scheduler. Its stated loop uses an online Q-network, epsilon-greedy action selection, replay, a periodically synchronized target network, TD learning, and Adam. A guard validates the selected resource and repairs it or selects a fallback if constraints fail. The paper's method is DQN, not actor–critic, PPO, or MARL.

The paper adds three supporting mechanisms around DQN:

1. Context prediction for latency, energy, and SLA-violation risk.
2. Adaptive weights for the SLA, latency, and energy reward terms.
3. A feasibility guard with repair/fallback behavior.

**Verified—paper:** Predictor models are said to be trained offline on simulator-generated historical traces, using feed-forward networks with hidden layers 64 and 32, ReLU, Adam, MSE, and learning rate 0.001. The predictor outputs are then fixed during policy learning.

**Paper parameter details are not fully consistent.** Section 4.7 allows two to three hidden layers and broad ranges for learning rate, buffer, batch size, and network architecture. Section 4.8 then gives a two-layer 128/64 network, a 20-interval meta-controller window, adaptation sensitivity 2.0, and ten repeated runs. The paper gives no single clear set of values for DQN learning rate, gamma, epsilon schedule, target synchronization interval, training episode/step budget, or exact optimizer-update cadence in the text that could be verified here. It reports other experiment counts and workload sizes in results sections, but these are not a substitute for an executable training protocol.

## 2. What algorithm does the source code implement?

**Verified—repository:** `src/agents/actor_critic.py` implements an actor–critic update:

- Actor produces categorical action logits and samples from the resulting policy.
- Critic estimates a scalar state value.
- The critic uses a one-step TD target `r + gamma * (1-done) * V(next_state)` and squared TD error.
- The actor uses the detached TD error as an advantage and adds an entropy term.
- Separate Adam optimizers update actor and critic.

The configured values in `configs/agent.yaml` are gamma 0.99, actor learning rate 1e-4, critic learning rate 1e-3, batch size 128, entropy coefficient 0.01, gradient clip 1.0, CPU, and replay capacity 100,000. The actor and critic default to two 256-unit hidden layers in `src/agents/networks.py`.

This is not DQN. The repository contains no Q-value output head, epsilon-greedy policy, target Q-network, or TD target based on max-Q. `src/agents/replay_buffer.py` is a generic uniform transition buffer, but the actor–critic update receives a caller-supplied batch; no code connects the buffer to an agent training loop. The source therefore provides actor–critic components, not a complete, named, end-to-end actor–critic training algorithm either. Calling it A2C would be too specific: there is no implemented rollout/advantage-accumulation trainer or complete on-policy training driver.

## 3. Paper-to-code match

| Component | Paper | Repository snapshot | Finding |
|---|---|---|---|
| RL algorithm | Guarded DQN | Categorical actor + value critic | **Core mismatch** |
| Action policy | Epsilon-greedy during training; greedy Q at evaluation | Stochastic categorical sampling in `act`; no evaluation policy driver | Mismatch |
| Q target / stabilization | Replay-based TD learning, target network | No Q-network or target network | Absent |
| Replay | DQN experience replay | Uniform array buffer module, not wired to the agent loop | Component only; not paper's DQN mechanism |
| Network | Paper ultimately says 128/64 in §4.8 | Actor and critic default to 256/256 | Mismatch |
| Predictor training | Three offline-trained neural predictors, 64/32 layers | Hand-coded latency/energy equations and a sigmoid risk formula | Mismatch; no predictor training code/data |
| State | Per-resource utilization/queue/network/energy plus predicted latency, energy, risk; one equation says dimension 4n+3 | Per-node hand-built features plus top-k prediction aggregation; dimension is implementation-configured and generally differs from 4n+3 | Partial conceptual overlap; different vector and no policy runner |
| Guard | Validate capacity, deadline, queue, energy; repair/fallback | Feasibility predicate, feasible-set repair and EFT/least-energy/weighted fallback functions | Partial component match; no integrated learned policy path in the supplied scripts |
| Reward | Negative weighted SLA penalty, normalized latency, normalized energy; weights adapt | SLA penalty helper and weight meta-controller exist separately, but no reward/training pipeline combines them | Partial primitives only |
| Simulator | Discrete-event, edge-cloud, time-varying network and workload conditions | Small custom Python queue-decay simulator with fixed links/configuration | Partial toy simulation; no full paper experiment system |
| Experiment runner | Training/evaluation and comparisons | Train and evaluate scripts are placeholders | Absent |

## 4. State, action, and reward

### Paper specification

**Verified—paper:** For `n` candidate resources, the MDP section gives a base state containing per-resource utilization `u`, queue length/work `q`, communication latency `l`, and energy status `e`, augmented by predicted latency, energy, and SLA risk. The equation is written as `s = [u_1…u_n, q_1…q_n, l_1…l_n, e_1…e_n, Lhat, Ehat, Vhat]`, for a stated dimension `4n + 3`. Elsewhere it denotes the augmented state as base state concatenated with predicted latency/energy/risk. A separate state equation and the exact definitions/units/normalization of all base features are not fully consistent or operationally specified.

**Verified—paper:** Each action assigns the incoming task to one of the `n` edge/cloud resources. The guard can replace an infeasible proposed action with a feasible alternative or fallback.

**Verified—paper:** The reward is `r_t = -(alpha_t * S_t + beta_t * normalized_latency_t + gamma_t * normalized_energy_t)`. `S_t` is an SLA-violation penalty; latency and energy are min–max normalized using scenario bounds. The weights are adaptive based on recent SLA violations, latency, congestion, and energy pressure. The paper names a 20-decision sliding window and sensitivity 2.0 in its setup but does not provide a fully unambiguous, executable specification of every signal, normalization bound, clipping operation, update order, and reward timing.

### Repository specification

**Verified—repository:** `StateVectorizer` encodes eight per-node numeric values (utilization, queued MI, processing rate, per-step capacity, bandwidth, RTT, loss, and whether an energy budget exists), plus a cloud/edge bit by default. It appends a `kappa` vector supplied by the caller. `PredictionAggregator` can produce top-k triples of predicted latency, energy, and risk plus the number of candidates. That is not the paper's stated 4n+3 state. Candidate features include task MI, deadline, input size, and priority, but those raw task fields are not directly inserted into the vector by `StateVectorizer`; predictions may indirectly vary with task features.

**Verified—repository:** The simulator API accepts one task and one node ID per step. A transition is not generated by any checked-in training script. The guard helper checks task MI against per-step capacity, predicted latency against deadline, predicted energy against energy budget, and risk against a threshold for high-priority tasks. `repair_action` ranks feasible nodes using weighted risk, latency, and energy; fallback can use EFT, least-energy, or weighted ranking.

**Verified—repository:** There is no integrated reward function used by an RL trainer. `sla.py` computes a deadline-violation indicator and penalty; `MetaController` updates three weights; neither is combined with measured latency/energy in a checked-in training loop.

## 5. Simulator, data, and dependencies

### Simulator/workload

**Verified—repository:** The project has a custom local Python simulator under `src/env`; it does not use CloudSim or a cloud provider. It represents node processing rate, per-step MI capacity, idle/dynamic power, optional energy budget, node kind, queue work, utilization, and static IoT-to-node links with bandwidth, RTT, loss, and overhead. `EdgeCloudEnv.step` computes execution, queue and communication time, SLA status, and energy, adds work to the node queue, and decays queues by a fixed `dt_s`.

The checked-in `configs/env.yaml` gives three edge nodes and one cloud node with fixed capacities/power/budgets and fixed link parameters. No time-varying network process is implemented in `NetworkModel`; no memory capacity or memory feasibility is modeled. The task schema has MI, deadline, input size and priority. The workload generator supports Poisson and alternating on/off burst arrivals from synthetic lognormal task distributions. It does not load a real dataset or configure workflow dependencies.

The README's asserted “complete” framework should be read alongside the nested `TriSchedRL/README.md`, which calls the training, baseline, and evaluation scripts placeholders and asks the reader to supply full versions “from the methodology implementation.”

### Files/configurations

**Verified—repository:** There are YAML files for agent, environment, meta-controller, and workload settings. Synthetic workload-generation code and two small tests are present. There are no benchmark dataset files, pretrained predictor weights, trained policies/checkpoints, evaluation outputs, or experiment result artifacts in the archive inspected. A `tests/` folder exists, but tests were not run.

The GitHub snapshot downloaded for inspection is the `main` archive whose URL resolves to commit prefix `370b827` (repository API reported pushed 2026-02-26). The archive contains a top-level README and a nested `TriSchedRL/` project directory. The nested project has the source/configs/scripts/tests. There is no `LICENSE` file in the archive and GitHub repository metadata reports no detected license, despite the top-level README saying MIT and linking to a missing license file.

### Dependencies and local execution

**Verified—repository:** The nested `requirements.txt` asks for NumPy >=1.24, pandas >=2.0, matplotlib >=3.7, PyYAML >=6.0, PyTorch >=2.1, and pytest >=7.0. The top-level README also lists Gymnasium and Python >=3.10, but Gymnasium is absent from the requirements file and is not used by the inspected simulator. No cloud account or paid infrastructure is required by the simulator code.

**Assessment:** The small smoke-test script is intended to run locally after its dependencies are installed, from the nested project directory so `src` imports resolve. I did not execute it. The paper's training/evaluation experiments cannot be run from this snapshot as provided: `train_trischedrl.py`, `run_baselines.py`, and `evaluate_and_plot.py` each only print placeholder instructions, and `run_all.sh` invokes only the smoke test. Thus local computation is feasible in principle, but the reported experiments are not executable from this repository without substantial missing implementation work.

## 6. Training/evaluation completeness and missing pieces

### Explicit placeholders / absent functions

- `scripts/train_trischedrl.py`: placeholder print; no training loop, replay sampling/update orchestration, checkpoints, or episode control.
- `scripts/run_baselines.py`: placeholder print; no runner for the reported comparison suite.
- `scripts/evaluate_and_plot.py`: placeholder print; no evaluation/plot pipeline.
- `scripts/run_all.sh`: runs only `smoke_test_guard.py`, not train, evaluate, or compare.
- No DQN implementation, target network, optimizer for Q-values, epsilon scheduler, DQN config, or end-to-end reward calculation.
- No training code for the three predictors and no generated historical training set or saved model parameters. Predictor modules are analytic heuristics.
- No code for paper-reported C-PPO, MO-PPO, SafeRL, NSGA-II, SQF, SLA/latency-oriented DRL comparison implementations. Included baseline functions are small selectors (EFT, least-energy, weighted sum, min-min/max-min); their evaluation runner is a placeholder.
- No table/figure reproduction scripts, multi-seed orchestration, confidence interval/statistical tests, ablation runner, sensitivity sweep, workload scaling sweep, or recorded run outputs.

### Other inconsistencies / limitations

- `EdgeCloudEnv.reset(seed)` accepts a seed but does not use it; randomness is in the separately seeded workload generator. Links are static despite the paper discussing time-varying bandwidth and delay.
- The smoke test generates arrivals with timestamps but loops over tasks without advancing/using those timestamps. The environment's `step` always returns `done=False`, so an episode lifecycle is not implemented.
- The paper mentions task priority and optional workflow chains; task priority only affects one risk-threshold guard check in the supplied code, and workflow dependencies are absent.
- The paper describes offline neural prediction modules, while current predictor functions are deterministic formulas. Their evaluation scores/accuracy claims cannot be reproduced from supplied materials.
- Simulator feasibility, environment state and policy state are not clearly tied together by a checked-in end-to-end scheduler. The test suite covers one environment step and one guard predicate only.
- No run was made, so runtime behavior beyond static source inspection is unknown. No performance figures are verified.

## 7. Is the paper a suitable baseline for our project?

### Carbon-intensity-aware scheduling

**Assessment:** The design is conceptually extensible: the simulator already has per-resource energy accounting and the policy state/reward framework is described as multi-objective. A carbon-aware extension could add time- and region-specific grid carbon intensity and optimize emissions (for example, energy multiplied by carbon intensity) with explicit treatment of task delay/SLA. However, no carbon-intensity data, region or time mapping, forecast, emission metric, or carbon reward exists in this paper/code. Carbon scheduling would be a new extension requiring these definitions and data; it is not a reproduced feature.

### Heterogeneous cloud resources

**Assessment:** The toy environment already distinguishes edge/cloud nodes and allows different processing rates, capacities, power values, and link characteristics. It is a reasonable scaffold for heterogeneous-resource concepts. It represents only three fixed edge nodes and one cloud node in its provided configuration, has no multi-cloud regions/providers, no memory model despite paper prose referencing resource capacities, and no GPU/accelerator or AI-specific resource model. Material extension is needed for heterogeneous distributed AI workload scheduling.

### Multi-agent reinforcement learning

**Assessment:** The paper and code use one centralized decision policy choosing one destination among candidate resources; the code has no independent agents, coordination protocol, centralized-training/decentralized-execution setup, or multi-agent benchmark. A MARL extension is possible but would be a substantial redesign: agent boundaries (e.g. per region/cloud), shared or local observations, conflict resolution, shared objectives/reward, communication, and evaluation under non-stationarity would need to be specified. The paper is not a MARL baseline.

## 8. Reproduction difficulty

**Assessment: high for a faithful reproduction; moderate-to-high for a paper-inspired reimplementation.** The simulator and some supporting modules provide a useful starting scaffold, but the repository's RL algorithm conflicts with the paper and the execution pipeline is missing. To reproduce the stated work, the team would need to implement the paper's DQN and trainer, trainable predictors, reward/weight pipeline, integrated guard interaction, baseline implementations, evaluation/statistical scripts, and precise workload/environment scenario definitions. Since the paper itself leaves some exact settings and definitions broad or inconsistent, any reimplementation would need a clearly documented assumptions register and should be described as a reconstruction rather than an exact reproduction unless the authors supply the missing implementation and artifacts.

## 9. Verified facts vs assumptions at a glance

| Statement | Status |
|---|---|
| Paper's central RL method is guarded DQN | Verified—paper |
| Checked-in agent is actor–critic, not DQN | Verified—repository |
| Training/evaluation scripts are placeholders | Verified—repository source text |
| Current predictors are analytic functions, not trained neural networks | Verified—repository source text |
| Simulator and workload are local, custom, synthetic Python | Verified—repository source/config |
| There are no bundled production datasets or trained artifacts | Verified—inspected archive contents |
| Paper's reported performance numbers can be regenerated with this snapshot | Not supported; scripts needed are absent |
| Carbon intensity could be added as input/objective | Assessment/proposal, not an existing feature |
| MARL can be built on top of it | Assessment; would require substantial design and implementation |

## Sources inspected

- Paper: [Springer article, DOI 10.1007/s10791-026-10607-x](https://link.springer.com/article/10.1007/s10791-026-10607-x)
- Repository: [AngularWaseem/TriSchedRL](https://github.com/AngularWaseem/TriSchedRL)
- Repository API metadata: [GitHub repository API](https://api.github.com/repos/AngularWaseem/TriSchedRL)
- Paper lines relevant to algorithm/state/reward/setup/results are in Sections 3.3–4.8 and 5.1–5.5. The source findings above come from the full public `main` source archive, read from a temporary inspection folder; no files were copied into the project.
