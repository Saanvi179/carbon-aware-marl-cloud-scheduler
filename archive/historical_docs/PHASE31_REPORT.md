# Phase 3.1 — robustness and generalisation

## Method

Inputs are the retained official Alibaba-derived 2020 workload archive and 2023 hourly direct regional carbon profiles. This run sampled 144 task appearances in the primary spread/burst cohorts; seeded subset replications reuse the same source windows and may overlap in job IDs. No task fields or arrival times were fabricated. The trace supplies no per-task deadline or geo-origin, so deadline slack and ingress are varied explicitly as assumptions. Carbon observations use zero-order-held source values, and online candidate estimates remain current-observation-only. MILP uses the full future profile and is an offline oracle.

Sensitivity settings are controlled one-factor scenario assumptions: month-offset replay of 2023 profiles; commonized profiles as a regional-variation ablation; deadline slack, ingress region, PUE, GPU active power, and network bandwidth/RTT. The 2020/2023 offset sweep quantifies date-mismatch sensitivity but cannot establish a historical year-to-year comparison. Network, PUE and power values are model inputs, not trace measurements.

Results show mean ± sample SD [95% percentile bootstrap interval] across instances. Confidence intervals resample instances; they are descriptive, particularly with three instances. MILP gaps are included only when the solver certifies optimality and both schedules complete all tasks; the gap cell gives the number of qualifying paired instances.

## Regional carbon profiles

| Region | Source zone | Mean direct intensity gCO₂e/kWh | Min | Max | Estimated hourly rows |
|---|---|---:|---:|---:|---:|
| north | US-NY-NYIS | 209.68 | 130.95 | 300.60 | 49 |
| west | US-CAL-CISO | 193.96 | 54.47 | 331.67 | 2 |
| east | US-TEX-ERCO | 316.72 | 124.00 | 494.32 | 0 |

Regional carbon summaries describe the measured 2023 source values; the simulator's task outcomes below replay these series against 2020 workload timestamps.

## Results

### 2023 carbon April offset

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 569.484 ± 691.185 [109.659, 1364.336] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 79.52 ± 6.26 [72.33, 83.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 315.967 ± 379.234 [59.652, 751.606] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 0.31 ± 0.27 [0.00, 0.48] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 314.575 ± 377.317 [59.652, 748.025] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.055 ± 0.018 [0.035, 0.071] | n/a | 0.33 | 7.67 | 0.00 |

### 2023 carbon July offset

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 745.465 ± 909.535 [141.800, 1791.572] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 95.38 ± 9.51 [87.54, 105.95] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 395.551 ± 490.881 [68.850, 960.043] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 0.26 ± 0.25 [0.00, 0.50] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 393.811 ± 488.255 [68.850, 955.282] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.047 ± 0.016 [0.029, 0.059] | n/a | 0.33 | 7.67 | 0.00 |

### 2023 carbon October offset

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 590.511 ± 725.108 [111.516, 1424.739] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.001, 0.002] | 62.82 ± 9.21 [52.88, 71.06] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 357.600 ± 428.216 [67.784, 849.457] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 1.02 ± 1.00 [0.00, 1.99] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 351.520 ± 419.088 [67.784, 832.881] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.053 ± 0.015 [0.036, 0.067] | n/a | 0.33 | 7.67 | 0.00 |

### 24-task recorded burst windows

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 591.663 ± 483.137 [259.102, 1145.854] | 2.558 ± 1.871 [1.214, 4.695] | 0.986 ± 0.024 [0.958, 1.000] | 0.014 ± 0.024 [0.000, 0.042] | 0.333 ± 0.577 [0.000, 1.000] | 2573.929 ± 556.901 [2150.057, 3204.659] | 0.005 ± 0.000 [0.004, 0.005] | 47.37 ± 0.00 [47.37, 47.37] (n=1) | 18.33 | 4.33 | 1.00 |
| Greedy carbon | 519.775 ± 385.010 [228.835, 956.361] | 2.237 ± 1.582 [0.965, 4.008] | 0.986 ± 0.024 [0.958, 1.000] | 0.014 ± 0.024 [0.000, 0.042] | 0.333 ± 0.577 [0.000, 1.000] | 2379.074 ± 448.481 [2041.433, 2887.945] | 0.005 ± 0.001 [0.005, 0.006] | 23.00 ± 0.00 [23.00, 23.00] (n=1) | 5.33 | 17.67 | 0.67 |
| Offline MILP | 458.770 ± 277.843 [267.869, 777.523] | 2.042 ± 1.277 [1.204, 3.512] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2431.379 ± 660.416 [1933.595, 3180.578] | 11.340 ± 6.482 [3.855, 15.086] | n/a | 4.33 | 17.67 | 2.00 |

### 24-task spread subset seed 31031

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 552.124 ± 245.629 [368.726, 831.193] | 2.968 ± 1.271 [1.983, 4.402] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2892.633 ± 692.606 [2458.625, 3691.385] | 0.008 ± 0.000 [0.008, 0.008] | 46.65 ± 11.07 [33.93, 54.04] (n=3) | 24.00 | 0.00 | 0.00 |
| Greedy carbon | 413.681 ± 169.104 [273.901, 601.648] | 2.347 ± 1.070 [1.533, 3.559] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2531.159 ± 618.314 [2150.196, 3244.576] | 0.010 ± 0.002 [0.008, 0.012] | 10.55 ± 2.95 [7.24, 12.91] (n=3) | 1.00 | 23.00 | 0.00 |
| Offline MILP | 374.339 ± 151.321 [242.590, 539.611] | 2.267 ± 1.028 [1.432, 3.415] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2637.457 ± 684.087 [2208.680, 3426.378] | 2.205 ± 3.073 [0.397, 5.753] | n/a | 6.67 | 17.33 | 0.00 |

### 24-task spread subset seed 31032

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 789.144 ± 112.045 [676.684, 900.770] | 4.269 ± 0.560 [3.691, 4.809] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2983.186 ± 86.592 [2923.769, 3082.539] | 0.009 ± 0.001 [0.008, 0.009] | 38.40 ± 10.01 [27.50, 47.20] (n=3) | 24.00 | 0.00 | 0.00 |
| Greedy carbon | 603.094 ± 40.611 [559.820, 640.377] | 3.378 ± 0.500 [2.896, 3.895] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2603.914 ± 76.592 [2548.522, 2691.319] | 0.010 ± 0.001 [0.009, 0.011] | 6.15 ± 1.93 [4.65, 8.33] (n=3) | 1.00 | 23.00 | 0.00 |
| Offline MILP | 568.310 ± 40.953 [530.717, 611.951] | 3.455 ± 0.430 [3.047, 3.904] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2727.340 ± 108.716 [2620.803, 2838.111] | 2.481 ± 2.748 [0.537, 5.625] | n/a | 7.67 | 16.33 | 0.00 |

### 24-task spread windows

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 814.680 ± 642.186 [370.526, 1551.002] | 4.435 ± 3.445 [2.000, 8.376] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2770.030 ± 586.729 [2102.338, 3203.325] | 0.009 ± 0.002 [0.008, 0.012] | 23.05 ± 10.91 [10.51, 30.37] (n=3) | 23.67 | 0.33 | 0.00 |
| Greedy carbon | 688.100 ± 501.377 [306.260, 1255.886] | 3.531 ± 2.836 [1.539, 6.778] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2419.773 ± 516.906 [1828.468, 2785.852] | 0.010 ± 0.002 [0.009, 0.012] | 5.93 ± 0.33 [5.57, 6.21] (n=3) | 0.67 | 23.33 | 0.00 |
| Offline MILP | 650.455 ± 475.944 [288.892, 1189.674] | 3.517 ± 2.791 [1.548, 6.712] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2515.584 ± 553.174 [1886.864, 2927.590] | 1.740 ± 1.899 [0.350, 3.904] | n/a | 4.67 | 18.67 | 0.67 |

### Baseline assumptions

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 533.660 ± 646.949 [104.117, 1277.735] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.001, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.720 ± 490.517 [89.133, 984.187] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.082 ± 0.028 [0.056, 0.112] | n/a | 1.33 | 6.67 | 0.00 |

### Common regional carbon

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 585.547 ± 702.054 [118.029, 1392.847] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 29.95 ± 5.06 [24.13, 33.37] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 469.956 ± 575.245 [90.022, 1131.774] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 1.29 ± 0.67 [0.87, 2.06] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 465.168 ± 570.860 [89.186, 1122.050] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.059 ± 0.027 [0.034, 0.088] | n/a | 0.33 | 7.67 | 0.00 |

### Deadline slack 1800s

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 533.660 ± 646.949 [104.117, 1277.735] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.720 ± 490.517 [89.133, 984.187] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.057 ± 0.019 [0.040, 0.077] | n/a | 1.33 | 6.67 | 0.00 |

### Deadline slack 7200s

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 533.660 ± 646.949 [104.117, 1277.735] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.720 ± 490.517 [89.133, 984.187] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.079 ± 0.030 [0.051, 0.111] | n/a | 1.33 | 6.67 | 0.00 |

### GPU power +20%

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 619.690 ± 771.750 [113.511, 1507.945] | 3.332 ± 4.161 [0.594, 8.120] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.82 ± 7.88 [16.16, 29.92] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 507.662 ± 611.611 [98.596, 1210.760] | 2.681 ± 3.414 [0.453, 6.612] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.44] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 487.579 ± 585.345 [97.539, 1160.648] | 2.733 ± 3.439 [0.463, 6.690] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.070 ± 0.022 [0.047, 0.092] | n/a | 1.33 | 6.67 | 0.00 |

### GPU power -20%

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 447.631 ± 522.217 [94.722, 1047.526] | 2.409 ± 2.816 [0.497, 5.642] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.97 ± 7.58 [15.89, 29.69] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 368.285 ± 413.594 [81.603, 842.413] | 1.929 ± 2.310 [0.378, 4.584] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 353.860 ± 395.765 [80.727, 807.726] | 1.975 ± 2.328 [0.388, 4.647] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.083 ± 0.032 [0.047, 0.109] | n/a | 1.33 | 6.67 | 0.00 |

### Ingress east

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 904.998 ± 1138.858 [167.878, 2216.685] | 3.654 ± 4.441 [0.695, 8.761] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 3152.065 ± 1144.106 [1866.866, 4059.569] | 0.002 ± 0.000 [0.002, 0.002] | 96.19 ± 26.03 [74.98, 125.23] (n=3) | 0.00 | 0.00 | 8.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.101 ± 900.050 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.720 ± 490.517 [89.133, 984.187] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2541.090 ± 946.432 [1478.243, 3292.741] | 0.081 ± 0.027 [0.049, 0.099] | n/a | 1.33 | 6.67 | 0.00 |

### Ingress west

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2475.644 ± 899.868 [1461.025, 3177.054] | 0.002 ± 0.000 [0.001, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2475.644 ± 899.868 [1461.025, 3177.054] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.728 ± 490.531 [89.133, 984.212] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.733 ± 946.306 [1478.031, 3292.295] | 0.068 ± 0.017 [0.051, 0.085] | n/a | 1.33 | 6.67 | 0.00 |

### Network throughput/RTT double

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 533.660 ± 646.949 [104.117, 1277.735] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.001, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 437.973 ± 512.560 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2475.981 ± 899.953 [1461.276, 3177.488] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.723 ± 490.523 [89.133, 984.197] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.904 ± 946.307 [1478.193, 3292.442] | 0.074 ± 0.032 [0.040, 0.105] | n/a | 1.33 | 6.67 | 0.00 |

### Network throughput/RTT half

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 533.660 ± 646.949 [104.117, 1277.735] | 2.870 ± 3.488 [0.546, 6.881] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 437.974 ± 512.561 [90.099, 1026.586] | 2.305 ± 2.862 [0.416, 5.598] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.437 ± 900.231 [1461.427, 3178.188] | 0.002 ± 0.000 [0.001, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 420.712 ± 490.504 [89.133, 984.165] | 2.354 ± 2.883 [0.425, 5.669] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2541.239 ± 946.500 [1478.301, 3292.902] | 0.076 ± 0.027 [0.053, 0.105] | n/a | 1.33 | 6.67 | 0.00 |

### PUE +10%

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 587.026 ± 711.644 [114.528, 1405.509] | 3.157 ± 3.837 [0.600, 7.569] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 481.771 ± 563.816 [99.109, 1129.245] | 2.536 ± 3.148 [0.458, 6.158] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 462.792 ± 539.569 [98.047, 1082.606] | 2.590 ± 3.172 [0.468, 6.236] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.091 ± 0.046 [0.046, 0.138] | n/a | 1.33 | 6.67 | 0.00 |

### PUE -10%

| Policy | CO₂e g | Energy kWh | Completion | Rejection | SLA violations | Latency s | Runtime s | Gap % (n) | North placements | West | East |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 480.294 ± 582.254 [93.705, 1149.962] | 2.583 ± 3.139 [0.491, 6.193] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2836.859 ± 1029.695 [1680.179, 3653.613] | 0.002 ± 0.000 [0.002, 0.002] | 20.89 ± 7.75 [16.04, 29.83] (n=3) | 8.00 | 0.00 | 0.00 |
| Greedy carbon | 394.176 ± 461.304 [81.089, 923.928] | 2.075 ± 2.576 [0.374, 5.038] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2476.094 ± 900.046 [1461.286, 3177.681] | 0.002 ± 0.000 [0.002, 0.002] | 3.28 ± 1.90 [1.08, 4.45] (n=3) | 0.33 | 7.67 | 0.00 |
| Offline MILP | 378.648 ± 441.465 [80.220, 885.769] | 2.119 ± 2.595 [0.383, 5.102] | 1.000 ± 0.000 [1.000, 1.000] | 0.000 ± 0.000 [0.000, 0.000] | 0.000 ± 0.000 [0.000, 0.000] | 2540.982 ± 946.372 [1478.194, 3292.560] | 0.077 ± 0.031 [0.046, 0.108] | n/a | 1.33 | 6.67 | 0.00 |

## Findings

On the three 24-task spread windows, greedy completed every task and averaged 688.10 gCO₂e with a 5.93% gap to certified MILP (95% bootstrap interval 5.57–6.21; n=3); FCFS averaged 814.68 g and a 23.05% gap. The two seeded alternate spread subsets also completed all jobs, but greedy emissions were 413.68 and 603.09 g and the gaps were 10.55% and 6.15% respectively (three date windows per seed). This demonstrates meaningful sensitivity to which eligible trace jobs are sampled, while all reported spread MILPs solved optimally.

The 24-task burst cohort had 98.6% mean completion for greedy and FCFS (one rejection across the three workloads); MILP schedules completed all tasks in all three. Only one burst MILP certified optimality within the 15-second limit; the other two returned feasible incumbents, so they contribute no optimality gaps. Greedy's 23.00% gap is for the sole fully completed, certified paired instance (n=1), a warning about burst congestion rather than a stable gap estimate. Baseline 8-task jobs completed at 100%, and greedy averaged 437.97 gCO₂e with a 3.28% gap [1.08, 4.45].

Deadline slack from 1,800 to 7,200 seconds did not change placements or outcomes in this sample. Changing ingress and halving/doubling the assumed network parameters left placement and completion unchanged; measured latency moved only slightly because these jobs' data volumes and deadlines did not make migration infeasible. PUE and GPU-power sweeps changed absolute emissions/energy roughly in proportion to the input scaling, while the baseline gap stayed at 3.28%. Rotating the carbon replay to April/July/October changed greedy emissions to 315.97/395.55/357.60 g and gaps to 0.31/0.26/1.02%; the workload and its 2.305 kWh energy remained fixed. This quantifies substantial year/profile timing sensitivity without resolving the year mismatch.

Measured regional 2023 means were 209.68 gCO₂e/kWh (north), 193.96 (west) and 316.72 (east). Greedy placed 23.33 of 24 spread jobs in west on average; with all regions assigned the same carbon profile, the 8-task baseline gap decreased from 3.28% to 1.29%. The selected cases therefore expose a regional carbon advantage, but this conclusion is conditioned on one ingress assumption and uncalibrated region energy/network characteristics.

Greedy's gap and service metrics must be interpreted together: a low-emissions result with lower completion is not considered an improvement. Carbon-profile month offsets change the emissions landscape while leaving the workload unchanged. The MILP gap is an oracle-lookahead comparison, not an online regret estimate.

## Limitations

This remains a simulator replay, not a production-cloud measurement. The source workload is a selected subset of a packaged processed trace whose timestamps conflict with its upstream source description. Attributes absent from the trace (deadlines and ingress geography) remain assumptions. Carbon years are not aligned, the monthly offsets are deterministic rotations (30-day months for sensitivity only), regional power/PUE and network are not calibrated, and MILP is limited to small instances and its configured time bound. Across 57 MILPs, 55 were certified optimal and two burst cases returned feasible incumbents at the 15-second limit. Three dates per configuration do not support strong population-level generalisation. Full per-run solver status, metrics and assumptions are in `phase31_evaluation.json`.
