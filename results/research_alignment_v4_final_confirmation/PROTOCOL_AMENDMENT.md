# Protocol amendment: fresh independent synthetic holdout

**Frozen before generating the new seeds or running the evaluation.** This amendment resolves the v3 blocker by creating a new synthetic holdout only after the evaluation protocol was frozen. It does not revise the methods, reward, model, or selected allowance.

## Fixed comparison

- Reference: A-MARL-derived IPPO; entropy-gated intervention selects the feasible destination with the shortest execution time (`IPPOScheduler._spt_destination`).
- Proposed: same IPPO policy checkpoint and entropy gate; intervention selects lowest estimated carbon among feasible destinations within 20% of the minimum total migration-plus-execution latency (`CarbonAwareSPTIPPOScheduler._spt_destination`). The allowance remains exactly 0.20.
- Reuse the existing proposed-epsilon-zero checkpoint for each policy seed `[7, 19, 42, 73, 101]` in both conditions. Do not train or update weights. This isolates the inference-time intervention rule, consistent with the v2 validation diagnostic.
- Both use stochastic action selection (`deterministic: false`), entropy fraction `0.8`, intervention probability `1.0`; reset policy RNGs to the same policy seed for matched conditions. Hold all other settings and the simulator fixed from `configs/research_alignment_v1.yaml` and `results/research_alignment_v1/ui_policy_index.json`.
- Evaluate three existing workload families (`variable`, `diverse`, `bursty`), 24 tasks per workload, six newly generated workload seeds reused across those families, with dynamic synthetic 512-slot carbon profiles. This is 18 workload instances × five policy seeds = 90 matched pairs and 180 method runs. Each workload-condition pair is evaluated once.

## New seed provenance and non-overlap

Only after this amendment is recorded, generate six 32-bit seeds with Python `secrets.randbits(32)` (OS-backed cryptographic randomness), reject duplicates, and compare them against seed values found in repository config files and prior result metadata/logs. Record UTC generation time, generator/runtime version, the complete set of prior seed values audited, source paths, and the overlap result in `seed_manifest.json` before any evaluation. If any collision is found, discard that candidate and draw another before running. Do not preview generated workloads or compute any method outcomes before the manifest is saved.

## Outcomes and inference

Capture total integrated simulator CO₂e, CO₂e per completed task, energy, completion rate/count, rejections, SLA violations, mean/total task latency, deferrals, intervention count/rate, and decision traces with feasible candidates, estimated carbon/latency, entropy, intervention and chosen destination. Label candidate carbon as an estimate; use final integrated simulator emissions for actual episode emissions.

Report proposed-minus-reference paired means with 95% two-factor crossed percentile-bootstrap intervals (10,000 replicates, resampling workload instances and policy seeds as crossed factors). Report the paired two-way-cluster wild-bootstrap test specified in v3 if supported by the fixed analysis code; otherwise report the pre-specified crossed-bootstrap intervals and clearly disclose unavailable p-values. Test service non-inferiority on rejection/SLA-violation rate with a **zero percentage-point margin**, justified by the simulator's hard per-task deadline feasibility (`environment/cloud_environment.py:130`) and its definition of SLA violations as rejections (`:231`). The one-sided upper 95% bound must be at most zero to establish non-inferiority. No average-latency margin is specified because the project defines no aggregate latency tolerance. Interpret all outcomes jointly; do not claim real-world generalization from synthetic workloads.

## Run controls

Run the full test suite before the evaluation. Save the manifest first, then the exact run command, config snapshot, checkpoint SHA-256 hashes, runtime/package versions, per-run output, per-decision trace, summary and final report in this new directory. Refuse to overwrite a nonempty directory. Do not inspect intermediate test outcomes, alter settings or run a second evaluation after seeing results. Existing results are immutable.
