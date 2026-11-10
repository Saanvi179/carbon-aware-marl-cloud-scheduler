# Phase 3.2 dataset notes

## Current workload input and date-axis audit

The local workload archive remains `data/raw/phase3/result_df_full_year_2020.zip` (75,625,706 compressed bytes; one 142,336,499-byte pickle). The pickle contains 37,552 `interval_15m` rows and 1,300,144 task records. Its interval axis runs from 2020-01-01 through 2021-01-26, but this must not be interpreted as a year of raw production observations. The official [SustainCluster dataset documentation](https://github.com/HewlettPackard/sustain-cluster#41-ai-workloads-alibaba-gpu-cluster-trace) states that the Alibaba source covers July–August 2020 and that the packaged year-long trace is built by repeating observed daily/weekly patterns.

`experiments.audit_phase32_sources` validates all interval timestamps and samples task fields at a deterministic stride of 75 interval rows. It found no invalid, non-monotonic, or duplicate interval timestamps; 80 interval steps are 30 minutes instead of 15 minutes. These gaps are retained. In the 16,720-task field sample, no malformed records were observed under the checked fields, but sampled internal start fields range from 1970-01-26 through 1970-03-15 while their associated `interval_15m` values are on the package 2020–2021 axis. The median-scale discrepancy is about 1.58–1.61 billion seconds. The fields therefore do not provide a verified UTC alignment; the package intervals are treated as scenario-axis coordinates only.

The deterministic `source_audit.json` documents these counts and caveats. Recreate it with:

```powershell
python -m experiments.audit_phase32_sources
```

## Expanded cohorts

`experiments.preprocess_phase32` samples 13 monthly package-axis windows across the full packaged interval range. It creates six families: spread or two-hour burst arrivals at 12, 24, and 48 tasks per window. All chosen tasks are records from the supplied pickle; task fields and their interval-derived arrival slots are retained. Selection uses a reproducible seed per task-count level. The two-hour pattern uses the first eligible records inside that short window, without moving their source intervals. “Low/medium/high intensity” refers only to the number of selected tasks and is not a claim about calibrated production load.

The selector applies runtime bounds of 900–7,200 seconds, CPU <=64, GPU <=8, memory <=256 GB, positive CPU/runtime, and nonnegative input volume. The 900-second minimum matches SustainCluster's documented short-task filter. It retains fractional GPU/CPU requests. Deadlines continue to be derived as runtime + 3,600 seconds slack, and every task retains the north ingress assumption because neither is present in the task schema. The source `bandwidth_gb` field is treated as estimated input volume for migration modeling, with the caveat that it is not a measured per-datacenter data-residency record.

Generate the bounded JSON cohorts with:

```powershell
python -m experiments.preprocess_phase32
```

The output is `data/processed/phase32/phase32_workloads.json`. It references the audit file and stores each family manifest and selected IDs. The raw source archive is unchanged.

## Additional workload source review

Alibaba's official [2023 GPU-sharing trace](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2023) provides an 8,152-pod `openb_pod_list_default.csv` (562 KB) and GPU node inventory (1,214 rows, 41.4 KB). Its schema includes CPU millicores, memory MiB, integer GPU count, GPU milli-share, QoS, pod phase and relative creation/scheduled/deletion times. It has no task input-size field and the page does not establish a UTC anchor for those relative times. Its folder-level README requests research use and citation; no explicit dataset license was located. We did not download or integrate it because missing transfer size blocks this project's realistic remote-migration latency and no formal license/calendar alignment was verified.

Other considered sources:

- SustainDC Alibaba and Google CSVs are aggregate hourly CPU profiles, not task-level GPU jobs.
- Google Cluster Trace 2019 is useful for CPU/memory scheduling, but has no compatible GPU request field.
- MIT Supercloud includes 460,497 jobs and 98,177 GPU-request jobs, but the dataset is on the order of a terabyte compressed/uncompressed data ecosystem and was excluded as an unnecessary large download.
- Alibaba 2025/2026 traces are newer candidates, but their specialized serving/fact-table schemas, relative time axes and additional data volume require separate compatibility/license analysis before import.

## Carbon data and alignment

The available local carbon input remains the official 2023 hourly direct-intensity series for NYISO, CAISO and ERCOT (gCO₂e/kWh), with hourly rows held across four simulator slots. Source values flagged estimated remain flagged and are not filled. Region mapping remains north=NYISO, west=CAISO, east=ERCOT.

The 2020 task/source-to-2023 carbon replay is not calendar-aligned. The SustainCluster README's current carbon section describes 2021–2024, while its release overview says environmental series 2020–2024; only 2023 all-region files are present locally. Other sources inspected do not fill the gap compatibly:

- [WattTime historical MOER](https://legacy-docs.watttime.org/#historical-emissions) has a suitable temporal signal (lb CO₂/MWh), but `/historical` is subscriber-restricted.
- [CAISO MEF/AEF 2019–2020](https://data.mendeley.com/datasets/7w87xy5pwj/1) is CC BY 4.0 and provides month-hour regressed factors for CAISO only, not an hourly three-region average-intensity series.
- [Google's 2020 region-carbon file](https://github.com/GoogleCloudPlatform/region-carbon-info/blob/main/data/yearly/2020.csv) is annual lifecycle intensity by Google Cloud region; it is not an hourly profile and does not map to the three ISO zones.

No values from these sources are substituted, rescaled, or interpolated. The carbon-offset sensitivity remains a scenario replay, not a repair of historical alignment.

## Licensing and attribution status

The containing SustainCluster software repository is MIT, but third-party dataset rights are separate. SustainCluster documentation describes the Alibaba source with CC BY 4.0 attribution language; the primary Alibaba trace README itself provides research/study guidance and citation instructions but no explicit standard license identifier. Preserve the existing source attribution, cite Weng et al. (NSDI 2022), and verify the applicable Alibaba data terms before redistributing raw or derived records. Electricity Maps' ODbL/data-provider terms continue to apply to carbon inputs as documented in `data/DATA_SOURCES.md`.
