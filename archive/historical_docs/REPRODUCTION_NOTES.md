# RL-MOTS Reproduction Notes

**Status:** reconnaissance only. No scheduler has been implemented and no experimental results have been generated.

## 1. Paper methodology summary

The selected paper is Yu et al., “Dynamic Multi Objective Task Scheduling in Cloud Computing Using Reinforcement Learning for Energy and Cost Optimization,” *Scientific Reports* 15, 45387 (2025), DOI [10.1038/s41598-025-29280-z](https://doi.org/10.1038/s41598-025-29280-z). The paper frames assignment of arriving jobs to heterogeneous cloud VMs and edge nodes as an MDP, with a DQN scheduler intended to balance energy, operating cost, and quality of service (QoS).

- **Simulation environment:** A simulated cloud-edge environment. The methods describe CloudSim-like cloudlets, one data center, hosts/VMs, edge nodes, and time-shared host/VM schedulers. The paper says traces from Google 2019, Alibaba 2018, and Azure 2019 are used, converted into cloudlets while preserving arrival times.
- **Tasks:** At minimum, tasks have instruction length (MI), arrival time, deadline, and resource demands. The paper discusses task lengths of 1,000–900,000 instructions and 200–1,000 tasks. Memory and I/O demands are said to be derived from trace counters, but the precise task schema is not fully specified.
- **VMs/resources:** Heterogeneous CPU/MIPS, RAM, bandwidth, storage, and usage costs. The simulation table lists 5–100 VMs (3,500–100,000 MIPS; 1–4 GB memory), 5–20 edge nodes (2,000–15,000 MIPS; 512 MB–2 GB), and 20 hosts (177,730 MIPS, 16 GB RAM, 10 GB/s bandwidth, 2 TB storage). It mentions Xen and time-shared scheduling.
- **State:** Described qualitatively as a feature vector of system/resource utilization, CPU and memory status, energy/cost context, and deadline/QoS information. Task queue and per-resource feature definitions, vector ordering, normalization, and dimension are not specified consistently enough to reconstruct the exact observation.
- **Action:** Assign a selected task to a VM or edge node; some prose also mentions moving/migrating work to balance load. The valid-action mask, task selection rule, and whether migration is truly an action are not formalized clearly.
- **Reward:** A weighted multi-objective reward penalizes energy use and operating cost and rewards QoS/deadline satisfaction and throughput. Weights are said to adapt to system conditions. The paper does not provide a complete executable reward equation, normalization ranges, or a precise adaptation rule. A migration penalty is also reported in the hyperparameter table.
- **DQN architecture/learning:** Fully connected network with two 256-unit hidden layers; Double DQN enabled; Adam learning rate 0.0005; discount factor 0.98; gradient clipping at 10. Prioritized replay is reported with buffer 50,000, batch 64, priority exponent 0.6, and importance-sampling beta 0.4→1.0.
- **Target/exploration:** Hard target-network synchronization every 750 steps. Epsilon-greedy exploration from 1.0 to 0.05, with 0.995 per-episode decay. Replay warm-up is 2,000 transitions. Training table states 600 episodes.
- **Evaluation:** The paper variously lists makespan, average waiting time, total energy, operational cost, deadline-violation rate, active VM count, and Q-value convergence; later it also reports throughput, average resource utilization rate (ARUR), and degree of imbalance (DI). It claims 25 independent seeds in its experimental description. This notes the claims, not reproduced findings.

The paper's introductory/algorithm prose mentions a generic DQN with experience replay and a periodically updated target network. The specific settings section later calls the method Double DQN with prioritized replay. The latter is the more detailed specification, but this conflict must be retained in any reproduction record.

## 2. Original implementation inspection

The project directory was empty at inspection: there were no pre-existing project files to preserve or compare. The Zenodo public API record was retrieved, and `rlmots-code-v1.zip` (7,498 bytes; MD5 `49cf3216b266ed56ce5f5848726bc2b9`) was downloaded and unpacked only in a temporary inspection folder. Nothing from the archive was copied into or used to overwrite the project. The record describes a CC BY 4.0 software upload by Ling Tang, published 2025-11-10. The archive README calls it a **“clean-room implementation”**, not the exact implementation used for the reported results; its `CITATION.cff` identifies an anonymous author and `https://example.com/rlmots` repository URL.

Archive contents inspected:

- `rlmots/env.py`: small synthetic cloud-edge simulator, task/node classes.
- `rlmots/dqn_agent.py`: PyTorch feed-forward Q-network, Double-DQN option, replay buffer, epsilon-greedy selection.
- `configs/google2019_small.yaml`: one small configuration.
- `scripts/run_experiments.py`: training loop and JSON reward/loss logging.
- `rlmots/baselines.py`: FCFS/Max-Min plus placeholder functions for Q-learning and two other baselines.
- `scripts/plot_pareto.py`: generates random “fake” points; it does not read the supplied results path.
- README, requirements, license, and citation file.

The source is readable, but it is not a complete or faithful reproduction package. In particular, the archive's README says the data is represented by synthetic generators and offers instructions for users to supply processed traces; no Google, Alibaba, or Azure trace data is included.

## 3. Algorithm and hyperparameter details

### Paper-reported settings

| Setting | Paper's detailed setting |
|---|---:|
| Episodes | 600 |
| Replay warm-up | 2,000 transitions |
| Replay capacity | 50,000 |
| Mini-batch | 64 |
| Optimizer / learning rate | Adam / 0.0005 |
| Discount factor | 0.98 |
| Target update | hard sync every 750 steps |
| Epsilon | 1.0 → 0.05, decay 0.995 per episode |
| Q-network | fully connected, 256 / 256 hidden units |
| DQN type | Double DQN |
| Replay type | prioritized; alpha 0.6, beta 0.4 → 1.0 |
| Gradient clipping | 10.0 |
| Initial reward weights | energy/cost/QoS = 0.4/0.3/0.3, then adaptive |
| Migration penalty | 0.10 normalized cost units |

The paper's HTML text extraction omits several mathematical symbols/values in the hyperparameter discussion, but Table 3 supplies the values above. The prose says a small validation-grid search was used, without giving the candidate grid or validation split. The environment table appears as “Table 2” in the HTML while the prose refers to a separate DQN parameter table; numbering/formatting is inconsistent.

### Archive settings and behavior

The YAML uses 50 episodes, 10 configured hosts, 50 VMs, 5 edge nodes, 400 tasks, VM speed 3,500–100,000 MIPS, edge speed 2,000–15,000 MIPS, task length 1,000–900,000 MI, and Poisson-style arrivals. DQN settings are lr 0.0005, gamma 0.98, batch 64, buffer 50,000, target interval 750, epsilon 1.0→0.05 with 0.995 decay, [256,256] layers, Double DQN and prioritized replay enabled.

The code uses a ReLU MLP and Adam. It selects a random action with epsilon probability and otherwise takes argmax Q. Double-DQN action selection/evaluation is implemented, and target weights are hard-copied on the configured optimizer-step interval. The replay prioritization uses stored priorities initialized from a caller-provided TD error (default 1), samples with replacement, and applies normalized inverse-probability weights. It does not update priorities after learning, apply the paper's beta annealing, or implement the stated 2,000-transition warm-up. Epsilon is decayed on every optimizer update, not per episode.

## 4. Paper-to-code comparison

| Area | Paper describes/reports | Archive implements | Assessment |
|---|---|---|---|
| Simulator | CloudSim-style heterogeneous cloud-edge environment | Custom Python toy simulator | Different simulator and semantics; no CloudSim implementation |
| Hosts | 20 hosts with stated capacity | `n_hosts` is configured but unused | Host layer absent |
| Resources | CPU, RAM, bandwidth, storage, costs; heterogeneous VMs and edge nodes | Nodes only have MIPS, time, energy, busy time | Most resource constraints and heterogeneity dimensions absent |
| Workloads | Google/Alibaba/Azure traces, preserved time order | Synthetic random MI and exponential arrival times | No trace loader, trace data, or trace-derived resource needs |
| State | Resource, energy/cost and deadline/QoS context | `[mean_load, pending_ratio]` only | Does not expose current task features or per-node alternatives to the policy |
| Action | Assign task to VM/edge; possibly migration | Index of a node for next FIFO task | No migration; no task selection or valid-action masking |
| Reward | Energy, cost, QoS/throughput; adaptive weights; migration penalty | Static weighted energy proxy + cost proxy + deadline-success bonus | No adaptive weights, throughput, migration penalty, or paper normalization |
| DQN | 2×256, Double DQN, Adam, clipping | These core elements are implemented | Partial match |
| Prioritized replay | Alpha 0.6, beta annealing 0.4→1.0 | Initial priorities only; no priority refresh or beta schedule | Not the reported PER algorithm; samples with replacement |
| Exploration | Per-episode epsilon decay | Per-learning-step decay | Different schedule and much faster effective decay |
| Episodes/warm-up | 600; 2,000 transitions | 50; no warm-up | Configuration mismatch |
| Evaluation | Multiple metrics and 25 seeds | Logs only episodic reward and loss | Metrics/replication pipeline absent |
| Baselines/plots | Multiple named methods and result figures | FCFS/Max-Min; others placeholders; plot is random synthetic points | Cannot reproduce comparisons or reported plots |

Additional code-level observations: each episode constructs a fresh environment with the same seed, so the generated tasks and nodes repeat across episodes. Python's `random`, NumPy's global RNG, and PyTorch are not all seeded. `reset_tasks` generates the whole synthetic task list before training and `step` stops when all tasks are assigned; it does not explicitly advance/drain the simulator until all executions finish. The configured `arrival_pattern` is not read. The environment's `migration_penalty` is stored but never used. The `n_hosts` field is unused. The README mentions PPO/A3C elsewhere in the paper context, but no such archive code is present.

## 5. Missing or ambiguous information

1. **What counts as the baseline:** the paper's narrative algorithm is not enough to resolve whether the intended reference is standard DQN or the later Double-DQN/PER configuration. The deposited code calls itself clean-room, which prevents treating it as the authors' exact run-generating code.
2. **State/action definition:** there is no complete fixed state vector, its normalization, task selection procedure, action legality rule, or precise migration decision definition.
3. **Reward math:** objective equations are described, but reward normalization/scales and exact adaptive weight updates are missing. Reported energy, cost, deadline/QoS and throughput terms cannot be reconstructed unambiguously from prose alone.
4. **Environment parameters:** multiple table values and simulation descriptions are available, but resource distributions, network/edge communication delays, interference, VM provisioning, failure behavior, and complete execution semantics are not specified.
5. **Trace processing:** named public traces and broad transformation claims are stated, but the exact source files, filters, aggregation windows, mappings, and processed data are not shipped in this archive.
6. **Training/evaluation protocol:** seed list, train/validation/test split, checkpoint selection, warm-up/update cadence details, and confidence intervals are not fully defined. The paper's 600 episodes and 25-run reporting do not by themselves resolve these.
7. **Paper inconsistencies:** high-level prose and detailed hyperparameter table differ in algorithm specificity; metrics and table numbering vary across sections. The text calls energy/cost/QoS a three-objective reward but elsewhere includes throughput and utilization. “Carbon footprint” appears in motivation but no carbon-intensity input or carbon objective is defined.

## 6. Proposed minimal reproduction plan

Keep the archived code and any eventual new baseline in separate directories. Since the archive is a toy clean-room implementation, use it as an inspection/reference artifact only; implement a small, independent local Python/PyTorch baseline guided by the paper, and label every choice not determined by the paper as an assumption.

1. Define a deterministic, discrete-event synthetic environment with a task queue, heterogeneous VM/edge nodes, explicit task MI/arrival/deadline and CPU/memory demands, and explicit node capacity/queue state. Do not claim to use Google/Alibaba/Azure traces unless trace inputs and the transformation are actually available.
2. Specify one central scheduler observation and action mapping in writing before coding. A minimal first version can schedule the next arrived task onto one available VM/node; include normalized task and per-node features so actions can be evaluated from the state. Do not include migration unless it is implemented and its paper semantics can be resolved.
3. Implement the paper's reported Double DQN settings (2×256, Adam 0.0005, gamma .98, replay 50,000, batch 64, warm-up 2,000, target sync 750, epsilon 1.0→.05 decayed per episode, gradient clip 10). Implement PER correctly only if alpha/beta annealing and per-sample priority updates are included. Mark the result as a paper-guided reconstruction, not exact reproduction.
4. Implement a static and explicit energy/cost/QoS reward first. Since adaptive weights are undefined, do not silently invent them; record an explicit fixed-weight assumption (paper's initial 0.4/0.3/0.3 is a reasonable provisional setting) and treat adaptive weighting as unresolved until specified.
5. Add transparent random seeds and report mean and spread across repeated runs. Log episode return, makespan, average waiting time, energy proxy, cost proxy, deadline violations, utilization, and Q-loss/convergence. Preserve raw per-run outputs.
6. Compare against simple local FCFS and Max-Min baselines on identical generated workloads. Do not use the archive's fake Pareto plotting function or placeholder methods as experimental baselines.
7. Keep the later carbon-aware/MARL extension in a separate module and out of the baseline reward and state.

Before interpreting any metrics as a reproduction of the paper, resolve (or explicitly freeze as assumptions) the reward definition, state/action representation, and trace/environment semantics. No results are claimed here.

## 7. Dependencies and setup instructions

The archive's unpinned `requirements.txt` lists NumPy, pandas, matplotlib, PyTorch, tqdm, PyYAML, and scikit-learn. No Python version, package versions, lockfile, or CloudSim dependency is declared. The proposed independent baseline needs Python and PyTorch locally; NumPy and PyYAML are sufficient for a minimal simulator/config. Add plotting or tabular dependencies only when those features are implemented. Pin tested versions in a future requirements file or lockfile before claiming reproducibility.

The archive README suggests:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

This documents how the archive says to set up its own clean-room package; it should not be read as evidence that the package reproduces the paper. No dependencies were installed and no code was executed as part of this inspection.

## 8. Known limitations

- The public Zenodo archive is only 7.5 KB and explicitly describes itself as a clean-room reference implementation. It does not substantiate the paper's claims of containing the exact code used to generate the results.
- The archive lacks benchmark traces, complete baselines, metric aggregation, and valid plotting from experiment outputs.
- Its replay priorities are not maintained from TD errors, and its epsilon decay and episode/configuration values do not match the reported protocol.
- The paper leaves central MDP and reward details underspecified, and its narrative/hyperparameter sections conflict. Exact numerical reproduction is therefore not currently well-defined from the available artifacts.
- The available source text and archive were inspected, but the paper equations include image-based math that the text extraction does not render reliably. Verify equations against the PDF before finalizing any formula-level implementation.
- Baseline reproduction should remain isolated from carbon-aware rewards and MARL until the baseline design is approved and validated.

## Sources

- Paper full text indexed by PubMed Central: [PMC12749791](https://pmc.ncbi.nlm.nih.gov/articles/PMC12749791/)
- Paper record: [PubMed](https://pubmed.ncbi.nlm.nih.gov/41298680/)
- Original archive record and metadata: [Zenodo 17575537](https://zenodo.org/records/17575537)
- Archive file: `rlmots-code-v1.zip` (record file checksum and size recorded in §2; inspected from a temporary folder, not retained in this project).
