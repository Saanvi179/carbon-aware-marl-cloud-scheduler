# A-MARL paper and GitHub verification

**Scope:** Read-only review of the public paper metadata, the GitHub `develop` branch, the paper-specific code/configuration, included run logs, and the Jumanji JobShop simulator documentation. No project code or existing files were changed. No scripts, tests, or experiments were run, and no reproduction is claimed.

## Executive finding

The paper and repository describe **A-MARL as IPPO (independent PPO) with entropy-guided SPT action intervention**. The repository contains a full Mava/JAX training and evaluation path and checked-in training logs, so it is more runnable than a code-only sketch. However, the environment is a small Jumanji **job-shop scheduling** problem: one agent per machine selects a job (or no-op) at each step. It is not an edge/cloud resource simulator, and the source reward is a makespan proxy with an invalid-action/idle penalty—not a carbon-, energy-, SLA-, or cloud-cost objective.

The implementation aligns at the algorithm-label level with the public paper description (Multi-Agent PPO plus SPT-guided exploration), but the repository README overstates some implementation details and its setup does not establish a faithful reproduction of all paper claims. I could not access the IEEE full text in this session, so paper-specific equations and experimental protocol beyond its public abstract/metadata remain unverified. For the target project, A-MARL is a useful **MARL training scaffold and exploration idea**, but not a directly reusable cloud-scheduling baseline. Extending it to the target simulator would require substantial environment and objective redesign.

## Evidence labels

- **Verified—paper/public metadata:** available article metadata and abstract/summary associated with the DOI. The IEEE article page itself returned an anti-bot page, so full paper equations/tables could not be inspected.
- **Verified—repository:** checked in the public GitHub `develop` branch source, configuration, tests, and logs.
- **Verified—simulator documentation:** official Jumanji JobShop documentation used to interpret the environment's state, action, and reward.
- **Assessment:** comparison or engineering judgment based on those facts.
- **Unverified:** information not available from the accessible sources; no assumption is presented as a paper fact.

## 1. Paper method and code algorithm

### What the paper publicly describes

**Verified—paper/public metadata:** The work is “A-MARL: Agile Multi-Agent Reinforcement Learning for Soft Real-Time Task Scheduling in Edge Computing,” IEEE CASCON 2025, DOI [10.1109/CASCON66301.2025.00053](https://doi.org/10.1109/CASCON66301.2025.00053). Its public abstract/summary describes an enhancement to **Multi-Agent PPO**: when policy entropy is high, use **Shortest Processing Time (SPT)** as informed exploration; as entropy falls, rely more on the learned policy. The intended benefit is faster convergence / improved sample efficiency on the paper's scheduling problem.

The accessible abstract and the repository's own description do not expose enough of the paper to independently verify its exact state, action, reward, network, task/resource semantics, or all reported experiment settings. Those are marked unverified below unless directly observable in code.

### What the repository implements

**Verified—repository:** `mava/systems/ppo/anakin/informed_ff_ippo.py` is a substantial PPO learner/evaluator derived from Mava's feed-forward IPPO path, with an added entropy threshold and SPT intervention. The underlying learner is PPO: rollout collection, generalized advantage estimation, clipped probability-ratio objective, critic loss, entropy regularization, minibatches, multiple PPO epochs, and Adam updates are present.

For each rollout step, the code computes the mean policy entropy over the batched policy, compares it to `0.8 * log(action_count)`, samples the policy action, and computes an SPT action for JobShop. If mean entropy is above the threshold, the joint SPT action replaces the sampled action; otherwise the sampled policy action is used. `0.8` is hard-coded in the script rather than read from YAML.

This is **not** centralized-critic MAPPO. It is the Mava **IPPO** implementation, with actor and value critic networks applied to per-agent observations. The same actor/critic parameter sets are applied across agent entries (parameter sharing), with agent ID support enabled in the configuration. Each agent acts independently at execution time, while the environment gives all agents the same global scheduling observation and shared reward.

## 2. Agents, state, action, and reward

### Agents and environment meaning

**Verified—repository:** `JobShopWrapper` sets `num_agents = env.num_machines`. With the checked-in test scenario this means four agents, interpreted as four machines. The README instead says “one RL-agent per Edge-Server”; that wording does not match the implemented JobShop mapping. There are no edge-server objects in the environment.

### State / observation

**Verified—simulator documentation and repository:** The underlying JobShop observation includes:

- For every job and operation: required machine ID, operation duration, and a mask indicating which operations remain / which is next.
- For each machine: current job ID and remaining processing time.
- An action mask showing legal job choices and no-op for each machine.

The wrapper normalizes and flattens operation machine IDs, durations, remaining-operation masks, machine job IDs, and machine remaining times, then duplicates the same flattened global vector for every agent. It also supplies the action mask and step count. Mava configuration enables implicit/explicit agent identity handling (`implicit_agent_id: true`, `add_agent_id: true` in the PPO config).

This state does not represent cloud regions, VM/GPU types, carbon intensity, electricity prices, network routes, task arrival times, or task deadlines.

### Action

**Verified—simulator documentation and repository:** The environment action is a vector with one discrete choice per machine. Each machine chooses one job ID to schedule its next eligible operation, or the no-op action. In the supplied scenario there are five jobs, four machines, and six choices per machine (five jobs plus no-op), with legality governed by the action mask.

This is not a direct `(task, edge-server)` placement action as the top-level README's architecture sketch suggests. The machine identity determines the resource; the action selects the job for that machine.

### Reward

**Verified—simulator documentation:** Jumanji JobShop returns `-1` per time step while scheduling continues. Invalid actions and a state in which all machines are idle receive a large negative penalty equal to `-num_jobs * max_num_ops * max_op_duration`. Completing a schedule terminates the episode. This reward minimizes schedule length/makespan indirectly.

`JobShopWrapper` broadcasts the scalar environment reward to all agents. The checked-in A-MARL code does not add a separate reward function for soft deadlines, SLA satisfaction, energy, cost, or carbon. The paper's exact reward formula could not be verified from the accessible paper text.

## 3. Paper-to-code comparison

| Claim/feature | Paper/public description | Checked-in code | Assessment |
|---|---|---|---|
| Core algorithm | Multi-Agent PPO augmented with entropy-guided SPT | Mava IPPO/PPO learner plus entropy-triggered SPT action substitution | Broad algorithm concept matches |
| Agent count/meaning | Multi-agent scheduling in edge computing | One agent per JobShop machine (4 in checked-in scenario) | Domain interpretation differs from README's “per Edge-Server” wording |
| Exploration rule | SPT when entropy is high, policy when entropy falls | Hard-coded threshold `0.8 * log(action_count)`; SPT replaces sampled joint action | Mechanism broadly matches; exact paper threshold/formula unverified |
| Pseudo-action masking | README calls this pruning the effective action set to SPT-guided choices | Code replaces the policy's whole joint action with the SPT action while above threshold; it does not construct a new distribution masked to only SPT candidates | Description and implementation are not identical |
| Batch handling | Not verifiable from accessible paper text | SPT computes from the first environment in a batch and broadcasts that action to the other environments | Risk of invalid or poor actions when vectorized environment states differ; outcome not tested here |
| Policy/network | README advertises residual MLP plus self-attention | Active IPPO actor/critic configs use `JobShopTorso` residual MLP plus MLP heads; `JobShopAttentionTorso` exists for a q-network config, but IPPO does not train/use a Q-network | Self-attention is not on the active actor/critic path |
| Scheduling problem | Soft-real-time task scheduling in edge computing | Jumanji static job-shop operations/machines; no edge/cloud network or deadline model | Major environment/domain gap |
| Reward | Paper's exact formula inaccessible here | Jumanji makespan proxy and terminal invalid/idle penalty | Code reward is confirmed; paper match cannot be established |
| Evaluation claims | Paper abstract reports comparative improvement | Embedded evaluator and training/evaluation logger exist; two log artifacts are checked in | Pipeline exists, but logs alone do not validate all reported claims |

**Assessment:** The source is plausibly an implementation of the method's central idea (IPPO plus entropy-conditioned SPT) on the authors' selected job-shop benchmark, but a complete paper-to-code match cannot be verified without paper equations/tables. The source and README also disagree in meaningful architecture and action-mask descriptions.

## 4. Training, evaluation, and tests

### Completeness

**Verified—repository:** Unlike a placeholder, `informed_ff_ippo.py` contains a full training loop, optimizer updates, logging, periodic evaluation, and optional checkpoint saves. `ff_ippo.py` provides the plain IPPO comparison. The evaluation function is called inside each training run; a separate paper-specific evaluation script is not present. Hydra configurations define the default environment, network, architecture, and PPO training parameters.

The standard Mava integration tests are in `test/integration_test.py`, but their enumerated PPO systems and environments do not include `informed_ff_ippo` or `JobShop`. No dedicated test covers SPT selection, entropy switching, batch behavior, or the A-MARL JobShop training path. I did not run the test suite.

### Configurations, dependencies, and data

**Verified—repository:** Configurations are present. The JobShop scenario is small: 5 jobs, 4 machines, at most 4 operations/job, max operation duration 4. The default training config specifies 16 vectorized environments, 1,000 PPO updates, rollout length 128, 4 PPO epochs, 2 minibatches, gamma .99, GAE lambda .95, actor/critic learning rates 2.5e-4, and entropy coefficient .01. The Anakin config requests 122 evaluations and 32 evaluation episodes, with 320 episodes for the final absolute metric. The `informed_ff_ippo.py` script itself uses the same base Hydra config as IPPO.

The repository is a large Mava/JAX project, with `pyproject.toml` and `uv.lock`. It requires Python >=3.10 and <3.13 and includes JAX/JAXlib, Flax, Optax, Hydra, Jumanji, and other MARL/environment dependencies (including Git-sourced packages). JAX installation is hardware-sensitive. The workload is generated by Jumanji's random JobShop generator; no external dataset is needed or supplied. No cloud account or paid cloud service is required by the inspected experiment path.

**Assessment:** Experiments appear runnable locally after installing the locked dependencies, using the repository's documented commands:

```bash
python mava/systems/ppo/anakin/ff_ippo.py env=job_shop
python mava/systems/ppo/anakin/informed_ff_ippo.py env=job_shop
```

This was inferred from the source, lockfile and documented entry points; commands were not run in this inspection. JAX CPU execution is possible in principle, but runtime and compatibility depend on the local platform. The repository logs report roughly 4 million training timesteps and about 4,300–4,700 seconds elapsed for the checked-in runs, so a full run is not a quick smoke test; the logs do not identify the hardware.

### Reproducibility

**Verified—repository:** Two checked-in `.csv` files are actually text logs for `ff_ippo` and `informed_ff_ippo`. Each contains records through timestep 3,997,696, evaluator/trainer summaries, and an absolute evaluation summary. A dependency lockfile, default seed 42, scenario YAML, and run commands are also present.

**Limits:** The logs do not establish run provenance (hardware, exact package resolution at execution, command overrides, commit/config hash), and they appear to be one training trace per variant rather than multi-seed statistics. No checkpoints or independent result-aggregation/statistical-analysis script were present in the inspected relevant tree. The integration tests do not test the A-MARL path. Consequently, someone can run the included setup locally, and the committed logs provide partial reference evidence, but independent reproduction of the paper's headline results is not demonstrated by the repository alone.

## 5. Missing code, placeholders, and inconsistencies

- No separate pseudo-action mask over SPT candidate actions: the custom code switches the full action vector to SPT above the entropy threshold. The environment's ordinary legal-action mask is separate from that intervention.
- The entropy threshold fraction is hard-coded at 0.8 and not exposed as a config setting. The README's displayed threshold equation is malformed and does not make the precise implemented formula clearer.
- For batched environments, SPT is calculated from environment index 0 and broadcast across the batch. If those environments have different job/machine states, the resulting decisions may not be valid for all of them.
- The code stores the log-probability of the action after possible SPT replacement. Thus PPO's later ratio is computed for an action that may have been imposed by the heuristic rather than sampled from that policy distribution. The practical learning effect is not evaluated here.
- The active PPO actor/critic do not use the configured JobShop attention torso; it is present for the q-network path, while IPPO uses actor/critic and no Q-network.
- The README's “per Edge-Server” agent and `(Task ID, Edge-Server ID)` action sketch do not describe the actual machine/job action semantics.
- The environment has no deadlines, release/arrival times, soft-real-time hit ratio, edge/cloud hierarchy, communication latency, energy, or carbon model. JobShop operation durations and precedence constraints are not equivalent to those omitted features.
- The generic test suite samples other Mava systems/environments; it does not exercise the custom A-MARL learner or JobShop scenario.
- The README's speed/sample-efficiency claims and the tracked logs are not independently verifiable from the repository alone; no repeated-seed statistical pipeline is supplied for those headline claims.

## 6. Fit for carbon-aware heterogeneous cloud scheduling

### Carbon intensity

**Assessment:** The PPO/IPPO learner and explicit state/action mask structure can be reused conceptually, but adding carbon awareness to this code is not a small reward-only change. The current simulator has no energy use or region/time-varying carbon intensity. A cloud scheduling environment would need per-resource energy models, carbon-intensity inputs or forecasts, time/region indexing, a clear emissions objective, and an SLA/latency trade-off. Training would then need to be rerun in that environment.

### Heterogeneous cloud resources

**Assessment:** JobShop machines are distinct by operation routing, but are not modeled as heterogeneous cloud instances with CPU/GPU/memory/bandwidth, prices, availability, or regional carbon intensities. A heterogeneous-cloud simulator and new observation/action semantics would need to replace or substantially extend Jumanji JobShop. The source provides little direct resource-model code to reuse.

### Multi-agent learning

**Assessment:** This repository already supplies a multi-agent PPO scaffold, which is the most reusable part. Its current agents correspond to machines sharing one global JobShop state and team reward, not separate cloud providers/regions independently scheduling AI workloads. Defining cloud-level agent boundaries, local/global observations, contention coordination, action legality, and credit assignment would be a material redesign. Framework reuse is plausible; direct method transfer is not.

### Implementation difficulty

**Assessment:** **Moderate** to rerun the included small JobShop IPPO/A-MARL benchmark in a compatible local JAX environment; **high** to verify/reproduce all paper results; **high** to adapt the benchmark into carbon-aware heterogeneous cloud scheduling. The main work is the new simulator/problem formulation, not changing the SPT rule. The repository uses JAX/Flax/Optax rather than PyTorch, so a project requirement to use PyTorch would add a port or reimplementation.

## 7. Sources and limits

- Paper DOI: [IEEE CASCON 2025 paper](https://doi.org/10.1109/CASCON66301.2025.00053). The IEEE full-text page was blocked by its anti-bot interstitial in this inspection; formal paper equations/tables were therefore not independently checked.
- Public abstract/metadata summary: [EurekaMag record](https://eurekamag.com/research/104/995/104995732.php). Used only for the broad Multi-Agent PPO + entropy-guided SPT description.
- Repository README and source: [AminAvan/a_marl-scheduler](https://github.com/AminAvan/a_marl-scheduler), [informed IPPO implementation](https://github.com/AminAvan/a_marl-scheduler/blob/develop/mava/systems/ppo/anakin/informed_ff_ippo.py), [JobShop wrapper](https://github.com/AminAvan/a_marl-scheduler/blob/develop/mava/wrappers/job_shop_wrapper.py), [JobShop scenario config](https://github.com/AminAvan/a_marl-scheduler/blob/develop/mava/configs/env/scenario/jobshop-test-scenario.yaml), [dependency manifest](https://github.com/AminAvan/a_marl-scheduler/blob/develop/pyproject.toml), [integration tests](https://github.com/AminAvan/a_marl-scheduler/tree/develop/test).
- Simulator semantics: [Official Jumanji JobShop documentation](https://instadeepai.github.io/jumanji/environments/job_shop/).
- The GitHub branch inspected was `develop`, resolving to commit `fe5b17a8b0c2ecb9ee60bcbd8777315873939e6d` during this review. As a branch can change, repeat checks against this commit for an exact snapshot.
