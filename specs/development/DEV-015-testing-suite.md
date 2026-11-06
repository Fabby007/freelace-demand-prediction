# DEV-015 — Testing Suite

## Specification ID
DEV-015

## Feature/Module Name
Testing Suite

## Purpose
Consolidate the data, model, and dashboard tests required by the source documentation into a single automated test suite under `tests/`, written incrementally alongside DEV-004 through DEV-013.

## Background/Context
Source doc Section 26 (Testing Strategy): Section 26.1 (Data tests), Section 26.2 (Model tests), Section 26.3 (Dashboard tests). This spec is cross-cutting — it is authored incrementally as each producing spec is implemented, then consolidated/verified here per DEV-PLAN.md Section 5.

## Related Requirements
- Section 26.1, 26.2, 26.3
- All DEV specs whose acceptance criteria reference "Section 26.x"

## User Roles
None (developer-facing testing infrastructure).

## Preconditions
Relevant upstream specs (DEV-004 for data tests, DEV-008/DEV-010 for model tests, DEV-013 for dashboard tests) have working implementations to test against.

## User Stories/Use Cases
- As the developer, I need a single test suite I can run before marking any TODO.md item complete, so "complete" always means "verified," not "should work" (MASTER_PROMPT.md Stage 6/7).

## Functional Requirements

### 26.1 Data tests (verbatim) — owned primarily by DEV-004
- No unknown district names after normalization.
- No duplicated district-time-vehicle key unless explicitly justified.
- Numeric fields contain valid ranges.
- Observation years match source tables.
- Missing values are reported, not silently replaced.
- source_id exists for every processed row.

### 26.2 Model tests (verbatim) — owned primarily by DEV-008/DEV-009/DEV-010
- Model receives the expected feature columns and order.
- No future-period feature leakage.
- Saved model reloads and produces the same prediction shape.
- Predictions checked for impossible values when the target is non-negative.
- SHAP output aligns with the model feature schema.

### 26.3 Dashboard tests (verbatim) — owned primarily by DEV-011/DEV-012/DEV-013
- Filters correctly update all panels.
- Unsupported SBERT queries produce a safe fallback rather than a wrong category.
- Missing-period data displays a clear message.
- Ranking table and map use the same prediction values.
- Model limitation text is visible to the user.

## Business Rules
- Tests are written **incrementally alongside** the spec that produces the behavior being tested, not deferred to a single end-of-project pass (DEV-PLAN.md Section 5).
- A `TODO.md` item may only be checked off once its corresponding test(s) here pass (MASTER_PROMPT.md Stage 6).
- No test may be weakened/skipped to make a feature appear complete — if a test can't pass, the underlying implementation is not done.

## Data Requirements
N/A (this spec organizes tests, it doesn't introduce new data).

## Database/Schema Changes
None.

## API Requirements
None.

## Backend Behavior
Tests live under `tests/`, organized to mirror `src/` structure (e.g. `tests/test_data.py`, `tests/test_features.py`, `tests/test_models.py`, `tests/test_explainability.py`, `tests/test_nlp.py`, `tests/test_recommendation.py`, `tests/test_dashboard.py`), using a standard Python test runner (e.g. pytest — record as ADR in REF-009 if a specific framework choice needs justification, otherwise pytest is the industry-standard default consistent with the stack).

## Frontend Behavior
N/A (dashboard tests exercise dashboard logic/behavior, not visual UI, unless a lightweight UI-interaction test framework is later justified and logged as an ADR).

## UI States
N/A.

## Validation
Each test in Sections 26.1–26.3 above must be implemented as an automated, repeatable test — not a manual checklist item performed once and forgotten.

## Permissions
N/A.

## Error Cases
N/A (this spec's "error cases" are, by design, what the tests themselves check for).

## Edge Cases
N/A.

## Security Considerations
Tests must not use real personal data, even inadvertently, in fixtures (consistent with REF-005).

## Dependencies
- DEV-004 (Data Cleaning), DEV-005 (Feature Engineering — leakage test), DEV-008 (XGBoost), DEV-009 (LSTM), DEV-010 (SHAP), DEV-011 (SBERT), DEV-012 (Ranking Engine), DEV-013 (Dashboard)

## Testing Requirements
This spec *is* the testing requirements consolidation; see Functional Requirements above.

## Acceptance Criteria
- [x] All Section 26.1 data tests implemented and passing — `tests/test_data_cleaning.py` (8 tests) covers all six items verbatim; `tests/test_clean_dataset_deduplicate.py` (5 tests, added during this audit) directly verifies the "no duplicated key unless explicitly justified" dedup rule itself (previously only checked at the end-to-end output level).
- [x] All Section 26.2 model tests implemented and passing — feature columns/order (`test_xgboost_model.py`, `test_shap_explainer.py`), no future-period leakage (`test_feature_engineering.py`, structural guard in `test_xgboost_model.py`), save/reload consistency (`test_xgboost_model.py`), impossible-value checking (`test_xgboost_model.py`, `test_baseline_model.py`, new negative-band test in `test_ranking_engine.py`), SHAP-schema alignment (`test_shap_explainer.py`).
- [x] All Section 26.3 dashboard tests implemented and passing — `tests/test_dashboard_app.py` (13 tests via Streamlit's real `AppTest` harness): filters update all panels, unsupported/ambiguous SBERT fallback, missing-period clear message, table/map identical values, disclaimer visibility.
- [x] Test suite runnable as a single command (e.g. `pytest tests/`) — **191/191 passing**.
- [x] Test suite organized to mirror `src/` module structure — one or more files per `src/` package (`test_data_*` / `test_clean_dataset_*` → `src/data`, `test_feature_engineering` / `test_dataset_assembly` → `src/features`, `test_baseline_model` / `test_xgboost_model` / `test_lstm_model` → `src/models`, `test_shap_explainer` → `src/explainability`, `test_sbert_router` → `src/nlp`, `test_ranking_engine` → `src/recommendation`, `test_experiment_tracking` / `test_model_evaluation` → `src/evaluation`, `test_dashboard_*` → `dashboard/`); split into multiple granular files per package rather than one file per package (the spec's own "e.g." wording), which was a deliberate, better-practice choice, not a deviation.

## Audit performed (this phase)

A full audit of the existing suite against every DEV spec's Testing Requirements/Section 26 references found it substantially complete, but surfaced six genuine issues, all fixed (not merely noted) — see TODO.md Phase 13 for the full list. Headline finding: `src/models/{baseline,xgboost_model,lstm_model}.py` and `src/evaluation/model_evaluation.py`'s `run()` functions hardcoded the real `mlruns/` MLflow store and, in three cases, real report/dataset file paths, with no way for a test to redirect them — every `pytest tests/` run was silently mutating production artifacts and appending duplicate MLflow run entries indefinitely (28 accumulated before the fix, 22 from one test file). Fixed by adding path-override parameters to all four `run()` functions and redirecting every affected test to `tmp_path`; verified `mlruns/` now stays at exactly 4 entries (one per model type) across repeated full-suite runs, and that real production files' modification times are unchanged by running the test suite.

Also found and fixed: a missing test file that a module's own docstring and the data source register claimed existed (`tests/test_district_geojson.py`), a dangling "(log as ADR)" reference in TODO.md with no corresponding REF-009 entry (retroactively logged as ADR-025), a foundational smoke test that hadn't been updated for DEV-014's new `src/evaluation` package, and a `pytestmark` scoping mistake caught in this session's own new test file before it shipped.

**Correction (2026-11-07, REF-009 ADR-035):** the isolation audit above missed one path: seven test modules were still rewriting `data/processed/modelling_base_2024.csv` and `reports/dmt_cross_validation.md` through `build()`, and three upload tests were writing into `app/static/images/mechanics/`. Both are now redirected to temporary folders, and checksums of all project files were compared before and after a full-suite run.

No test was weakened, skipped, or had its assertions loosened to obtain a green suite (Business Rule) — every change either added a missing test, fixed a genuine bug the tests exposed, or corrected test isolation without changing what is being verified.

## Dashboard QA (real, not just AppTest simulation)
In addition to the automated `AppTest`-based suite (`tests/test_dashboard_app.py`), a real `streamlit run dashboard/app.py` server process was started and confirmed healthy (`HTTP 200` on the root page, `ok` from `/_stcore/health`) before being stopped cleanly — consistent with the same check performed during DEV-013. This is a QA verification step, not new dashboard implementation logic (DEV-013 owns the dashboard itself).

## Definition of Done
All acceptance criteria met; the full test suite (191 tests) passes; every genuine gap found during the audit was fixed, not deferred; no `TODO.md` item is marked complete without a corresponding passing test where Section 26 specifies one.
