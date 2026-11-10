# System architecture

## Runtime layout

The repository uses importable top-level Python packages. Their locations are part of the runtime layout; run commands from the repository root.

```text
Task/workload generator
        |
        v
CloudEnvironment ---- Resource manager / feasibility
        |              Network / energy / carbon models
        v
Region IPPO scheduler (masked categorical policy)
        |
        +-- entropy gate -> fastest-feasible SPT (base)
        |                 -> carbon-aware latency-bounded SPT (proposed)
        v
Episode metrics, task outcomes, decision traces
        |
        +-- v4 saved result artifacts -> Streamlit research view / charts
        +-- fresh synthetic demo     -> Streamlit demonstration view
```

## Main packages

- `agents/`: independent IPPO agents, actor and critic networks, rollout buffer, shared reward, plus historical MAPPO and contextual-bandit implementations.
- `environment/`: task generation, the three-region cloud simulator, action/observation API, resource accounting, network delay, energy and carbon models.
- `agents/ippo_agent.py`: the entropy-guided IPPO scheduler and the base/proposed SPT destination selectors.
- `schedulers/`: supporting FCFS, Greedy, and Forecast MPC schedulers retained for historical/auxiliary experiments; they are not the primary v4 comparison.
- `experiments/`: training, workload preprocessing, diagnostics, historical benchmark scripts, and the one-pass v4 confirmation driver.
- `configs/`: training and simulator configurations. V4 records the frozen configuration snapshot in its own result directory.
- `data/`: local-only third-party inputs and derived historical trace data; omitted from the public release pending source-term verification. The final v4 holdout is generated synthetic data and does not use these files.
- `results/`: versioned historical runs, trained checkpoints and the authoritative v4 confirmation.
- `ui/`: Streamlit application and a runner that loads existing policy checkpoints for fresh demonstrations.
- `tests/`: simulator, method, constraint and supporting algorithm tests.

## Scheduling decision path

Each task is represented in the normalized 54-value observation. The actor for its source region produces probabilities over four actions: defer, execute in the local region, or migrate to either remote region. The action mask removes placements that fail current feasibility checks and always leaves deferral available. The entropy gate uses the masked legal distribution and the configured threshold fraction `0.8` of `log(legal action count)`.

If the SPT intervention triggers, both primary methods receive the same feasible candidate set. The base chooses the feasible destination with minimum estimated execution time. The proposed method computes estimated migration-plus-execution latency, retains candidates within 20% of the minimum latency, then chooses the candidate with lowest estimated incremental carbon (latency and fixed region order break ties). This allowance applies to estimated candidate latency at that decision only; it does not guarantee an overall latency limit. Placement still passes through the simulator's resource and deadline constraints.

## Physical and service models

The network model estimates migration time using task data volume, configured throughput and round-trip delay. The energy model accounts for region power, workload use and PUE; the carbon model integrates energy against a region-specific carbon-intensity profile. These are simulator estimates and scenario assumptions, not live cloud telemetry. Workloads can be generated synthetically or loaded from preserved historical datasets through the preprocessing and experiment utilities.

## Training and result flow

IPPO training and evaluation are separate scripts. The final v4 confirmation loads the existing `proposed_eps_0.000` checkpoints (from a common configuration of 16 episodes and 24 tasks per episode); it does not update the optimizer. For each of five policy seeds, both methods reuse the same checkpoint and matched workload, carbon profile, random seeds and simulator conditions. The one-pass outputs include `frozen_evaluation_config.json`, `seed_manifest.json`, `run_metadata.json`, `run_metrics.jsonl`, `task_outcomes.jsonl`, `decision_traces.jsonl`, `final_summary.json`, and `FINAL_REPORT.md` in `results/research_alignment_v4_final_confirmation/`.

The Streamlit saved-results section reads the v4 summary and saved charts. The fresh demonstration creates new illustrative synthetic tasks and reports those separately. It is not a replacement or extension of the confirmatory evaluation.
