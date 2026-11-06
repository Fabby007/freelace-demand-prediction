# MASTER PROMPT FOR CLAUDE CODE — SPEC-DRIVEN BUILD
## Project: Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka

Paste everything below into Claude Code as your first message in a new session for this project.

---

You are about to build a **Final Year Project (HND Computing, ESOFT Metro Campus)** called the **"Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka"** (subtitle: *"A data-driven decision-support system for freelance mechanics"*).

Your job has two parts, in strict order:

1. **Convert the project documentation below into a structured, spec-driven development environment** (SpecKit-style: `CLAUDE.md`, `TODO.md`, `specs/development/`, `specs/reference/`, a development plan/index).
2. **Only after that structure exists and has been validated for coverage**, begin implementing the system specification by specification.

**Do not write application source code before Stage 2 (establishing the spec system) and Stage 3 (coverage validation) are complete.** Follow the 7-stage workflow defined near the end of this prompt.

The full source-of-truth project documentation is reproduced in the section "PROJECT SOURCE DOCUMENTATION" below. Treat it as the primary source of truth for everything you build. If the original file `Mechanic_Demand_Prediction_Project_Documentation.docx` is available in the working directory or uploads, read it directly as well and reconcile against the extract below (the extract below preserves all requirements, rules, tables and wording from that document — it has not been simplified or trimmed of any requirement).

---

## 0. HARD RULES (apply throughout the entire project, every session)

- **Do not invent major features, modules, data sources, or ML components** that are not in the documentation.
- **Do not silently remove or weaken a documented requirement** (e.g., do not quietly drop LSTM, SBERT, SHAP, or the two-path target strategy because they are harder to implement).
- **Do not fabricate data.** No synthetic/invented mechanic-job counts, no random High/Medium/Low demand labels used as training targets, no placeholder rows presented as real data. This is a repeated, explicit constraint in the source documentation (Sections 3, 8.3, 26.1) and is the single most important rule in this project.
- **Do not claim exact job counts or guaranteed demand.** All outputs must be framed as relative opportunity/ranking/forecast unless a genuine observed mechanic-demand target exists in the data. Every recommendation surface must carry the disclaimer language defined in Appendix C.3 of the source doc (reproduced below).
- **Do not change the technology stack** (Python, Pandas/NumPy, XGBoost, scikit-learn, TensorFlow/Keras for LSTM, sentence-transformers/SBERT, SHAP, Streamlit, Plotly, MLflow or Weights & Biases, Git/GitHub) without a documented, justified technical reason recorded in an ADR (Architecture Decision Record) inside `specs/reference/`.
- **Do not use future-period data to predict an earlier period (no leakage).** This applies to every lag/rolling/growth feature and every train/test split.
- **Do not use random train/test splitting** for any model that predicts future periods — use chronological/time-aware validation only.
- **Do not over-engineer.** No microservices, no Kubernetes, no enterprise auth systems, no unnecessary abstraction layers. This is a final-year academic project that must be maintainable, explainable in a viva, and reproducible — not a production SaaS platform.
- **When a low-level technical decision is not specified in the documentation** (e.g., exact Streamlit page layout, exact SQLite schema syntax, specific charting color palette), you may choose a sensible, industry-standard, well-justified solution — but record the decision and its rationale in `specs/reference/REF-009-architecture-decisions.md` and clearly label it as an implementation decision, distinct from a documented requirement.
- **Every top-ranked district recommendation shown by the system must be accompanied by a SHAP-based explanation and the standard limitation disclaimer.** This is non-negotiable per Sections 17, 18, and Appendix C.3.

---

## 1. SOURCE-OF-TRUTH HIERARCHY

When any conflict arises, resolve it using this order (highest wins):

1. **Original Final Project Documentation** (`Mechanic_Demand_Prediction_Project_Documentation.docx`, reproduced in full below as "PROJECT SOURCE DOCUMENTATION").
2. **Approved reference specifications** in `specs/reference/` derived from it.
3. **Development specifications** in `specs/development/`.
4. **`CLAUDE.md`**.
5. **Development plan** (`specs/development/DEV-PLAN.md` or equivalent index).
6. **`TODO.md`**.
7. **Implementation / code.**

If you detect a conflict between levels (e.g., code does something `TODO.md` doesn't describe, or a development spec contradicts the original documentation), **do not silently pick whichever is easiest to implement.** Stop, flag the conflict explicitly in your output and in a `## Open Questions / Conflicts` section of the relevant spec file, and preserve the original documented requirement unless there is a strong, stated technical reason to deviate — in which case log it as an ADR and ask the user to confirm before proceeding if the deviation is non-trivial.

---

## 2. THE 7-STAGE WORKFLOW

### Stage 1 — Understand the project
Read the full "PROJECT SOURCE DOCUMENTATION" section below (and the original `.docx`/`.pdf` if present in the working directory). Identify and internally list: requirements, features, user roles, workflows, entities, business rules, constraints, and dependencies. Do not skip to implementation.

### Stage 2 — Establish the specification system
Create the following, exactly as detailed in Sections 3–6 of this prompt:
- `CLAUDE.md`
- `TODO.md`
- `specs/development/` (DEV-001 … DEV-017, see Section 5)
- `specs/reference/` (REF-001 … REF-009, see Section 6)
- `specs/development/DEV-PLAN.md` (the development plan/index, see Section 7)
- The project folder skeleton defined in Section 8 (derived from Appendix B of the source doc).

### Stage 3 — Validate coverage
Before writing any implementation code, produce a coverage checklist mapping **every** functional requirement (FR-01…FR-12), every non-functional requirement, every data rule, every modelling rule, every testing rule, and every deliverable from the source documentation to at least one of: a development spec, a reference spec, a `TODO.md` item, or another named planning artifact. Output this as `specs/COVERAGE.md`. Explicitly call out anything in the documentation that is unclear, ambiguous, or internally inconsistent (e.g., "monthly vs yearly granularity depends on source data — not fixed" is intentional and should be documented as a data-driven decision point, not treated as a defect). Do not proceed to Stage 4 until coverage is complete.

### Stage 4 — Plan implementation
Using `DEV-PLAN.md`, determine the safest, dependency-aware build order. The documentation already provides a phase sequence (Section 25 of the source doc) — use it as the backbone, but express it as explicit spec-to-spec dependencies (e.g., DEV-008 XGBoost depends on DEV-005 Feature Engineering and DEV-006 Target/Dataset Assembly, which depend on DEV-003/DEV-004 Data Acquisition & Cleaning, which depend on DEV-002 Data Source Register).

### Stage 5 — Implement specification by specification
Work through `specs/development/` in dependency order, one spec at a time. Before implementing a spec, (re-)read that spec file and any reference specs it links to. Do not jump ahead to a later spec while an earlier dependency is incomplete unless explicitly told to.

### Stage 6 — Test and verify
After completing each meaningful implementation unit (e.g., "extraction script for one district," "trained baseline model," "SHAP panel wired into dashboard"), verify it against that spec's Acceptance Criteria and Definition of Done. Run the relevant tests described in DEV-015 (Testing) before marking a `TODO.md` item complete.

### Stage 7 — Keep project state synchronized
As work progresses:
- Update `TODO.md` checkboxes (`- [ ]` → `- [x]`) only when the implementation genuinely satisfies the spec's acceptance criteria — never mark complete based on "should work."
- Update the relevant spec file if the implementation legitimately required a documented deviation (log it as an ADR in `specs/reference/REF-009-architecture-decisions.md`).
- Keep `CLAUDE.md` accurate — if conventions change, update `CLAUDE.md` in the same commit/change as the code that required the change.
- Never mark a phase in `DEV-PLAN.md` complete while any of its constituent dev specs are incomplete.

---

## 3. `CLAUDE.md` — REQUIRED CONTENTS

Create `CLAUDE.md` at the repository root as the permanent context file for every future Claude Code session on this project. It must contain, at minimum:

**Project overview** — Name, subtitle, academic context (ESOFT Metro Campus HND Final Year Project), one-paragraph purpose (use the Executive Summary and Section 2 content below), and the core user question: *"For the selected vehicle category and future period, which districts show the strongest predicted service opportunity, and what factors caused those districts to rank highly?"*

**Project objectives** — the full objectives list from Section 4.2 of the source doc.

**Important terminology** — define: opportunity/proxy vs. real demand target; district; vehicle category; new registrations vs. vehicle population; leakage; opportunity band (Low/Moderate/High/Very High); source_id/provenance; walk-forward validation. Pull exact definitions from Sections 6, 8, 12.1, 18 below.

**Target users and roles** — Primary user: freelance/independent mechanic (motorcycle mechanic is the first scenario; car and three-wheeler mechanics supported by the same architecture). There is no multi-tenant account system, no admin backend with user management, and no customer-facing role described in the documentation — do not invent one. If any lightweight "admin"/config view is needed (e.g., to view data-source register or model version), scope it as a dashboard panel, not a separate authenticated role, unless the user later asks for one.

**Technology stack** — reproduce the exact stack table from Section 30 below (Python 3.10+, Pandas/NumPy, XGBoost + scikit-learn, TensorFlow/Keras for LSTM, sentence-transformers/SBERT, SHAP, Streamlit, Plotly, MLflow or W&B, Git/GitHub, VS Code/Jupyter, CSV/Parquet with optional SQLite).

**Architecture rules** — the pipeline is: real data → extraction & validation → district/time/vehicle feature table → feature engineering → XGBoost & LSTM modelling → SHAP explanations → district ranking & recommendation → Streamlit/Plotly dashboard, with SBERT operating at the user-interaction layer to route natural-language queries to the correct prediction category (Section 20). Code must be modular: extraction, preprocessing, modelling, explainability, NLP, recommendation, and dashboard are separate packages/modules (per Appendix B folder structure and NFR "Maintainability" in Section 22).

**Frontend conventions** — Streamlit multi-panel dashboard; Plotly for all charts/maps; no other frontend framework. Reproduce the required controls and panels from Section 19 (see DEV-013 below) verbatim as UI requirements.

**Backend/ML conventions** — chronological data splits only; XGBoost trained via the process in Section 14.2; LSTM per Section 15; SHAP per Section 17; SBERT routing per Section 16; models saved with exact feature list + dataset version (model registry, per Section 24).

**Database conventions** — primary storage is CSV/Parquet files under `data/`, with optional SQLite for the app layer if needed for the dashboard; no requirement for a full relational DBMS. The canonical schema is the Appendix A data dictionary (reproduced in REF-001).

**API conventions** — if an internal API layer is introduced between the modelling backend and the Streamlit dashboard (optional, implementation decision), keep it a thin function-call or lightweight local API; do not introduce external network services unless justified.

**Authentication/authorization rules** — not required by the documentation for this academic dashboard; do not add a login system unless the user explicitly requests one later. Note this explicitly in `CLAUDE.md` so future sessions don't invent auth.

**Security requirements** — from Section 22 and Section 28: no unnecessary personal data collection, no personal vehicle-owner information, respect scraping terms/robots rules, record dataset licences/attribution, disclose data cut-off dates and limitations, never present model output as guaranteed income/employment/customer numbers.

**Validation and error-handling rules** — from Section 26 (Testing Strategy) and Sections 10–11 (data acquisition/cleaning): missing values must be surfaced, never silently zeroed; unsupported SBERT queries must fail safe (no wrong-category guess presented as confident); missing-period dashboard data must show a clear message rather than a blank or misleading chart.

**Testing expectations** — reproduce the Data tests / Model tests / Dashboard tests lists from Section 26 below (see DEV-015).

**Coding standards** — Python 3.10+, PEP8-consistent, type hints where practical, docstrings on public functions, config-driven (feature lists, target name, split dates, model params live in `configs/`, not hardcoded).

**Folder/file organization** — reproduce the Appendix B structure, extended with `specs/` (Section 8 below).

**Environment/configuration rules** — dependencies pinned via `requirements.txt` or `pyproject.toml`; config files for feature lists/target name/date split/model parameters; random seeds recorded where supported (Section 24, NFR "Portability").

**Important project constraints** — the "What the project will not do" list (Section 8.3) and the scope boundaries table (Section 5) reproduced verbatim.

**Source-of-truth hierarchy** — reproduce Section 1 of this prompt.

**Rules Claude must follow before changing code** — always re-read the relevant `specs/development/DEV-XXX.md` and any linked `specs/reference/REF-XXX.md` before implementing or modifying that area; never implement a feature not traceable to a spec; if a user request conflicts with a spec, flag it rather than silently complying.

**Rules for keeping documentation/specs synchronized with implementation** — reproduce Stage 7 above.

**Rules against inventing undocumented requirements** — reproduce Section 0 (Hard Rules) above.

---

## 4. `TODO.md` — REQUIRED STRUCTURE

Create a detailed, dependency-ordered checklist using `- [ ]` Markdown checkboxes. Do **not** produce a shallow 3-line checklist. Structure it by **Phase → Spec → Task**, referencing the DEV-ID that controls each task, so both you and the user can see status, dependencies, and which spec governs each item. Use this skeleton (fill in real sub-tasks derived from the specs in Section 5 — this is a minimum bar, expand it further where the source documentation implies more granular steps, e.g. Section 10's 9-step extraction workflow, Section 14.2's 6-step XGBoost training approach, Section 18's 6-step ranking process):

```
# TODO — Mechanic Service Demand Opportunity Prediction and Recommendation System

Legend: [ ] not started · [~] in progress · [x] complete · (depends: DEV-XXX)

## Phase 0 — Foundation & Specification System (governs: DEV-001)
- [ ] Initialize Git repository and GitHub remote
- [ ] Create Appendix-B-derived folder structure (see Section 8)
- [ ] Create Python environment + requirements.txt / pyproject.toml
- [ ] Create specs/, CLAUDE.md, TODO.md, DEV-PLAN.md, COVERAGE.md
- [ ] Create configs/ scaffolding (feature list, target name, split-date config)

## Phase 1 — Research & Data-Source Confirmation (governs: DEV-002)
- [ ] Create data source register (source name, URL, expected variables, geography, time range, file type)
- [ ] Identify and record DCS District Statistical Handbook editions to use
- [ ] Identify DMT statistics to use for cross-validation
- [ ] Evaluate candidate Kaggle datasets against research-question fit (record licence, geography, coverage, whether target represents real mechanic demand)
- [ ] Decide target-variable path: Preferred (real demand target) vs Fallback (proxy forecast) — record decision and rationale

## Phase 2 — Data Acquisition (governs: DEV-003)
- [ ] Download and store raw District Statistical Handbook files in data/raw (unedited)
- [ ] Download DMT publications into data/raw
- [ ] (If applicable) implement compliant web scraper respecting robots/ToS/rate limits
- [ ] Proof-of-concept: extract Kandy motorcycle registrations for several consecutive years into a small CSV
- [ ] Validate extraction structure/naming consistency on 2–3 additional districts before scaling
- [ ] Scale extraction to all 25 districts

## Phase 3 — Extraction, Normalization & Cleaning (governs: DEV-004)
- [ ] District name normalization to 25 canonical names
- [ ] Vehicle-category normalization (Motorcycle/Car/Three-wheeler canonical labels)
- [ ] Deduplication across handbook editions using documented source-priority rule
- [ ] Missing-value investigation & handling (never auto-zero)
- [ ] Outlier review against source publication
- [ ] Numeric conversion (strip commas/footnotes) while preserving raw values in archive
- [ ] Chronological sort per district/vehicle series
- [ ] Append source metadata (source_id, source_url, retrieved_date) to every row
- [ ] Write cleaned data to data/processed as CSV/Parquet
- [ ] Automated validation tests on processed dataset (see DEV-015 data tests)

## Phase 4 — Feature Engineering (governs: DEV-005)
- [ ] Lag features (reg_lag_1, reg_lag_2, demand_lag_1 if real target exists)
- [ ] Growth features (reg_growth_pct, year-on-year growth)
- [ ] Rolling trend features (rolling_mean_3, rolling_std_3)
- [ ] Time features (year, month, quarter, cyclic month sin/cos if monthly)
- [ ] District context features (population, population_density)
- [ ] Vehicle intensity feature (vehicles_per_1000_people)
- [ ] Enforce and unit-test the leakage rule (no feature may use data from period ≥ t)

## Phase 5 — Target & Dataset Assembly (governs: DEV-006)
- [ ] Finalize long-format district/time/vehicle_type table per Section 9 schema
- [ ] Freeze modelling dataset version and document it
- [ ] Create chronological train/validation/test split

## Phase 6 — Baseline + XGBoost (governs: DEV-007, DEV-008)
- [ ] Implement baseline (previous-period / moving-average) forecast
- [ ] Train XGBoost regressor on same target/split
- [ ] Hyperparameter tuning (n_estimators, learning_rate, max_depth, min_child_weight, subsample, colsample_bytree) using train/validation only
- [ ] Select model on validation performance; report final metrics on untouched test period
- [ ] Save final model + exact feature list + dataset version to model registry

## Phase 7 — LSTM Comparison Model (governs: DEV-009) — only if sequence density supports it
- [ ] Build sliding-window sequences (6–12 month lookback) per district/vehicle series
- [ ] Fit scaler on training data only
- [ ] Build model: input sequence layer, 1–2 LSTM layers, dropout, dense output
- [ ] Train with early stopping on validation loss + checkpoint best epoch
- [ ] Evaluate LSTM vs XGBoost on identical target/held-out periods; decide production model accordingly

## Phase 8 — SHAP Explainability (governs: DEV-010)
- [ ] Global SHAP summary across test set
- [ ] Per-district local SHAP contributions (top positive/negative factors)
- [ ] Verify SHAP output aligns with model feature schema (test)

## Phase 9 — Ranking & Recommendation Engine (governs: DEV-012)
- [ ] Implement 6-step ranking process from Section 18 (predict per district → sort → band via quantiles → SHAP reasons → top-N + trend + disclaimer)
- [ ] Implement opportunity bands (Low/Moderate/High/Very High) with documented threshold rule

## Phase 10 — SBERT NLP Query Layer (governs: DEV-011)
- [ ] Define category description embeddings (motorcycle/car/three-wheeler mechanic)
- [ ] Implement query embedding + similarity match to category
- [ ] Route matched category into prediction/ranking pipeline
- [ ] Implement safe-fallback behavior for unsupported/ambiguous queries (never silently guess)

## Phase 11 — Dashboard (governs: DEV-013)
- [ ] Vehicle type selector, period selector, district selector, top-N selector, NL query box
- [ ] Sri Lanka choropleth map (Plotly)
- [ ] Ranking table/bar chart
- [ ] Historical trend chart
- [ ] Forecast/predicted value panel
- [ ] SHAP explanation panel
- [ ] Data-source & model-version info panel
- [ ] Persistent disclaimer text (Appendix C.3 wording)

## Phase 12 — Evaluation & Experiment Tracking (governs: DEV-014)
- [ ] Regression metrics (MAE, RMSE, R²) vs baselines
- [ ] Ranking metrics (Spearman correlation, top-k overlap) where real target available
- [ ] Time-aware validation implemented (chronological holdout / walk-forward)
- [ ] MLflow or W&B experiment logging wired into training scripts
- [ ] Model registry populated (model, preprocessing objects, feature schema, eval report)

## Phase 13 — Testing (governs: DEV-015)
- [ ] Data tests (Section 26.1 list)
- [ ] Model tests (Section 26.2 list)
- [ ] Dashboard tests (Section 26.3 list)

## Phase 14 — Documentation & Viva Prep (governs: DEV-016)
- [ ] Technical documentation
- [ ] User guide
- [ ] Model evaluation / error-analysis report
- [ ] Viva/presentation material (use Section 32 talking points)

## Phase 15 — Deployment/Reproducibility Readiness (governs: DEV-017)
- [ ] requirements.txt / pyproject.toml finalized and pinned
- [ ] README with setup + run instructions
- [ ] Reproducibility check: same dataset version + config reproduces same trained model within normal nondeterminism
```

Expand every leaf item above into more granular sub-tasks as you build out each `specs/development/DEV-XXX.md` file — the spec is the source of truth for the detailed task breakdown; `TODO.md` should mirror it at checklist granularity, not duplicate its prose.

---

## 5. DEVELOPMENT SPECIFICATIONS — `specs/development/`

Create one file per ID below. Each file must contain: Specification ID, Feature/Module Name, Purpose, Background/Context, Related Requirements (FR-xx/NFR references), User Roles, Preconditions, User Stories/Use Cases, Functional Requirements, Business Rules, Data Requirements, Database/Schema Changes, API Requirements (if any), Backend Behavior, Frontend Behavior (if any), UI States (if any), Validation, Permissions, Error Cases, Edge Cases, Security Considerations, Dependencies (on other DEV/REF IDs), Testing Requirements, Acceptance Criteria, Definition of Done.

- **DEV-001 — Project Foundation, Environment & Repository Structure.** Repo init, folder skeleton (Section 8), Python environment, dependency pinning, config scaffolding, GitHub setup. Depends on: none.
- **DEV-002 — Data Source Register & Target-Variable Decision.** The source register (Section 7, Section 10 step 1), evaluation criteria for candidate sources/Kaggle datasets (Section 7.3), and the formal Preferred-vs-Fallback target decision (Section 8). Depends on: DEV-001.
- **DEV-003 — Data Acquisition & Extraction Pipeline.** DCS handbook extraction, DMT cross-validation data, optional compliant web scraping, the 9-step acquisition workflow (Section 10), and the Kandy proof-of-concept → multi-district scale-up approach (Section 10.1). Depends on: DEV-002.
- **DEV-004 — Data Cleaning, Normalization & Validation.** District/vehicle-category normalization, dedup rules, missing-value policy, outlier review, numeric conversion, chronological sorting, source-metadata attachment, automated dataset validation tests (Section 11, Section 26.1). Depends on: DEV-003, REF-002.
- **DEV-005 — Feature Engineering Pipeline.** Lag/growth/rolling/time/context/intensity features and the strict no-leakage rule (Section 12). Depends on: DEV-004.
- **DEV-006 — Modelling Dataset Assembly & Target Definition.** Long-format district/time/vehicle_type table assembly (Section 9), dataset freezing/versioning, chronological train/val/test split. Depends on: DEV-005, REF-001.
- **DEV-007 — Baseline Forecasting Model.** Previous-period and moving-average baselines used to prove ML value-add (Section 23.1). Depends on: DEV-006.
- **DEV-008 — XGBoost Primary Prediction Model.** Inputs, training/tuning approach, chronological validation, model + feature-list + dataset-version persistence (Section 14). Depends on: DEV-007.
- **DEV-009 — LSTM Time-Series Comparison Model.** Sequence construction, model architecture, training regime, fair comparison against XGBoost; explicitly conditional on sufficient sequence density (Section 15). Depends on: DEV-006 (may run in parallel with DEV-008; ranking/dashboard depend only on whichever model is selected as production).
- **DEV-010 — SHAP Explainability Module.** Global + local explanations wired to XGBoost (and LSTM if applicable) (Section 17). Depends on: DEV-008.
- **DEV-011 — SBERT Natural-Language Query Module.** Query embedding, category-description matching, safe fallback, routing into the prediction pipeline (Section 16). Depends on: DEV-008 (needs a working prediction pipeline to route into), REF-003.
- **DEV-012 — District Ranking & Recommendation Engine.** The deterministic 6-step ranking/recommendation process, opportunity bands, uncertainty/limitation notes (Section 18). Depends on: DEV-008, DEV-010.
- **DEV-013 — Streamlit + Plotly Dashboard.** All controls and panels listed in Section 19, wired to DEV-008/009/010/011/012 outputs. Depends on: DEV-010, DEV-011, DEV-012.
- **DEV-014 — Model Evaluation & Experiment Tracking.** Baselines-vs-model comparison, regression + ranking metrics, time-aware validation methodology, MLflow/W&B integration, model registry (Sections 23, 24). Depends on: DEV-008 (and DEV-009 where applicable).
- **DEV-015 — Testing Suite.** Data tests, model tests, dashboard tests exactly as enumerated in Section 26. Cross-cutting; write incrementally alongside DEV-004 through DEV-013, consolidated here.
- **DEV-016 — Documentation, Reporting & Viva Preparation.** Technical documentation, user guide, evaluation/error-analysis report, viva talking points (Sections 29, 32). Depends on: all prior DEV specs substantially complete.
- **DEV-017 — Reproducibility & Deployment Readiness.** Dependency pinning, config files, README, reproducibility verification (Section 22 "Portability", Section 24). Depends on: DEV-014.

Do not create additional development specs purely to raise the count, and do not merge unrelated modules into one spec (e.g., do not merge SHAP and SBERT — they are functionally distinct per Section 13's component table).

---

## 6. REFERENCE SPECIFICATIONS — `specs/reference/`

These hold stable, project-wide information that would otherwise be duplicated across development specs.

- **REF-001 — Data Dictionary & Dataset Schema.** Reproduce Appendix A verbatim (columns, types, descriptions, required/conditional/recommended/optional/engineered status) plus the Section 9 example table.
- **REF-002 — District & Vehicle-Category Canonical Lists / Normalization Rules.** The 25 official Sri Lankan district names (to be enumerated/confirmed during DEV-004) and canonical vehicle-category labels (Motorcycle, Car, Three-wheeler) with normalization mapping rules from Section 11.
- **REF-003 — ML Component Architecture Reference.** The component/role/priority table from Section 13, plus the end-to-end architecture flow from Section 20, plus the "why each component" rationale from Section 32.3–32.6 (why XGBoost, why LSTM, why SBERT, why SHAP) — useful both for implementation and for viva prep.
- **REF-004 — Non-Functional Requirements & System Constraints.** Reproduce Section 22 in full (reproducibility, explainability, usability, performance, maintainability, data integrity, security/privacy, portability) plus the scope boundaries table from Section 5.
- **REF-005 — Ethical, Legal & Data-Governance Rules.** Reproduce Section 28 in full.
- **REF-006 — Risks, Assumptions & Limitations.** Reproduce the full risk table from Section 27.
- **REF-007 — Domain Rationale & Terminology.** Reproduce Sections 2, 6 (why vehicle data signals mechanic opportunity; new registrations vs. vehicle population; correct vs. incorrect wording examples).
- **REF-008 — Technology Stack Reference.** Reproduce the Section 30 stack table verbatim, plus the folder structure from Appendix B.
- **REF-009 — Architecture Decision Records (ADRs).** Empty at project start; every time an implementation decision is made where the documentation is silent (Section 0 rule), log it here with date, decision, alternatives considered, and rationale.

Avoid duplicating REF content inside DEV specs — DEV specs should link to the relevant REF-ID rather than re-pasting the table.

---

## 7. DEVELOPMENT PLAN — `specs/development/DEV-PLAN.md`

Create an index that shows build order and dependencies as a simple ordered list or dependency graph, grouped into these stages (mirrors Section 25 of the source doc, mapped to DEV-IDs):

1. Foundation & setup — DEV-001
2. Data-source confirmation & target decision — DEV-002
3. Data acquisition — DEV-003
4. Extraction, cleaning & validation — DEV-004
5. Feature engineering — DEV-005
6. Dataset assembly & split — DEV-006
7. Baseline + XGBoost (core prediction path) — DEV-007, DEV-008
8. LSTM comparison (conditional on data density) — DEV-009
9. Explainability (SHAP) — DEV-010
10. NLP query layer (SBERT) — DEV-011
11. Ranking & recommendation engine — DEV-012
12. Dashboard (Streamlit/Plotly) — DEV-013
13. Evaluation & experiment tracking — DEV-014 (ongoing from Phase 7 onward, consolidated here)
14. Testing — DEV-015 (ongoing, consolidated here)
15. Documentation & viva prep — DEV-016
16. Reproducibility & deployment readiness — DEV-017

State explicitly, as the source documentation does (Section 25 closing note): *"The highest-priority path is real data → target definition → clean dataset → baseline/XGBoost → SHAP → ranking → dashboard. LSTM and SBERT should not delay the core model if the data pipeline is still incomplete."* Encode this as an explicit note in `DEV-PLAN.md` so Claude Code does not block core delivery on LSTM/SBERT.

---

## 8. FOLDER STRUCTURE TO CREATE

Base the repository layout on Appendix B of the source documentation, extended with the SpecKit `specs/` directory:

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

---

## 9. IMPLEMENTATION QUALITY BAR

Treat this as a Final Project deliverable, not a prototype:
- Maintainable, modular architecture with clear separation of concerns (extraction / cleaning / features / models / explainability / nlp / recommendation / dashboard, per Appendix B).
- Reusable components; no copy-pasted logic across district/vehicle-category handling.
- Input validation and defensive handling of missing/malformed source data at every ingestion point.
- Config-driven behavior (feature lists, target name, split dates, model hyperparameters) rather than hardcoded values.
- Database/data integrity: every processed row must be traceable to a `source_id` (Section 26.1).
- Authorization: none required (single-user academic dashboard) — do not add complexity here.
- Responsive-enough Streamlit UI; consistent UX across panels (same prediction values feed both the ranking table and the map, per Section 26.3).
- Testing per DEV-015/Section 26.
- Environment/config management via `requirements.txt`/`pyproject.toml` and `configs/`.
- Light logging for the extraction and training pipelines (so failures during scheduled/batch runs are diagnosable) — this is a reasonable industry-standard addition where the documentation is silent; log it in REF-009 as an ADR.
- Avoid unjustified enterprise complexity (no message queues, no container orchestration, no multi-service architecture) unless the user explicitly asks for it later.

---

## 10. STAGE 3 COVERAGE CHECK — REQUIREMENTS TO TRACE

Ensure `specs/COVERAGE.md` maps every one of these to a DEV/REF spec or TODO item:
- FR-01 … FR-12 (Section 21 below)
- NFR list (Section 22 below): reproducibility, explainability, usability, performance, maintainability, data integrity, security/privacy, portability
- Scope boundaries table (Section 5 below)
- Data acquisition workflow steps 1–9 (Section 10 below)
- Data cleaning rules (Section 11 below)
- Feature engineering rules + leakage rule (Section 12 below)
- XGBoost training steps 1–6 (Section 14.2 below)
- LSTM sequence/model/comparison rules (Section 15 below)
- SBERT interaction steps 1–5 (Section 16.1 below)
- SHAP global/local explanation requirements (Section 17 below)
- Ranking engine steps 1–6 (Section 18 below)
- Dashboard controls and panels (Section 19 below)
- Model evaluation strategy (Section 23 below)
- Experiment tracking/reproducibility items (Section 24 below)
- Testing strategy — data/model/dashboard tests (Section 26 below)
- Risks/limitations table (Section 27 below) — as documented cautions, not defects to "fix away"
- Ethical/legal/governance rules (Section 28 below)
- Deliverables list (Section 29 below)
- Data dictionary (Appendix A below)
- Folder structure (Appendix B below)
- Disclaimer wording (Appendix C.3 below) — must appear on every recommendation-bearing dashboard view

---

# PROJECT SOURCE DOCUMENTATION (extracted in full from the uploaded Final Project Documentation — do not simplify, remove, or reinterpret any requirement below)

## Executive Summary
This project will develop a machine-learning-based decision-support system for freelance mechanics in Sri Lanka. The system will use real vehicle-registration statistics and other relevant district-level data to identify where mechanic-service opportunity is likely to be stronger. The first implementation will focus on mechanics, with motorcycles as the clearest initial use case. Cars and three-wheelers can also be included where reliable data is available.

The central idea is that vehicles registered and operating in a district become part of the local servicing and repair market. New vehicles enter scheduled maintenance cycles, while older vehicles continue to require repairs, parts replacement and routine servicing. Vehicle statistics therefore provide a meaningful signal for analysing the size and direction of the mechanic service market. The system will not claim that a registration count is equal to a mechanic job count; instead, it will use those real observations as model features or as a clearly labelled service-opportunity proxy when direct job-demand labels are not available.

XGBoost is the primary prediction model because the core dataset is expected to be tabular and will contain district, time, vehicle category and engineered trend features. LSTM is used as a time-series model when the available data contains enough sequential observations. SHAP explains why a prediction is high or low. SBERT provides an NLP layer that can understand a natural-language user request such as "I repair motorcycles; which district looks best next month?" and map that query to the correct prediction category. Streamlit and Plotly provide the dashboard, maps, trend charts and recommendation interface.

The project will use real data collected from official government publications, Kaggle where appropriate, and legally permitted public web sources. Fabricated rows or invented mechanic-job labels will not be used for training. Data provenance, extraction dates and source references will be preserved so that the final model is reproducible and defensible in the viva.

## 2. Project Definition
**Working title:** Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka.

The system collects and integrates real vehicle and district data, models historical patterns, predicts a future service-demand signal or opportunity indicator, ranks Sri Lankan districts, explains the reasons for each ranking, and presents the results in an interactive web application for freelance mechanics.

**2.1 Primary user:** A freelance or independent mechanic who wants data-driven guidance about where service and repair opportunities may be stronger. First scenario: motorcycle mechanic. Same structure also supports car mechanics and three-wheeler mechanics.

**2.2 Core user question:** "For the selected vehicle category and future period, which districts show the strongest predicted service opportunity, and what factors caused those districts to rank highly?"

## 3. Problem Statement
Freelance mechanics often make location and work-planning decisions using personal experience, customer referrals and informal knowledge. Public statistics exist about vehicle registrations and vehicle populations, but those statistics are not normally transformed into an explainable district-level decision-support tool for mechanics.

The technical challenge is that direct public records of informal mechanic jobs, bookings or completed repair orders may be limited. A scientifically valid system therefore needs to separate two concepts: observed mechanic-demand labels and proxy indicators. If a real service-demand target is available, the model can predict that target. If such a target is not available, the system should predict a real observable proxy, such as future vehicle registrations or a related service-market indicator, and present the output as an opportunity ranking rather than as an exact number of mechanic jobs.

The project addresses this problem by building a reproducible pipeline that converts real district and vehicle statistics into a predictive, explainable and user-friendly ranking system.

## 4. Aim, Objectives and Research Questions
**4.1 Aim:** To develop an explainable machine-learning system that uses real Sri Lankan vehicle and district data to predict and rank mechanic-service opportunity by district and provide practical recommendations through an interactive dashboard.

**4.2 Objectives:**
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

**4.3 Research Questions:**
1. Can real vehicle-registration and district-level data produce a useful future signal for mechanic service opportunity?
2. Which variables contribute most strongly to district-level predictions?
3. Does XGBoost outperform simple baselines on the chosen target?
4. When sufficient sequential data is available, does LSTM provide additional forecasting value?
5. Can SHAP explanations make the district recommendations understandable and defensible?
6. Can an SBERT-based query layer make the system easier for a mechanic to use without changing the underlying prediction logic?

## 5. Project Scope and Boundaries
| Area | Included in the project | Boundary / rule |
|---|---|---|
| Domain | Freelance mechanic service opportunity in Sri Lanka | The core implementation focuses on mechanics. |
| Initial vehicle category | Motorcycles | Cars and three-wheelers can be added if data quality is sufficient. |
| Geography | Sri Lankan administrative districts | The design supports all 25 districts, subject to consistent data availability. |
| Time | Yearly or monthly historical observations | Final granularity is determined by the best common resolution across sources. |
| Prediction output | Relative demand/opportunity score, forecast, or district ranking | Exact job counts are only allowed if a genuine job-demand target is available. |
| Data | Real observed data from government, Kaggle or permitted public sources | No fabricated rows or invented labels for model training. |
| Interface | Web dashboard for analysis and recommendation | No mobile application is required for the first release. |
| Expansion | Other freelance service categories | Only considered after the mechanic system is complete and validated. |

## 6. Domain Rationale: Why Vehicle Data Can Support Mechanic Opportunity Analysis
A vehicle that is registered and used in a district becomes part of that district's service market. New vehicles require scheduled maintenance according to manufacturer recommendations, while older vehicles continue to create demand for repairs, tyre work, electrical work, replacement parts and general maintenance. Vehicle registrations and total vehicle population can help describe the potential market available to mechanics.

**6.1 New registrations:** measures vehicles registered during a specific reporting period. A large increase does not mean the district has the same number of new mechanic jobs — it means the serviceable vehicle base has grown, which can influence future maintenance opportunity.

**6.2 Total vehicle population:** different from new registrations. A district may have few new registrations but a large stock of older vehicles requiring more repair work. Include total vehicle population by type when reliable figures are available.

**6.3 Correct interpretation:**
- Good: "Kandy shows a high predicted motorcycle-service opportunity for the selected period."
- Good: "Kandy ranks first because recent motorcycle registrations and vehicle-stock indicators are relatively strong."
- Avoid: "Kandy will definitely have 1,240 mechanic jobs," unless a real job-count label supports that statement.

## 7. Data Collection Strategy
Prioritise official and traceable sources. Every extracted table must be accompanied by source name, publication title, page/table number where possible, reporting period, download date and source URL. Preserve the raw file before any cleaning so every processed value can be traced to its origin.

**7.1 Department of Census and Statistics — District Statistical Handbooks.** Inspect the Transport chapter for tables such as "New Vehicle Registrations." Handbook editions may contain several historical years — record exact observation years from each table, not assumed from the handbook title. Capture at least: district, observation year, vehicle category, registration count, handbook edition, table/page reference, source URL. Deduplicate repeated values across editions using source priority rules.

**7.2 Department of Motor Traffic.** National vehicle-population/registration context for cross-checking totals, trend analysis, and validating district-level extracted values. A national table must not be treated as district-level data unless the publication explicitly contains a district breakdown.

**7.3 Kaggle.** Usable when it provides a real dataset relevant to vehicle servicing, repair demand, maintenance behaviour or another suitable target. Before use, record original source, geography, licence, time coverage, variables, row count, missing-value profile, and whether the target genuinely represents mechanic demand. Do not use a dataset simply because it is convenient — it must match the research question.

**7.4 Web scraping.** If permitted, respect website terms, robots guidance, request-rate limits and privacy. Store source URLs and extraction timestamps. Do not collect personal information when aggregate statistics suffice.

**7.5 Supporting district features:** population/population density; total vehicle population by type where available; historical new registrations by type; year-on-year registration growth; district-level income/economic indicators where clearly related to vehicle ownership/service capacity; road/transport indicators where available and justifiable. Other real features only with a clear domain rationale and consistent coverage. Rainfall is not a priority for the first implementation.

## 8. Prediction Target and Scientific Framing
**8.1 Preferred path — real mechanic-demand target.** If a real dataset contains repair requests, service bookings, completed jobs, workshop visits, maintenance transactions or another credible mechanic-demand signal, that observed value becomes the target; vehicle registrations/stock/district features become predictors.

**8.2 Fallback path — forecast a real service-market proxy.** If no suitable mechanic-demand target can be obtained, do not invent one. Forecast a real observable vehicle-market variable (e.g., future motorcycle registrations) and convert the forecast into a relative opportunity ranking with explicit wording that it is a proxy-based indicator, not a measured number of mechanic jobs.

**8.3 What the project will not do:**
- Create arbitrary job counts to make the dataset larger.
- Assign random "High/Medium/Low" demand labels and train a classifier on those labels.
- Claim causal relationships when the model only identifies predictive associations.
- Use future-year features to predict an earlier year.
- Present a proxy score as if it were a government-recorded mechanic-demand statistic.

## 9. Proposed Dataset Design
One row per district, time period and vehicle category (long format).

| Field | Example | Purpose |
|---|---|---|
| district | Kandy | Geographic unit |
| year | 2024 | Time index |
| month | 03 (if available) | Monthly time index |
| vehicle_type | Motorcycle | Mechanic category |
| new_registrations | 12450 | Observed new registrations |
| vehicle_population | 185000 | Existing vehicle stock, if available |
| population | 1480000 | District context |
| reg_lag_1 | 11780 | Previous period registrations |
| reg_lag_2 | 10920 | Two-period lag |
| reg_growth_pct | 5.69 | Growth feature |
| rolling_mean_3 | 11600 | Smoothed historical trend |
| target_value | Observed real target | Training label |
| source_id | DCS_Kandy_2025_T9_4 | Data provenance |

When monthly data does not exist consistently, prefer a clean yearly dataset over pretending to have monthly detail. Granularity is determined by the real source data.

## 10. Data Acquisition and Extraction Workflow
1. Create a source register before downloading data: source name, URL, expected variables, geography, time range, file type.
2. Download and store the original PDF/CSV/XLSX/HTML snapshot in data/raw without editing it.
3. Extract the required table using a repeatable method (table extraction / carefully validated parser; source-specific extraction rules if structure changes across handbooks).
4. Normalize district names and vehicle-category names into a controlled lookup table.
5. Convert numeric strings to numeric values; preserve missing values as missing, not zero.
6. Validate extracted totals against the source table and, where possible, national DMT statistics.
7. Append source metadata to each observation.
8. Write cleaned observations to a standard CSV or Parquet file in data/processed.
9. Run automated validation tests before using the dataset for modelling.

**10.1 Recommended proof of concept:** Begin with Kandy motorcycle registrations, extract several consecutive years into a small CSV. Once correct, repeat for a few additional districts to confirm table structure/naming consistency. Only then scale across all districts.

## 11. Data Cleaning and Preprocessing
- District normalisation: map spelling variations to the 25 official district names.
- Vehicle-category normalisation: map "Motor Cycle," "Motorcycle," etc. to one canonical category.
- Duplicate handling: retain one observation per district-year across multiple handbook editions using a documented source-priority rule.
- Missing values: investigate why the value is missing; do not automatically convert blanks to zero.
- Outliers: compare extreme values against the source publication before removing/winsorising.
- Numeric conversion: remove commas/footnote markers while preserving original raw text in the source archive.
- Time sorting: sort each district/vehicle category chronologically before constructing lag features.
- Scaling: XGBoost normally does not require feature standardisation; LSTM inputs usually benefit from scaling fitted only on the training period.
- Categorical encoding: one-hot or appropriate representation for district/vehicle type if the model needs it.
- Train-test separation: perform the time split before any transformation that could learn information from future periods.

## 12. Feature Engineering
Convert raw statistics into variables representing recent level, direction and momentum. Features must only use information available before the prediction period.

| Feature group | Examples | Reason |
|---|---|---|
| Current/lagged level | new_registrations_lag_1, vehicle_population | Represents size of recent vehicle market |
| Growth | year_on_year_growth, change_from_lag_2 | Captures acceleration/decline |
| Rolling trend | rolling_mean_3, rolling_std_3 | Reduces noise, describes stability |
| Time | year, month, quarter, cyclic month sin/cos | Represents temporal structure when monthly data exists |
| District context | population, population_density | Controls for district size |
| Vehicle intensity | vehicles_per_1000_people | Normalises vehicle counts by population |
| Category | motorcycle/car/three-wheeler | Allows one model or separate models by vehicle type |
| Target lags | demand_lag_1 if a real demand target exists | Uses recent observed demand without leaking future values |

**12.1 Leakage rule:** When predicting year t, every feature must be computable using information available before year t. A feature calculated using year t+1 or the final dataset average would create leakage and make the model appear more accurate than it really is.

## 13. Machine Learning Strategy
| Component | Role | Priority |
|---|---|---|
| Baseline | Simple previous-period or moving-average forecast | Required |
| XGBoost | Primary tabular prediction model | Core |
| LSTM | Sequence/time-series forecasting comparison | Planned when data supports it |
| SHAP | Explain XGBoost predictions | Core |
| SBERT | Understand user queries and match categories | Interface/NLP layer |
| Ranking engine | Sort districts and create opportunity recommendations | Core |
| Streamlit + Plotly | Present results interactively | Core |

## 14. XGBoost — Primary Tabular Prediction Model
XGBoost is the primary model because the expected dataset is mainly tabular; it learns nonlinear relationships and feature interactions without requiring a very large dataset.

**14.1 Inputs:** lagged vehicle registrations; vehicle population where available; registration growth and rolling statistics; district population/density; vehicle type; time features; lagged observed demand if a real demand label exists.

**14.2 Training approach:**
1. Create a chronological train/validation/test split.
2. Train a simple baseline first.
3. Train an XGBoost regressor on the same target and time split.
4. Tune parameters (n_estimators, learning_rate, max_depth, min_child_weight, subsample, colsample_bytree) using only training/validation periods.
5. Select the model using validation performance and report final performance on the untouched test period.
6. Save the final model together with the exact feature list and dataset version.

**14.3 Why XGBoost fits the project:** multiple district-level features, potential missing values, nonlinear effects, limited historical data compared with deep-learning tasks. Practical, defendable primary model; integrates naturally with SHAP.

## 15. LSTM — Time-Series Forecasting Model
Used to model sequential patterns when the final dataset contains enough observations per district/vehicle category; most meaningful with monthly or another dense resolution. If only a small number of yearly observations exist, treat LSTM results cautiously and possibly as an experimental comparison only.

**15.1 Sequence construction:** for monthly data, sliding window of previous 6 or 12 months to predict the next month; sequences built separately within a district/vehicle series or via a well-defined multi-series design; scaling parameters fitted on training data only.

**15.2 Model design:** input sequence layer; one or two LSTM layers; dropout to reduce overfitting; dense output layer for the forecast; early stopping on validation loss; model checkpoint for the best validation epoch.

**15.3 Comparison with XGBoost:** LSTM and XGBoost must predict the same target over the same held-out periods before comparison. A more complex model is not automatically better — keep the model that performs reliably and can be explained.

## 16. SBERT — Natural-Language Query Understanding
Converts a user's natural-language question into an embedding and matches it to the correct mechanic/vehicle category. SBERT is NOT the model that predicts district demand, and it is NOT used as a free-form explanation generator.

**16.1 Example interaction:** User query: "I repair motorcycles. Which district should I consider next month?"
1. SBERT embeds the query.
2. The embedding is compared with predefined category descriptions ("motorcycle mechanic," "car mechanic," "three-wheeler mechanic").
3. The highest semantic match selects the appropriate prediction pipeline.
4. The ranking engine returns the top districts.
5. SHAP provides model-based reasons for the recommendation.

**16.2 Why this is useful:** makes the dashboard easier to use without changing the scientific prediction model; gives the project a clear, technically correct NLP component that's easy to demonstrate in the viva.

## 17. SHAP — Model Explainability
Explains how individual variables influence XGBoost predictions.

**17.1 Global explanations:** a global SHAP summary shows the most influential features across the full test dataset (e.g., lagged motorcycle registrations, vehicle population, registration growth, district population may be strongest — actual result must come from the trained model, not be assumed in advance).

**17.2 Local explanations:** for a selected district, display the largest positive and negative SHAP contributions (example: "The prediction for Kandy is increased by strong recent motorcycle-registration growth and a high recent registration level, while another feature slightly reduces the score.").

**17.3 Viva value:** shows the model is not a black box; makes suspicious predictions easier to investigate; connects the recommendation to real input variables; supports discussion of feature importance, limitations and model behaviour.

## 18. Recommendation and District Ranking Engine
Deterministic, traceable, based on model output — must not invent narrative explanations unsupported by features/SHAP values.
1. Receive the selected vehicle category and prediction period.
2. Generate the model prediction for each eligible district.
3. Sort districts from highest to lowest predicted target/service-opportunity value.
4. Optionally convert predictions to transparent bands (Low, Moderate, High, Very High) with thresholds based on quantiles or a documented training-data rule.
5. Use SHAP to extract the strongest reasons for the top-ranked districts.
6. Return the top three or top five districts together with trend context and an uncertainty/limitation note.

**18.1 Example recommendation:** "For motorcycle mechanics in the selected period, Kandy is ranked as a high-opportunity district. The main model factors are strong recent motorcycle registrations and positive registration growth. This is a model-based opportunity estimate and does not represent a guaranteed number of jobs."

## 19. Dashboard and User Experience
Built with Streamlit; Plotly provides interactive charts and maps. Must be simple enough for a mechanic to understand without ML knowledge.

**19.1 Main controls:** vehicle type selector; prediction year/month selector; district selector for detailed analysis; top-N recommendation selector; optional natural-language query box powered by SBERT.

**19.2 Main dashboard panels:** Sri Lanka choropleth map showing predicted opportunity by district; top district ranking table or bar chart; historical registration trend for the selected district/vehicle type; forecast/predicted value for the selected period; SHAP explanation panel showing main positive/negative factors; data-source and model-version information; clear note explaining that opportunity estimates are not guaranteed job counts.

## 20. End-to-End System Architecture
Architecture flow: real data → extraction and validation → district/time/vehicle feature table → feature engineering → XGBoost and LSTM modelling → SHAP explanations → district ranking and recommendation → Streamlit/Plotly dashboard. SBERT operates at the user-interaction layer to understand natural-language requests and route them to the correct prediction category.

## 21. Functional Requirements
| ID | Functional requirement |
|---|---|
| FR-01 | The system shall import real vehicle and district data from documented sources. |
| FR-02 | The system shall clean and normalize district and vehicle-category names. |
| FR-03 | The system shall create lag, growth and trend features without future leakage. |
| FR-04 | The system shall train and load an XGBoost prediction model. |
| FR-05 | The system shall train an LSTM model when the selected dataset supports sequence modelling. |
| FR-06 | The system shall calculate SHAP explanations for XGBoost predictions. |
| FR-07 | The system shall rank districts for a selected vehicle category and period. |
| FR-08 | The system shall display results on an interactive Sri Lanka district map. |
| FR-09 | The system shall display historical trends and top recommendations. |
| FR-10 | The system shall accept a natural-language query and use SBERT to map it to a supported category. |
| FR-11 | The system shall display source, model and limitation information. |
| FR-12 | The system shall export selected results or provide a reproducible analysis view if time permits. |

## 22. Non-Functional Requirements
- Reproducibility: the same dataset version and configuration should reproduce the same trained model within normal library-level nondeterminism.
- Explainability: each top recommendation should have model-based explanatory factors.
- Usability: a user should be able to choose a vehicle category and view recommendations without understanding ML terminology.
- Performance: dashboard predictions for a pre-trained model should return within a few seconds on a normal laptop.
- Maintainability: extraction, preprocessing, modelling and dashboard code should be separated into modules.
- Data integrity: processed values must be traceable to a raw source.
- Security/privacy: do not collect unnecessary personal data.
- Portability: the project should run from a documented Python environment using requirements.txt or pyproject.toml.

## 23. Model Evaluation Strategy
**23.1 Baselines:** previous-period value, moving average, simple linear regression when appropriate — to demonstrate whether the ML model adds predictive value.

**23.2 Regression metrics:** MAE (average absolute prediction error); RMSE (penalises larger errors more strongly); R² (proportion of target variance explained, interpreted carefully on small datasets).

**23.3 Ranking metrics:** where a real target is available — Spearman rank correlation, top-k overlap, whether true highest-demand districts appear in the predicted top group.

**23.4 Time-aware validation:** random train/test splitting is not appropriate for predicting future values. Use chronological holdout, walk-forward validation, or another time-aware approach. Districts can be grouped within each time period so the model is tested on future periods rather than random historical rows.

**23.5 LSTM evaluation:** must be evaluated on the same target and comparable future periods as XGBoost. Report whether the additional complexity produces a meaningful improvement; if not, XGBoost remains the recommended production model.

## 24. Experiment Tracking, Reproducibility and Version Control
- GitHub — source code, extraction scripts, notebooks, dashboard code, documentation.
- MLflow or Weights & Biases — model parameters, metrics, dataset version, artefacts, selected model runs.
- requirements.txt or pyproject.toml — exact Python dependencies.
- Configuration files — feature lists, target name, date split, model parameters.
- Data source register — source URL, date retrieved, publication/table reference, licence/usage notes.
- Random seeds — recorded where supported.
- Model registry folder — final model, preprocessing objects, feature schema, evaluation report.

AI-assisted coding tools may be used as development aids, but every final module should be tested, documented and understood well enough to explain in the viva.

## 25. Implementation Plan
| Phase | Main work | Deliverable | Suggested duration |
|---|---|---|---|
| 1. Research and data-source confirmation | Confirm target, source coverage and extraction method | Data-source register + target decision | 1 week |
| 2. Data collection | Download district handbooks, DMT data and approved additional datasets | Raw source archive | 2 weeks |
| 3. Extraction and cleaning | Extract tables, normalize names, deduplicate, validate | Clean base dataset | 2 weeks |
| 4. Feature engineering | Create lags, growth, rolling features and context variables | Feature matrix | 1 week |
| 5. Baseline + XGBoost | Train baseline, tune XGBoost, evaluate chronologically | Primary model + metrics | 2 weeks |
| 6. LSTM | Create sequences and train time-series model if data supports it | LSTM comparison | 2 weeks |
| 7. SHAP + ranking | Build explanations and district ranking rules | Explainability + recommendation module | 1 week |
| 8. SBERT | Implement semantic query-to-category matching | NLP query module | 1 week |
| 9. Dashboard | Build Streamlit/Plotly application and map | Working web dashboard | 2 weeks |
| 10. Testing + tracking | Integration tests, experiment tracking, error analysis | Test and experiment report | 1 week |
| 11. Documentation + viva | Final report, user guide, presentation and demo prep | Submission package | 2 weeks |

The order can be compressed if the schedule is shorter. Highest-priority path: real data → target definition → clean dataset → baseline/XGBoost → SHAP → ranking → dashboard. LSTM and SBERT should not delay the core model if the data pipeline is still incomplete.

## 26. Testing Strategy
**26.1 Data tests:** no unknown district names after normalization; no duplicated district-time-vehicle key unless explicitly justified; numeric fields contain valid ranges; observation years match source tables; missing values are reported, not silently replaced; source_id exists for every processed row.

**26.2 Model tests:** model receives the expected feature columns and order; no future-period feature leakage; saved model reloads and produces the same prediction shape; predictions checked for impossible values when the target is non-negative; SHAP output aligns with the model feature schema.

**26.3 Dashboard tests:** filters correctly update all panels; unsupported SBERT queries produce a safe fallback rather than a wrong category; missing-period data displays a clear message; ranking table and map use the same prediction values; model limitation text is visible to the user.

## 27. Risks, Assumptions and Limitations
| Risk / limitation | Impact | Mitigation |
|---|---|---|
| No direct mechanic-demand target | Cannot claim exact job demand | Use a real observed target if found; otherwise forecast a clearly labelled service-market proxy |
| Short annual time series | LSTM may overfit or be unjustified | Prefer XGBoost; use LSTM only when sequence length is sufficient |
| Different handbook formats | Extraction scripts may fail across districts/years | Use source-specific parsers and manual validation samples |
| New registrations ignore older vehicles | Can underestimate mature repair markets | Add total vehicle stock where available and state the limitation |
| Data publication lag | Latest prediction may rely on older official observations | Show data cut-off date and update the dataset when new releases appear |
| Proxy correlation is not causation | High registrations do not guarantee mechanic jobs | Use cautious wording and explain the statistical framing |
| Small dataset / many features | Overfitting risk | Limit feature count, use time-aware validation and regularisation |
| Geographic aggregation | District-level patterns hide local town differences | State that recommendations are district-level, not workshop-level |
| SBERT misclassification | User query could map to wrong category | Show selected category and allow manual correction |
| Web-source changes | Scraper may break or terms may change | Prefer official downloadable files; log source version and date |

## 28. Ethical, Legal and Data-Governance Considerations
- Use aggregated public statistics wherever possible.
- Do not collect personal vehicle-owner information for this project.
- Respect website terms and access limits when scraping.
- Record dataset licences and attribution requirements.
- Do not present model output as a guarantee of income, employment or customer availability.
- Disclose data cut-off dates and major missing-data limitations.
- Keep source files and transformations reproducible so results can be audited.
- Avoid unfairly labelling a district as "bad"; use neutral opportunity bands and explain that model output is probabilistic.

## 29. Project Deliverables
1. A documented real-data collection and extraction pipeline.
2. A cleaned district-time-vehicle dataset with provenance fields.
3. A baseline forecasting model.
4. A trained XGBoost primary model.
5. An LSTM comparison model when data resolution supports sequence modelling.
6. A SHAP explainability module.
7. An SBERT natural-language query matching module.
8. A district ranking and recommendation engine.
9. A Streamlit/Plotly dashboard with map, trends and explanations.
10. MLflow or W&B experiment history and a GitHub repository.
11. Model evaluation and error-analysis report.
12. Technical documentation, user guide and viva/presentation material.

## 30. Final Technology Stack
| Layer | Technology | Purpose |
|---|---|---|
| Programming | Python 3.10+ | Main implementation language |
| Data processing | Pandas, NumPy | Cleaning, transformation, feature engineering |
| Tabular ML | XGBoost, scikit-learn | Primary model, metrics, validation, baselines |
| Deep learning | TensorFlow / Keras | LSTM model |
| NLP | sentence-transformers / SBERT | Semantic query understanding |
| Explainability | SHAP | Feature-attribution explanations |
| Dashboard | Streamlit | Web application |
| Visualisation | Plotly | Interactive charts and choropleth maps |
| Experiment tracking | MLflow or Weights & Biases | Parameters, metrics and artefacts |
| Version control | Git + GitHub | Code history and collaboration |
| Development | VS Code / Jupyter Notebook | Implementation and analysis |
| Data storage | CSV / Parquet; optional SQLite | Processed dataset and application data |

## 31. Future Extensions (OUT OF SCOPE for the current build — do not implement until core mechanic system is complete and validated)
- Car-mechanic and three-wheeler-mechanic submodels using the same vehicle-data pipeline.
- More detailed service categories (electrical repair, tyre work, scheduled maintenance) if a suitable target dataset exists.
- Finer geographic granularity (divisional/city level) if reliable data becomes available.
- Near-real-time public signals if a lawful and stable source exists.
- Other freelance services (electricians, plumbers) using appropriate domain data, only after the mechanic implementation is complete.
- User feedback collection to evaluate whether recommendations are useful in practice.

## 32. Viva / Presentation Explanation (for DEV-016)
**32.1 Short explanation:** "My project helps freelance mechanics identify Sri Lankan districts that are likely to provide stronger servicing and repair opportunities. I collect real vehicle-registration and district data, create historical and trend features, and use XGBoost as the main prediction model. I also use LSTM for time-series forecasting when the data supports it. SHAP explains why a district receives a high or low prediction, while SBERT lets the user ask natural-language questions and maps them to the correct mechanic category. The results are shown in a Streamlit dashboard with district rankings, maps and trends. I do not claim an exact number of mechanic jobs unless the dataset contains real job records."

**32.2 Why mechanics?** Vehicle statistics have a direct and understandable connection to the mechanic service market.

**32.3 Why XGBoost?** The core dataset is tabular and may not be very large; XGBoost models nonlinear relationships in this type of data, handles heterogeneous features well, and can be explained using SHAP.

**32.4 Why LSTM?** Designed for sequential patterns; included to test whether time-series structure adds predictive value when monthly or sufficiently dense historical data is available; compared fairly against XGBoost rather than assumed to be better.

**32.5 Why SBERT?** Provides semantic understanding of user questions; does not predict demand; helps the interface understand that a question about "bike repair" relates to the motorcycle-mechanic prediction category.

**32.6 Why SHAP?** Shows which input variables increased or decreased the prediction, making the model easier to inspect, explain and defend.

## 33. Immediate Implementation Steps
1. Create the GitHub repository and project folder structure.
2. Create a data-source register.
3. Download several District Statistical Handbooks, beginning with Kandy, and identify the exact new-vehicle-registration tables and observation years.
4. Extract a proof-of-concept motorcycle-registration CSV for Kandy.
5. Repeat the extraction for several other districts and validate consistency.
6. Collect total vehicle-population and population features where reliable district data is available.
7. Identify the real target variable. Search Kaggle or permitted web sources for mechanic/service-demand data if necessary.
8. Freeze the first modelling dataset and create a chronological train/validation/test split.
9. Train a simple baseline and then XGBoost.
10. Add SHAP and build the first ranking output.
11. If sequence density is sufficient, train LSTM and compare it with XGBoost.
12. Implement the Streamlit dashboard and Plotly map.
13. Add SBERT query matching after the core prediction path works.
14. Run integration tests, record final metrics and prepare the viva demo.

## 34. References and Source Notes
- Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining.
- Hochreiter, S., & Schmidhuber, J. (1997). Long Short-Term Memory. Neural Computation, 9(8), 1735–1780.
- Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. Proceedings of EMNLP-IJCNLP 2019.
- Lundberg, S. M., & Lee, S.-I. (2017). A Unified Approach to Interpreting Model Predictions. Advances in Neural Information Processing Systems.
- Sri Lanka Department of Census and Statistics. District Statistical Handbooks. Transport chapter and vehicle-registration tables, editions used by the project.
- Sri Lanka Department of Motor Traffic. Vehicle statistics and registration publications used for validation/context.
- Any Kaggle or web-scraped dataset used in the final model must be added here with its exact title, creator, source, licence, retrieval date and URL.

Source note: exact publication years, table numbers and URLs should be filled from the files actually downloaded and used in the final dataset. This prevents the report from claiming data coverage that was not verified.

## Appendix A. Suggested Data Dictionary
| Column | Type | Description | Required? |
|---|---|---|---|
| district | string | Canonical Sri Lankan district name | Yes |
| year | integer | Observation year | Yes |
| month | integer/null | Observation month when monthly data exists | Conditional |
| vehicle_type | category | Motorcycle, car, three-wheeler, etc. | Yes |
| new_registrations | numeric | Newly registered vehicles in the period | Core |
| vehicle_population | numeric/null | Total registered/operating vehicle stock if available | Recommended |
| population | numeric/null | District population | Recommended |
| population_density | numeric/null | Population per unit area | Optional |
| reg_lag_1 | numeric | Previous-period new registrations | Engineered |
| reg_lag_2 | numeric | Two-period lag | Engineered |
| reg_growth_pct | numeric | Percentage growth from previous period | Engineered |
| rolling_mean_3 | numeric | Three-period rolling mean using past data | Engineered |
| target_value | numeric | Observed modelling target | Yes for training |
| source_id | string | Unique source/table identifier | Yes |
| source_url | string | Original source URL | Yes |
| retrieved_date | date | Date data was obtained | Yes |

## Appendix B. Suggested Project Folder Structure
```
mechanic-demand-project/
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
├── requirements.txt
└── README.md
```

## Appendix C. Example System Outputs
**C.1 Ranking view (example wording only, not factual predictions — must be replaced by actual model outputs after training):**
| Rank | District | Predicted opportunity | Main explanation shown to user |
|---|---|---|---|
| 1 | Kandy | High | Strong recent motorcycle-registration level and positive historical trend |
| 2 | Colombo | High | Large vehicle-market indicators and strong recent levels |
| 3 | Kurunegala | Moderate–High | Stable registration growth and supportive district features |

**C.2 Natural-language query example:** Input: "I am a bike mechanic. Where should I focus next month?" → SBERT route: motorcycle mechanic → selected prediction period → district ranking → SHAP explanation → dashboard response.

**C.3 Required disclaimer (must appear wherever recommendations/rankings are shown):** "Predictions are based on available historical and proxy data. They indicate relative service opportunity and do not guarantee customer numbers, employment or income."

---

# END OF MASTER PROMPT

When you begin, start with Stage 1 (confirm you have read and understood this documentation) and Stage 2 (create the spec system files). Report back a summary of what was created and the Stage-3 coverage check before writing any application code.