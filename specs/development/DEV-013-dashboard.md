# DEV-013 — Streamlit + Plotly Dashboard

## Specification ID
DEV-013

## Feature/Module Name
Streamlit + Plotly Dashboard

## Purpose
Present ranking, map, trend, forecast, and explanation outputs to the freelance mechanic through a simple, non-technical interactive web dashboard.

## Background/Context
Source doc Section 19 (Dashboard and User Experience), Section 19.1 (controls), Section 19.2 (panels), Appendix C (example outputs). NFR "Usability" (REF-004): "a user should be able to choose a vehicle category and view recommendations without understanding ML terminology."

## Related Requirements
- FR-08 (interactive Sri Lanka district map), FR-09 (historical trends and top recommendations), FR-11 (source/model/limitation info), FR-12 (export/reproducible view, if time permits)
- Section 19, Section 26.3 (dashboard tests), Appendix C.3 (disclaimer)

## User Roles
Primary user: freelance/independent mechanic (CLAUDE.md Section 4). No login/account system.

## Preconditions
DEV-010 (SHAP), DEV-011 (SBERT), DEV-012 (Ranking Engine) complete for the full feature set; per DEV-PLAN.md Section 2, the core panels (map/ranking/trend/forecast/SHAP/disclaimer) must work on the DEV-008→DEV-010→DEV-012 path even if DEV-011 (SBERT) lags behind.

## User Stories/Use Cases
- As a mechanic, I want to select my vehicle category and a future period and immediately see which districts look strongest, with a map and a ranked list (Section 19.1–19.2).
- As a mechanic, I want to see why a district is ranked highly, in plain terms, and be reminded that this isn't a guarantee (Section 19.2, Appendix C.3).
- As a mechanic, I want to optionally just type my situation in plain language instead of using the filters (Section 19.1 NL query box).

## Functional Requirements

### 19.1 Main controls (verbatim)
- Vehicle type selector.
- Prediction year/month selector.
- District selector for detailed analysis.
- Top-N recommendation selector.
- Optional natural-language query box powered by SBERT (DEV-011).

### 19.2 Main dashboard panels (verbatim)
- Sri Lanka choropleth map showing predicted opportunity by district (Plotly).
- Top district ranking table or bar chart.
- Historical registration trend for the selected district/vehicle type.
- Forecast/predicted value for the selected period.
- SHAP explanation panel showing main positive/negative factors.
- Data-source and model-version information (reads DEV-002's source register + DEV-006's dataset version + DEV-008/DEV-014's model version).
- Clear note explaining that opportunity estimates are not guaranteed job counts (Appendix C.3, verbatim disclaimer — persistent, not just on one panel).

### FR-12 (if time permits)
- Export selected results (e.g. CSV download of the current ranking) or a reproducible analysis view. Explicitly optional/best-effort per the source doc's "if time permits" wording — do not treat as blocking for project completion.

## Business Rules
- All panels driven from **DEV-012's single ranking-engine output** for a given selection — map and ranking table must never diverge (Section 26.3).
- The Appendix C.3 disclaimer must be visible wherever recommendations/rankings are shown, not buried in a separate help page.
- No ML jargon required to operate the dashboard (Usability NFR) — plain-language labels and explanations throughout.

## Data Requirements
Reads: DEV-012 ranking output, DEV-010 SHAP output (via DEV-012), DEV-002 source register, DEV-006 dataset version, DEV-008/DEV-014 model version/metrics, DEV-011 SBERT routing result.

## Database/Schema Changes
None (dashboard is a presentation layer; optional local SQLite only if needed for app-layer state — CLAUDE.md Section 9).

## API Requirements
None required; if a thin internal API is introduced between backend and dashboard, it's an implementation decision (log as ADR) per CLAUDE.md Section 10.

## Backend Behavior
Dashboard app code lives in `dashboard/` (separate from `src/` per Appendix B / REF-008 folder structure), calling into `src/recommendation/`, `src/explainability/`, `src/nlp/` as needed — dashboard code itself contains no modelling/ranking logic (thin presentation layer, per Maintainability NFR).

## Frontend Behavior
Streamlit multi-panel layout; Plotly for all charts/maps (no other frontend framework, per CLAUDE.md Section 7). Interactions: changing any control (vehicle type, period, district, top-N, or NL query) updates all dependent panels consistently.

## UI States
- **Normal:** all panels populated for the current selection.
- **Missing-period data:** a clear message is shown instead of a blank/misleading chart (Section 26.3) when no data exists for the selected period/district/vehicle-type combination.
- **SBERT fallback:** NL query box shows a "couldn't confidently match" message and prompts manual selection (DEV-011), rather than silently picking a category.
- **Loading/pre-trained-model-ready:** predictions for a pre-trained model return within a few seconds (Performance NFR, REF-004).

## Validation
Section 26.3 Dashboard tests (verbatim):
- Filters correctly update all panels.
- Unsupported SBERT queries produce a safe fallback rather than a wrong category.
- Missing-period data displays a clear message.
- Ranking table and map use the same prediction values.
- Model limitation text is visible to the user.

## Permissions
N/A — no auth/login (CLAUDE.md Section 11).

## Error Cases
- Backend model/artifact fails to load — dashboard must show a clear error state, not crash silently or show stale/fabricated data.
- A selection with no valid ranking output (e.g. per DEV-012's error case) — show the "missing data" message, not an empty or broken chart.

## Edge Cases
- User selects a district/period far outside the training data's real coverage — the limitation/disclaimer text must be prominent, and ideally the UI notes the data cut-off date (REF-005 governance rule).
- Very small top-N selection (e.g. top-1) vs. large (e.g. top-10, more than districts with valid predictions) — must handle gracefully (cap at available valid districts).

## Security Considerations
No personal data collected via the NL query box or any control beyond the query text itself (REF-005). No login credentials to protect (no auth system).

## Dependencies
- DEV-010 (SHAP Explainability Module)
- DEV-011 (SBERT Natural-Language Query Module)
- DEV-012 (District Ranking & Recommendation Engine)

## Testing Requirements
Section 26.3 dashboard tests (see Validation) implemented under `tests/` (consolidated in DEV-015).

## Acceptance Criteria
- [x] All Section 19.1 controls implemented and functional — `dashboard/app.py::render_sidebar_controls()`: vehicle type selectbox, prediction-year selectbox (data-driven from the real available periods, no fabricated month control since the dataset is yearly-only per REF-001 Section 5), district selectbox, top-N slider, NL query box + submit button (form-wrapped so SBERT isn't invoked per keystroke).
- [x] All Section 19.2 panels implemented and functional, sourced from a single consistent prediction computation — choropleth map, ranking table, historical trend, forecast metric, SHAP explanation, data-source/model-version panel, persistent disclaimer. All panels for a given selection are built from exactly one `RankingEngine.rank()` call's output (`cached_rank`), never a separate re-derived computation per panel.
- [x] Appendix C.3 disclaimer visible wherever recommendations/rankings are shown — rendered at the top of the main content, again at the bottom, and persistently in the sidebar; verbatim string verified by test.
- [x] Section 26.3 dashboard tests pass — `tests/test_dashboard_app.py`, 13/13 passing via Streamlit's `AppTest` harness (real script execution, real widget interactions, no browser needed): filters update all panels; unsupported/ambiguous SBERT queries produce a safe fallback without changing the vehicle-type control; missing-period data shows a clear message with zero charts rendered; ranking table values are a verified subset of the map's underlying colour data; disclaimer/model-limitation text is visible.
- [x] Dashboard usable without ML terminology knowledge (manual usability check) — plain-language labels throughout ("Describe your work," "Number of districts to recommend," "Why this prediction?"); recommendation sentences use REF-007 Section 4's wording (opportunity bands, never guaranteed counts); verified via a real `streamlit run` launch (see below), not only AppTest.
- [x] Predictions return within a few seconds for a pre-trained model (Performance NFR) — first page load ~16s (one-time SBERT/XGBoost/SHAP-explainer construction, cached via `@st.cache_resource`); every subsequent interaction (changing a filter, selecting a district) completes in well under 1 second, since `cached_rank` (`@st.cache_data`) avoids recomputing predictions/SHAP for an unchanged (vehicle_type, period, top_n) selection.

## New dependency acquired during this phase
No district boundary geometry existed anywhere in the project before this spec needed a real choropleth map. `src/data/fetch_district_geojson.py` acquires and verifies Sri Lanka's 25 district boundaries from geoBoundaries.org (ODbL-licensed, built from OpenStreetMap), registered in `data/source_register.csv` following DEV-002's existing governance pattern — see REF-009 ADR-019. While integrating the source register into this panel, two pre-existing malformed CSV rows (unquoted comma-bearing fields) were also found and fixed — REF-009 ADR-020.

## Additional implementation notes
- **Full-coverage SHAP, sliced for display:** the dashboard always requests SHAP explanations for all 25 eligible districts (not just the configured top-N) so the "district selector for detailed analysis" can show a real, non-fabricated explanation for any district, not only whichever ones are top-ranked — REF-009 ADR-021.
- **Real launch verified:** in addition to the automated `AppTest` suite, `streamlit run dashboard/app.py` was started as a real server process and confirmed to serve HTTP 200 successfully, then stopped — the automated tests are not the only verification performed.
- **Historical trend never fabricates gaps:** missing years (e.g. Kandy Motorcycle 2022, REF-009 ADR-005) are left as gaps in the trend line, never interpolated or zero-filled; a district/vehicle_type with zero real observations shows a clear "no historical data" message instead of an empty chart.

## Testing Requirements — completed
- Section 26.3 dashboard tests — see above; `tests/test_dashboard_app.py` (13/13).
- Pure presentation-logic unit tests (map/table/trend/source-panel data transforms, independent of Streamlit) — `tests/test_dashboard_views.py`, 10/10 passing; caught and fixed a real bug (an empty top-N slice crashed `build_ranking_table` before the fix).
- Full project test suite: 155/155 passing.

## Definition of Done
All acceptance criteria met; the dashboard is runnable end-to-end (`streamlit run dashboard/app.py`, confirmed) and demonstrates the full user journey: select category/period (directly or via NL query) → view map/ranking/trend/forecast/SHAP → see disclaimer and data-source info.

## Dataset v2 addendum (2026-11-07)
v1 panels stay unchanged and are the default. When `configs/recommendation_v2.yaml` selects v2, the dashboard shows the "Vehicle-Fleet Service Opportunity" view, with licence trends and a rule-based explanation panel in place of the SHAP panel (REF-009 ADR-042, ADR-043).
