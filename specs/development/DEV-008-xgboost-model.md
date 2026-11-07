# DEV-008 — XGBoost Primary Prediction Model

## Specification ID
DEV-008

## Feature/Module Name
XGBoost Primary Prediction Model

## Purpose
Train, tune, and persist the primary tabular prediction model, evaluated with strict chronological validation, saved with its exact feature list and dataset version.

## Background/Context
Source doc Section 14 (XGBoost — Primary Tabular Prediction Model), Section 14.1 (Inputs), Section 14.2 (6-step training approach), Section 14.3 (Why XGBoost fits the project), Section 13 (priority: Core).

## Related Requirements
- FR-04 (train and load an XGBoost prediction model)
- Section 14, Section 23 (evaluation), Section 24 (model registry)
- REF-003 (ML Component Architecture — Why XGBoost, Section 4)

## Dataset v2 note
XGBoost on Dataset v2 is investigated in `src/models/ml_experiments_v2.py` (REF-009 ADR-040). The `src/models/xgboost_model.py` module described below still serves Dataset v1 and is unchanged.

## User Roles
None (backend/modelling spec).

## Preconditions
DEV-007 complete: baseline established on the same split.

## User Stories/Use Cases
- As the developer, I need a tuned XGBoost regressor that outperforms the baseline on the untouched test period, trained without leakage, so the model is defensible in the viva.
- As the developer, I need the final model saved with its exact feature list and dataset version, so predictions remain reproducible and traceable (Section 24).

## Functional Requirements

### 14.1 Inputs (verbatim, adapted)
- Lagged vehicle registrations.
- Vehicle population where available.
- Registration growth and rolling statistics.
- District population/density.
- Vehicle type.
- Time features.
- Lagged observed demand, if a real demand label exists (Preferred path only).

### 14.2 Training approach (6 steps, verbatim)
1. Create a chronological train/validation/test split. *(Done in DEV-006 — reused here, not recreated.)*
2. Train a simple baseline first. *(Done in DEV-007 — reused here for comparison.)*
3. Train an XGBoost regressor on the same target and time split.
4. Tune parameters (`n_estimators`, `learning_rate`, `max_depth`, `min_child_weight`, `subsample`, `colsample_bytree`) using only training/validation periods.
5. Select the model using validation performance and report final performance on the untouched test period.
6. Save the final model together with the exact feature list and dataset version.

## Business Rules
- Hyperparameter tuning must never touch the test period (Section 14.2 step 4: "using only training/validation periods").
- Test-period metrics are reported once, after model selection — not used to pick hyperparameters (prevents test-set leakage via repeated tuning).
- Feature list used for training must come from `configs/feature_list.*` (DEV-005), not be hardcoded inline.

## Data Requirements
Input: frozen dataset + split (DEV-006) with DEV-005 engineered features. Output: trained model artifact + exact feature list + dataset version, persisted to `models/` (model registry, Section 24 — implemented fully in DEV-014, this spec produces the artifact DEV-014 registers).

## Database/Schema Changes
None beyond the model artifact file(s) under `models/`.

## API Requirements
None (unless a thin prediction function/API is introduced for the dashboard — optional, see CLAUDE.md Section 10; if added, log as ADR).

## Backend Behavior
- Training/tuning code lives in `src/models/xgboost_model.py` (or equivalent), separate from LSTM code (Maintainability NFR).
- Hyperparameters and search space are config-driven (`configs/`), not hardcoded.
- Random seed recorded for reproducibility (Section 22 Reproducibility NFR, Section 24).

## Frontend Behavior
N/A. (Dashboard forecast panel, DEV-013, consumes this model's predictions via DEV-012's ranking engine.)

## UI States
N/A.

## Validation
- Model receives the expected feature columns and order (Section 26.2 model test).
- No future-period feature leakage (reuses DEV-005's leakage guarantees; additionally verify the model's training call only sees train/validation rows during fitting/tuning).
- Saved model reloads and produces the same prediction shape (Section 26.2).
- Predictions checked for impossible values when the target is non-negative (Section 26.2) — e.g. reject/flag negative predicted registrations.

## Permissions
N/A.

## Error Cases
- Tuning search selects a degenerate model (e.g. all predictions identical) — flag and investigate rather than accepting silently; compare against baseline metrics to catch this.
- Model file fails to reload with the exact same feature schema — treat as a blocking error, not a warning.

## Edge Cases
- A vehicle_type or district with very few training rows — model may perform poorly for that slice; this must be visible in per-slice evaluation (DEV-014), not hidden behind an aggregate metric.

## Security Considerations
None beyond general data-governance rules already enforced upstream.

## Dependencies
- DEV-007 (Baseline Forecasting Model)
- DEV-006 (Modelling Dataset Assembly & Target Definition)
- REF-003 (ML Component Architecture Reference)

## Testing Requirements
- Section 26.2 model tests (feature columns/order, no leakage, reload consistency, non-negative-value check).
- Comparison test: XGBoost test-period metrics vs. DEV-007 baseline metrics, both computed identically.

## Acceptance Criteria
- [x] XGBoost regressor trained on the DEV-006 chronological split — `src/models/xgboost_model.py::run()`; reads `split` directly from `data/processed/modelling_dataset_v1.csv` (102 train / 49 validation / 47 test rows), no re-derivation.
- [x] Hyperparameters tuned using only training/validation periods — full 972-combination grid search over `configs/model_params.yaml`'s `xgboost.tuning_search_space`, fit on `train` only, scored on `validation` only; `tune_hyperparameters()` structurally has no test-period parameter (REF-009 ADR-012).
- [x] Final model selected on validation performance; test-period performance reported once — selected on validation MAE (best: `n_estimators=500, learning_rate=0.01, max_depth=5, min_child_weight=3, subsample=1.0, colsample_bytree=1.0`, validation MAE 125.2, RMSE 218.5, R² 0.37); refit on train+validation, then evaluated exactly once on test: MAE 312.9, RMSE 696.8, R² 0.14 (47/47 rows scored, full coverage).
- [x] Model saved with exact feature list and dataset version — `models/xgboost_v1/model.json` (native XGBoost format), `models/xgboost_v1/onehot_encoder.joblib` (fitted `vehicle_type` preprocessing object), `models/xgboost_v1/metadata.json` (11 feature columns in fixed order, `excluded_all_null_features`, dataset_version `modelling_dataset_v1_1310eaead622`, random_seed 42, full tuning/selection/evaluation record).
- [x] Model outperforms (or is honestly reported not to outperform) the DEV-007 baseline on the test period — **honestly reported: does NOT outperform.** `baseline_previous_period` scores test MAE 230.5 (42/47 rows scored) vs. XGBoost's matched-subset MAE 306.4 (same 42 rows) / full-coverage MAE 312.9 (all 47 rows). Root cause investigated and documented as REF-006 Section 5.3, tied to the same real 2020-2022 registration collapse (Section 5.2) combined with the very small (102-row) training set — not an implementation defect. XGBoost remains the production model per REF-003 Section 13 (documented "Core" component), with this limitation disclosed rather than hidden.
- [x] Section 26.2 model tests pass — `tests/test_xgboost_model.py`, 14/14 passing: feature columns/order (fixed, config-driven), no-leakage-by-construction (tuning function signature has no test-period parameter), save/reload produces identical predictions, reload raises on feature-schema mismatch, negative-prediction diagnostic (1/47 test predictions negative, disclosed not clipped — see module docstring), baseline comparison computed identically via the shared `evaluate_predictions()`.

## Implementation decisions logged as ADRs
- REF-009 ADR-011: all-null feature exclusion (auto-detected, not hardcoded), one-hot encoding of `vehicle_type` for a single combined model, model artifact folder layout.
- REF-009 ADR-012: grid-search tuning methodology, validation-MAE selection metric (chosen over RMSE/R² due to outlier domination — REF-006 Section 5.2), refit-on-train+validation before the one-shot test evaluation.

## Definition of Done
All acceptance criteria met; the trained XGBoost model (`models/xgboost_v1/`), its exact feature list, and its dataset version are ready to be consumed by DEV-010 (SHAP), DEV-011 (SBERT routing target), DEV-012 (Ranking), and registered by DEV-014. `tests/test_xgboost_model.py` (14/14) is part of the automated test suite and passes; full project test suite is 68/68 passing. The honest non-improvement over the DEV-007 baseline is documented in REF-006 Section 5.3 for DEV-014/DEV-016 to carry forward, not silently dropped.
