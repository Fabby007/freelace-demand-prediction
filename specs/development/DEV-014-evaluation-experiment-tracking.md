# DEV-014 — Model Evaluation & Experiment Tracking

## Specification ID
DEV-014

## Feature/Module Name
Model Evaluation & Experiment Tracking

## Purpose
Establish rigorous, time-aware evaluation of all models against baselines, and track experiments/dataset versions/artifacts so results are reproducible and defensible.

## Background/Context
Source doc Section 23 (Model Evaluation Strategy), Section 24 (Experiment Tracking, Reproducibility and Version Control).

## Related Requirements
- Section 23 (23.1–23.5), Section 24
- REF-004 (Reproducibility NFR), REF-008 (MLflow/W&B stack choice)

## User Roles
None (backend/reporting spec).

## Preconditions
DEV-007 (Baseline) and DEV-008 (XGBoost) complete; DEV-009 (LSTM) complete or its conditionality assessment documented.

## User Stories/Use Cases
- As the developer, I need regression and (where possible) ranking metrics computed identically across baseline/XGBoost/LSTM so I can honestly report which model wins and by how much.
- As the developer, I need every training run logged (parameters, metrics, dataset version, artifacts) so any result can be reproduced or audited later (Section 24).

## Functional Requirements

### 23.1 Baselines
Reuse DEV-007's previous-period, moving-average, and (where appropriate) simple linear regression baselines "to demonstrate whether the ML model adds predictive value."

### 23.2 Regression metrics
- MAE (average absolute prediction error).
- RMSE (penalises larger errors more strongly).
- R² (proportion of target variance explained, interpreted carefully on small datasets — do not over-claim R² significance on a small sample).

### 23.3 Ranking metrics (where a real target is available)
- Spearman rank correlation.
- Top-k overlap: whether true highest-demand districts appear in the predicted top group.
- Only computable on the Preferred target path (DEV-002) where a genuine ground-truth ranking exists; on the Fallback/proxy path, note explicitly that ranking metrics are evaluated against the proxy target, not real demand.

### 23.4 Time-aware validation
- Reuses DEV-006's chronological split — "random train/test splitting is not appropriate for predicting future values."
- Districts grouped within each time period so the model is tested on future periods, not random historical rows.

### 23.5 LSTM evaluation
- LSTM (DEV-009, if built) evaluated on the same target and comparable future periods as XGBoost.
- Report whether the additional complexity produces a meaningful improvement; "if not, XGBoost remains the recommended production model" — this conclusion must be stated plainly, not soft-pedaled.

### Section 24 — Experiment tracking
- **GitHub:** source code, extraction scripts, notebooks, dashboard code, documentation (ongoing, via DEV-001's repo).
- **MLflow or Weights & Biases:** log model parameters, metrics, dataset version, artefacts, and selected model runs for every training run (baseline, XGBoost, LSTM). The MLflow-vs-W&B choice is recorded as an ADR in REF-009 if not already decided.
- **requirements.txt/pyproject.toml:** exact dependencies (DEV-001/DEV-017).
- **Configuration files:** feature lists, target name, date split, model parameters (DEV-005/DEV-006/DEV-008/DEV-009's `configs/` outputs).
- **Data source register:** source URL, date retrieved, publication/table reference, licence/usage notes (DEV-002).
- **Random seeds:** recorded where supported, for every stochastic training run.
- **Model registry folder:** final model, preprocessing objects, feature schema, evaluation report — populated here as the consolidated artifact set under `models/`.

## Business Rules
- Test-period metrics must be computed once per model, after model/hyperparameter selection is finalized (no repeated test-set peeking — reiterates DEV-008's rule).
- LSTM must not be declared superior to XGBoost without a like-for-like comparison on identical held-out periods (Section 23.5).
- Ranking metrics must never be computed against a fabricated ground-truth ranking — only against the real or proxy `target_value` actually used for training (Hard Rule).

## Data Requirements
Input: DEV-007/DEV-008/DEV-009 predictions and the DEV-006 test-period ground truth. Output: an evaluation report (e.g. `reports/model_evaluation.md` or `.json`) comparing all models, plus MLflow/W&B run logs.

## Database/Schema Changes
None beyond the model registry folder structure under `models/` (model artifact + preprocessing objects + feature schema + evaluation report, per Section 24).

## API Requirements
None.

## Backend Behavior
Evaluation/tracking code lives alongside `src/models/` or in a small `src/evaluation/`-style module if warranted (log as ADR if a new top-level module beyond Appendix B's list is introduced) — otherwise implemented as scripts invoked after each training run.

## Frontend Behavior
N/A. (DEV-013's data-source/model-version panel surfaces summary info from here.)

## UI States
N/A.

## Validation
- Metrics computed identically (same test rows, same metric implementation) across baseline/XGBoost/LSTM for fair comparison.
- Every training run has a corresponding MLflow/W&B log entry with parameters, metrics, dataset version, and artifact reference.

## Permissions
N/A.

## Error Cases
- Experiment-tracking backend (MLflow/W&B) unavailable at run time — training must not silently proceed unlogged; either retry, fall back to a local log file, or clearly flag the run as untracked (do not present an untracked run's results as equally reproducible).

## Edge Cases
- Very small test set (few rows) — R² and ranking metrics may be unstable; this must be stated as a caveat in the evaluation report (REF-006 "Small dataset / many features" risk), not hidden.

## Security Considerations
None beyond general provenance rules; W&B/MLflow cloud usage (if any) must not upload personal data (there is none in this dataset per REF-005).

## Dependencies
- DEV-007 (Baseline), DEV-008 (XGBoost), DEV-009 (LSTM, where applicable)
- REF-004 (NFRs — Reproducibility), REF-008 (Technology Stack)

## Testing Requirements
- Metric-computation correctness test against a hand-computed sample.
- Test that an MLflow/W&B run log exists for every completed training run.

## Acceptance Criteria
- [x] Regression metrics (MAE, RMSE, R²) computed for baseline, XGBoost, and LSTM (if built) on identical test periods — `src/evaluation/model_evaluation.py::build_regression_comparison_table()`; baseline metrics reused verbatim from `reports/baseline_metrics.json` (DEV-007), XGBoost metrics reused verbatim from `models/xgboost_v1/metadata.json` (DEV-008), both computed via the identical `evaluate_predictions()`-shaped schema (n_total/n_scored/mae/rmse/r2/n_negative_predictions) so the comparison is apples-to-apples by construction. LSTM: no metrics table row (never built — see below), stated explicitly rather than omitted silently.
- [x] Ranking metrics (Spearman, top-k overlap) computed where a real/proxy target supports it — `compute_ranking_metrics()`, per vehicle_type, on the real XGBoost test-set predictions vs. the real (proxy) `target_value`. Explicitly labelled throughout as evaluated against the Fallback-path proxy target, never presented as a real-demand ranking (Business Rule). Real result: Motorcycle ρ=0.705 (p=0.001, n=19), Car ρ=0.228 (p=0.334, n=20), Three-wheeler ρ=0.048 (p=0.910, n=8) — a genuine, disclosed finding (REF-006 Section 5.6), not hidden.
- [x] Time-aware validation methodology documented and confirmed (no random splitting) — restated in the evaluation report referencing REF-009 ADR-008's exact boundaries; verified by test that the real test-split row count (47) is unchanged from DEV-006's frozen split.
- [x] LSTM vs. XGBoost comparison completed and a production-model recommendation stated plainly — **XGBoost**, stated plainly: LSTM was assessed and skipped (DEV-009, REF-009 ADR-013) on categorical data-density grounds (0/75 series meet the minimum lookback), not a resourcing shortfall — the report is explicit that this is "not a comparison between two trained models where XGBoost happened to win."
- [x] MLflow or W&B logging wired into all training scripts — `src/evaluation/experiment_tracking.py::log_run()`, called from `src/models/baseline.py`, `src/models/xgboost_model.py`, and `src/models/lstm_model.py`'s `run()` functions (REF-009 ADR-022: MLflow, local file store), plus from `model_evaluation.py` itself. Verified: rerunning all three training scripts reproduced identical results to their original (pre-DEV-014) outputs (same selected hyperparameters, same test MAE) — logging was added without altering any prior result.
- [x] Model registry populated: model, preprocessing objects, feature schema, evaluation report — `models/xgboost_v1/{model.json, onehot_encoder.joblib, metadata.json (feature schema), evaluation_report.{json,md}}`.

## Honest headline finding (stated plainly, not softened)
On the untouched test period, `baseline_previous_period` (MAE 230.5) outperforms tuned XGBoost (matched-subset MAE 306.4 on the identical 42 rows, full-coverage MAE 312.9 on all 47). This is reported as the report's own headline line, not buried — see `reports/model_evaluation.md`.

## New module and dependency decisions logged as ADRs
- REF-009 ADR-022: MLflow (not W&B) with a local file-based tracking store — formalizes the choice `requirements.txt`/ADR-002/ADR-004 had already implicitly made since DEV-001.
- REF-009 ADR-023: new `src/evaluation/` module (`experiment_tracking.py` + `model_evaluation.py`), shared by DEV-007/DEV-008/DEV-009's training scripts rather than duplicated per module.

## Testing Requirements — completed
- Metric-computation correctness test against a hand-computed sample — `tests/test_model_evaluation.py`: perfect correlation/anti-correlation and a hand-computed partial top-k overlap case, all verified against manually-derived expected values.
- Test that an MLflow/W&B run log exists for every completed training run — `tests/test_experiment_tracking.py`; real `mlruns/` inspection confirmed 4 run types present (`baselines`, `xgboost_v1`, `lstm_conditionality_assessment`, `model_evaluation`) after rerunning all training scripts.
- No re-tuning against the test set — `tests/test_model_evaluation.py::test_run_does_not_call_tune_hyperparameters` (patches DEV-008's tuning function and confirms it is never called by the evaluation report).
- Error Case (tracking backend unavailable) — `tests/test_experiment_tracking.py::test_log_run_falls_back_to_local_json_when_mlflow_unavailable`, `::test_log_run_never_raises_on_backend_failure`.
- Full suite: `tests/test_experiment_tracking.py` (5/5) + `tests/test_model_evaluation.py` (14/14) = 19/19 new tests passing; full project test suite 174/174 passing.

## Definition of Done
All acceptance criteria met; `reports/model_evaluation.{json,md}` (also copied into `models/xgboost_v1/`) compares all models honestly, including the finding that XGBoost does not beat the simplest baseline and that LSTM was never built; every model in the registry (`models/xgboost_v1/`) is reproducible from its logged parameters (`metadata.json`, MLflow), dataset version, and seed (42).
