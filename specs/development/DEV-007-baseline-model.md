# DEV-007 — Baseline Forecasting Model

## Specification ID
DEV-007

## Feature/Module Name
Baseline Forecasting Model

## Purpose
Implement simple previous-period and moving-average (and, where appropriate, simple linear regression) baselines so the value added by XGBoost/LSTM can be demonstrated rather than assumed.

## Background/Context
Source doc Section 13 (baseline is "Required" priority), Section 14.2 step 2 ("Train a simple baseline first"), Section 23.1 (Baselines).

## Related Requirements
- Section 13, Section 14.2, Section 23.1
- REF-003 (ML Component Architecture)

## User Roles
None (backend/modelling spec).

## Preconditions
DEV-006 complete: frozen, versioned dataset and chronological split exist.

## User Stories/Use Cases
- As the developer, I need a baseline forecast so I can prove (not assume) that XGBoost adds predictive value over simple heuristics (Section 23.1).

## Functional Requirements
1. Implement **previous-period baseline**: predict `target_value(t)` = `target_value(t-1)` (i.e. `reg_lag_1` or the equivalent target lag) for each district/vehicle-category series.
2. Implement **moving-average baseline**: predict `target_value(t)` = rolling mean of the previous N periods (reuse `rolling_mean_3` from DEV-005 where available, or compute directly).
3. Implement **simple linear regression baseline** where appropriate (Section 23.1) — e.g. a linear trend fit per district/vehicle series on training-period data only.
4. Evaluate all baselines using the same chronological split and metrics that will later be used for XGBoost/LSTM (MAE, RMSE, R² — Section 23.2), so the comparison in DEV-014 is apples-to-apples.
5. Persist baseline predictions/metrics for reuse in DEV-014's comparison report.

## Business Rules
- Baselines must be evaluated on the exact same target and time split as XGBoost (Section 14.2 step 2 requires "same target and time split").
- No baseline may use future-period information (same leakage rule as DEV-005/DEV-006).

## Data Requirements
Input: frozen dataset + split from DEV-006. Output: baseline prediction columns/artifacts and baseline metrics for the validation/test periods.

## Database/Schema Changes
None beyond a baseline predictions/metrics artifact (e.g. `reports/baseline_metrics.json` or similar, under `reports/`).

## API Requirements
None.

## Backend Behavior
Baseline logic lives in `src/models/` alongside XGBoost/LSTM training code (shared module structure, not duplicated).

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
- Baseline predictions computed only from information available before the prediction period (no leakage).
- Metrics computed on validation/test periods only, matching DEV-008's evaluation periods exactly.

## Permissions
N/A.

## Error Cases
- A series too short to compute a moving average (e.g. single observation) — baseline prediction is null for that row; do not fabricate a value.

## Edge Cases
- A district/vehicle series with a genuine zero registration period — baseline must treat this as a valid observed value, not as missing.

## Security Considerations
None.

## Dependencies
- DEV-006 (Modelling Dataset Assembly & Target Definition)

## Testing Requirements
- Baseline prediction correctness test against a hand-computed sample.
- Baseline evaluated on identical validation/test periods as DEV-008.

## Acceptance Criteria
- [x] Previous-period baseline implemented and evaluated — `src/models/baseline.py::add_previous_period_baseline()`; `target_value(t) = target_value(t-1)` per district x vehicle_type series (equivalently, the row's own current-period `new_registrations` - see module docstring). Test MAE 230.5, RMSE 555.8, R² 0.49 (47 rows, 42 scored); validation MAE 130.8, RMSE 442.6, R² -1.40 (49 rows, 43 scored).
- [x] Moving-average baseline implemented and evaluated — `add_moving_average_baseline()`; reuses DEV-005's `rolling_mean_3` directly (config window matches), recomputes if `configs/model_params.yaml`'s window ever diverges. Test MAE 2714.6, RMSE 4641.0, R² -35.8; validation MAE 4161.2, RMSE 7293.6, R² -669.9.
- [x] Simple linear regression baseline implemented where appropriate — `add_linear_trend_baseline()`; per-series fit on `train`-split rows only, extrapolated to `target_year`. Implemented as specified, but disclosed as statistically weak on this dataset (only 2 training years/series; 60% of series fittable at all; 82-93% of its scored predictions are physically impossible negative values) — see REF-009 ADR-010 for the full appropriateness analysis and the decision to disclose rather than omit or clip. Test MAE 5576.9, RMSE 10484.8, R² -172.5; validation MAE 2690.1, RMSE 5151.2, R² -305.2.
- [x] All baselines evaluated on the same chronological split/target as will be used for XGBoost — `evaluate_baselines()` reads `split` directly off the DEV-006 frozen dataset (`data/processed/modelling_dataset_v1.csv`); no re-derivation, no re-splitting. `tests/test_baseline_model.py::test_evaluate_baselines_uses_dev006_split_labels_only` confirms `n_total` per split matches the DEV-006 split counts exactly (validation=49, test=47).
- [x] Baseline metrics persisted for DEV-014's comparison report — `reports/baseline_metrics.json` (MAE/RMSE/R²/coverage/`n_negative_predictions` per split per baseline, tagged with the DEV-006 `dataset_version`) and `data/processed/baseline_predictions_v1.csv` (per-row predictions, kept separate from the frozen `modelling_dataset_v1.csv` so the frozen artifact itself is never mutated post-freeze).

All three baselines are real, honestly-scored, and reveal a genuine finding, not a modelling artifact: `baseline_previous_period` (simple persistence) clearly outperforms both `baseline_moving_average` and `baseline_linear_trend` by roughly 15-25x on MAE, because Sri Lanka's real 2020-2022 vehicle-registration collapse (newly documented as REF-006 Section 5.2) breaks any baseline that assumes continuity from pre-2021 training years - persistence is comparatively robust because it only ever carries forward the single most recent actual value.

## Definition of Done
All acceptance criteria met; baseline metrics (`reports/baseline_metrics.json`) and predictions (`data/processed/baseline_predictions_v1.csv`) exist and are ready to be compared against XGBoost (DEV-008) and, if built, LSTM (DEV-009) results in DEV-014; `tests/test_baseline_model.py` (12/12) is part of the automated test suite and passes; full project test suite is 54/54 passing.
