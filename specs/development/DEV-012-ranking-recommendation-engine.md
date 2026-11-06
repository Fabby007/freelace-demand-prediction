# DEV-012 — District Ranking & Recommendation Engine

## Specification ID
DEV-012

## Feature/Module Name
District Ranking & Recommendation Engine

## Purpose
Deterministically turn per-district model predictions into a sorted, banded, SHAP-explained, disclaimer-carrying recommendation output — the direct answer to the project's core user question.

## Background/Context
Source doc Section 18 (Recommendation and District Ranking Engine), Section 18.1 (example), Appendix C.1 (example ranking view), Appendix C.3 (required disclaimer). This is explicitly a **deterministic, traceable** process — Section 18: "must not invent narrative explanations unsupported by features/SHAP values."

## Related Requirements
- FR-07 (rank districts for a selected vehicle category and period)
- Section 18, Appendix C.1, Appendix C.3
- MASTER_PROMPT.md Section 0: every top-ranked recommendation must carry a SHAP-based explanation and the disclaimer — non-negotiable.

## User Roles
None directly (backend engine); output is consumed by DEV-013's dashboard for the end user (freelance mechanic).

## Preconditions
DEV-008 (XGBoost) and DEV-010 (SHAP) complete.

## User Stories/Use Cases
- As a mechanic, I want to see which districts rank highest for my vehicle category and period, with a plain-language reason and a clear statement that this isn't a guarantee (Section 18.1 example).

## Functional Requirements

### 18. Six-step ranking process (verbatim, adapted)
1. Receive the selected vehicle category and prediction period (from the dashboard controls, DEV-013, or from SBERT routing, DEV-011).
2. Generate the model prediction for each eligible district (via DEV-008's production model).
3. Sort districts from highest to lowest predicted target/service-opportunity value.
4. Convert predictions to transparent opportunity bands (Low, Moderate, High, Very High) with thresholds based on quantiles or a documented training-data rule (the exact rule must be chosen and recorded here or as an ADR in REF-009 once decided — the source doc leaves the precise thresholding mechanism open).
5. Use SHAP (DEV-010) to extract the strongest reasons for the top-ranked districts.
6. Return the top three or top five districts together with trend context and an uncertainty/limitation note.

### 18.1 Example recommendation wording (verbatim template)
"For motorcycle mechanics in the selected period, Kandy is ranked as a high-opportunity district. The main model factors are strong recent motorcycle registrations and positive registration growth. This is a model-based opportunity estimate and does not represent a guaranteed number of jobs."

All generated recommendation sentences must follow this template's structure: category + period → district → band → top SHAP factors (in plain language, not raw feature names where avoidable) → limitation statement.

## Business Rules
- **Deterministic and traceable:** every recommendation must be derivable purely from the model's prediction and SHAP output — no invented/narrative explanation not backed by actual feature/SHAP values (Section 18, explicit).
- **Every top-ranked recommendation must carry:** (a) a SHAP-based explanation (DEV-010 output) and (b) the exact Appendix C.3 disclaimer (see REF-007 Section 4 wording rules and CLAUDE.md Section 15). This is non-negotiable per MASTER_PROMPT.md Section 0.
- **Wording rules (REF-007 Section 4):** use framing like "Kandy shows a high predicted motorcycle-service opportunity"; never state or imply an exact guaranteed job count unless a real job-count label backs it (only possible on the Preferred target path, DEV-002).
- **Neutral opportunity bands:** avoid unfairly labelling a district as "bad" — bands are neutral (Low/Moderate/High/Very High), and the output must state that results are probabilistic (REF-005 governance rule).

## Data Requirements
Input: DEV-008 model predictions per eligible district for the selected category/period; DEV-010 SHAP values per district. Output: a ranked list of districts, each with predicted value, opportunity band, top positive/negative SHAP factors (plain-language), trend context, and the disclaimer text.

## Database/Schema Changes
None beyond a ranking-output structure (in-memory / cached artifact consumed by DEV-013).

## API Requirements
None (function-level module; optionally a thin internal API if DEV-013 is decoupled from the modelling backend — see CLAUDE.md Section 10).

## Backend Behavior
Ranking logic lives in `src/recommendation/` (separate module, per Maintainability NFR and MASTER_PROMPT.md Section 5's instruction not to merge unrelated modules).

## Frontend Behavior
N/A directly — DEV-013 renders this engine's output in the ranking table/bar chart, map, and SHAP panel, all sourced from the **same** prediction values (Section 26.3: "ranking table and map use the same prediction values").

## UI States
N/A (owned by DEV-013), but the engine's output must include enough structure to drive: ranking table, map coloring, and SHAP panel from one shared computation (no separate/divergent prediction calls per panel).

## Validation
- Every returned top-N district includes a non-empty SHAP-based explanation and the exact disclaimer text.
- Opportunity band thresholds are documented and applied consistently (not recomputed ad hoc per query).
- Ranking table and map-ready output use identical underlying prediction values (Section 26.3).

## Permissions
N/A.

## Error Cases
- A selected district/category/period combination with no valid model prediction (e.g. insufficient historical data for that series) — must be excluded from the ranking with a clear reason, not silently omitted or given a fabricated placeholder value.

## Edge Cases
- Two or more districts tied at the same predicted value — deterministic tie-break rule required (e.g. alphabetical) so repeated runs are reproducible.
- A district with a genuinely declining trend ranked "High" due to base level despite negative growth — the SHAP explanation must reflect this honestly (e.g. note the negative growth factor), not oversell the ranking.

## Security Considerations
None beyond upstream rules.

## Dependencies
- DEV-008 (XGBoost Primary Prediction Model)
- DEV-010 (SHAP Explainability Module)
- REF-005 (Ethical/Legal/Governance — neutral bands), REF-007 (wording rules, disclaimer)

## Testing Requirements
- Test that every top-N output row carries a SHAP explanation and the disclaimer text.
- Test that opportunity-band thresholds are applied deterministically and consistently.
- Test that ranking-table and map data sources are identical (Section 26.3).

## Acceptance Criteria
- [x] Six-step ranking process (Section 18) implemented end-to-end — `src/recommendation/ranking_engine.py::RankingEngine.rank()`; step 1 (category/period) accepted directly or resolved via `rank_from_query()` using DEV-011's `SBERTRouter`; step 2 (predictions) reuses DEV-008's `build_feature_matrix()`/saved model unchanged; step 3 (sort + deterministic tie-break); step 4 (bands, REF-009 ADR-018); step 5 (SHAP factors for top-N, via DEV-010's `explain_rows()` unchanged); step 6 (top-N with trend/factor context + disclaimer).
- [x] Opportunity bands (Low/Moderate/High/Very High) implemented with a documented threshold rule — per-vehicle-type quartiles of the `train`-split `target_value` distribution, computed once per process, never recomputed per query (REF-009 ADR-018). Real thresholds: Motorcycle {25/50/75}={190.0, 664.5, 3876.5}; Car={28.0, 149.0, 531.0}; Three-wheeler={6.0, 22.0, 118.5}.
- [x] Every top-N recommendation includes a SHAP-based explanation — `positive_factors`/`negative_factors` (plain-language, drawn from DEV-010's real aggregated SHAP `contributions`, never invented) plus `shap_note` (the prediction-vs-causal distinction, carried through unmodified from DEV-010).
- [x] Every recommendation-bearing output includes the exact Appendix C.3 disclaimer — verbatim string match verified in tests (`tests/test_ranking_engine.py::test_every_top_n_row_has_non_empty_shap_explanation_and_exact_disclaimer`, `::test_top_level_output_also_carries_the_exact_disclaimer`); present even on a `no_data` fallback response.
- [x] Wording follows the "Good"/"Avoid" rules from REF-007 Section 4 — recommendation sentences use "is ranked as a {band}-opportunity district" framing, never an exact/guaranteed count; the sentence's own closing clause is the verbatim disclaimer, not a paraphrase (see module docstring for how Section 18.1's example structure and Appendix C.3's mandatory verbatim text are reconciled).
- [x] Ranking output and map-ready output share the same underlying prediction values — `top_n` entries are built from the exact same `ranked_districts` rows (same `predicted_value`/`opportunity_band`), never a separate computation; `tests/test_ranking_engine.py::test_top_n_predicted_values_match_ranked_districts_exactly`.

## Additional implementation notes
- **SBERT boundary preserved:** `rank_from_query()` calls `SBERTRouter.route()` purely to select `vehicle_type`; on `ambiguous`/`unsupported`/`empty`, it returns immediately with no ranking computed and `vehicle_type: None` - SBERT never influences a prediction or explanation (Business Rule).
- **`vehicle_type` excluded from displayed factors:** its SHAP contribution is constant across every district within one `rank()` call (single category per query), so it cannot explain relative ranking - see module docstring. It remains available via DEV-010's raw per-row output outside a ranking context.
- **Missing-period handling:** a period with no eligible districts at all (outside the dataset's real 2020-2024 target-year coverage) returns `status="no_data"` with a clear message and the full canonical district list as `excluded_districts` - never a silently empty/blank response (Error Case, CLAUDE.md Section 14).
- **Data-quality flags preserved:** every ranked district carries its `data_quality_flag` (feature-side, REF-006 Section 5.1) and `target_data_quality_flag` (target-side, REF-009 ADR-007) through to the output, unmodified.

## Testing Requirements — completed
- Every top-N output row carries a SHAP explanation and the disclaimer text — see above.
- Opportunity-band thresholds applied deterministically and consistently — `tests/test_ranking_engine.py::test_bands_not_recomputed_ad_hoc_per_query` (object-identity check, not just equal values).
- Ranking-table and map data sources are identical (Section 26.3) — see above.
- Full suite: `tests/test_ranking_engine.py`, 26/26 passing; full project test suite 132/132 passing.

## Definition of Done
All acceptance criteria met; DEV-013 can render the full recommendation view (ranking table, map, SHAP panel, disclaimer) purely from `RankingEngine.rank()` / `RankingEngine.rank_from_query()`'s output.
