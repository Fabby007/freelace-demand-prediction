# DEV-005 — Feature Engineering Pipeline

## Specification ID
DEV-005

## Feature/Module Name
Feature Engineering Pipeline

## Purpose
Convert the cleaned processed dataset into model-ready features representing recent level, direction, and momentum, under a strict, testable no-leakage rule.

## Background/Context
Source doc Section 12 (Feature Engineering) and Section 12.1 (Leakage rule). This is one of the two specs (alongside DEV-006/DEV-008/DEV-009's split logic) most responsible for scientific validity — a leakage bug here silently inflates every downstream metric.

## Related Requirements
- FR-03 (create lag, growth and trend features without future leakage)
- Section 12, Section 12.1
- Hard Rule: no future-period data used to predict an earlier period (MASTER_PROMPT.md Section 0)

## User Roles
None (backend pipeline).

## Preconditions
DEV-004 complete: clean processed dataset exists conforming to REF-001.

## User Stories/Use Cases
- As the developer, I need lag/growth/rolling/time/context/intensity features computed per district/vehicle-category series so the model has signal about recent level and momentum.
- As the developer, I need an automated, unit-tested leakage check so that no feature for period t ever uses data from period ≥ t.

## Functional Requirements
Implements the Section 12 feature groups:
1. **Current/lagged level:** `new_registrations_lag_1` (i.e. `reg_lag_1`), `reg_lag_2`, `vehicle_population` (as-of period).
2. **Growth:** `reg_growth_pct` (year-on-year growth), `change_from_lag_2`.
3. **Rolling trend:** `rolling_mean_3`, `rolling_std_3` (computed using only periods strictly before the target period within each district/vehicle-category series).
4. **Time features:** `year`, `month` (if monthly data exists), `quarter`, cyclic month `sin`/`cos` encoding when monthly data exists.
5. **District context:** `population`, `population_density`.
6. **Vehicle intensity:** `vehicles_per_1000_people` (registrations or population normalized by district population).
7. **Category:** `vehicle_type` retained as a feature (categorical), enabling either one combined model or separate models per vehicle type — decision recorded as an ADR once made if it deviates from a single combined model.
8. **Target lags:** `demand_lag_1` — only if a real demand target exists (Preferred path per DEV-002's Target Decision Record); uses recent observed demand without leaking future values.

## Business Rules — Leakage rule (Section 12.1, verbatim)
"When predicting year t, every feature must be computable using information available before year t. A feature calculated using year t+1 or the final dataset average would create leakage and make the model appear more accurate than it really is."

Concretely:
- Lag/rolling features must be computed strictly within-group (per district × vehicle_type), sorted chronologically, using `shift`/window operations that only look backward.
- No feature may be derived from a full-dataset (all years) aggregate, mean, or normalization computed before the chronological split — such statistics must be fit on training-period data only if used at all (this rule is fully enforced together with DEV-006's split, but feature *construction* here must already be leakage-safe on a per-row basis regardless of where the split falls).
- Global/full-series rolling windows that include future periods relative to the row being computed are forbidden.

## Data Requirements
Input: `data/processed/` dataset from DEV-004 (REF-001 schema). Output: same dataset extended with engineered columns; the definitive engineered feature list is appended to REF-001 Section 6 once finalized here (not duplicated elsewhere).

## Database/Schema Changes
Extends the processed dataset with the engineered columns listed above (appended to REF-001, per REF-001 Section 6).

## API Requirements
None.

## Backend Behavior
Feature engineering logic lives in `src/features/`, one shared module (not duplicated per district/vehicle type). Feature list itself is config-driven (`configs/feature_list.*`), not hardcoded, per CLAUDE.md coding standards — this is also the config scaffold created in DEV-001 and populated here.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
- Automated leakage unit test: for a synthetic/sample series, assert that a feature computed for period t is unaffected by mutating data at period ≥ t (Section 26.2-adjacent, implemented under DEV-015 but authored here since it's feature-specific).
- Spot-check that lag/rolling values match manual calculation for a sample district/vehicle series.

## Permissions
N/A.

## Error Cases
- A district/vehicle series too short to compute `reg_lag_2` or `rolling_mean_3` (e.g. only 1–2 observed years) — leave those features as missing for that row rather than fabricating a value; do not drop the row unless the downstream model requires complete cases (a decision to drop must be documented, not silent).

## Edge Cases
- Monthly data available for some districts but not others — per Section 9, prefer a clean yearly dataset over pretending to have monthly detail; cyclic month features are only computed where monthly granularity is genuinely present and consistent (this granularity decision is finalized by DEV-006, but DEV-005 must not fabricate a `month` value where the source has none).
- First observed year in a series has no prior period — lag/growth features are legitimately null there, not zero.

## Security Considerations
None beyond the general no-fabrication and provenance rules already enforced upstream.

## Dependencies
- DEV-004 (Data Cleaning, Normalization & Validation)
- REF-001 (Data Dictionary)

## Testing Requirements
- Leakage unit test (see Validation).
- Feature-value correctness test against a hand-computed sample.
- Config-driven feature list test: model training code reads the feature list from `configs/`, not a hardcoded list.

## Acceptance Criteria
- [x] All Section 12 feature groups implemented (lag, growth, rolling, time, district context, vehicle intensity, category, target lag if applicable) — `src/features/build_features.py`. Groups 1-3 (lag/growth/rolling) and 7 (category, pass-through) are populated with real values. Groups 4 (time/cyclic), 5 (district context), and 6 (vehicle intensity) are implemented and correct but are honestly null for every row in the current dataset version: the dataset is yearly-only (no `month`, group 4) and `population` has not yet been acquired by DEV-003 (groups 5-6) — both are "Recommended"/"Optional" per REF-001, not "Required", and are documented gaps, not silent ones (see `data/source_register.csv` and the module docstring). Group 8 (`demand_lag_1`) is deliberately not produced — Fallback path, no real demand series exists (DEV-002 Target Decision Record); `build_features()` raises `NotImplementedError` with clear instructions if `configs/target_config.yaml` is ever changed to a real-demand-target without this being implemented, so the omission cannot silently go stale.
- [x] Leakage unit test passes: no feature for period t uses data from period ≥ t — `tests/test_feature_engineering.py::test_no_leakage_mutating_future_period_does_not_change_past_features` and `::test_leakage_across_multiple_groups_independent`, both passing.
- [x] Feature list is config-driven and documented in `configs/feature_list.*` and REF-001 Section 6 — `configs/feature_list.yaml` populated with the real engineered/provenance/data-quality column lists; kept in sync with the code by `tests/test_feature_engineering.py::test_engineered_columns_match_config`; REF-001 Section 6 updated with the finalized column definitions.
- [x] Short-series edge cases produce null features, not fabricated values — `tests/test_feature_engineering.py::test_short_series_produces_null_not_fabricated_values`.

Additional tests beyond the spec's minimum, also passing: hand-computed value regression test against the real Kandy Motorcycle series (`test_kandy_motorcycle_hand_computed_values`), yearly-only-dataset null-not-fabricated check (`test_yearly_only_dataset_leaves_month_features_null_not_fabricated`), `demand_lag_1` absence check (`test_demand_lag_1_not_present_on_fallback_path`).

## Definition of Done
All acceptance criteria met; the feature-engineered dataset (`data/processed/modelling_features_2024.csv`, 375 rows x 28 columns) is ready for DEV-006 dataset assembly and splitting; leakage tests are part of the automated test suite (`tests/test_feature_engineering.py`, 8/8 passing) and pass; full project test suite is 30/30 passing.
