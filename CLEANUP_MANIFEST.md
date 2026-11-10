# Repository cleanup manifest

**Publication scope:** This is the cleanup record for the local project workspace, not a claim that every retained local file is published. The public Git tree applies the conservative exclusions in `docs/PUBLICATION_NOTES.md`; original local files remain untouched.

This manifest records the final-consolidation file dispositions. No research method, model weight, dataset, configuration, or experiment result was changed, regenerated, or overwritten. The authoritative v4 directory remains at its original path.

## Deleted

Generated Python bytecode caches only:

- `agents/__pycache__/`
- `environment/__pycache__/`
- `experiments/__pycache__/`
- `schedulers/__pycache__/`
- `tests/__pycache__/`
- `tools/__pycache__/`
- `ui/__pycache__/`

The new root `.gitignore` prevents common Python/test cache and local environment files from becoming repository artifacts again. No source files were deleted.

## Archived

Historical, superseded or potentially useful root documentation moved unchanged to `archive/historical_docs/`:

- `ALGORITHM_ASSESSMENT.md`
- `AMARL_VERIFICATION.md`
- `IMPLEMENTATION_NOTES.md`
- `PHASE31_REPORT.md`
- `PHASE32_REPORT.md`
- `PHASE33_AUDIT.md`
- `PHASE33_CORRECTED_REPORT.md`
- `PHASE33_REPORT.md`
- `REPRODUCTION_NOTES.md`
- `TRISCHEDRL_VERIFICATION.md`
- `data/PHASE32_DATASET_NOTES.md`

Their associated historical benchmark outputs under `results/` were retained in place. `archive/README.md` explains that these materials are historical and are not the final v4 evidence.

## Moved and consolidated

- `FINAL_PROJECT_REPORT.md` → `docs/FINAL_PROJECT_REPORT.md`
- `RESEARCH_AND_IMPLEMENTATION_COMPARISON.md` → `docs/RESEARCH_AND_IMPLEMENTATION_COMPARISON.md`
- `RESEARCH_METHOD_SPECIFICATION.md` → `docs/RESEARCH_METHOD_SPECIFICATION.md`
- `ui/README.md` → `docs/UI_USAGE.md`; a short `ui/README.md` now points to the canonical guide.
- `data/DATA_SOURCES.md` → `docs/DATA_SOURCES.md`
- `presentation_assets/research_alignment_v4/*` → `assets/presentation/research_alignment_v4/*`

## Modified

- `README.md`: replaced with a complete final-project guide, frozen-method summary, v4 metrics and statistical caveats, installation, UI, structure, limitations and references.
- `ui/app.py`: updated the presentation chart lookup path to `assets/presentation/research_alignment_v4/`.
- `tools/render_final_confirmation_charts.py`: updated its chart output path to the consolidated assets directory. It was not run during cleanup.
- `docs/FINAL_PROJECT_REPORT.md`, `docs/RESEARCH_AND_IMPLEMENTATION_COMPARISON.md`, `docs/RESEARCH_METHOD_SPECIFICATION.md`, `docs/UI_USAGE.md`, `docs/DATA_SOURCES.md`: retained canonical content with links and asset paths updated for the new locations.
- `ui/README.md`: replaced with a pointer to `docs/UI_USAGE.md` and the launch command.
- `assets/presentation/research_alignment_v4/chart_manifest.json`: retained unchanged; its recorded source summary path and SHA-256 continue to identify the v4 result.

## Added

- `CLEANUP_MANIFEST.md` — this disposition record.
- `docs/SYSTEM_ARCHITECTURE.md` — package and runtime architecture.
- `docs/REPRODUCIBILITY.md` — frozen-artifact, setup, verification and safe replay guidance.
- `archive/README.md` and `archive/historical_docs/README.md` — archive interpretation.
- `.gitignore` — common generated/local files.

## Retained in place

- All implementation code in `agents/`, `environment/`, `schedulers/`, `experiments/`, `ui/`, and `tools/` (except path updates above).
- All configurations in `configs/`, package dependencies in `requirements.txt`, and tests in `tests/`.
- All datasets and their provenance inputs under `data/raw/` and `data/processed/`.
- All historical results and checkpoints under `results/`, including the policy index and checkpoint files used by v4.
- Every file in `results/research_alignment_v4_final_confirmation/`: frozen evaluation config, seed manifest and audit, run metadata, metrics, task outcomes, decision traces, summary, protocol amendment and final report.
- The five v4 chart groups in PNG, SVG and PDF formats, plus the chart manifest.

The suggested `models/` and `results/final/` folders were not introduced: checkpoints are already versioned with experiment artifacts, and relocating the authoritative v4 directory would break established references and risk altering its provenance. The existing package structure is import-sensitive and was kept intact.

## Final verification

- `python -m unittest discover -s tests`: 77 tests passed.
- Python compilation and `import ui.app`: passed.
- Streamlit started and its local `/_stcore/health` endpoint returned `ok`.
- All 5 v4 policy checkpoint files exist and their SHA-256 hashes match the frozen v4 configuration.
- Required v4 artifacts are present; chart-manifest source hash matches `final_summary.json`; local Markdown links resolve.
- The installed project libraries import successfully. `python -m pip check` reports one unrelated environment-level conflict: installed `selenium 4.33.0` expects `typing-extensions~=4.13.2`, while the environment has `typing-extensions 4.15.0`.
- No training, research evaluation, or chart regeneration was run during cleanup.
