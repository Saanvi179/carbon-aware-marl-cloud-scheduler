# Phase 3.3 — Corrected Forecast-Aware Scheduling Evaluation

## Status and artifact lineage

This report reconciles Phase 3.3 using the final corrected evaluation in `results/phase33_corrected_v5/`. The original Phase 3.3 implementation and its report remain preserved in `results/phase33/`; the first corrected artifacts remain in `results/phase33_corrected/`. Intermediate validation and corrected runs are retained in their versioned result folders. The detailed validated tables are in [PHASE33_CORRECTED_REPORT.md](PHASE33_CORRECTED_REPORT.md), and the audit trail is in [PHASE33_AUDIT.md](PHASE33_AUDIT.md).

The original root report's burst-48 completion claim and aggregate interpretation were incorrect. They are superseded here, not silently carried forward. Original files under `results/phase33/` are retained as historical artifacts and should not be cited as corrected findings.

## Validated scope and accounting

The full-size benchmark evaluates 78 instances (six workload families, 13 windows each) under five online policies: FCFS, greedy carbon, original MPC, corrected MPC 2h, and corrected MPC 4h. The corrected CSV contains 390 online rows. The matched prefix experiment covers 24 family/window cases, with five online policies and one MILP result per case: 120 online rows + 24 MILP rows = 144 total. Thus “120” denotes online rows only; “144” includes the MILP rows. The MILP attempted 24 cases: 17 certified optimal and 7 feasible incumbents; none were infeasible or without a solution.

## Main paired findings

Across 78 matched full-size instances, corrected MPC (2h) minus greedy carbon had:

- Emissions: −31.36 gCO₂e mean difference (SD 91.22; 95% bootstrap CI [−54.02, −14.61]).
- Emissions per completed task: −1.04 gCO₂e/task (SD 2.41; CI [−1.64, −0.60]).
- Energy: −0.053 kWh (SD 0.330; CI [−0.136, +0.009]).
- Completion rate: −0.0011 (SD 0.0161; CI [−0.0048, +0.0024]).
- SLA violations: +0.013 per instance (SD 0.634; CI [−0.141, +0.141]).

The full report gives means, standard deviations, and 95% bootstrap intervals for emissions, energy, emissions per completed task, completion, rejection, SLA violations, and latency in each workload family, plus matched-prefix MILP comparisons. These results show lower mean emissions in the aggregate paired comparison, while energy and completion differences have intervals that include zero. They do not establish universal MPC superiority or production effectiveness.

## Horizon interpretation

Corrected MPC 2h and 4h are configured for different lookahead windows (8 versus 16 fifteen-minute slots) with the same two-transition deferral budget. Their decision signatures are identical on 78/78 evaluated instances. The implementation now evaluates distinct horizons correctly, and a regression test constructs a carbon valley visible to 4h but outside 2h. However, the selected benchmark's runtime-plus-3,600-second deadlines and carbon/workload profiles did not distinguish the horizons; no empirical 2h-versus-4h advantage is claimed.

## Reservation lifecycle and validation

A deferral stores the destination and retry slot and reserves GPU, CPU, and memory capacity over the migration-plus-execution interval. At retry, the environment restricts placement to the reserved destination and checks live feasibility. A conflict causes a safe reschedule or terminal rejection; reservations are released on placement, rejection, expired target, or rescheduling. The environment's loop bound supports reserved retry slots beyond the latest arrival and checks that all tasks end completed or rejected.

Validation actually run:

- `python -m unittest discover -s tests -p test_forecast_mpc.py -v`: 17 tests passed.
- `python -m unittest discover -s tests -v`: 74 tests passed.
- `python -m experiments.run_phase33_corrected --matched-smoke --output-dir results/phase33_validation_smoke_v5`: 36 policy rows across six workload families.
- `python -m experiments.run_phase33_corrected --output-dir results/phase33_corrected_v5`: full corrected benchmark, 390 online rows plus matched MILP comparisons; outputs are in `results/phase33_corrected_v5/`.
- `python -m experiments.run_phase33_corrected --output-dir results/phase33_corrected_v5 --render-existing`: regenerated report and paired summary from the preserved v5 CSV/JSON without rerunning the simulation.

## Remaining limitations

The trace is a derived package-axis workload, and deadlines are assumptions; these evaluations do not establish real-world cloud performance. Region capacities are static. Reservations protect against known assignments and reservations, but cannot account for future arrivals, so live conflicts may trigger rescheduling. The small MILP subset has time-limited incumbents in seven cases; only certified optimal cases support exact optimality statements. A horizon comparison requires a separate predeclared workload/deadline design with enough feasible slack.
