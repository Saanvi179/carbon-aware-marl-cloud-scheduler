# Phase 3.2 — dataset expansion and validation

## Executed findings

The run evaluated 78 full-size workload instances across six families and 13 package-axis windows: 156 full-size FCFS/greedy runs, 72 matched 12-task policy runs, 96 online sensitivity runs, and 144 sensitivity-prefix policy runs. Spread greedy carbon changes relative to FCFS were 12 tasks: -17.6% emissions, 100.0% completion; 24 tasks: -15.9% emissions, 100.0% completion; 48 tasks: -18.3% emissions, 100.0% completion. Two-hour burst results were 12 tasks: -2.5% emissions, 100.0% completion, 0.0% rejection; 24 tasks: +0.2% emissions, 98.7% completion, 1.3% rejection; 48 tasks: -2.4% emissions, 92.3% completion, 7.7% rejection. Lower emissions in burst cases must be read alongside the completion/rejection results. The 72 baseline and sensitivity MILPs yielded 47 certified optima, 25 feasible incumbents without optimality proof, and 0 with no feasible solution.

## Data validity and provenance

The only benchmark workload evaluated here is the retained Alibaba-derived SustainCluster processed trace. Official SustainCluster documentation says the underlying Alibaba PAI 2020 trace covers July–August 2020 and its packaged trace is extended to a simulated year by repeating daily/weekly patterns. This project’s package has 37,552 interval rows (2020-01-01 through 2021-01-26), but the task-level timestamp fields in a 16,720-record deterministic audit sample resolve to surrogate 1970 timestamps and differ from the package interval axis by about 1.58–1.61 billion seconds. Therefore the package axis is a scenario clock, not validated wall-clock observation time. Its 1.30 million task records do not provide 1.30 million independent production observations.

The interval index is monotonic with no duplicate timestamps; 80 of 37551 interval steps are 30 minutes instead of 15 minutes. These gaps are retained. The sampled task-field audit found 0 malformed/invalid records under the checked fields; this is a sample check, not a proof that every task field is complete. We preserve source rows and do not fill missing intervals or attributes. Resource conversions remain runtime minutes→seconds, CPU/GPU percent÷100, memory GB as supplied, and `bandwidth_gb` retained as the source's estimated input-volume field.

Coverage cohorts use 13 monthly start coordinates across the packaged axis, three sampled task counts (12/24/48), and two recorded-arrival patterns: spread across a 24-hour window and a two-hour busy window. The 15-minute task arrivals and distinct task records are preserved; lower/higher intensity means sampling different counts, not generating jobs. A seeded selector is used, with seeds recorded in the processed payload. Upstream temporal extension means monthly cohorts are not independent raw-trace months; confidence intervals are descriptive across package-axis windows.

## Additional source review

Alibaba’s official 2023 GPU-sharing trace has 8,152 pod records (~562 KiB) and a 1,214-node GPU inventory (~41 KiB). Its schema provides CPU millicores, memory MiB, GPU count/share, QoS and relative creation/scheduled/deletion times. It does not document a UTC calendar anchor or task input-size field; these omissions block date-matched carbon replay and realistic migration-latency modeling. The source README grants research/study use and requests citation, but no explicit per-data license was found in the inspected dataset subdirectory. It is documented as a follow-up candidate, not mixed into the current simulator or assigned invented values.

Other inspected candidates are not compatible as-is: SustainDC Alibaba/Google files are aggregate hourly CPU profiles, not per-task GPU jobs; Google 2019 cluster traces are CPU-centric; the MIT Supercloud GPU workload archive is roughly terabyte-scale and outside this bounded phase. We did not download these datasets.

For aligned carbon, the existing 2023 NYISO/CAISO/ERCOT direct-intensity CSVs are complete UTC hourly series with 51 source rows marked estimated (retained). SustainCluster’s current README describes carbon coverage as 2021–2024, while its release overview broadly says environmental data 2020–2024; local Phase 3 files contain 2023 only. WattTime exposes historical MOER in lb CO₂/MWh, but the historical data endpoint is subscriber-restricted. A public CAISO 2019–2020 research dataset reports month-hour regressed AEF/MEF factors (CC BY 4.0), not a full hourly 3-region average-intensity panel. Google’s 2020 regional carbon file is annual lifecycle intensity by Google Cloud region, not hourly ISO data. None is an authentic, compatible hourly 2020 profile for all three simulator regions, so we retain the 2023 signal as a separate unsynchronized carbon replay and do not claim calendar alignment.

## Evaluation protocol

Every online run compares FCFS and greedy carbon on the full selected workload and uses current-observation-only carbon estimation. FCFS, greedy and offline MILP are compared on the same 12-task prefix from each cohort at four representative package-axis windows; MILP uses the complete future workload and carbon and is an oracle. Gaps are reported only where MILP certifies optimality and all tasks complete. Sensitivity reuses identical 24-task spread/burst cohorts at two package-axis windows for deadline slack (1,800/3,600/7,200 s), PUE (±10%), GPU active power (±20%), network throughput/RTT (half/double), and 2023 carbon replay offsets. Each MILP has a two-second configured limit. Values are mean ± sample SD [95% percentile bootstrap interval] across windows; small n and upstream temporal repetition limit interpretation.

## Full-size online results

### Workload family: burst_2h_12tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 153.540 ± 92.828 [106.932, 203.191] (n=13) | 0.750 ± 0.457 [0.528, 0.995] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2328.984 ± 432.001 [2101.779, 2556.756] (n=13) | n/a |
| Greedy carbon | 149.703 ± 91.617 [104.346, 199.003] (n=13) | 0.662 ± 0.425 [0.457, 0.892] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2092.386 ± 385.016 [1884.365, 2291.769] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Workload family: burst_2h_24tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 517.831 ± 546.187 [291.920, 855.189] (n=13) | 2.354 ± 2.391 [1.359, 3.734] (n=13) | 0.984 ± 0.058 [0.952, 1.000] (n=13) | 0.016 ± 0.058 [0.000, 0.048] (n=13) | 0.385 ± 1.387 [0.000, 1.154] (n=13) | 2399.209 ± 433.847 [2189.346, 2646.536] (n=13) | n/a |
| Greedy carbon | 518.795 ± 542.843 [294.194, 856.743] (n=13) | 2.276 ± 2.349 [1.297, 3.641] (n=13) | 0.987 ± 0.046 [0.962, 1.000] (n=13) | 0.013 ± 0.046 [0.000, 0.038] (n=13) | 0.308 ± 1.109 [0.000, 0.923] (n=13) | 2260.007 ± 404.925 [2068.277, 2494.730] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Workload family: burst_2h_48tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 1030.632 ± 497.794 [782.465, 1322.044] (n=13) | 4.562 ± 2.099 [3.554, 5.728] (n=13) | 0.931 ± 0.120 [0.859, 0.979] (n=13) | 0.069 ± 0.120 [0.021, 0.143] (n=13) | 3.308 ± 5.779 [0.923, 6.769] (n=13) | 2714.966 ± 502.487 [2446.520, 2970.333] (n=13) | n/a |
| Greedy carbon | 1005.468 ± 498.630 [760.318, 1297.997] (n=13) | 4.398 ± 2.124 [3.375, 5.588] (n=13) | 0.923 ± 0.128 [0.846, 0.979] (n=13) | 0.077 ± 0.128 [0.022, 0.154] (n=13) | 3.692 ± 6.156 [1.000, 7.308] (n=13) | 2634.875 ± 489.089 [2373.777, 2881.214] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Workload family: spread_12tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 382.480 ± 262.371 [271.232, 544.481] (n=13) | 2.076 ± 1.391 [1.481, 2.892] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 3025.291 ± 426.820 [2805.571, 3256.469] (n=13) | n/a |
| Greedy carbon | 315.154 ± 246.007 [215.973, 469.624] (n=13) | 1.636 ± 1.079 [1.168, 2.270] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2642.319 ± 364.338 [2456.184, 2840.429] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Workload family: spread_24tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 753.285 ± 358.582 [586.294, 950.487] (n=13) | 4.172 ± 1.997 [3.251, 5.302] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2853.076 ± 388.853 [2648.746, 3051.838] (n=13) | n/a |
| Greedy carbon | 633.200 ± 337.591 [476.706, 819.117] (n=13) | 3.399 ± 1.871 [2.541, 4.456] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2496.685 ± 339.268 [2318.592, 2668.500] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Workload family: spread_48tasks (13 windows; full workload size)

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 1134.729 ± 205.012 [1023.715, 1237.585] (n=13) | 6.185 ± 1.099 [5.599, 6.747] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2785.365 ± 354.733 [2606.747, 2968.493] (n=13) | n/a |
| Greedy carbon | 926.510 ± 149.807 [846.804, 1001.767] (n=13) | 5.016 ± 0.939 [4.515, 5.498] (n=13) | 1.000 ± 0.000 [1.000, 1.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 0.000 ± 0.000 [0.000, 0.000] (n=13) | 2448.481 ± 327.245 [2284.654, 2617.894] (n=13) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Matched 12-task FCFS/greedy/MILP results

### Matched prefix: burst_2h_12tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 191.755 ± 95.520 [95.532, 259.835] (n=4) | 0.939 ± 0.468 [0.467, 1.272] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2133.299 ± 350.129 [1798.372, 2347.632] (n=4) | 22.00 ± 8.57 [15.95, 28.06] (n=2) |
| Greedy carbon | 186.508 ± 93.201 [91.970, 245.746] (n=4) | 0.797 ± 0.399 [0.391, 1.045] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1875.893 ± 319.522 [1573.438, 2076.864] (n=4) | 11.78 ± 5.95 [7.57, 15.99] (n=2) |
| Offline MILP | 167.485 ± 85.865 [81.074, 225.336] (n=4) | 0.715 ± 0.368 [0.345, 0.966] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1855.924 ± 304.372 [1564.787, 2042.258] (n=4) | n/a |

### Matched prefix: burst_2h_24tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 216.058 ± 134.462 [93.319, 339.780] (n=4) | 1.067 ± 0.673 [0.457, 1.690] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2156.338 ± 355.855 [1805.689, 2352.892] (n=4) | 28.55 ± 0.00 [28.55, 28.55] (n=1) |
| Greedy carbon | 207.428 ± 123.761 [89.867, 316.038] (n=4) | 0.892 ± 0.536 [0.383, 1.362] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1895.943 ± 323.585 [1579.868, 2081.416] (n=4) | 16.43 ± 0.00 [16.43, 16.43] (n=1) |
| Offline MILP | 191.130 ± 120.861 [79.175, 300.678] (n=4) | 0.822 ± 0.529 [0.337, 1.307] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1875.973 ± 309.290 [1571.216, 2046.809] (n=4) | n/a |

### Matched prefix: burst_2h_48tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 185.236 ± 85.908 [98.228, 243.675] (n=4) | 0.906 ± 0.419 [0.482, 1.190] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2120.000 ± 440.751 [1755.847, 2484.153] (n=4) | 20.26 ± 9.72 [13.38, 27.13] (n=2) |
| Greedy carbon | 181.104 ± 85.592 [94.918, 231.364] (n=4) | 0.774 ± 0.366 [0.407, 0.980] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1874.156 ± 413.961 [1533.093, 2215.218] (n=4) | 10.05 ± 6.00 [5.80, 14.29] (n=2) |
| Offline MILP | 164.033 ± 79.511 [83.444, 215.926] (n=4) | 0.698 ± 0.338 [0.354, 0.923] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 1844.368 ± 383.194 [1527.760, 2160.975] (n=4) | n/a |

### Matched prefix: spread_12tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 541.907 ± 441.424 [226.795, 935.698] (n=4) | 2.902 ± 2.341 [1.242, 5.002] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2901.795 ± 430.813 [2527.739, 3273.504] (n=4) | 27.53 ± 11.04 [16.84, 34.55] (n=4) |
| Greedy carbon | 461.810 ± 426.529 [176.765, 858.725] (n=4) | 2.344 ± 1.762 [1.072, 3.905] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2553.667 ± 362.438 [2254.409, 2873.836] (n=4) | 2.66 ± 0.71 [2.11, 3.21] (n=4) |
| Offline MILP | 448.198 ± 411.202 [172.527, 830.037] (n=4) | 2.411 ± 1.887 [1.069, 4.101] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2581.157 ± 372.122 [2257.011, 2915.144] (n=4) | n/a |

### Matched prefix: spread_24tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 345.580 ± 117.341 [241.660, 456.069] (n=4) | 1.917 ± 0.651 [1.339, 2.531] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 3111.913 ± 566.572 [2647.954, 3575.871] (n=4) | 10.38 ± 3.57 [7.28, 13.02] (n=4) |
| Greedy carbon | 336.240 ± 112.890 [237.896, 439.889] (n=4) | 1.554 ± 0.588 [1.047, 2.117] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2736.514 ± 467.201 [2353.507, 3119.521] (n=4) | 7.52 ± 4.74 [3.36, 11.96] (n=4) |
| Offline MILP | 314.886 ± 115.643 [217.420, 427.273] (n=4) | 1.588 ± 0.623 [1.087, 2.201] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2868.527 ± 503.713 [2476.946, 3260.109] (n=4) | n/a |

### Matched prefix: spread_48tasks

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 276.482 ± 120.409 [177.927, 375.038] (n=4) | 1.458 ± 0.645 [0.944, 1.971] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2745.886 ± 326.362 [2474.862, 3000.059] (n=4) | 15.07 ± 5.90 [11.71, 20.89] (n=4) |
| Greedy carbon | 261.589 ± 116.031 [169.025, 354.153] (n=4) | 1.142 ± 0.501 [0.742, 1.541] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2427.732 ± 320.795 [2175.335, 2680.128] (n=4) | 8.75 ± 5.61 [4.16, 13.81] (n=4) |
| Offline MILP | 242.522 ± 110.374 [151.829, 333.215] (n=4) | 1.167 ± 0.564 [0.742, 1.648] (n=4) | 1.000 ± 0.000 [1.000, 1.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 0.000 ± 0.000 [0.000, 0.000] (n=4) | 2486.516 ± 327.852 [2212.009, 2761.023] (n=4) | n/a |

## Sensitivity results

### Full-size sensitivity: burst_2h_24tasks__baseline

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.803 ± 382.308 [310.470, 851.135] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 465.353 ± 245.503 [291.757, 638.950] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__carbon_april_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.005 ± 407.152 [292.105, 867.905] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 355.024 ± 218.844 [200.278, 509.770] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__carbon_july_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 704.585 ± 457.207 [381.290, 1027.879] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 417.186 ± 266.223 [228.937, 605.434] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__carbon_october_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 690.290 ± 535.734 [311.469, 1069.111] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 394.319 ± 236.791 [226.882, 561.756] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__gpu_power_minus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 484.052 ± 313.650 [262.268, 705.836] (n=2) | 2.175 ± 1.287 [1.265, 3.085] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 388.339 ± 199.735 [247.105, 529.572] (n=2) | 1.750 ± 0.934 [1.090, 2.410] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__gpu_power_plus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 677.553 ± 450.965 [358.673, 996.434] (n=2) | 3.036 ± 1.841 [1.734, 4.338] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 542.368 ± 291.271 [336.409, 748.328] (n=2) | 2.442 ± 1.363 [1.478, 3.406] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__network_double

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.803 ± 382.307 [310.471, 851.135] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.653 ± 192.387 [2169.615, 2441.691] (n=2) | n/a |
| Greedy carbon | 465.353 ± 245.503 [291.756, 638.950] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.182 ± 214.620 [1996.423, 2299.941] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__network_half

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.803 ± 382.308 [310.470, 851.135] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.936 ± 192.287 [2169.968, 2441.903] (n=2) | n/a |
| Greedy carbon | 465.354 ± 245.502 [291.758, 638.950] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.518 ± 214.783 [1996.644, 2300.393] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__pue_minus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 522.722 ± 344.077 [279.423, 766.021] (n=2) | 2.345 ± 1.408 [1.349, 3.340] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 418.818 ± 220.953 [262.581, 575.055] (n=2) | 1.886 ± 1.034 [1.156, 2.617] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__pue_plus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 638.883 ± 420.538 [341.517, 936.248] (n=2) | 2.866 ± 1.721 [1.649, 4.083] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 511.889 ± 270.053 [320.932, 702.845] (n=2) | 2.306 ± 1.263 [1.412, 3.199] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__slack_1800s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.803 ± 382.308 [310.470, 851.135] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 465.353 ± 245.503 [291.757, 638.950] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: burst_2h_24tasks__slack_7200s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 580.803 ± 382.308 [310.470, 851.135] (n=2) | 2.605 ± 1.564 [1.499, 3.711] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2305.741 ± 192.354 [2169.726, 2441.755] (n=2) | n/a |
| Greedy carbon | 465.353 ± 245.503 [291.757, 638.950] (n=2) | 2.096 ± 1.149 [1.284, 2.908] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2148.268 ± 214.672 [1996.472, 2300.063] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__baseline

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 529.635 ± 200.043 [388.183, 671.088] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 449.982 ± 184.434 [319.568, 580.397] (n=2) | 2.274 ± 0.912 [1.630, 2.919] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__carbon_april_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 573.860 ± 229.886 [411.306, 736.413] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 355.902 ± 132.459 [262.239, 449.565] (n=2) | 2.242 ± 0.866 [1.630, 2.855] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2417.777 ± 492.159 [2069.768, 2765.786] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__carbon_july_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 738.615 ± 288.591 [534.550, 942.679] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 414.269 ± 150.440 [307.892, 520.646] (n=2) | 2.242 ± 0.866 [1.630, 2.855] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2417.777 ± 492.159 [2069.768, 2765.786] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__carbon_october_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 574.228 ± 227.077 [413.661, 734.796] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 401.640 ± 169.272 [281.947, 521.334] (n=2) | 2.242 ± 0.866 [1.630, 2.855] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2417.777 ± 492.159 [2069.768, 2765.786] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__gpu_power_minus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 480.605 ± 174.613 [357.135, 604.075] (n=2) | 2.650 ± 0.985 [1.954, 3.346] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 405.804 ± 159.559 [292.979, 518.629] (n=2) | 2.057 ± 0.791 [1.498, 2.616] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__gpu_power_plus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 578.666 ± 225.474 [419.232, 738.101] (n=2) | 3.196 ± 1.277 [2.293, 4.099] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 494.161 ± 209.309 [346.157, 642.164] (n=2) | 2.492 ± 1.033 [1.761, 3.222] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__network_double

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 529.635 ± 200.043 [388.183, 671.088] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 449.978 ± 184.439 [319.560, 580.396] (n=2) | 2.274 ± 0.912 [1.630, 2.919] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.096 ± 498.509 [2069.597, 2774.595] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__network_half

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 529.635 ± 200.043 [388.183, 671.088] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 449.991 ± 184.423 [319.584, 580.397] (n=2) | 2.274 ± 0.912 [1.630, 2.919] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.858 ± 498.699 [2070.224, 2775.491] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__pue_minus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 476.672 ± 180.039 [349.365, 603.979] (n=2) | 2.631 ± 1.018 [1.911, 3.350] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 404.984 ± 165.991 [287.611, 522.357] (n=2) | 2.047 ± 0.821 [1.467, 2.627] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__pue_plus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 582.599 ± 220.048 [427.002, 738.196] (n=2) | 3.215 ± 1.244 [2.336, 4.095] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 494.981 ± 202.877 [351.525, 638.437] (n=2) | 2.502 ± 1.003 [1.793, 3.211] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__slack_1800s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 529.635 ± 200.043 [388.183, 671.088] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 449.982 ± 184.434 [319.568, 580.397] (n=2) | 2.274 ± 0.912 [1.630, 2.919] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Full-size sensitivity: spread_24tasks__slack_7200s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 529.635 ± 200.043 [388.183, 671.088] (n=2) | 2.923 ± 1.131 [2.123, 3.723] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2767.568 ± 582.866 [2355.420, 3179.716] (n=2) | n/a |
| Greedy carbon | 449.982 ± 184.434 [319.568, 580.397] (n=2) | 2.274 ± 0.912 [1.630, 2.919] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2422.312 ± 498.572 [2069.768, 2774.855] (n=2) | n/a |
| Offline MILP | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Sensitivity matched 12-task solver comparisons

### Sensitivity prefix: burst_2h_24tasks__baseline

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 298.941 ± 117.059 [216.168, 381.714] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 283.345 ± 93.587 [217.169, 349.520] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 265.591 ± 100.569 [194.479, 336.704] (n=2) | 1.149 ± 0.453 [0.828, 1.469] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__carbon_april_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 296.291 ± 118.260 [212.668, 379.913] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | 78.20 ± 12.93 [69.06, 87.35] (n=2) |
| Greedy carbon | 184.950 ± 67.050 [137.538, 232.361] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | 12.28 ± 12.56 [3.40, 21.16] (n=2) |
| Offline MILP | 169.117 ± 78.633 [113.515, 224.719] (n=2) | 1.147 ± 0.459 [0.822, 1.472] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__carbon_july_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 394.887 ± 157.898 [283.236, 506.537] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | 129.47 ± 15.04 [118.83, 140.11] (n=2) |
| Greedy carbon | 196.375 ± 64.407 [150.832, 241.918] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | 16.19 ± 16.51 [4.51, 27.86] (n=2) |
| Offline MILP | 174.719 ± 80.265 [117.963, 231.475] (n=2) | 1.147 ± 0.459 [0.822, 1.472] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__carbon_october_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 310.921 ± 121.822 [224.780, 397.062] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | 60.96 ± 10.15 [53.78, 68.14] (n=2) |
| Greedy carbon | 212.432 ± 76.001 [158.692, 266.173] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | 10.90 ± 11.04 [3.09, 18.70] (n=2) |
| Offline MILP | 195.943 ± 88.038 [133.690, 258.195] (n=2) | 1.147 ± 0.459 [0.822, 1.472] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__gpu_power_minus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 249.782 ± 97.529 [180.818, 318.745] (n=2) | 1.239 ± 0.498 [0.887, 1.591] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 238.852 ± 76.055 [185.073, 292.631] (n=2) | 1.031 ± 0.328 [0.799, 1.263] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 221.723 ± 83.525 [162.662, 280.783] (n=2) | 0.957 ± 0.380 [0.688, 1.226] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__gpu_power_plus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 348.100 ± 136.589 [251.517, 444.683] (n=2) | 1.725 ± 0.697 [1.232, 2.217] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 327.838 ± 111.118 [249.265, 406.410] (n=2) | 1.411 ± 0.481 [1.070, 1.751] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 309.414 ± 117.679 [226.203, 392.625] (n=2) | 1.337 ± 0.530 [0.962, 1.713] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__network_double

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 298.941 ± 117.059 [216.168, 381.714] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 283.344 ± 93.586 [217.169, 349.519] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.207 ± 50.694 [2007.361, 2079.053] (n=2) | n/a |
| Offline MILP | 265.594 ± 100.566 [194.483, 336.704] (n=2) | 1.149 ± 0.453 [0.828, 1.469] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.488 ± 33.801 [1996.587, 2044.390] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__network_half

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 298.941 ± 117.059 [216.168, 381.714] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 283.346 ± 93.588 [217.169, 349.522] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.970 ± 50.821 [2008.034, 2079.906] (n=2) | n/a |
| Offline MILP | 265.587 ± 100.575 [194.470, 336.704] (n=2) | 1.149 ± 0.453 [0.828, 1.469] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2021.509 ± 33.817 [1997.596, 2045.421] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__pue_minus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 269.047 ± 105.353 [194.551, 343.543] (n=2) | 1.334 ± 0.538 [0.954, 1.714] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 255.010 ± 84.228 [195.452, 314.568] (n=2) | 1.099 ± 0.364 [0.841, 1.357] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 239.032 ± 90.512 [175.031, 303.034] (n=2) | 1.034 ± 0.408 [0.745, 1.322] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__pue_plus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 328.835 ± 128.765 [237.784, 419.885] (n=2) | 1.630 ± 0.657 [1.165, 2.095] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 311.679 ± 102.945 [238.886, 384.472] (n=2) | 1.343 ± 0.445 [1.028, 1.658] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 292.151 ± 110.626 [213.926, 370.375] (n=2) | 1.263 ± 0.499 [0.911, 1.616] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__slack_1800s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 298.941 ± 117.059 [216.168, 381.714] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 283.345 ± 93.587 [217.169, 349.520] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 265.591 ± 100.569 [194.479, 336.704] (n=2) | 1.149 ± 0.453 [0.828, 1.469] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: burst_2h_24tasks__slack_7200s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 298.941 ± 117.059 [216.168, 381.714] (n=2) | 1.482 ± 0.597 [1.059, 1.904] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2322.940 ± 38.866 [2295.458, 2350.423] (n=2) | n/a |
| Greedy carbon | 283.345 ± 93.587 [217.169, 349.520] (n=2) | 1.221 ± 0.405 [0.935, 1.507] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2043.424 ± 50.736 [2007.549, 2079.300] (n=2) | n/a |
| Offline MILP | 265.591 ± 100.569 [194.479, 336.704] (n=2) | 1.149 ± 0.453 [0.828, 1.469] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2020.788 ± 33.807 [1996.883, 2044.694] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__baseline

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 274.576 ± 93.100 [208.744, 340.408] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 262.739 ± 83.356 [203.797, 321.680] (n=2) | 1.199 ± 0.432 [0.894, 1.505] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 245.085 ± 78.248 [189.755, 300.414] (n=2) | 1.222 ± 0.381 [0.952, 1.491] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__carbon_april_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 289.152 ± 97.550 [220.173, 358.130] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 39.24 ± 0.84 [38.64, 39.83] (n=2) |
| Greedy carbon | 217.942 ± 67.104 [170.492, 265.391] (n=2) | 1.167 ± 0.387 [0.894, 1.440] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2687.578 ± 353.192 [2437.833, 2937.323] (n=2) | 5.49 ± 2.64 [3.62, 7.36] (n=2) |
| Offline MILP | 207.464 ± 68.811 [158.807, 256.120] (n=2) | 1.118 ± 0.391 [0.841, 1.394] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2705.889 ± 327.297 [2474.455, 2937.323] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__carbon_july_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 373.176 ± 126.586 [283.666, 462.686] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 59.98 ± 1.36 [59.01, 60.94] (n=2) |
| Greedy carbon | 241.040 ± 71.410 [190.546, 291.535] (n=2) | 1.167 ± 0.387 [0.894, 1.440] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2687.578 ± 353.192 [2437.833, 2937.323] (n=2) | 4.11 ± 3.83 [1.40, 6.81] (n=2) |
| Offline MILP | 232.943 ± 77.150 [178.390, 287.496] (n=2) | 1.131 ± 0.409 [0.841, 1.420] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2705.889 ± 327.297 [2474.455, 2937.323] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__carbon_october_offset

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 284.244 ± 101.361 [212.571, 355.917] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 22.85 ± 0.12 [22.76, 22.93] (n=2) |
| Greedy carbon | 239.141 ± 79.122 [183.193, 295.089] (n=2) | 1.167 ± 0.387 [0.894, 1.440] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2687.578 ± 353.192 [2437.833, 2937.323] (n=2) | 3.86 ± 2.94 [1.78, 5.94] (n=2) |
| Offline MILP | 231.416 ± 82.734 [172.914, 289.918] (n=2) | 1.131 ± 0.409 [0.841, 1.420] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2705.889 ± 327.297 [2474.455, 2937.323] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__gpu_power_minus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 246.047 ± 81.576 [188.364, 303.730] (n=2) | 1.360 ± 0.446 [1.044, 1.675] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 12.54 ± 2.44 [10.81, 14.27] (n=2) |
| Greedy carbon | 235.409 ± 72.756 [183.963, 286.855] (n=2) | 1.072 ± 0.375 [0.806, 1.337] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 8.07 ± 0.21 [7.92, 8.22] (n=2) |
| Offline MILP | 217.899 ± 67.754 [169.990, 265.808] (n=2) | 1.088 ± 0.327 [0.857, 1.319] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__gpu_power_plus20pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 303.105 ± 104.625 [229.125, 377.086] (n=2) | 1.676 ± 0.574 [1.270, 2.081] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 10.96 ± 2.26 [9.36, 12.56] (n=2) |
| Greedy carbon | 290.068 ± 93.956 [223.631, 356.505] (n=2) | 1.327 ± 0.489 [0.981, 1.673] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 6.57 ± 0.23 [6.41, 6.74] (n=2) |
| Offline MILP | 272.270 ± 88.742 [209.520, 335.020] (n=2) | 1.355 ± 0.435 [1.048, 1.663] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__network_double

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 274.576 ± 93.100 [208.744, 340.408] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 262.735 ± 83.361 [203.790, 321.680] (n=2) | 1.199 ± 0.432 [0.894, 1.505] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.423 ± 365.911 [2437.684, 2955.161] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 245.087 ± 78.251 [189.755, 300.419] (n=2) | 1.222 ± 0.381 [0.952, 1.491] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.004 ± 281.907 [2663.666, 3062.342] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__network_half

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 274.576 ± 93.100 [208.744, 340.408] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.32] (n=2) |
| Greedy carbon | 262.746 ± 83.346 [203.811, 321.680] (n=2) | 1.199 ± 0.432 [0.894, 1.505] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2697.208 ± 366.234 [2438.242, 2956.174] (n=2) | 7.24 ± 0.23 [7.08, 7.41] (n=2) |
| Offline MILP | 245.080 ± 78.241 [189.755, 300.404] (n=2) | 1.222 ± 0.381 [0.952, 1.491] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.607 ± 282.242 [2664.032, 3063.182] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__pue_minus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 247.119 ± 83.790 [187.870, 306.367] (n=2) | 1.366 ± 0.459 [1.041, 1.690] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 236.465 ± 75.020 [183.418, 289.512] (n=2) | 1.079 ± 0.389 [0.804, 1.354] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 220.576 ± 70.423 [170.779, 270.373] (n=2) | 1.099 ± 0.343 [0.857, 1.342] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__pue_plus10pct

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 302.034 ± 102.410 [229.619, 374.449] (n=2) | 1.669 ± 0.561 [1.273, 2.066] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 289.013 ± 91.691 [224.177, 353.848] (n=2) | 1.319 ± 0.475 [0.983, 1.655] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 269.593 ± 86.073 [208.730, 330.456] (n=2) | 1.344 ± 0.419 [1.048, 1.640] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__slack_1800s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 274.576 ± 93.100 [208.744, 340.408] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 262.739 ± 83.356 [203.797, 321.680] (n=2) | 1.199 ± 0.432 [0.894, 1.505] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 245.085 ± 78.248 [189.755, 300.414] (n=2) | 1.222 ± 0.381 [0.952, 1.491] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

### Sensitivity prefix: spread_24tasks__slack_7200s

| Policy | Emissions gCO₂e | Energy kWh | Completion | Rejection | SLA violations | Latency s | Optimality gap % |
|---|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 274.576 ± 93.100 [208.744, 340.408] (n=2) | 1.518 ± 0.510 [1.157, 1.878] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 3065.714 ± 439.982 [2754.600, 3376.828] (n=2) | 11.66 ± 2.34 [10.01, 13.31] (n=2) |
| Greedy carbon | 262.739 ± 83.356 [203.797, 321.680] (n=2) | 1.199 ± 0.432 [0.894, 1.505] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2696.648 ± 366.019 [2437.833, 2955.462] (n=2) | 7.24 ± 0.23 [7.08, 7.40] (n=2) |
| Offline MILP | 245.085 ± 78.248 [189.755, 300.414] (n=2) | 1.222 ± 0.381 [0.952, 1.491] (n=2) | 1.000 ± 0.000 [1.000, 1.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 0.000 ± 0.000 [0.000, 0.000] (n=2) | 2863.183 ± 282.007 [2663.774, 3062.592] (n=2) | n/a |

## MILP solver status

Across 24 baseline matched 12-task MILPs, 17 were certified optimal, 7 returned a feasible incumbent without a proof of optimality, and 0 had no feasible solution. Across 48 sensitivity MILPs, 30 were certified optimal, 18 returned feasible incumbents, and 0 had no feasible solution. Only certified optimal complete cases contribute gaps.

## Interpretation and limitations

This expansion increases scenario coverage and tests whether placement results vary with arrival concentration and sampled task count. It does not create new measured trace evidence: official preprocessing repeats a two-month source pattern across the package axis, and the interval timestamps are not validated against task event timestamps. The phase’s 2020/2023 mismatch cannot be repaired from the currently available, compatible all-region data. The 2023 Alibaba trace is a promising independent workload family but lacks a verified absolute timestamp and transfer-size field; adding it requires either an official richer schema or a separately defined no-migration benchmark.

Deadlines (runtime + configured slack), north ingress, capacities, execution characteristics, PUE, GPU power, network and transfer sizes remain simulator assumptions or source estimates. The simulator does not represent task failures, GPU-type constraints, multiple instances as gang-scheduled job groups, data locality, or real origin geography. The 12-task MILP is offline and lookahead-aware; its gap is not online regret. Larger workloads are not solved exactly. No claim of production-cloud effectiveness is made. See machine-readable per-run results and solver statuses under `results/phase32/`.
