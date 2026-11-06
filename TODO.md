# TODO — Mechanic Service Demand Opportunity Prediction and Recommendation System

Legend: `[ ]` not started · `[~]` in progress · `[x]` complete · (depends: DEV-XXX)

Rules for using this file (see CLAUDE.md Sections 22–23): re-read the governing spec before starting a task; only check an item complete when its spec's acceptance criteria are genuinely satisfied and its DEV-015 test(s) pass; update `specs/reference/REF-009-architecture-decisions.md` whenever an implementation decision is made along the way.

---

## Phase 0 — Foundation & Specification System (governs: DEV-001)
- [x] Create `specs/`, `CLAUDE.md`, `TODO.md`, `DEV-PLAN.md`, reference specs (REF-001..009), development specs (DEV-001..017)
- [x] Create `specs/COVERAGE.md` (Stage 3 deliverable)
- [x] Initialize Git repository (local only; no remote created/pushed — will ask before doing so)
- [x] Create Appendix-B-derived folder structure on disk (`data/raw|interim|processed`, `notebooks/`, `src/data|features|models|explainability|nlp|recommendation`, `dashboard/`, `models/`, `reports/`, `tests/`, `configs/`)
- [x] Create Python virtual environment (documented, not committed) — used Python 3.12 rather than the machine's default 3.14, see ADR-001
- [x] Create `requirements.txt` pinning the full REF-008 stack (plus transitively-required pins: `pyarrow` ADR-002, `torch` ADR-003, `setuptools` ADR-004)
- [x] Create `.gitignore` (venv, data artefacts, secrets)
- [x] Create `configs/` scaffolding: placeholder files for feature list, target name, split-date config, model hyperparameters
- [x] Create root `README.md` stub
- [x] Verify full pinned stack installs and imports together in one process (`tests/test_environment.py`, passing)

## Phase 1 — Research & Data-Source Confirmation (governs: DEV-002)
- [x] Create data source register (source name, URL, expected variables, geography, time range, file type) — `data/source_register.csv`
- [x] Register DCS District Statistical Handbook editions to use (observation years, table/page refs) — real URL pattern discovered and verified (see DEV-003 notes); Kandy 2024 edition covers 2019-2023
- [x] Register DMT statistics to use for cross-validation — 2 national publications confirmed reachable
- [x] Evaluate candidate Kaggle datasets against research-question fit (licence, geography, coverage, whether target represents real mechanic demand) — record approved and rejected datasets — 3 datasets evaluated, all rejected (synthetic and/or not Sri Lanka-specific and/or not a demand/registration signal)
- [x] Register supporting district features under consideration (population, vehicle stock) — DCS Chapter 2 (Population) and Table 9.3 (vehicle stock proxy) confirmed available; income/road indicators not yet located, left open
- [ ] If web scraping is a candidate source, record target site's ToS/robots status — not needed; DCS/DMT direct-download URLs are sufficient, no scraping required
- [x] Decide target-variable path: Preferred (real demand target) vs Fallback (proxy forecast) — **Fallback** chosen; see Target Decision Record in `specs/development/DEV-002-data-source-register.md` and `configs/target_config.yaml`

## Phase 2 — Data Acquisition (governs: DEV-003)
- [x] Download and store raw District Statistical Handbook files in `data/raw/` (unedited) — `data/raw/dcs_handbooks/`, 53 PDFs (25 districts x Table 9.3 + 9.4, plus index/chapter files from discovery)
- [x] Download DMT publications into `data/raw/` — `data/raw/dmt/DMT_Vehicle_Population_2014-2025.pdf` (national new_registrations and vehicle_population by class/year, 2014-2025)
- [x] Download approved Kaggle dataset(s), if any, into `data/raw/` — N/A, no Kaggle dataset was approved (Fallback path chosen; see DEV-002)
- [x] (If applicable) implement compliant web scraper respecting robots/ToS/rate limits — N/A, direct government PDF URLs used instead (no scraping required); acquisition script (`src/data/extract_dcs_handbook.py`) uses a polite 1s delay and a descriptive User-Agent regardless
- [x] Proof-of-concept: extract Kandy motorcycle registrations for several consecutive years into a small CSV — `data/interim/dcs_kandy_2024_raw.csv` (125 raw observations, all vehicle types x 2019-2023, motorcycle rows verified by hand against the source PDF)
- [x] Validate extraction structure/naming consistency on 2–3 additional districts before scaling — Colombo, Galle, Jaffna validated (`tests/test_data_extraction.py`), including discovering and handling a real PDF text-extraction artifact (split numbers) and a real "n/r" (not-reported) marker distinct from "-"
- [x] Scale extraction to all 25 districts — `data/interim/dcs_multi_district_2024_raw.csv` (2940 raw observations, zero parser warnings on the final run); required discovering that 3 districts (Kalutara, Nuwara Eliya, Polonnaruwa) use different URL-segment spellings on the table-download endpoint than on the cover-index endpoint (`configs/dcs_district_url_segments.csv`), and iterating the word-position parser through several real layout variants (number-splitting across word fragments, an "n/r" not-reported marker colliding with the label-word pattern, Tamil-majority districts rendering label+values on the same line or wrapping a translation across an extra line). Table 9.3 (vehicle stock) is now 100% clean across all 25 districts; Table 9.4 (new registrations) has a small long-tail of isolated per-district artifacts (title/footer text leaking in as pseudo-labels) that do not match any real vehicle category and will be filtered out by DEV-004 normalization rather than silently included.
- [x] Cross-check extracted totals against source tables and DMT statistics — extracted values verified by hand against the source PDF text (Kandy) and independently cross-checked via a second extraction library (pypdf); DMT national cross-check completed via `src/data/validate_against_dmt.py` (`reports/dmt_cross_validation.md`, `tests/test_dmt_cross_validation.py`) — this belongs to DEV-003 itself (Section 10 step 6), not a later spec, and was resolved here rather than re-deferred. Found and documented a genuine, unresolved DCS/DMT reconciliation gap for Car (2019-2021) and Three-wheeler (2022) `new_registrations` (district sums exceed the national total) — flagged in the processed dataset and logged in REF-006 Section 5.1, not hidden.
- [x] Append source metadata (`source_id`, `source_url`, `retrieved_date`) to extracted observations — present on every row
- [x] Add light logging to extraction scripts (log as ADR in REF-009) — `logging` used throughout `src/data/extract_dcs_handbook.py`; addition itself already pre-approved as a reasonable industry-standard addition per MASTER_PROMPT.md Section 9, no separate ADR needed beyond that note

## Phase 3 — Extraction, Normalization & Cleaning (governs: DEV-004)
- [x] Confirm/finalize REF-002's 25 canonical district names against actual handbook spellings — district names were already canonical at acquisition time (DEV-003 requests by known canonical/variant name); REF-002 was updated with real observed URL-namespace spelling variants
- [x] District name normalization to the 25 canonical names — enforced defensively in `src/data/clean_dataset.py` (raises if an unknown district appears, rather than silently dropping)
- [x] Vehicle-category normalization (Motorcycle/Car/Three-wheeler canonical labels) — `configs/vehicle_category_lookup.csv`, extended with real observed raw labels (`Motor Bicycles`, `Motor Cars`, `Three Weelers`); out-of-scope/garbled labels excluded and logged, never folded into a canonical category
- [x] Decide and document the source-priority rule for deduplication across handbook editions (log as ADR) — most-recent-edition-wins for genuine cross-edition duplicates; same-edition conflicts (a real extraction artifact, not a legitimate duplicate) are excluded and logged loudly for manual review rather than silently resolved (found and correctly handled 1 case: Trincomalee 2019 Three-wheeler new_registrations). **DEV-015 audit finding:** this ADR reference was dangling (rule implemented and marked complete here, but never actually logged in REF-009) — retroactively logged as REF-009 ADR-025, with a direct unit test added (`tests/test_clean_dataset_deduplicate.py`).
- [x] Deduplication across handbook editions using the documented source-priority rule — `deduplicate()` in `src/data/clean_dataset.py`
- [x] Missing-value investigation & handling (never auto-zero; report counts) — "-" and "n/r" both preserved as NaN with a distinct `*_quality_note` per row (see REF-009 ADR-005 for the investigation and rationale); 80/697 raw values were missing after conversion
- [x] Outlier review against source publication before correction/removal — the repeated 2022/2023 `vehicle_population` values (seen first in Kandy) are flagged via `data_quality_flag`, not removed or corrected (3 rows flagged across the full dataset). A second, larger flag category (100 rows) was added afterward by DEV-003's DMT cross-check (`district_sum_exceeds_dmt_national_total_for_new_registrations`, see Phase 2) — same `data_quality_flag` column, same not-removed/not-corrected disposition.
- [x] Numeric conversion (strip commas/footnotes) while preserving raw values in the archive — `*_raw` columns retained in the processed file alongside the converted numeric columns
- [x] Chronological sort per district/vehicle series — processed file sorted by district/vehicle_type/year
- [x] Verify/finalize source metadata on every row — every row carries at least one of `new_registrations_source_id`/`vehicle_population_source_id` (tested)
- [x] Write cleaned data to `data/processed/` as CSV/Parquet, per REF-001 schema — `data/processed/modelling_base_2024.csv`, 375 rows (25 districts x 5 years x 3 vehicle types), extends REF-001 with per-metric provenance columns (documented in REF-001 Section 6 and in `clean_dataset.py`'s module docstring)
- [x] Implement Section 26.1 automated data validation tests (see Phase 13 / DEV-015) — `tests/test_data_cleaning.py`, 8 tests, all passing

## Phase 4 — Feature Engineering (governs: DEV-005)
- [x] Lag features (`reg_lag_1`, `reg_lag_2`) — `src/features/build_features.py`; `demand_lag_1` deliberately not created (Fallback path, no real target — see DEV-002 Target Decision Record); hand-verified against the real Kandy Motorcycle series
- [x] Growth features (`reg_growth_pct`, `change_from_lag_2`) — divide-by-zero guarded via masking (not post-hoc inf replacement, avoids a pandas deprecation warning)
- [x] Rolling trend features (`rolling_mean_3`, `rolling_std_3`) — computed via `shift(1)` before `rolling()`, so the window never includes the current row
- [x] Time features (`year`, `month`, `quarter`, cyclic month sin/cos if monthly data exists) — `year`/`month` pass through; `quarter`/`month_sin`/`month_cos` correctly implemented but null in the current dataset version (no monthly data — REF-001 Section 5), not fabricated
- [x] District context features (`population`, `population_density`) — pass through from DEV-004 output; currently null for every row since DEV-003 has not yet acquired DCS Chapter 2 population tables (open item, tracked in `data/source_register.csv`, does not block DEV-005 — `population`/`population_density` are "Recommended"/"Optional" per REF-001, not "Required")
- [x] Vehicle intensity feature (`vehicles_per_1000_people`) — implemented correctly, null for the same reason as `population` above
- [x] Make feature list config-driven (`configs/feature_list.*`) — `configs/feature_list.yaml` populated with real engineered/provenance/data-quality columns; kept in sync with code by a dedicated test
- [x] Write and pass the leakage unit test (no feature for period t uses data from period ≥ t) — `tests/test_feature_engineering.py`, 2 leakage tests (single-group mutation, cross-group independence), both passing
- [x] Append finalized engineered-feature list to REF-001 Section 6 — done, with type/description/null-reason per column

Also discovered and fixed during this phase: `clean_dataset.run()` alone (called by a test fixture) silently regenerated `data/processed/modelling_base_2024.csv` without the DMT cross-validation flags applied by `validate_against_dmt.run()` (DEV-003 Section 10 step 6), making the "final" file's contents depend on execution order. Fixed with a single canonical pipeline entry point, `src/data/build_processed_dataset.py::build()` (clean, then DMT-validate, always in that order); all test fixtures and the DEV-005 module now use it. Logged as REF-009 ADR-006.

## Phase 5 — Target & Dataset Assembly (governs: DEV-006)
- [x] Finalize long-format district/time/vehicle_type table per REF-001 schema — `data/processed/modelling_dataset_v1.csv`, 375 rows x 32 columns, `src/features/assemble_modelling_dataset.py`
- [x] Populate `target_value` per the DEV-002 Preferred/Fallback decision — Fallback: `target_value` = next-period (`year + 1`) `new_registrations` for the same district x vehicle_type series, computed leakage-safely via `groupby(...).shift(-1)`; hand-verified against the real Kandy Motorcycle series, including a genuinely-missing-source-year case producing a null (not fabricated) target
- [x] Decide and document final time granularity (yearly vs. monthly) based on real source coverage — **yearly** (5 distinct years, 2019-2023; no monthly data in any series) — `configs/split_config.yaml`
- [x] Freeze modelling dataset version and record its identifier — content-hash-derived version id (`modelling_dataset_v1_1310eaead622`), recorded in `configs/split_config.yaml` (`dataset_version`/`dataset_sha256`/`frozen_date`); stable across reruns absent a genuine data change (REF-009 ADR-009)
- [x] Create chronological train/validation/test split; record boundaries in `configs/split_config.*` — boundaries keyed by `target_year`: train 2020-2021 (102 rows), validation 2022 (49 rows), test 2023 (47 rows), 177 rows `unlabeled` (null target); thin 2/1/1 split forced by the real 5-year series, logged as REF-009 ADR-008. The 100 DCS/DMT-flagged rows (REF-006 Section 5.1) are disclosed via `target_data_quality_flag`, not excluded (REF-009 ADR-007).
- [x] Run split-integrity tests (no row in multiple splits; strictly chronological) — `tests/test_dataset_assembly.py`, 12/12 passing

## Phase 6 — Baseline + XGBoost (governs: DEV-007, DEV-008)
- [x] Implement previous-period baseline — `src/models/baseline.py::add_previous_period_baseline()`; target_value(t) = target_value(t-1) per series
- [x] Implement moving-average baseline — `add_moving_average_baseline()`; reuses DEV-005's `rolling_mean_3` (config-driven window check)
- [x] Implement simple linear regression baseline where appropriate — `add_linear_trend_baseline()`; per-series trend fit on train-split years only, implemented as specified but disclosed as statistically weak on this dataset (REF-009 ADR-010)
- [x] Evaluate all baselines on the DEV-006 chronological split; persist metrics — `reports/baseline_metrics.json`, `data/processed/baseline_predictions_v1.csv`; previous-period baseline clearly outperforms the other two (see REF-006 Section 5.2, real 2020-2022 registration collapse)
- [x] Train XGBoost regressor on same target/split — `src/models/xgboost_model.py`; 102 train / 49 validation / 47 test rows, reused verbatim from DEV-006
- [x] Hyperparameter tuning (`n_estimators`, `learning_rate`, `max_depth`, `min_child_weight`, `subsample`, `colsample_bytree`) using train/validation only — full 972-combination grid search, selected on validation MAE (REF-009 ADR-012)
- [x] Select model on validation performance; report final metrics on untouched test period (once) — selected params: n_estimators=500, learning_rate=0.01, max_depth=5, min_child_weight=3, subsample=1.0, colsample_bytree=1.0; refit on train+validation; test MAE 312.9, RMSE 696.8, R² 0.14
- [x] Save final model + exact feature list + dataset version to `models/` — `models/xgboost_v1/{model.json, onehot_encoder.joblib, metadata.json}`
- [x] Run Section 26.2 model tests against the saved XGBoost model — `tests/test_xgboost_model.py`, 14/14 passing

**Honest finding:** XGBoost does **not** outperform DEV-007's `baseline_previous_period` on the test period (baseline MAE 230.5 vs. XGBoost matched-subset MAE 306.4) — root-caused to the real 2020-2022 registration collapse plus a very small (102-row) training set, not an implementation defect. Documented in REF-006 Section 5.3 and DEV-008. XGBoost remains the production model per REF-003 (documented Core component), with this limitation disclosed for DEV-014/DEV-016.

## Phase 7 — LSTM Comparison Model (governs: DEV-009) — only if sequence density supports it
- [x] Assess sequence density per district/vehicle series; document proceed / experimental-only / skip decision — **SKIP**: `month` is null for 100% of rows (no monthly data at all - Section 15.1's construction is inapplicable on its own terms), and even reinterpreting the 6-month lookback as 6 yearly periods, 0/75 series reach the required 7 consecutive periods (dataset spans only 5 distinct years total, 2019-2023). `src/models/lstm_model.py`, `reports/lstm_sequence_density_assessment.json`, REF-009 ADR-013, REF-006 Section 5.4.
- [x] Build sliding-window sequences (6–12 month lookback) per district/vehicle series (if proceeding) — N/A, not proceeding (deliberately not attempted even experimentally — see ADR-013's "Alternatives considered")
- [x] Fit scaler on training data only — N/A, same reason
- [x] Build model: input sequence layer, 1–2 LSTM layers, dropout, dense output — N/A, same reason
- [x] Train with early stopping on validation loss + checkpoint best epoch — N/A, same reason
- [x] Evaluate LSTM vs XGBoost on identical target/held-out periods; record production-model decision — **XGBoost remains production model** (LSTM was never built; recorded in REF-009 ADR-013). DEV-012/DEV-013 proceed unblocked on the XGBoost path.

## Phase 8 — SHAP Explainability (governs: DEV-010)
- [x] Global SHAP summary across test set — `src/explainability/shap_explainer.py`, `reports/shap_global_summary.json`; top feature (data-driven, not assumed): `new_registrations`
- [x] Per-district local SHAP contributions (top positive/negative factors) — `explain_rows()`/`explain_row()`, `data/processed/shap_local_explanations_test_v1.csv`; vehicle_type one-hot dummies aggregated into one readable factor (REF-009 ADR-014) alongside full raw detail
- [x] Verify SHAP output aligns with model feature schema (Section 26.2 test) — `tests/test_shap_explainer.py`, 11/11 passing, including the additivity sanity check

**Environment fix required:** `shap.TreeExplainer` crashed whenever `transformers` (via sentence-transformers) was already imported in the same process (Keras 3 vs. `tensorflow==2.16` incompatibility inside an unrelated transformers isinstance probe) — pinned `tf-keras==2.16.0` to fix; this exact process shape (SHAP + SBERT together) is what DEV-013's dashboard needs, so it had to be fixed now, not deferred. See REF-009 ADR-015.

## Phase 9 — Ranking & Recommendation Engine (governs: DEV-012)
- [x] Implement step 1–2: receive category/period, generate per-district predictions — `src/recommendation/ranking_engine.py::RankingEngine.rank()`; category/period accepted directly or via `rank_from_query()` (DEV-011 SBERT routing); predictions reuse DEV-008's saved model/encoder unchanged
- [x] Implement step 3: sort districts by predicted value — descending, deterministic tie-break
- [x] Decide and document opportunity-band threshold rule (quantiles or training-data rule); log as ADR if not already fixed — per-vehicle-type train-split quartiles, REF-009 ADR-018
- [x] Implement step 4: opportunity bands (Low/Moderate/High/Very High) — `assign_band()`
- [x] Implement step 5: extract strongest SHAP reasons for top-ranked districts — `select_top_factors()`, reuses DEV-010's real SHAP output unmodified, plain-language mapping, `vehicle_type` excluded (constant within a query)
- [x] Implement step 6: return top-3/top-5 with trend context and limitation note — `top_n` (config-driven, default 5) with `recommendation_sentence` + exact Appendix C.3 disclaimer
- [x] Enforce wording rules (REF-007 Section 4) and attach the Appendix C.3 disclaimer to every recommendation output — verbatim string, verified by test
- [x] Add deterministic tie-break rule for equal predicted values — predicted_value descending, district name ascending

## Phase 10 — SBERT NLP Query Layer (governs: DEV-011)
- [x] Define category description embeddings (motorcycle/car/three-wheeler mechanic) — `src/nlp/sbert_router.py::SBERTRouter.load()`, computed once from `configs/sbert_categories.yaml`, model `all-MiniLM-L6-v2` (REF-009 ADR-016)
- [x] Implement query embedding + similarity match to category — `SBERTRouter.route()`, cosine similarity
- [x] Decide and document similarity threshold for confident vs. ambiguous match — `similarity_threshold=0.30` (retuned from 0.55 placeholder), `ambiguous_margin=0.05` (confirmed); REF-009 ADR-017, empirical spot-check table in DEV-011
- [x] Route matched category into prediction/ranking pipeline — `matched_category` output field is the sole interface DEV-012 needs; SBERT itself makes no predictions (Business Rule)
- [x] Implement safe-fallback behavior for unsupported/ambiguous queries (never silently guess) — 4 distinct statuses (`confident`/`ambiguous`/`unsupported`/`empty`); `matched_category` is `None` for all but `confident`
- [x] Always surface matched category to the user with a manual-override option — every result exposes full `similarity_scores` for all 3 categories regardless of status

**Note:** the source doc's own Section 16.1 example query lands as "ambiguous" under the tuned threshold — a deliberate, evidence-based outcome, not a defect (see REF-006 Section 5.5, REF-009 ADR-017).

## Phase 11 — Dashboard (governs: DEV-013)
- [x] Vehicle type selector, period selector, district selector, top-N selector, NL query box — `dashboard/app.py::render_sidebar_controls()`
- [x] Sri Lanka choropleth map (Plotly) — `dashboard/views.py::build_choropleth_figure()`; real district boundaries from geoBoundaries.org (REF-009 ADR-019), never fabricated
- [x] Ranking table/bar chart — `build_ranking_table()`, includes a data-quality-note column
- [x] Historical trend chart — `build_trend_figure()`; real gaps left as gaps, never interpolated (REF-009 ADR-005)
- [x] Forecast/predicted value panel — `st.metric` in `render_district_detail()`
- [x] SHAP explanation panel — reuses DEV-012's real recommendation sentence + SHAP note, full district coverage (REF-009 ADR-021)
- [x] Data-source & model-version info panel — reads `data/source_register.csv` (2 pre-existing malformed rows fixed, REF-009 ADR-020), `configs/split_config.yaml`, `models/xgboost_v1/metadata.json`
- [x] Persistent disclaimer text (Appendix C.3 wording) — top, bottom, and sidebar; verbatim, verified by test
- [x] Missing-period-data clear-message state — `render_no_data_state()`; tested via mocked `RankingEngine.rank()`
- [x] SBERT-fallback UI state — confident match shown with override available; ambiguous/unsupported show the exact SBERT fallback message, vehicle-type control never silently changed
- [x] (If time permits, FR-12) export/reproducible-view feature — CSV download button on the ranking table (best-effort, small addition)

**Tests:** `tests/test_dashboard_app.py` (13/13, Streamlit `AppTest` harness) + `tests/test_dashboard_views.py` (10/10, pure logic). Full project suite: 155/155 passing. Real `streamlit run dashboard/app.py` launch also verified (HTTP 200), not only simulated.

## Phase 12 — Evaluation & Experiment Tracking (governs: DEV-014)
- [x] Regression metrics (MAE, RMSE, R²) vs baselines, computed identically across models — `src/evaluation/model_evaluation.py`; identical `evaluate_predictions()`-shaped schema reused from DEV-007/DEV-008 verbatim
- [x] Ranking metrics (Spearman correlation, top-k overlap) where real/proxy target available — computed per vehicle_type on the proxy target; Motorcycle ρ=0.705, Car ρ=0.228, Three-wheeler ρ=0.048 (REF-006 Section 5.6, new discovered finding)
- [x] Confirm time-aware validation implemented (chronological holdout / walk-forward) — reused verbatim from DEV-006/REF-009 ADR-008, verified unaltered by test
- [x] Decide MLflow vs Weights & Biases (log as ADR if not already fixed in REF-009) — **MLflow**, local file store; REF-009 ADR-022
- [x] Wire MLflow/W&B experiment logging into all training scripts — `src/evaluation/experiment_tracking.py::log_run()`, wired into baseline.py/xgboost_model.py/lstm_model.py; verified reruns reproduce identical prior results
- [x] Record random seeds for every stochastic run — seed 42, logged as an MLflow param on every run
- [x] Populate model registry: model, preprocessing objects, feature schema, evaluation report — `models/xgboost_v1/` now contains all four
- [x] Write consolidated evaluation report stating the LSTM-vs-XGBoost production decision plainly — `reports/model_evaluation.md`; states XGBoost as production model, states plainly that XGBoost does not beat the DEV-007 baseline on test, states LSTM was assessed and skipped (not "lost a comparison")

**Tests:** `tests/test_experiment_tracking.py` (5/5) + `tests/test_model_evaluation.py` (14/14). Full project suite: 174/174 passing.

## Phase 13 — Testing (governs: DEV-015)
- [x] Data tests (Section 26.1 list) — implemented alongside Phase 3, audited/completed here; `tests/test_data_cleaning.py` + new `tests/test_clean_dataset_deduplicate.py` (dedup source-priority rule, previously untested directly — see REF-009 ADR-025, retroactively logged after being found dangling)
- [x] Model tests (Section 26.2 list) — implemented alongside Phase 6–8, audited here; all five Section 26.2 items confirmed covered across `test_xgboost_model.py`/`test_shap_explainer.py`/`test_feature_engineering.py`
- [x] Dashboard tests (Section 26.3 list) — implemented alongside Phase 10–11, audited here; all five Section 26.3 items confirmed covered in `test_dashboard_app.py` via Streamlit's real `AppTest` harness
- [x] Full suite runnable as a single command (e.g. `pytest tests/`) and passing — **191/191 passing**

**DEV-015 audit findings (fixed, not just noted):**
1. **Real bug — production-artifact mutation on every test run:** `baseline.py`/`xgboost_model.py`/`lstm_model.py`/`model_evaluation.py`'s `run()` functions all hardcoded the real `mlruns/` MLflow store with no override, so every `pytest tests/` invocation silently appended duplicate run entries — 28 accumulated runs found (22 from one test file alone) before the fix. Also found: `test_dataset_assembly.py` and `test_shap_explainer.py` had tests calling `run()` with real default paths, rewriting the real frozen dataset/split_config/SHAP reports on every test run. Fixed: added an `mlruns_dir` parameter (threaded to `log_run()`) to all four `run()` functions, added output-path parameters to `shap_explainer.run()`, and redirected every affected test to `tmp_path`. Verified: `mlruns/` now stays at exactly 4 runs (one per model type) across repeated full-suite runs.
2. **Missing test file referenced but never created:** `src/data/fetch_district_geojson.py`'s docstring and `data/source_register.csv` both claimed `tests/test_district_geojson.py` verified the district-name reconciliation "programmatically, not merely assumed" — the file didn't exist. Created (10 tests).
3. **Dangling ADR reference:** TODO.md Phase 3 marked the deduplication source-priority rule's "(log as ADR)" requirement complete, but no such entry existed in REF-009. Retroactively logged as ADR-025, with a direct unit test (`test_clean_dataset_deduplicate.py`, 5 tests) added since the rule previously had no test beyond an end-to-end "no dupes in final output" check.
4. **Foundational smoke test missed a package:** `test_environment.py::test_src_subpackages_import` never included `src.evaluation` (added in DEV-014) — fixed.
5. **Test-file scoping mistake caught in my own new code:** a module-level `pytestmark` defined mid-file would have skipped every test in `test_district_geojson.py`, including synthetic-data unit tests that don't need the real file — fixed with a per-test decorator before it shipped.
6. Added a characterization test confirming `assign_band()` handles a genuinely negative predicted value (a real, disclosed XGBoost finding) honestly rather than crashing or requiring special-casing.

No test was weakened, skipped, or removed to obtain a green suite — every fix above added or corrected a test; none reduced coverage.

## Phase 14 — Documentation & Viva Prep (governs: DEV-016)
- [ ] Technical documentation (architecture, modules, data pipeline, models, explainability/NLP/ranking, dashboard)
- [ ] User guide (dashboard usage, control/panel meaning, opportunity-band/disclaimer interpretation)
- [ ] Model evaluation / error-analysis report (honest limitations, referencing REF-006)
- [ ] Viva/presentation material (Section 32 talking points: why mechanics, why XGBoost, why LSTM, why SBERT, why SHAP)
- [ ] Cross-check documentation against `specs/COVERAGE.md` for completeness

## Phase 15 — Deployment/Reproducibility Readiness (governs: DEV-017)
- [ ] `requirements.txt` / `pyproject.toml` finalized and pinned
- [ ] README with setup + run instructions
- [ ] Reproducibility check: same dataset version + config reproduces same trained model within normal nondeterminism (documented outcome)
- [ ] Confirm random seeds recorded and applied wherever the stack supports them

---

# EXTENSION — Mechanic Discovery Web Platform (governs: DEV-018–024)

**Status:** Planning complete (2026-08-21); no implementation started. See `MARKETPLACE_EXTENSION.md` for the full extension plan and `specs/development/DEV-PLAN.md` Section 7 for how these phases relate to Phases 0–15 above (they do not depend on Phases 14–15 and may proceed independently — see the dependency note there).

This is an **additive extension**, approved by the user on 2026-08-21, layered on top of the completed/near-complete ML system above. Phases 0–15 and their governing DEV-001–017 specs are unmodified by this extension. Do not mark any phase below complete while its constituent DEV spec's acceptance criteria remain unmet (same rule as Phases 0–15, CLAUDE.md Section 23).

## Phase 16 — Web Application Foundation, Database & Authentication (governs: DEV-018) — COMPLETE (2026-08-21)
- [x] Scaffold `app/` per REF-010 Section 3 (app factory, blueprints, config, extensions)
- [x] Configure Flask-SQLAlchemy against `instance/marketplace.db`; enable SQLite foreign-key enforcement
- [x] Define `User` model (REF-011 Section 3.1)
- [x] Implement customer registration and mechanic registration (two distinct forms/routes)
- [x] Implement login/logout (Flask-Login) and the `role_required(*roles)` decorator
- [x] Build `base.html`, `home.html`, `static/css/style.css` (role-aware nav, responsive layout)
- [x] Provision exactly one admin account via a CLI/seed mechanism (never a public form) — `flask create-admin`
- [x] Create `configs/marketplace_config.yaml`; wire `SECRET_KEY`/DB URI from environment variables
- [x] Append Flask/Flask-SQLAlchemy/Flask-Login/Flask-WTF pins to `requirements.txt`; add `instance/` to `.gitignore` — also added `email-validator` and promoted Flask/SQLAlchemy/Werkzeug/PyYAML/click from transitive to explicit pins (REF-009 ADR-029)
- [x] `tests/marketplace/test_auth.py` passing (26/26); full existing ML suite passes unmodified (191/191 alone; see DEV-018.md's Acceptance Criteria for the isolated full-suite flake finding, unrelated to this extension)
- [x] Also implemented FR-M03 (customer account view/edit) as DEV-018 FR13, correcting a DEV-018.md/COVERAGE.md gap found during implementation — see DEV-018.md's Related Requirements note

## Phase 17 — Mechanic Profiles & User Roles (governs: DEV-019) — COMPLETE (2026-08-21)
- [x] Define `MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType` models (REF-011 Sections 3.2–3.5)
- [x] Seed the `Service` starter list, clearly labelled as seed/reference data — auto-seeded idempotently at app startup (REF-009 ADR-030)
- [x] Build the "complete your profile" redirect flow for newly registered mechanics — implemented in the shared login route (REF-009 ADR-030)
- [x] Build `mechanic_edit_profile.html` and `mechanic_dashboard.html`
- [x] Implement profile create/edit with server-side ownership enforcement (a mechanic can only edit their own profile) — enforced by construction: the edit route takes no ID parameter and always resolves `current_user.mechanic_profile`
- [x] Implement profile photo upload (extension allow-list, size limit, randomized filename, default avatar) per REF-012 Section 5 — extension allow-list + magic-byte content sniff + 2MB global cap (413 page) + UUID filenames, all verified by test
- [x] `tests/marketplace/test_mechanic_profile.py` passing (28/28, including the ownership-isolation test); full marketplace suite 54/54; one pre-existing DEV-018 test corrected (not weakened) to match DEV-019's intentional `/mechanic/profile` behavior change
- [x] Final combined suite (`pytest tests/`, ML + marketplace): **245/245 passed, 0 failures** — authoritative sign-off run; see DEV-019.md Acceptance Criteria for the known, pre-existing, load-dependent `test_dashboard_app.py` flake observed (and independently re-confirmed as unrelated to this extension) during verification, absent from this final run

## Phase 18 — Mechanic Search & Discovery (governs: DEV-020) — COMPLETE (2026-08-21)
- [x] Build `mechanic_list.html` filter form (district, vehicle type, service type, optional name search) and results grid
- [x] Implement the ORM search query (REF-011 Section 6), excluding blocked accounts — `.any()` EXISTS-subquery filtering (REF-009 ADR-031), no raw SQL
- [x] Implement live average-rating/review-count computation on results (no N+1 queries) — no `Review` table exists yet (DEV-021 not implemented); static "No ratings yet" shown, zero per-card queries; `contains_eager`/`selectinload` keep `user`/vehicle-type/service loading to a constant number of queries regardless of result count (REF-009 ADR-031)
- [x] Implement sort order (rated-desc, then unrated) and pagination — falls back to a stable alphabetical-by-name order until DEV-021 provides a real rating to sort by (documented dependency-sequencing note in DEV-020.md); pagination via Flask-SQLAlchemy `.paginate()`, page size from `configs/marketplace_config.yaml`
- [x] Build `mechanic_profile.html` (full profile + contact number, shown only here, not on cards) — plus a `tel:` "Call Mechanic" link and the review-disclaimer sentence
- [x] Implement empty-state and not-found states — "No mechanics found" + Clear filters link; nonexistent and blocked mechanic IDs both return an identical 404 (no moderation-state leak)
- [x] `tests/marketplace/test_search.py` passing (24/24); full marketplace suite 78/78

## Phase 19 — Ratings & Reviews (governs: DEV-021) — COMPLETE (2026-08-21)
- [x] Define `Review` model (REF-011 Section 3.6: rating 1–5 constraint, one-review-per-customer-per-mechanic uniqueness) — both `CheckConstraint`s and the `UniqueConstraint` verified directly at the DB level (REF-009 ADR-032 documents the unconditional-uniqueness scope decision)
- [x] Implement submit/edit (pre-filled if a review already exists)/delete for the owning customer only — no `review_id` in any URL (ownership by construction, same pattern as DEV-019)
- [x] Implement the shared average-rating aggregate query reused by DEV-020 and this spec — `compute_rating_stats()`/`compute_rating_stats_bulk()`, also reused by DEV-019's mechanic dashboard (FR-M11); DEV-020's temporary alphabetical-only sort replaced with a real `AVG(rating)` correlated-subquery `ORDER BY`
- [x] Implement admin moderation functions (`remove_review`/`restore_review`, soft delete) — verified directly and end-to-end (a removed review disappears from the profile page and average)
- [x] Render the review-disclaimer sentence (REF-013 Section 4) wherever reviews are shown — public profile page and mechanic's own dashboard, via one shared macro
- [x] `tests/marketplace/test_reviews.py` passing (40/40, including duplicate-submission and ownership rejection tests); full marketplace suite 118/118
- [x] Also implemented the customer's own "My Reviews" page (`customer.reviews`), completing the DEV-018/DEV-019 nav stub — not itemized in DEV-021's FR list but a natural, low-risk completion of an already-declared feature (see DEV-021.md's Additional Implementation Notes)
- [x] Final combined suite (`pytest tests/`, ML + marketplace): **309/309 passed, 0 failures, 61.81s** — authoritative sign-off run; ML suite alone also passed 191/191 clean; the known Streamlit `AppTest` flake (documented since DEV-018) did not recur in either run

## Phase 20 — Admin Dashboard & Management (governs: DEV-022) — COMPLETE (2026-08-21)
- [x] Build `admin_dashboard.html` summary counts — customers, mechanics, mechanic profiles, blocked accounts, total reviews, removed reviews
- [x] Build user management view (block/unblock/delete, customers and mechanics) — `admin/users.html`, filterable by role/status, paginated
- [x] Build mechanic management view (`admin/mechanics.html`) — links to the real DEV-020 profile page, extended so only an admin can view a blocked mechanic's full profile
- [x] Build review management view (remove/restore, reusing DEV-021's functions) — `admin/reviews.html`, filterable by status, paginated
- [x] Enforce blueprint-level `role_required('admin')` on all `/admin/*` routes — plus a per-view decorator on every route (defense in depth, matching DEV-018's established pattern)
- [x] Implement self-block/self-delete guard — admin accounts are excluded from every management route entirely (not just self), also ruling out one admin managing another (REF-012 Section 3 gained an explicit row for this); cascade delete verified empirically for both a customer and a mechanic (REF-009 ADR-033)
- [x] `tests/marketplace/test_admin.py` passing (32/32, including the 403-for-every-non-admin-role test); full marketplace suite 150/150
- [x] Final combined suite (`pytest tests/`, ML + marketplace): **341/341 passed, 0 failures, 72.41s** — authoritative sign-off run; ML suite alone also passed 191/191 clean; the known Streamlit `AppTest` flake (documented since DEV-018) did not recur in either run

## Phase 21 — ML Opportunity Insights Web Integration (governs: DEV-023) — COMPLETE (2026-08-21)
- [x] Build `app/routes/insights.py` calling `RankingEngine.rank()` unchanged (no new prediction/ranking logic in `app/`) — verified byte-for-byte against a direct `RankingEngine.rank()` call
- [x] Build `opportunity_insights.html` (vehicle-type/period selectors, ranking table, SHAP reasons) — top_n selector too, matching DEV-013 parity; cards show band, predicted value, positive/negative SHAP factors, full recommendation sentence
- [x] Render the Appendix C.3 disclaimer verbatim on this page — sourced directly from `result["disclaimer"]`, not a second hardcoded copy
- [x] Implement the no-data state and model-load-failure error state — 503 with a clear message on load/predict failure, no stack trace leaked
- [x] Cache model/artifact loading once per process (not per request) — lock-guarded lazy singleton (REF-009 ADR-034); measured ~12.7s cold / ~90ms warm on a real dev server
- [x] Verify zero writes to `data/`, `models/`, or `mlruns/` from this route — directory-snapshot test
- [x] `tests/marketplace/test_insights_integration.py` passing (19/19); confirmed `dashboard/app.py` still runs unmodified (source-text check; `data_access.py`/`views.py` still import cleanly)
- [x] Verified (not newly built): blocked-mid-session mechanics already lose access automatically via DEV-018's existing `User.is_active`/Flask-Login wiring — no code change needed (REF-009 note)
- [x] Final combined suite (`pytest tests/`, ML + marketplace): **360/360 passed, 0 failures, 77.74s** — authoritative sign-off run; ML suite alone also passed 191/191 clean; the known Streamlit `AppTest` flake (documented since DEV-018) did not recur in either run

## Phase 22 — Web Application Testing, Security & Final Integration (governs: DEV-024) — COMPLETE (2026-08-21)
- [x] Audit `tests/marketplace/` against REF-012's full authorization matrix; fill any gap found — found 3 over-specified matrix cells (documentation errors, corrected in REF-012, not new features) and 8 genuine test-coverage gaps (all closed); see DEV-024.md's "Audit findings" section for the full record
- [x] Add/verify CSRF, password-hashing, SQL-injection-resistance, and upload-validation tests — CSRF added for all 4 previously-uncovered admin actions; SQL-injection resistance newly tested with real injection-shaped payloads; upload validation re-verified plus a new path-traversal-filename test
- [x] Add the cross-role end-to-end scenario test (register → profile → search → review → moderate) — `test_full_customer_mechanic_admin_review_lifecycle`, `tests/marketplace/test_e2e_workflow.py`
- [x] Perform and document the UI QA pass (desktop + mobile, all four role states, both disclaimers correctly placed) — role-aware nav and disclaimer placement now verified by test (`tests/marketplace/test_security_audit.py`); mobile responsiveness verified by CSS review (one breakpoint covers every template)
- [x] Confirm full existing ML `pytest tests/` suite and `streamlit run dashboard/app.py` are unaffected by the extension — 191/191 (matches pre-extension baseline exactly); real `streamlit run` smoke test confirmed HTTP 200
- [x] Confirm `pytest tests/` runs both suites together; `pytest tests/marketplace/` runs the marketplace suite alone — 184 marketplace tests alone, both re-confirmed this phase
- [x] Explicitly implement or explicitly defer (with reason) each optional-hardening item (rate limiting, image-content validation) — both explicitly deferred with documented reasoning (DEV-024.md FR7 section); neither silently skipped
- [x] `pip check` — no broken requirements; no secret/database file staged in git; `.gitignore` confirmed complete for `instance/`
- [x] Final combined suite (`pytest tests/`, ML + marketplace): **375/375 passed, 0 failures, 87.55s** — authoritative final sign-off run for the entire marketplace extension; ML suite alone also passed 191/191 clean (matching the pre-extension baseline exactly); the known Streamlit `AppTest` flake did not recur in this final run

## Marketplace extension (DEV-018–024) — COMPLETE (2026-08-21)
All seven marketplace specs (DEV-018 through DEV-024) are functionally complete, individually verified, and re-verified together in this final audit phase. The ML research system (DEV-001–017) remains completely unmodified and untouched throughout. See `MARKETPLACE_EXTENSION.md` for the full extension record and `specs/development/DEV-PLAN.md` Section 7 for the dependency graph this phase closes out.
