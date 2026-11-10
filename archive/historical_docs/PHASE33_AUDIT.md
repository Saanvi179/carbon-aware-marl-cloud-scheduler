# Independent Audit Report: Phase 3.3 Forecast-Aware MPC Scheduling

**Audit Date:** November 1, 2026  
**Auditor:** Independent Research Auditor (AI Pair Programmer)  
**Subject:** Phase 3.3 Implementation (`schedulers/forecast_mpc.py`, `experiments/run_phase33.py`, `configs/phase33_forecast_config.yaml`, and artifacts `results/phase33/*`)  
**Status:** Audit Complete — Corrections and Methodological Clarifications Required Prior to Publication

---

## Executive Summary & Audit Verdict

This audit conducted an independent, mathematically rigorous inspection of the Phase 3.3 Forecast-Aware Receding Horizon Model Predictive Control (MPC) scheduling implementation, its raw execution data (`results/phase33/phase33_runs.csv`), evaluation aggregation (`results/phase33/phase33_evaluation.json`), and accompanying report (`PHASE33_REPORT.md`).

### Summary of Audit Findings:

1. **2h vs. 4h Horizon Degeneracy (CRITICAL DESIGN BOTTLENECK):**
   *Forecast MPC (2h)* and *Forecast MPC (4h)* produced **100% bit-for-bit identical scheduling decisions** (zero difference across carbon, energy, completion, SLA violations, deferrals, and latency).
   - **Root Cause:** In `ForecastAwareMPCScheduler.evaluate_forecast_opportunity()`, the lookahead window is computed as:
     $$\text{lookahead\_slots} = \min(\text{remaining\_deferrals}, \text{self.horizon\_slots}, \text{slots\_from\_slack})$$
   - In `CloudEnvironment`, `max_deferrals` is hardcoded to $2$. Because `remaining_deferrals <= 2`, `lookahead_slots` was clamped to at most $2$ slots ($30\text{ minutes}$) under both the 2-hour ($8\text{ slots}$) and 4-hour ($16\text{ slots}$) configurations.
   - Consequently, neither configuration ever queried carbon forecasts beyond $30\text{ minutes}$. **The experiment did not evaluate 2h vs. 4h horizons; it evaluated two instances of a 30-minute horizon.**

2. **Burst 48 Completion Drop (CAPACITY CLIFF EFFECT):**
   On the 48-task burst family (`burst_2h_48tasks`), MPC completion dropped from **92.31% (576/624 tasks)** under Greedy to **91.83% (573/624 tasks)** under MPC (3 additional task rejections).
   - **Root Cause:** MPC defers delay-tolerant tasks when regions are congested. However, online deferral without slot reservation defers tasks directly into a fully saturated cluster at slot $s+2$. When the hard deferral limit is reached (`force = True`), no candidate region has available capacity, causing immediate task rejection.
   - Conversely, in peak-burst Instance 11, MPC's deferral successfully load-leveled the cluster, completing 40 tasks vs. Greedy's 36 tasks. Across the cohort, completion varied in 5 out of 13 instances.

3. **Confounded Burst Emissions vs. Verified Spread Emissions:**
   - On **spread workloads** (100% completion across all policies), MPC achieved statistically significant carbon reductions over Greedy:
     - `spread_12tasks`: $-1.08\%$ ($p = 0.0470$, 95% CI $[-6.66, -0.91]\text{ g}$)
     - `spread_24tasks`: $-1.32\%$ ($p = 0.0128$, 95% CI $[-14.43, -4.02]\text{ g}$)
     - `spread_48tasks`: $-0.94\%$ ($p = 0.0009$, 95% CI $[-12.49, -4.94]\text{ g}$)
   - On **equal-completion instances** (73 of 78 instances where Greedy and MPC completed identical task counts), MPC achieved a **$-2.02\%$ carbon reduction** ($p = 0.00235$, 95% CI $[-19.35, -5.42]\text{ gCO2e}$). This confirms the fundamental carbon-saving mechanism of MPC when capacity is sufficient.
   - However, on `burst_2h_48tasks`, the raw $-3.61\%$ emissions reduction ($-36.32\text{ gCO2e}$) is **partially confounded** by completing 3 fewer tasks (unexecuted tasks emit zero compute carbon).

4. **Internal Inconsistency in `PHASE33_REPORT.md` (DOCUMENTATION ERROR):**
   Section 1 of `PHASE33_REPORT.md` states:
   > *"Burst 48-task cohorts: 100.0% completion with ZERO rejections, achieving 866.57 gCO2e vs Greedy's 926.51 gCO2e."*
   - This statement is **factually false** and contradicts the data in the report's own Table 1, `phase33_runs.csv`, and `phase33_evaluation.json`.
   - The actual generated figures for `burst_2h_48tasks` are: **91.8% completion, 3.923 SLA violations/rejections per window, and 969.15 gCO2e** (vs Greedy's 92.3% completion, 3.692 rejections, and 1005.47 gCO2e). The text appears to have accidentally copied metrics from `spread_48tasks`.

5. **Future-Information Leakage Audit (CLEAN):**
   `CarbonForecastProvider` strictly enforces horizon bounds, introduces zero-mean Gaussian forecast noise ($\pm 5\%$), and prohibits access beyond `current_slot + lookahead_slots`. No future workload arrival information is leaked.

6. **Publication Readiness Verdict:**
   **NOT READY FOR PUBLICATION AS-IS.** While the modular implementation, forecast provider, and unit test suite are mathematically sound, the empirical comparison between 2h and 4h forecast horizons is degenerate due to the `max_deferrals = 2` environment clamp, and the burst emissions reduction is confounded by completion loss.

---

## Detailed Investigation 1 & 2: Why 2h and 4h Horizons are Identical

### 1. Verification of Simulation Outputs
Inspection of the 312 execution rows in `results/phase33/phase33_runs.csv` reveals that for every single instance $(i \in \{0, \dots, 77\})$, the metrics for *Forecast MPC (2h)* and *Forecast MPC (4h)* match exactly:

$$\max_{i \in [0, 77]} |\text{metric}_{2h}(i) - \text{metric}_{4h}(i)| = 0.0$$

Across all metrics:
- `carbon_gco2e`: $\Delta = 0.0000$
- `energy_kwh`: $\Delta = 0.0000$
- `completed`: $\Delta = 0$
- `rejected`: $\Delta = 0$
- `sla_violations`: $\Delta = 0$
- `deferrals_recommended`: $\Delta = 0$
- `urgent_placements`: $\Delta = 0$
- `total_latency_seconds`: $\Delta = 0.0000$
- The only non-zero difference is operating system thread timing (`runtime_seconds`, max jitter $< 0.035\text{ s}$).

### 2. Code Path Trace & Mathematical Degeneracy
In `configs/phase33_forecast_config.yaml`, the two schedulers are configured as:
- `forecast_mpc_2h`: `horizon_hours: 2.0` $\implies$ `horizon_slots = 8` (at $900\text{ s/slot}$)
- `forecast_mpc_4h`: `horizon_hours: 4.0` $\implies$ `horizon_slots = 16`

In `schedulers/forecast_mpc.py`, `evaluate_forecast_opportunity` computes the lookahead horizon:
```python
# schedulers/forecast_mpc.py, Line 166
slots_from_slack = int(max_slack // self.slot_seconds)
remaining_deferrals = self.max_deferrals - defer_count
lookahead_slots = min(remaining_deferrals, self.horizon_slots, slots_from_slack)
```

In `environment/cloud_environment.py`, the environment is initialized with:
```python
# environment/cloud_environment.py, Line 23
def __init__(self, regions, network=None, slot_seconds=60, max_deferrals=2, ...):
    self.max_deferrals = max_deferrals
```
Because `max_deferrals` is set to $2$ in the simulation environment, any task arriving has:
$$\text{remaining\_deferrals} \le 2$$

Evaluating the minimum expression for both schedulers:
$$\text{lookahead\_slots}_{2h} = \min(2, 8, \text{slack}) \le 2$$
$$\text{lookahead\_slots}_{4h} = \min(2, 16, \text{slack}) \le 2$$

Since $\min(2, 8, k) \equiv \min(2, 16, k)$ for all $k \ge 0$, **both schedulers only ever evaluated offset 1 ($15\text{ min}$) and offset 2 ($30\text{ min}$)**. Neither scheduler ever queried the forecast provider at offsets $3, \dots, 16$.

### Conclusion for Investigations 1 & 2:
The experiment was mechanically executed with distinct configuration objects, but the algorithm's lookahead was completely choked off by the environment's `max_deferrals = 2` parameter. The claim of evaluating "2-hour vs. 4-hour forecast horizons" is invalid.

---

## Detailed Investigation 3: Recomputed Empirical Statistics

All paired differences, standard deviations, and 95% bootstrap confidence intervals ($B = 10,000$ resamples) were recomputed directly from `results/phase33/phase33_runs.csv`.

### 1. Overall Paired Comparison (All $N = 78$ Workload Instances)

| Metric | FCFS Baseline | Greedy Carbon | Forecast MPC (2h / 4h) | Paired $\Delta$ vs. Greedy | 95% Bootstrap CI | Paired $t$-test $p$ | Wilcoxon $p$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Carbon (gCO2e)** | $662.08 \pm 496.18$ | $591.47 \pm 459.98$ | **$580.37 \pm 449.13$** | **$-11.10\text{ g}$ ($-1.88\%$)** | $[-22.14, -0.91]$ | $p = 0.0446$ | $p = 7.23 \times 10^{-5}$ |
| **Energy (kWh)** | $3.35 \pm 2.45$ | $2.90 \pm 2.19$ | **$2.89 \pm 2.20$** | **$-0.0065\text{ kWh}$ ($-0.22\%$)** | $[-0.0439, +0.0337]$ | $p = 0.7417$ | $p = 0.5147$ |
| **Completion Rate** | $98.58\% \pm 5.85\%$ | $98.50\% \pm 6.08\%$ | **$98.42\% \pm 5.96\%$** | **$-0.08\%$** | $[-0.37\%, +0.24\%]$ | $p = 0.5933$ | $p = 0.5002$ |
| **SLA Violations / Rejections** | $0.62 \pm 2.64$ | $0.67 \pm 2.82$ | **$0.71 \pm 2.76$** | **$+0.0385\text{ tasks}$ ($+5.77\%$)** | $[-0.1154, +0.1795]$ | $p = 0.5933$ | $p = 0.4982$ |

*Summary:* Across all 78 instances, MPC yields a statistically significant carbon reduction over Greedy ($-1.88\%$, paired $t$-test $p = 0.0446$, Wilcoxon signed-rank $p < 0.0001$), and a $-12.34\%$ reduction over FCFS ($p < 10^{-9}$). However, completion rate slightly decreases ($-0.08\%$) and SLA rejections increase ($+5.77\%$), though neither completion difference is statistically significant across the full cohort.

---

### 2. Family-by-Family Breakdown ($n = 13$ Instances per Family)

| Workload Family | Metric | Greedy Carbon | Forecast MPC | Paired Difference | 95% Bootstrap CI | Paired $p$-value |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`spread_12tasks`** | Carbon (gCO2e) | $315.15 \pm 228.61$ | **$311.76 \pm 224.23$** | **$-3.39\text{ g}$ ($-1.08\%$)** | $[-6.66, -0.91]$ | $p = 0.0470$ |
| | Completion Rate | $100.0\%$ | $100.0\%$ | $0.00\%$ | $[0.00\%, 0.00\%]$ | — |
| | SLA Violations | $0.00$ | $0.00$ | $0.00$ | $[0.00, 0.00]$ | — |
| | Deferrals / Urgent | $0.0 / 0.0$ | $1.08 / 0.23$ | $+1.08 / +0.23$ | $[+0.62, +1.54]$ | $p = 0.0016$ |
| **`spread_24tasks`** | Carbon (gCO2e) | $633.20 \pm 462.63$ | **$624.87 \pm 453.79$** | **$-8.33\text{ g}$ ($-1.32\%$)** | $[-14.43, -4.02]$ | $p = 0.0128$ |
| | Completion Rate | $100.0\%$ | $100.0\%$ | $0.00\%$ | $[0.00\%, 0.00\%]$ | — |
| | SLA Violations | $0.00$ | $0.00$ | $0.00$ | $[0.00, 0.00]$ | — |
| | Deferrals / Urgent | $0.0 / 0.0$ | $1.77 / 0.46$ | $+1.77 / +0.46$ | $[+1.31, +2.31]$ | $p < 0.0001$ |
| **`spread_48tasks`** | Carbon (gCO2e) | $926.51 \pm 626.85$ | **$917.84 \pm 617.93$** | **$-8.67\text{ g}$ ($-0.94\%$)** | $[-12.49, -4.94]$ | $p = 0.0009$ |
| | Completion Rate | $100.0\%$ | $100.0\%$ | $0.00\%$ | $[0.00\%, 0.00\%]$ | — |
| | SLA Violations | $0.00$ | $0.00$ | $0.00$ | $[0.00, 0.00]$ | — |
| | Deferrals / Urgent | $0.0 / 0.0$ | $6.46 / 2.00$ | $+6.46 / +2.00$ | $[+5.85, +7.15]$ | $p < 0.0001$ |
| **`burst_2h_12tasks`**| Carbon (gCO2e) | **$149.70 \pm 99.88$** | $151.14 \pm 101.44$ | **$+1.44\text{ g}$ ($+0.96\%$)** | $[0.00, +3.29]$ | $p = 0.1162$ |
| | Completion Rate | $100.0\%$ | $100.0\%$ | $0.00\%$ | $[0.00\%, 0.00\%]$ | — |
| | SLA Violations | $0.00$ | $0.00$ | $0.00$ | $[0.00, 0.00]$ | — |
| | Deferrals / Urgent | $0.0 / 0.0$ | $0.54 / 0.15$ | $+0.54 / +0.15$ | $[+0.15, +1.00]$ | $p = 0.0470$ |
| **`burst_2h_24tasks`**| Carbon (gCO2e) | $518.80 \pm 384.81$ | **$507.48 \pm 378.14$** | **$-11.31\text{ g}$ ($-2.18\%$)** | $[-35.07, +3.39]$ | $p = 0.3336$ |
| | Completion Rate | $98.72\%$ | $98.72\%$ | $0.00\%$ | $[0.00\%, 0.00\%]$ | — |
| | SLA Violations | $0.31$ | $0.31$ | $0.00$ | $[0.00, 0.00]$ | — |
| | Deferrals / Urgent | $0.0 / 0.0$ | $7.08 / 2.77$ | $+7.08 / +2.77$ | $[+3.92, +10.46]$ | $p = 0.0014$ |
| **`burst_2h_48tasks`**| Carbon (gCO2e) | $1005.47 \pm 709.80$ | **$969.15 \pm 683.74$** | **$-36.32\text{ g}$ ($-3.61\%$)** | $[-95.80, +19.20]$ | $p = 0.2553$ |
| | Completion Rate | **$92.31\%$ (576/624)**| $91.83\%$ (573/624) | **$-0.48\%$** | $[-1.92\%, +0.96\%]$ | $p = 0.6101$ |
| | SLA Violations | **$3.69 \pm 6.13$** | $3.92 \pm 6.01$ | **$+0.23$ ($+6.25\%$)** | $[-0.62, +1.00]$ | $p = 0.6101$ |
| | Deferrals / Urgent | $0.0 / 0.0$ | $40.54 / 15.00$ | $+40.54 / +15.00$ | $[+33.46, +47.69]$ | $p < 0.0001$ |

---

### 3. Equal-Completion Cohort Analysis ($N = 73$ Instances)
To test whether carbon savings are genuine or merely artifacts of dropped tasks, we partitioned the 78 instances into those with identical task completion counts ($N = 73$) and those with divergent completion counts ($N = 5$):

- **Identical Completion Instances ($N = 73 / 78$, $93.6\%$ of instances):**
  - Greedy Mean Emissions: $565.97 \pm 450.12\text{ gCO2e}$
  - Forecast MPC Mean Emissions: **$554.54 \pm 440.08\text{ gCO2e}$**
  - **Paired Difference:** **$-11.42\text{ gCO2e}$ ($-2.02\%$)**
  - **95% Bootstrap CI:** $[-19.35, -5.42]\text{ gCO2e}$
  - **Paired $t$-test:** $t = -3.15$, **$p = 0.00235$**
  - **Verdict:** When task completion is held strictly constant, Forecast MPC achieves a **genuine, statistically robust $2.02\%$ carbon reduction**.

- **Divergent Completion Instances ($N = 5 / 78$, all in `burst_2h_48tasks`):**
  - *Instance 2:* Greedy completed 44 tasks ($653.82\text{ g}$); MPC completed 43 tasks ($678.27\text{ g}$) $\implies$ MPC $-1$ task, $+24.45\text{ g}$
  - *Instance 6:* Greedy completed 45 tasks ($1402.82\text{ g}$); MPC completed 42 tasks ($1393.47\text{ g}$) $\implies$ MPC $-3$ tasks, $-9.35\text{ g}$
  - *Instance 9:* Greedy completed 45 tasks ($1403.96\text{ g}$); MPC completed 43 tasks ($1141.63\text{ g}$) $\implies$ MPC $-2$ tasks, $-262.33\text{ g}$
  - *Instance 10:* Greedy completed 45 tasks ($659.67\text{ g}$); MPC completed 44 tasks ($678.30\text{ g}$) $\implies$ MPC $-1$ task, $+18.63\text{ g}$
  - *Instance 11:* Greedy completed 36 tasks ($698.91\text{ g}$); MPC completed 40 tasks ($895.73\text{ g}$) $\implies$ **MPC $+4$ tasks**, $+196.82\text{ g}$
  - **Net Difference Across Cohort:** Greedy completed 215 tasks; MPC completed 212 tasks ($-3$ tasks net).

---

### 4. Matched 12-Task MILP Optimality Gap ($N = 24$ Instances)
Evaluated on the bounded 12-task prefix of Windows 0, 4, 8, 12 across all 6 families:
- **Solver Certification:** Out of 24 MILP instances, **17 were certified global optima** (within $180\text{ s}$ limit) and **7 terminated with verified feasible incumbents** (gap $< 4\%$). Zero solver timeouts without incumbent.
- **Optimality Gaps:**
  - `spread_12tasks`: MILP $448.20\text{ g}$ | MPC $460.83\text{ g}$ (**$+2.82\%$ gap**) | Greedy $461.81\text{ g}$ ($+3.04\%$) | FCFS $541.91\text{ g}$ ($+20.91\%$)
  - `spread_24tasks`: MILP $314.89\text{ g}$ | MPC $336.08\text{ g}$ (**$+6.73\%$ gap**) | Greedy $336.24\text{ g}$ ($+6.78\%$) | FCFS $345.58\text{ g}$ ($+9.75\%$)
  - `spread_48tasks`: MILP $242.52\text{ g}$ | MPC $256.90\text{ g}$ (**$+5.93\%$ gap**) | Greedy $261.59\text{ g}$ ($+7.86\%$) | FCFS $276.48\text{ g}$ ($+14.00\%$)
  - `burst_2h_12tasks`: MILP $167.49\text{ g}$ | MPC $187.64\text{ g}$ ($+12.03\%$ gap) | Greedy $186.51\text{ g}$ (**$+11.36\%$**) | FCFS $191.75\text{ g}$ ($+14.49\%$)
  - `burst_2h_24tasks`: MILP $191.13\text{ g}$ | MPC $207.58\text{ g}$ ($+8.61\%$ gap) | Greedy $207.43\text{ g}$ (**$+8.53\%$**) | FCFS $216.06\text{ g}$ ($+13.04\%$)
  - `burst_2h_48tasks`: MILP $164.03\text{ g}$ | MPC $182.49\text{ g}$ ($+11.25\%$ gap) | Greedy $181.10\text{ g}$ (**$+10.41\%$**) | FCFS $185.24\text{ g}$ ($+12.93\%$)

*Key Insight:* On spread workloads, MPC tightens the optimality gap towards MILP (e.g. $5.93\%$ vs. $7.86\%$). On small burst cohorts (12-task prefix), Greedy slightly outperforms MPC by $0.1\% - 0.8\%$ because deferrals under unconstrained burst prefixes introduce slot delays without compensating carbon advantages.

---

## Detailed Investigation 4: Root-Cause of 48-Task Burst Completion Drop

The user specifically requested: *"Investigate why 48-task burst completion drops from 92.3% (Greedy) to 91.8% (MPC)."*

### The "Capacity Cliff" Mechanism
In `cloud_environment.py`, candidate regions are filtered by:
```python
# cloud_environment.py, Lines 114-115
available = resources.can_fit(task)
feasible = available and candidate["end"] <= task.deadline_seconds
if feasible:
    candidates.append(candidate)
```
If `candidates` is empty, or the scheduler chooses not to place the task, `choice` is `None`.
```python
# cloud_environment.py, Lines 150-157
if choice is None:
    if defer_count < self.max_deferrals:
        deferred[task.task_id] = slot + 1
        record = {"task_id": task.task_id, "slot": slot, "action": "defer"}
    else:
        record = {"task_id": task.task_id, "slot": slot, "action": "reject"}
```

In `schedulers/forecast_mpc.py`, when a task arrives during burst congestion, MPC checks:
```python
# schedulers/forecast_mpc.py, Lines 174-177
is_congested = any(c.get("queue_length", 0) > 0 for c in candidates)
if is_congested and max_slack >= self.slot_seconds * 3:
    self.deferrals_recommended += 1
    return None
```
Under heavy burst arrivals, multiple tasks satisfy `is_congested and max_slack >= 2700s`. MPC defers them to slot $s+1$ and then $s+2$.
Crucially, **deferral does NOT reserve capacity in future slots**.

### Micro-Analysis of Instance 6 vs. Instance 11:
1. **The Capacity Cliff in Instance 6 (Greedy 45 vs. MPC 42 completed):**
   - At slot 17435, tasks `...-21-...`, `...-22-...`, `...-4-...`, `...-7-...`, `...-8-...` arrive simultaneously.
   - Greedy places tasks immediately in available regional capacity.
   - MPC detects `is_congested` and defers 5 tasks.
   - During slots 17435 and 17436, newly arriving tasks occupy remaining regional GPU/CPU slots.
   - At slot 17437, the 5 deferred tasks reach `defer_count = 2`. Forced execution (`force = True`) is triggered.
   - However, at slot 17437, all regional resources are $100\%$ saturated by ongoing long tasks.
   - `candidates` is completely empty (`len(candidates) == 0`).
   - Forced placement fails to find a feasible region. The simulator records `action: reject` for all 5 tasks.
   - Greedy, having grabbed the open capacity immediately, successfully completed them.

2. **The Peak-Shaving Benefit in Instance 11 (Greedy 36 vs. MPC 40 completed):**
   - At slot 32094, a massive burst arrives. Greedy aggressively schedules 12 large jobs, exhausting all 3 regions.
   - At slot 32096, another burst arrives. Because Greedy's regions are completely full, Greedy is forced to reject 6 incoming tasks (rejection count = 12).
   - MPC selectively deferred delay-tolerant jobs at slot 32094, smoothing cluster utilization across slots 32095 and 32096.
   - When slot 32096 arrived, MPC had sufficient freed resources to accept 4 additional tasks that Greedy rejected.
   - MPC completed 40 tasks vs. Greedy's 36.

### Summary:
MPC's deferral heuristic is a double-edged sword: without a *reservation mechanism*, deferring during a burst is a gamble. If subsequent slots remain saturated, the task defers directly into a capacity cliff and is rejected.

---

## Detailed Investigation 5: Deferral, Rejection, and SLA Accounting

The accounting invariants in `CloudEnvironment` and `ForecastAwareMPCScheduler` were audited:

1. **Hard Deadline & Capacity Safety:**
   - Tasks are only eligible for scheduling if `resources.can_fit(task)` and `candidate["end"] <= task.deadline_seconds`.
   - Once assigned, tasks run to completion. **No assigned task ever violates its deadline or exceeds regional capacity.**
2. **SLA Violations $\equiv$ Rejections:**
   - In `cloud_environment.py`, Line 199:
     ```python
     "sla_violations": rejected
     ```
   - All SLA violations in this benchmark are unallocated/rejected tasks resulting from capacity exhaustion or deadline impossibility.
3. **Deferral Counting:**
   - Deferrals are recorded on each slot a task is deferred (`records.append({"action": "defer", ...})`).
   - Total recommendations are tracked via `scheduler.deferrals_recommended`.
   - The environment enforces `max_deferrals = 2` as a hard cutoff.

---

## Detailed Investigation 6: Experimental Rigor & Cohort Isolation

1. **78 Online Workload Instances:**
   - 6 scenario families (`spread_12`, `spread_24`, `spread_48`, `burst_12`, `burst_24`, `burst_48`).
   - 13 non-overlapping package-axis temporal windows per family ($6 \times 13 = 78$ distinct instances).
   - Real-world Alibaba 2020 cluster traces with real 2023 grid carbon profiles (CAISO, NYISO, ERCOT).
2. **312 Online Policy Runs:**
   - 78 instances evaluated across 4 online policies: FCFS, Greedy Carbon, Forecast MPC (2h), and Forecast MPC (4h) ($78 \times 4 = 312$ policy runs).
   - All 312 runs are cleanly logged in `results/phase33/phase33_runs.csv`.
3. **24 Matched MILP Solver Runs:**
   - Windows 0, 4, 8, 12 across 6 families ($6 \times 4 = 24$ instances).
   - Bounded to 12-task prefix to ensure solver tractability within $180\text{ s}$ per instance.
   - Cleanly isolated from online full-size runs and stored in `phase33_evaluation.json`.

---

## Detailed Investigation 7: Future-Information Leakage Audit

A line-by-line inspection of `schedulers/forecast_mpc.py` confirmed:
1. `CarbonForecastProvider`:
   - Enforces `if horizon_slots > self.horizon_slots: raise ValueError(...)`.
   - Adds zero-mean Gaussian forecast noise:
     $$\hat{I}_r(t + \Delta t) = \max\left(1.0, \, I_r(t + \Delta t) \cdot (1 + \epsilon)\right), \quad \epsilon \sim \mathcal{N}(0, \sigma^2)$$
   - Queries intensity only at target slot timestamps.
2. `ForecastAwareMPCScheduler`:
   - Never inspects future task arrival queues or future job durations.
   - Only queries carbon forecasts up to `current_slot + lookahead_slots`.
   - Strict future-information boundary is maintained. Unit test `test_forecast_provider_strict_horizon_enforcement` passes.

---

## Inconsistencies & Factual Errors Found in Existing Documentation

During the audit of `results/phase33/PHASE33_REPORT.md` (and root `PHASE33_REPORT.md`), a serious textual inconsistency was discovered:

### Documented Error:
In Section 1 ("Executive Summary"), bullet 3 states:
> *"Burst 48-task cohorts: 100.0% completion with ZERO rejections, achieving 866.57 gCO2e vs Greedy's 926.51 gCO2e."*

### Factual Correction:
- The actual values generated by the simulation (and shown in Table 1 directly below that text, as well as in `phase33_runs.csv`) are:
  - Greedy: $1005.47\text{ gCO2e}$, $92.31\%$ completion, $3.692$ SLA violations
  - Forecast MPC: $969.15\text{ gCO2e}$, $91.83\%$ completion, $3.923$ SLA violations
- The text in Section 1 appears to have erroneously copied numbers from `spread_48tasks` (which had $926.51\text{ g}$ Greedy emissions).
- **Impact:** Presenting "100% completion with zero rejections" in the executive summary when the actual data exhibits a completion drop to 91.8% would be a catastrophic peer-review failure.

---

## Scientific Defensibility & Paper Readiness Assessment

| Evaluation Criterion | Assessment | Defensibility Verdict |
| :--- | :--- | :--- |
| **Spread Workload Emissions** | MPC achieves $-0.94\%$ to $-1.32\%$ carbon reduction with 100% completion across all spread instances ($p < 0.05$). | **Fully Defensible** |
| **Equal-Completion Emissions** | On 73 identical-completion instances, MPC saves $2.02\%$ carbon ($p = 0.00235$, 95% CI $[-19.35, -5.42]\text{ g}$). | **Fully Defensible** |
| **Burst 48 Emissions Reduction** | Raw $-3.61\%$ emissions reduction is confounded by completing 3 fewer tasks. | **Partially Confounded** (Must report completion-adjusted or energy-normalized emissions). |
| **2h vs. 4h Horizon Comparison** | Mechanically identical due to `max_deferrals = 2` lookahead clamp. | **Methodologically Flawed** (Cannot be claimed as a multi-horizon study). |
| **Information Leakage** | Strict forecast horizon bounds and Gaussian noise verified. | **Fully Defensible** |
| **Ready for Research Paper?** | Current findings show promising mechanics but require methodological fixes. | **NOT READY FOR PUBLICATION AS-IS** |

---

## Prescribed Corrections for Future Work (Do Not Apply Silently)

To make Phase 3.3 fully publication-ready, the following corrections are recommended:

1. **Decouple Forecast Horizon from Maximum Deferrals:**
   - In `evaluate_forecast_opportunity`, allowing a task to evaluate an 8-slot ($2\text{h}$) or 16-slot ($4\text{h}$) horizon requires that either:
     - The environment allows larger deferral counts (`max_deferrals = 8` or `16`), OR
     - Tasks can schedule a future start slot (advance reservation / commitment) rather than only single-step online deferral.
2. **Implement Lookahead Shadow Reservation:**
   - When MPC decides to defer a task during a burst, it must reserve tentative capacity in the target slot to prevent "capacity cliffs" and eliminate completion loss under heavy load.
3. **Correct Documentation Text:**
   - Update `PHASE33_REPORT.md` Section 1 to accurately report the burst 48 metrics ($91.8\%$ completion, $969.15\text{ gCO2e}$).
4. **Report Completion-Normalized Metrics:**
   - In the paper, report grams of CO2e per completed task ($\text{gCO2e} / \text{task}$) alongside raw aggregate emissions to eliminate confounding from dropped tasks.

---

*Audit certified complete and strictly verified against raw simulation artifacts.*
