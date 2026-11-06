# DEV-023 — ML Opportunity Insights Web Integration

## Specification ID
DEV-023

## Feature/Module Name
ML Opportunity Insights Web Integration

## Purpose
Expose the existing, unmodified ML decision-support pipeline (XGBoost prediction, SHAP explanation, district opportunity ranking) to logged-in mechanics through a read-only page inside the marketplace, without duplicating or forking any prediction/ranking/explanation logic.

## Background/Context
MARKETPLACE_EXTENSION.md Section 7 (full boundary rules); REF-003 (ML Component Architecture — unchanged); REF-010 Section 4 (the one cross-subsystem integration point); REF-013 Section 5 (disclaimer placement). This spec is the only place in the entire marketplace extension where `app/` code imports from `src/`.

## Related Requirements
FR-M12. Reuses (does not redefine) FR-04 through FR-11 from the original source documentation (`MASTER_PROMPT.md` Section 21), which DEV-008/DEV-010/DEV-012/DEV-013 already satisfy.

## User Roles
Mechanic only (Opportunity Insights is a mechanic-facing tool per the original source documentation's primary-user framing, carried into the marketplace per MARKETPLACE_EXTENSION.md Section 3). Not exposed to customers or admins.

## Preconditions
DEV-018 (mechanic auth) complete. DEV-008 (XGBoost), DEV-010 (SHAP), DEV-012 (Ranking Engine) already complete in the existing ML system (they are — see TODO.md Phases 6, 8, 9) and are consumed here unchanged.

## User Stories/Use Cases
- As a logged-in mechanic, I want to select my vehicle category and a period and see which districts currently look like the strongest opportunity, using the same model the Streamlit dashboard uses.
- As a mechanic, I want to see the SHAP-based reasons for a district's ranking, in plain language, exactly as the Streamlit dashboard presents them.
- As a mechanic, I want the same "this is not a guarantee" disclaimer the ML system always shows, so I don't misread this page as a promise.

## Functional Requirements
- FR1 Build `app/routes/insights.py`, `@login_required` + `@role_required('mechanic')`, calling `src/recommendation/ranking_engine.py::RankingEngine.rank(vehicle_type, period, top_n=...)` exactly as `dashboard/app.py` does (DEV-013's existing call pattern) — no new ranking/prediction code is written in `app/`.
- FR2 Build `opportunity_insights.html`: vehicle-type selector, period selector (data-driven from the real available periods, mirroring DEV-013's approach — no fabricated month control if the dataset remains yearly-only per REF-001 Section 5), a ranking table/list, and the SHAP explanation for the selected/top districts, styled with the marketplace's own CSS (not an embedded Streamlit iframe — REF-010 Section 4). **Extended (2026-08-21, UI/UX refinement, approved):** an optional District selector (REF-002's 25 canonical names, default "All Districts") lets a mechanic view a single district's own rank/band/SHAP factors/recommendation sentence directly, instead of only the top-N grid. It filters `RankingEngine.rank()`'s own already-computed, full-coverage result (the route now always requests `top_n=len(canonical_districts)`, mirroring the Streamlit dashboard's own established full-coverage pattern, REF-009 ADR-021) — it never triggers a second prediction, ranking, or SHAP computation. A district with no eligible row for the selected vehicle type/period shows a clear "No opportunity data available for this district" message, never a fabricated card.
- FR3 Render the exact Appendix C.3 disclaimer (CLAUDE.md Section 15) on this page, verbatim, persistently visible wherever ranking/prediction output is shown (mirrors DEV-013's Business Rule).
- FR4 Handle the "no data for this selection" state identically in spirit to DEV-013's missing-period-data rule — a clear message, never a blank or misleading chart/table.
- FR5 This route must be read-only with respect to the ML system: it never writes to `data/`, `models/`, or `mlruns/`, and never persists a mechanic's Insights query as a new "demand" observation anywhere (MARKETPLACE_EXTENSION.md Section 7.2's boundary rule, restated as an explicit implementation constraint here).
- FR6 Model/data loading (`RankingEngine.load()` and whatever it depends on) is performed once per process and cached (e.g. Flask's application-context caching or a simple module-level singleton, analogous to Streamlit's `@st.cache_resource` in DEV-013) rather than reloaded on every request.

## Business Rules
- Opportunity Insights output must never be described in the UI as verified/guaranteed customer demand — language mirrors REF-007 Section 4's approved wording exactly (the same wording DEV-012's recommendation sentences already use).
- This page's ranking output and the marketplace's own "top-rated mechanics" sort (DEV-020) must never be visually or textually conflated — they answer different questions (district-level opportunity forecast vs. individual mechanic review average) and must be labelled distinctly (REF-013 Section 5).
- If `src/recommendation/ranking_engine.py`'s interface needs to change to serve two consumers (Streamlit + Flask) cleanly, that change is made in `src/` under the existing DEV-012 spec's governance, not by adding parallel logic inside `app/routes/insights.py`.

## Data Requirements
Reads (via `src/`, unchanged): DEV-012 ranking output, DEV-010 SHAP output, DEV-002 source register, DEV-006 dataset version, DEV-008/DEV-014 model version/metrics. No marketplace database table is read or written by this route beyond `current_user` (to confirm role).

## Database/Schema Changes
None. This spec touches neither `instance/marketplace.db` (beyond reading the session) nor any ML `data/` file/schema.

## API Requirements
None; the "integration" is a direct Python function call into `src/recommendation/ranking_engine.py` within the same process, exactly as DEV-013's dashboard code already does (CLAUDE.md Section 10 — thin function-call integration, no network service).

## Backend Behavior
`app/routes/insights.py` is a thin controller: parse the mechanic's selection, call `RankingEngine.rank(...)`, pass the result to the template. All actual modelling/ranking/explanation logic remains entirely inside `src/` (Maintainability NFR, REF-004, extended here to the marketplace).

## Frontend Behavior
Server-rendered table/list (Jinja2), optionally a simple Plotly or plain HTML bar-chart-style rendering for the ranking (no requirement to reproduce DEV-013's choropleth map — a ranked list/table is sufficient for this page's purpose per the approved feature list, which does not ask for a second map).

## UI States
- **Normal:** ranking table + SHAP reasons for the selected vehicle type/period.
- **No data for selection:** clear message (FR4).
- **Model/artifact load failure:** clear error state, never silent fallback to stale/fabricated data (mirrors DEV-013's Error Case).

## Validation
Vehicle-type and period selections are validated against the real values `RankingEngine` actually supports (data-driven, not hardcoded) — an invalid selection is rejected with a clear message, not passed through to `src/` and allowed to raise an unhandled exception.

## Permissions
Mechanic only (`role_required('mechanic')`); customers and admins receive HTTP 403 if they attempt to reach `/insights` directly.

## Error Cases
- `RankingEngine`/model artifacts fail to load (e.g. a missing `models/xgboost_v1/` at deploy time) — clear error page, not a crash or a silently empty page.
- A vehicle category/period combination with no eligible districts — the "no data" state (FR4), not an empty table with no explanation.

## Edge Cases
- A mechanic whose marketplace-profile `district`/vehicle types don't match any real districts with strong predicted opportunity — this page shows the ranking for whatever the mechanic selects; it does not auto-personalize or pre-filter based on the mechanic's own profile data unless a future specification explicitly asks for that (personalization is not part of the approved feature list and would risk blurring the marketplace/ML boundary — flagged as an open question, not implemented here).
- Concurrent mechanics viewing Insights simultaneously — the cached model/artifact loading (FR6) must be safe for Flask's default threaded/multi-worker request handling (read-only access to already-loaded, immutable model objects; no shared mutable state written per-request).

## Security Considerations
No new attack surface beyond standard route protection — this page performs no writes and accepts only two bounded, validated selector inputs (vehicle type, period), both matched against a small enumerable set of real values.

## Dependencies
DEV-018 (Auth). Existing, unmodified: DEV-008 (XGBoost), DEV-010 (SHAP), DEV-012 (Ranking Engine).

## Testing Requirements
`tests/marketplace/test_insights_integration.py` (19 tests, all passing, against the real ML backend — not mocked, except where a test's own purpose requires simulating a failure): mechanic-only access enforced (customer/admin/anonymous all rejected, plus a mid-session-block test — see the note below); a real vehicle-type/period selection renders real data; the rendered ranking (top district, predicted value, band, full recommendation sentence) matches an independent, direct `RankingEngine.rank()` call byte-for-byte, not a re-derived number; ranking order preserved in the HTML; the exact Appendix C.3 disclaimer text present verbatim; the model/data info panel present; invalid vehicle type/period/top_n all fall back safely (200, not 500); the no-data template branch renders `RankingEngine`'s own message correctly; a simulated load failure returns 503 with no stack trace leaked; the engine is loaded exactly once across three requests (`RankingEngine.load()` call-counted); this module imports no marketplace `Review`/`MechanicProfile` model; zero writes to `data/`/`models/`/`mlruns/`; `dashboard/data_access.py`/`views.py` still import cleanly and `dashboard/app.py`'s source still defines `main()` (not imported directly — see the note below).

## Acceptance Criteria
- [x] Mechanic can select vehicle type/period and see a ranking + SHAP explanation sourced directly from the existing `RankingEngine` — verified against the real backend via a real dev-server request (register → log in → `GET /insights/` → 200, real disclaimer text, 5 real ranking cards for the default `top_n`), not only the test client.
- [x] Appendix C.3 disclaimer visible verbatim on this page — rendered directly from `result["disclaimer"]` (the exact string `RankingEngine` itself returns, sourced from `configs/ranking_config.yaml`), not a second hand-copied constant.
- [x] No customer or admin can reach this page — verified individually; a blocked mechanic is also denied, including *mid-session* (verified directly, not assumed — see the note below).
- [x] No code in this spec writes to any ML-system data/model/experiment-tracking path — verified by a directory-snapshot test, and by design (the route only ever calls `.rank()`, a read/predict operation).
- [x] The existing Streamlit dashboard (`dashboard/app.py`) continues to run unmodified and unaffected by this integration — confirmed by `git`-diff-equivalent inspection (no file under `dashboard/` was touched) and a source-text check; `dashboard/app.py` itself is deliberately not imported by the new test (it calls `main()` unconditionally at module level and is only safe to execute inside Streamlit's own `AppTest`/script-run context, already covered by `tests/test_dashboard_app.py`).
- [x] All tests in `tests/marketplace/test_insights_integration.py` pass (19/19); full existing ML test suite (`pytest tests/ --ignore=tests/marketplace`) still passes unmodified (191/191).

## Additional implementation notes (added post-implementation)
- **Blocked-mid-session access was verified, not newly built.** Flask-Login's `UserMixin.is_authenticated` defaults to `return self.is_active`, and `User.is_active` (DEV-018) already checks `status`. Since Flask-Login reloads the `User` row fresh on every request, a mechanic blocked mid-session loses access on their very next request automatically — confirmed by a dedicated test in this spec's suite, since the instructions for this integration explicitly called for verifying it in the Insights context specifically. No code changed as a result; see REF-009's note (not an ADR — nothing was decided or altered).
- **Process-wide lazy singleton, not eager load.** `_get_ranking_engine()` loads `RankingEngine` once, lock-guarded against a concurrent double-load, on the *first* request to this page — not at `create_app()` time, so a marketplace request that never touches Insights never pays the ML stack's cold-load cost. Measured on a real dev server: ~12.7s cold, ~90ms warm. See REF-009 ADR-034.
- **No SBERT natural-language query box on this page**, unlike DEV-013's dashboard — a deliberate, narrower scope matching DEV-023's own FR1 wording (`RankingEngine.rank()`, not `rank_from_query()`). See REF-009 ADR-034 for the full reasoning; SBERT remains fully available, unchanged, on the Streamlit dashboard.
- **Model/data info panel** is a small dict built directly from `engine.metadata` in the route (production model name, dataset version, model-trained date, test MAE) — presentation-layer glue, not a new computation; mirrors what `dashboard/views.py::format_model_version_summary` already does for Streamlit, without reusing that function directly (it returns a pandas DataFrame shaped for `st.dataframe`, not a Jinja-friendly structure).
- **Optional district filter (2026-08-21, UI/UX refinement, approved) — FR2 extended.** The route now always calls `engine.rank(vehicle_type, period, top_n=len(engine.canonical_districts))` (full district coverage) regardless of whether a district is selected, then slices the result in the route: `result["top_n"][:top_n]` for the unfiltered view (byte-for-byte identical to the old behavior, since the first N of an already-sorted full list equals a direct `top_n=N` call — verified by test), or a single matching entry when a district is selected. This is not a new decision so much as this page now matching the Streamlit dashboard's own established full-coverage pattern (REF-009 ADR-021) — no new ADR was logged for it.

## Definition of Done
All acceptance criteria met; this spec demonstrably adds zero new prediction/ranking/explanation logic — it is verifiably a thin presentation wrapper around DEV-012's existing, tested interface (the byte-for-byte comparison test against a direct `RankingEngine.rank()` call is the concrete proof of this, not just an inspection claim).
