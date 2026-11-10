# Public-release audit notes

## Scope and preservation

This publication uses a fresh Git history in the project root. No pre-existing `.git` directory, branch, remote, or commit history was present. The Windows working copies of excluded datasets, trace-based results, and local-path metadata remain on the originating machine; publication exclusions do not delete or rewrite those files.

## Excluded pending source-term verification

The following are kept out of the public Git tree because original-provider redistribution permissions are not established in the project's provenance notes:

- `data/raw/phase3/`: the Alibaba GPU trace ZIP and regional Electricity Maps CSVs.
- `data/processed/phase3/` and `data/processed/phase32/`: derived workload/profile records and manifests/audits associated with those source inputs.
- `results/phase3*/`: historical Phase 3 through Phase 3.3 benchmark outputs, which are based on the excluded trace inputs.

The exclusion is intentionally conservative. The public project still includes the synthetic v4 confirmation and its configuration, seed provenance, task outcomes, decision traces, summary, report, and charts. To repeat historical trace experiments, obtain the inputs directly from their providers, verify their current terms, put them at the paths described in [`DATA_SOURCES.md`](DATA_SOURCES.md), and run the documented preprocessing steps. The v4 final evaluation does not need these datasets.

Historical Phase 2–2.9 outputs are not needed to reproduce the primary v4 comparison and are not part of the curated publication set. A small set of auxiliary scheduler checkpoints referenced by the existing UI is retained; their old benchmark outputs are not. The public set retains the five v4 policy checkpoints actually used by the final evaluation, the validation allowance-selection artifacts, source/config/tests/docs/UI, and the final synthetic v4 artifacts. This avoids uploading every superseded experiment merely because it exists locally.

## Path-safe metadata companions

The following original local files contain absolute local Windows paths and are ignored by Git:

- `results/research_alignment_v1/ui_policy_index.json`
- `results/research_alignment_v1_smoke/ui_policy_index.json`
- `results/research_alignment_v4_final_confirmation/run_metadata.json`

Their publication-safe companions use repository-relative checkpoint/output paths and preserve the original model weights and experimental values:

- `results/research_alignment_v1/ui_policy_index.public.json`
- `results/research_alignment_v4_final_confirmation/run_metadata.public.json`

The Streamlit runner prefers the public-safe index when present and resolves relative checkpoint paths from the project root. The sidecar preserves the prior index's `selected_allowance_fraction` and config fields as checkpoint-training provenance; these are historical v1 metadata and do not set the final proposed rule. The frozen final allowance is 0.20 as recorded in v2 validation and v4. To invoke the final evaluation script from a fresh clone, copy the safe index to the script's expected local filename as described in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md). No new evaluation is performed by this publication procedure.

## Other review results

- The repository-wide text scan found no email addresses or common credential patterns. Broad phone-number matches were numeric/hash-like workload IDs and result values; no contact records were identified. Third-party trace-derived files remain excluded regardless.
- No repository-level `LICENSE` file exists. This release does not select or add a license. Public visibility alone does not grant a general reuse license for this project's code.
- Git LFS is installed locally. The largest local file is the 75,625,706-byte trace ZIP (under GitHub's 100 MB individual-file limit), but it is excluded for source-term reasons. Required v4 checkpoints are approximately 0.61 MB each, so Git LFS is not needed for the retained artifacts.
- The `requirements.txt` file remains the dependency manifest; Python source and public result artifacts contain no vendored third-party packages.
