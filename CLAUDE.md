# CLAUDE.md — Mechanic Service Demand Opportunity Prediction and Recommendation System (Sri Lanka)

This file is the permanent context file for every Claude Code session on this project. Read it before doing any work. If anything here conflicts with `specs/`, resolve using the Source-of-Truth Hierarchy in Section 14 below.

---

## 1. Project overview

**Name:** Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka
**Subtitle:** A data-driven decision-support system for freelance mechanics
**Academic context:** Final Year Project, HND Computing, ESOFT Metro Campus.

**Purpose:** This project develops a machine-learning-based decision-support system for freelance mechanics in Sri Lanka. It uses real vehicle-registration statistics and other district-level data to identify where mechanic-service opportunity is likely to be stronger. The first implementation focuses on motorcycle mechanics; cars and three-wheelers are included where reliable data is available. The core idea: vehicles registered and operating in a district become part of the local servicing and repair market — new vehicles enter scheduled maintenance cycles, older vehicles continue to need repairs. Vehicle statistics are therefore a meaningful signal for the size and direction of the mechanic service market, but the system never claims that a registration count equals a mechanic job count. It uses real observations as model features, or as a clearly labelled service-opportunity proxy when no direct job-demand target is available.

**Core user question:** *"For the selected vehicle category and future period, which districts show the strongest predicted service opportunity, and what factors caused those districts to rank highly?"*

## 2. Project objectives (Section 4.2 of the source documentation)

- Collect real vehicle-registration and supporting district-level data from credible public sources.
- Create a clean district-time-vehicle dataset with complete source provenance.
- Use motorcycles as the initial mechanic category and support additional vehicle categories where data permits.
- Define a real target variable for model training; do not fabricate mechanic-demand labels.
- Develop XGBoost as the primary machine-learning model for tabular prediction.
- Develop an LSTM time-series model when the dataset provides a sufficient sequence length and time resolution.
- Use SHAP to explain global feature importance and individual district predictions.
- Use SBERT to interpret natural-language queries and map them to the correct vehicle/mechanic category.
- Rank districts and translate model outputs into clear, transparent opportunity bands or recommendations.
- Build a Streamlit and Plotly dashboard with maps, historical trends, forecasts, explanations and data-source information.
- Evaluate the models using appropriate regression and ranking metrics with time-aware validation.
- Track experiments and dataset versions using MLflow or Weights & Biases, and manage source code in GitHub.

## 3. Important terminology

See `specs/reference/REF-007-domain-rationale-terminology.md` Section 5 for full definitions. Summary:
- **Opportunity/proxy target vs. real demand target** — a real demand target is an observed mechanic-demand signal; a proxy target is a real observable vehicle-market variable used as a stand-in, always framed as relative opportunity, never as a job count.
- **District** — one of Sri Lanka's 25 official administrative districts (`specs/reference/REF-002-canonical-lists-normalization.md`).
- **Vehicle category** — Motorcycle, Car, or Three-wheeler; Motorcycle is the first/primary scenario.
- **New registrations vs. vehicle population** — distinct signals; do not conflate (source doc Section 6.1–6.2).
- **Leakage** — using information from period ≥ t to construct a feature used to predict period t (source doc Section 12.1).
- **Opportunity band** — transparent Low / Moderate / High / Very High categorization derived from quantiles or a documented rule (source doc Section 18 step 4).
- **source_id / provenance** — unique identifier tracing every processed row to its original source table/publication; required on every row.
- **Walk-forward validation** — time-aware validation where the model is evaluated on periods strictly after its training window; never random train/test splitting for future-period prediction.

## 4. Target users and roles

**Primary user:** a freelance/independent mechanic. Motorcycle mechanic is the first scenario; car and three-wheeler mechanics are supported by the same architecture.

There is **no multi-tenant account system, no admin backend with user management, and no customer-facing role**. Do not invent one. If a lightweight "admin"/config view is ever needed (e.g. to view the data-source register or model version), scope it as a dashboard panel, not a separate authenticated role, unless the user explicitly asks for one later.

## 5. Technology stack

See `specs/reference/REF-008-technology-stack.md` for the full table. Summary: Python 3.10+; Pandas/NumPy; XGBoost + scikit-learn; TensorFlow/Keras (LSTM); sentence-transformers/SBERT; SHAP; Streamlit; Plotly; MLflow or Weights & Biases; Git/GitHub; VS Code/Jupyter; CSV/Parquet with optional SQLite.

**Do not change this stack** without a documented, justified technical reason recorded as an ADR in `specs/reference/REF-009-architecture-decisions.md`.

## 6. Architecture rules

Pipeline: real data → extraction & validation → district/time/vehicle feature table → feature engineering → XGBoost & LSTM modelling → SHAP explanations → district ranking & recommendation → Streamlit/Plotly dashboard, with SBERT operating at the user-interaction layer to route natural-language queries to the correct prediction category (source doc Section 20).

Code must be modular: extraction, preprocessing, modelling, explainability, NLP, recommendation, and dashboard are **separate packages/modules** — see `src/data`, `src/features`, `src/models`, `src/explainability`, `src/nlp`, `src/recommendation`, `dashboard/` in the folder structure (Section 12 below; Appendix B of the source doc; NFR "Maintainability" — `specs/reference/REF-004-nfr-and-scope-boundaries.md`).

## 7. Frontend conventions

Streamlit multi-panel dashboard; Plotly for all charts/maps; no other frontend framework. Required controls and panels (source doc Section 19, governed by DEV-013):

**Controls:** vehicle type selector; prediction year/month selector; district selector for detailed analysis; top-N recommendation selector; optional natural-language query box powered by SBERT.

**Panels:** Sri Lanka choropleth map showing predicted opportunity by district; top district ranking table or bar chart; historical registration trend for the selected district/vehicle type; forecast/predicted value for the selected period; SHAP explanation panel showing main positive/negative factors; data-source and model-version information; clear note explaining that opportunity estimates are not guaranteed job counts (Appendix C.3 disclaimer, verbatim in Section 15 below).

## 8. Backend/ML conventions

- Chronological data splits only — never random train/test splitting for future-period prediction.
- XGBoost trained per source doc Section 14.2 (6-step process — see DEV-008).
- LSTM per source doc Section 15 (conditional on sequence density — see DEV-009).
- SHAP per source doc Section 17 (global + local — see DEV-010).
- SBERT routing per source doc Section 16 (see DEV-011).
- Models saved with exact feature list + dataset version (model registry — source doc Section 24, see DEV-014).

## 9. Database conventions

Primary storage is CSV/Parquet files under `data/`, with optional SQLite for the app layer if needed for the dashboard. No requirement for a full relational DBMS. Canonical schema: `specs/reference/REF-001-data-dictionary.md` (Appendix A of the source doc).

## 10. API conventions

If an internal API layer is introduced between the modelling backend and the Streamlit dashboard, it is optional and an implementation decision (log as ADR). Keep it a thin function-call or lightweight local API — do not introduce external network services unless justified.

## 11. Authentication/authorization rules

**Not required** by the documentation for this academic dashboard. Do not add a login system unless the user explicitly requests one later.

## 12. Folder/file organization

```
mechanic-demand-project/
├── specs/
│   ├── development/        (DEV-001 ... DEV-017, DEV-PLAN.md)
│   ├── reference/           (REF-001 ... REF-009)
│   └── COVERAGE.md
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── notebooks/
├── src/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── explainability/
│   ├── nlp/
│   └── recommendation/
├── dashboard/
├── models/
├── reports/
├── tests/
├── configs/
├── CLAUDE.md
├── TODO.md
├── requirements.txt
└── README.md
```

## 13. Security requirements

From source doc Sections 22 and 28 (`specs/reference/REF-005-ethical-legal-governance.md`): no unnecessary personal data collection; no personal vehicle-owner information; respect scraping terms/robots rules; record dataset licences/attribution; disclose data cut-off dates and limitations; never present model output as guaranteed income/employment/customer numbers.

## 14. Validation and error-handling rules

From source doc Section 26 (Testing Strategy) and Sections 10–11 (data acquisition/cleaning): missing values must be surfaced, never silently zeroed; unsupported SBERT queries must fail safe (no wrong-category guess presented as confident); missing-period dashboard data must show a clear message rather than a blank or misleading chart.

## 15. Required disclaimer (Appendix C.3, verbatim)

Must appear wherever recommendations/rankings are shown:

> "Predictions are based on available historical and proxy data. They indicate relative service opportunity and do not guarantee customer numbers, employment or income."

## 16. Testing expectations (source doc Section 26, governed by DEV-015)

**Data tests:** no unknown district names after normalization; no duplicated district-time-vehicle key unless explicitly justified; numeric fields contain valid ranges; observation years match source tables; missing values are reported, not silently replaced; source_id exists for every processed row.

**Model tests:** model receives the expected feature columns and order; no future-period feature leakage; saved model reloads and produces the same prediction shape; predictions checked for impossible values when the target is non-negative; SHAP output aligns with the model feature schema.

**Dashboard tests:** filters correctly update all panels; unsupported SBERT queries produce a safe fallback rather than a wrong category; missing-period data displays a clear message; ranking table and map use the same prediction values; model limitation text is visible to the user.

## 17. Coding standards

Python 3.10+, PEP8-consistent, type hints where practical, docstrings on public functions, config-driven (feature lists, target name, split dates, model params live in `configs/`, not hardcoded).

## 18. Environment/configuration rules

Dependencies pinned via `requirements.txt` or `pyproject.toml`; config files for feature lists/target name/date split/model parameters; random seeds recorded where supported.

## 19. Important project constraints

**What the project will not do (source doc Section 8.3):**
- Create arbitrary job counts to make the dataset larger.
- Assign random "High/Medium/Low" demand labels and train a classifier on those labels.
- Claim causal relationships when the model only identifies predictive associations.
- Use future-year features to predict an earlier year.
- Present a proxy score as if it were a government-recorded mechanic-demand statistic.

**Scope boundaries:** see `specs/reference/REF-004-nfr-and-scope-boundaries.md` Section 3 (verbatim scope table) and Section 4 (out-of-scope future extensions — do not implement until the core mechanic system is complete and validated).

## 20. Hard rules (apply throughout every session — see MASTER_PROMPT.md Section 0 for full text)

- Do not invent major features, modules, data sources, or ML components not in the documentation.
- Do not silently remove or weaken a documented requirement (e.g. do not quietly drop LSTM, SBERT, SHAP, or the two-path target strategy).
- **Do not fabricate data.** No synthetic/invented mechanic-job counts, no random High/Medium/Low labels used as training targets, no placeholder rows presented as real data. This is the single most important rule in this project.
- Do not claim exact job counts or guaranteed demand. Every recommendation surface must carry the Section 15 disclaimer.
- Do not change the technology stack without a documented ADR.
- Do not use future-period data to predict an earlier period (no leakage) — applies to every lag/rolling/growth feature and every train/test split.
- Do not use random train/test splitting for any model that predicts future periods.
- Do not over-engineer (no microservices, no Kubernetes, no enterprise auth, no unnecessary abstraction).
- When a low-level technical decision is not specified in the documentation, choose a sensible, industry-standard solution but record it in `specs/reference/REF-009-architecture-decisions.md` as an implementation decision, distinct from a documented requirement.
- Every top-ranked district recommendation shown by the system must be accompanied by a SHAP-based explanation and the standard limitation disclaimer. Non-negotiable. **Scoped exception (REF-009 ADR-042, confirmed by the project author 2026-11-07):** the Dataset v2 output comes from the previous-year baseline, which has no model for SHAP to explain, so it carries a rule-based explanation built only from published values, plus the same disclaimer. The SHAP requirement still applies in full to Dataset v1 output.

## 21. Source-of-truth hierarchy

When any conflict arises, resolve using this order (highest wins):
1. Original Final Project Documentation (`Mechanic_Demand_Prediction_Project_Documentation.docx`, reproduced in `MASTER_PROMPT.md`).
2. Approved reference specifications in `specs/reference/`.
3. Development specifications in `specs/development/`.
4. This file (`CLAUDE.md`).
5. Development plan (`specs/development/DEV-PLAN.md`).
6. `TODO.md`.
7. Implementation / code.

If a conflict is detected between levels, **do not silently pick whichever is easiest to implement**. Stop, flag the conflict explicitly, and record it in a `## Open Questions / Conflicts` section of the relevant spec file. Preserve the original documented requirement unless there is a strong, stated technical reason to deviate — in which case log it as an ADR and ask the user to confirm before proceeding if the deviation is non-trivial.

## 22. Rules Claude must follow before changing code

- Always re-read the relevant `specs/development/DEV-XXX.md` and any linked `specs/reference/REF-XXX.md` before implementing or modifying that area.
- Never implement a feature not traceable to a spec.
- If a user request conflicts with a spec, flag it rather than silently complying.

## 23. Rules for keeping documentation/specs synchronized with implementation

- Update `TODO.md` checkboxes (`- [ ]` → `- [x]`) only when the implementation genuinely satisfies the spec's acceptance criteria — never mark complete based on "should work."
- Update the relevant spec file if the implementation legitimately required a documented deviation (log it as an ADR in `specs/reference/REF-009-architecture-decisions.md`).
- Keep `CLAUDE.md` accurate — if conventions change, update it in the same commit/change as the code that required the change.
- Never mark a phase in `DEV-PLAN.md` complete while any of its constituent dev specs are incomplete.

## 24. Spec index

- `specs/development/DEV-PLAN.md` — build order and dependency graph.
- `specs/development/DEV-001.md` … `DEV-017.md` — one spec per module (see DEV-PLAN.md for the list).
- `specs/reference/REF-001.md` … `REF-009.md` — data dictionary, canonical lists, ML architecture, NFRs/scope, ethics/governance, risks/limitations, domain rationale/terminology, technology stack, ADR log.
- `specs/COVERAGE.md` — requirement-to-spec traceability matrix.
- `TODO.md` — dependency-ordered execution checklist.

## 25. Project extension — Mechanic Discovery Web Platform

**Everything in Sections 1–24 above describes the ML decision-support system exactly as originally documented, and remains unchanged and fully in force for that system.** This section records an **approved, additive extension** (approved by the user, 2026-08-21): a separate customer/mechanic/admin marketplace web application, planned in full in `MARKETPLACE_EXTENSION.md` and specified in `specs/development/DEV-018` through `DEV-024`, with supporting reference specs `specs/reference/REF-010` through `REF-013`.

**Reconciling this with Sections 4 and 5 above (do not silently drop either statement):**
- Section 4's "there is no multi-tenant account system, no admin backend with user management, and no customer-facing role... do not invent one" continues to describe the **ML dashboard/recommendation system** (`dashboard/`, `src/`). It does not apply to the new marketplace subsystem, which was explicitly requested and approved with exactly those roles. Do not add authentication, multi-tenancy, or a customer-facing role to `dashboard/` or `src/` on the strength of this extension — that boundary is intentional (see MARKETPLACE_EXTENSION.md Section 7).
- Section 5's "do not change this stack... without a documented ADR" is honored, not violated: the ML system's stack (Python, Pandas/NumPy, XGBoost, TensorFlow/Keras, SBERT, SHAP, Streamlit, Plotly, MLflow) is unchanged. The marketplace adds a **second, separate stack** (Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, SQLite, Jinja2/HTML/CSS) scoped entirely to a new `app/` directory — see `specs/reference/REF-010-marketplace-web-architecture.md` and REF-009 ADR-027.
- The full conflict analysis is in `MARKETPLACE_EXTENSION.md` Section 8 and `specs/reference/REF-009-architecture-decisions.md` ADR-026–028. Do not re-resolve these conflicts differently in a future session without the same explicit-user-confirmation step this section documents.

**Standing rules for the marketplace subsystem (apply every session, alongside Sections 1–24's rules for the ML system):**
- The marketplace (`app/`) may read from `src/` **only** through `DEV-023`'s Opportunity Insights integration point, and only read-only. No other marketplace route or module may import `src/`, and `src/`/`dashboard/` must never import from `app/`.
- Marketplace data (users, mechanic profiles, reviews) must never be written into `data/raw|interim|processed`, and must never be used as a feature, label, or training signal for any model in `src/models/`, unless a future, explicitly approved specification changes the research methodology (MARKETPLACE_EXTENSION.md Section 7.2).
- The Streamlit dashboard (`dashboard/app.py`) is not removed or degraded by this extension and must keep working exactly as DEV-013 left it (REF-009 ADR-026).
- The Appendix C.3 disclaimer (Section 15 above) appears only on marketplace pages that show ML prediction/ranking output (i.e. Opportunity Insights); the separate marketplace review disclaimer (see `specs/reference/REF-013-marketplace-ui-business-rules.md` Section 4) appears wherever ratings/reviews are shown. The two must never be merged into one sentence.
- Do not implement DEV-018 or any later marketplace spec until explicitly instructed — `MARKETPLACE_EXTENSION.md` Section 11 records this as the stop condition for the current planning pass.

## 26. Dataset v2 recommendation output

The approved plan is `specs/development/PLAN-recommendation-v2-integration.md`, with REF-009 ADR-042 and ADR-043. Standing rules:
- `configs/recommendation_v2.yaml` chooses the v1 or v2 engine for the dashboard and Opportunity Insights. **v2 is the default, approved by the project author on 2026-11-07.** Setting `active_engine: v1` rolls back to the v1 engine, which stays available and tested.
- v2 is labelled "Vehicle-Fleet Service Opportunity". It describes relative licensed-vehicle fleet size, not mechanic jobs or measured service demand. The official project title is unchanged.
- v2 reads Dataset v2 only, loads no model, and adds no scores, weights or formulas beyond the plan. `app/routes/insights.py` remains the only `app/` module that imports `src/`.
