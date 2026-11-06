# DEV-010 — SHAP Explainability Module

## Specification ID
DEV-010

## Feature/Module Name
SHAP Explainability Module

## Purpose
Provide global and per-district local SHAP explanations for the production prediction model (XGBoost, and LSTM if it becomes production) so every ranked recommendation is backed by a model-based explanation, per the project's non-negotiable explainability rule.

## Background/Context
Source doc Section 17 (SHAP — Model Explainability), Section 17.1 (global), Section 17.2 (local), Section 17.3 (viva value). MASTER_PROMPT.md Section 0: "Every top-ranked district recommendation shown by the system must be accompanied by a SHAP-based explanation and the standard limitation disclaimer. This is non-negotiable."

## Related Requirements
- FR-06 (calculate SHAP explanations for XGBoost predictions)
- Section 17
- REF-003 (Why SHAP, Section 7)

## User Roles
None (backend module; output consumed by DEV-012 and displayed by DEV-013).

## Preconditions
DEV-008 complete: trained XGBoost model with a fixed feature schema exists.

## User Stories/Use Cases
- As the developer, I need a global SHAP summary across the test set so I can report which features are genuinely most influential (Section 17.1) — not assumed in advance.
- As the developer, I need per-district local SHAP contributions so each ranked recommendation can state its top positive/negative factors (Section 17.2), feeding DEV-012's ranking output and DEV-013's explanation panel.

## Functional Requirements

### 17.1 Global explanations
- Compute a global SHAP summary across the full test dataset.
- Report which features are most influential **as found by the trained model** — the source doc explicitly warns the actual result "must come from the trained model, not be assumed in advance" (e.g. do not pre-assume lagged registrations will dominate).

### 17.2 Local explanations
- For a selected district (and vehicle type/period), compute and expose the largest positive and negative SHAP contributions.
- Output format supports a sentence like: "The prediction for Kandy is increased by strong recent motorcycle-registration growth and a high recent registration level, while another feature slightly reduces the score." — DEV-012 assembles this wording from the raw SHAP values; DEV-010 itself only computes and exposes the numeric contributions, it does not author the recommendation sentence.

## Business Rules
- SHAP explanations must never be replaced by an invented/narrative explanation not backed by actual SHAP values (Section 18: "must not invent narrative explanations unsupported by features/SHAP values" — applies at the DEV-012 consumption point, but DEV-010 must expose sufficiently granular, faithful values to make that possible).
- SHAP must be computed against the exact feature schema the model was trained on (Section 26.2: "SHAP output aligns with the model feature schema").

## Data Requirements
Input: trained model (DEV-008) + its exact feature list/schema + the dataset rows to explain (test set for global; a specific district/period row for local). Output: SHAP value arrays/summary artifacts consumable by DEV-012.

## Database/Schema Changes
None beyond a SHAP output artifact (e.g. cached SHAP values per row, to avoid recomputing on every dashboard interaction — implementation detail, log as ADR if a caching layer is added).

## API Requirements
None (function-level module, called by DEV-012).

## Backend Behavior
SHAP logic lives in `src/explainability/` (separate module from `src/models/`, per Maintainability NFR and MASTER_PROMPT.md Section 5's instruction not to merge SHAP and SBERT or SHAP and modelling code).

## Frontend Behavior
N/A directly — DEV-013's SHAP explanation panel renders DEV-010's output (via DEV-012).

## UI States
N/A (owned by DEV-013).

## Validation
- SHAP output aligns with the model's feature schema (Section 26.2) — same feature names/order as training.
- Global summary is computed from the trained model's actual behavior, not hardcoded/assumed feature importances.

## Permissions
N/A.

## Error Cases
- A requested district/period row that the model was never meaningfully trained/evaluated on (e.g. sparse data) — local SHAP can still be computed but must be paired with the limitation disclaimer (REF-005/REF-007) rather than presented with unwarranted confidence.

## Edge Cases
- A feature with near-zero global importance for a specific local prediction — still returned in the raw contribution set; DEV-012 decides how many top factors to surface, DEV-010 doesn't truncate silently.

## Security Considerations
None.

## Dependencies
- DEV-008 (XGBoost Primary Prediction Model)
- REF-003 (ML Component Architecture Reference)

## Testing Requirements
- Section 26.2 test: "SHAP output aligns with the model feature schema."
- Sanity test: sum of local SHAP contributions plus base value approximates the model's raw prediction for that row (standard SHAP consistency check).

## Acceptance Criteria
- [x] Global SHAP summary computed across the test set — `src/explainability/shap_explainer.py::run()`, `shap.TreeExplainer` against the saved DEV-008 model, all 47 test rows; persisted to `reports/shap_global_summary.json`. Top feature by mean(|SHAP|): `new_registrations` (814.2), followed by `reg_lag_1` (75.0), `vehicle_population` (40.2), `change_from_lag_2` (25.5), `reg_growth_pct` (21.0), `vehicle_type` (15.0), `rolling_mean_3` (11.0), `reg_lag_2` (0.52), `rolling_std_3` (0.39) — genuinely computed, not pre-assumed (consistent with DEV-007's finding that the previous-period/persistence baseline is strongest; the model leans on the same signal).
- [x] Per-district/period local SHAP contributions computed and exposed in a structured, consumable format — `explain_rows()`/`explain_row()`; each result carries `contributions` (human-readable, one entry per numeric feature plus one aggregated `vehicle_type` entry, sorted descending) and `raw_contributions` (every individual model-input column including the 3 one-hot dummies, nothing truncated per Edge Case). Persisted for the full test set to `data/processed/shap_local_explanations_test_v1.csv`; `explain_row()` additionally supports on-demand explanation of any (district, vehicle_type, year) row, including `unlabeled` (live-inference) rows, for DEV-012/DEV-013's runtime use.
- [x] SHAP output verified to align with the model's exact feature schema — `run()` explicitly re-derives the feature matrix via DEV-008's own `build_feature_matrix()` with the persisted encoder/`active_numeric_features` and raises if the result ever diverges from `metadata.json`'s `feature_columns`; `tests/test_shap_explainer.py::test_shap_values_shape_matches_feature_schema` and `::test_run_raises_if_rebuilt_features_diverge_from_metadata`.
- [x] No hardcoded/assumed feature-importance ordering — output reflects the actual trained model — confirmed by a genuine, non-obvious finding: the trained model's boosted trees never split on `vehicle_type_Car` or `vehicle_type_Three-wheeler` at all (0.0 SHAP importance for both, cross-checked against the booster's own `get_score()`), relying on `vehicle_type_Motorcycle` alone among the one-hot dummies to separate categories. This was discovered, not assumed, and is disclosed rather than smoothed over — see REF-009 ADR-014.

## Additional implementation decisions logged as ADRs
- REF-009 ADR-014: one-hot `vehicle_type` SHAP contributions are reported at two levels (aggregated single factor for readability, raw per-dummy for full transparency).
- REF-009 ADR-015: pinned `tf-keras==2.16.0` — `shap.TreeExplainer` construction was crashing whenever `transformers` (pulled in by `sentence-transformers`, DEV-011) was already imported in the same process, due to an unrelated internal isinstance probe hitting `tensorflow==2.16`'s Keras-3 default. Confirmed this is not a DEV-010-only issue: it reproduces in exactly the process shape DEV-013's dashboard requires (SHAP + SBERT loaded together), so it was fixed at the dependency level now.

## Testing Requirements — completed
- Section 26.2 test: "SHAP output aligns with the model feature schema" — see above.
- Sanity test: sum of local SHAP contributions plus base value approximates the model's raw prediction for that row — verified for every test-set row (`tests/test_shap_explainer.py::test_local_explanations_satisfy_additivity`, max reconstruction error < 0.001) and for the persisted CSV artifact (`::test_run_produces_additivity_consistent_csv`).
- Full suite: `tests/test_shap_explainer.py`, 11/11 passing; full project test suite 87/87 passing.

## Definition of Done
All acceptance criteria met; DEV-012 (Ranking Engine) can consume both global (`reports/shap_global_summary.json`) and local (`explain_row()`/`explain_rows()`, `data/processed/shap_local_explanations_test_v1.csv`) SHAP output to produce a per-district explanation, and DEV-013 can render it in the dashboard's SHAP panel. Every artifact carries `EXPLANATION_TYPE_NOTE`, distinguishing a prediction explanation (what moved this model's output) from a causal claim (CLAUDE.md Section 19) — downstream specs must preserve this distinction in their own wording, not just in DEV-010's raw output.
