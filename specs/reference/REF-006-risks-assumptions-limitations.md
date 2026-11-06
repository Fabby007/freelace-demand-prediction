# REF-006 — Risks, Assumptions & Limitations

**Status:** Approved reference specification
**Source:** Section 27 of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

This table documents known risks and limitations of the project **as designed** — these are documented cautions to be communicated (in code comments where relevant, in the dashboard disclaimer, and in DEV-016 reporting), not defects to silently "fix away" by overstating what the data or models can support (see MASTER_PROMPT.md Section 10, Stage 3 coverage note).

## 2. Section 27 — Risks, Assumptions and Limitations (verbatim table)

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

## 3. How mitigations map to specs

| Mitigation | Owning spec |
|---|---|
| Preferred/fallback target decision | DEV-002 |
| Prefer XGBoost, LSTM only if sequence length sufficient | DEV-008, DEV-009 |
| Source-specific parsers + manual validation samples | DEV-003 |
| Add total vehicle stock where available | DEV-003, DEV-005 |
| Show data cut-off date | DEV-013 |
| Cautious wording / statistical framing | DEV-012, DEV-013 (Appendix C.3 disclaimer) |
| Limit feature count, time-aware validation, regularisation | DEV-005, DEV-006, DEV-008, DEV-009, DEV-014 |
| District-level (not workshop-level) framing | DEV-012, DEV-013 |
| Show selected SBERT category, allow manual correction | DEV-011, DEV-013 |
| Prefer official downloadable files; log source version/date | DEV-002, DEV-003 |

## 4. Related specs

- REF-005 (Ethical, Legal & Data-Governance Rules)
- DEV-002 (Data Source Register & Target-Variable Decision)

## 5. Implementation-discovered risks (not in the original source doc — added as found, per Section 1's rule that these are documented cautions, not defects to hide)

### 5.1 DCS/DMT reconciliation gap for `new_registrations` (Car, Three-wheeler)

Discovered 2026-08-15 during DEV-003's Section 10 step 6 cross-validation (`src/data/validate_against_dmt.py`, `reports/dmt_cross_validation.md`). Summing the district-level DCS `new_registrations` figures across all 25 districts and comparing against the DMT national total for the same vehicle category/year:

- **Motorcycle** and **all three categories' `vehicle_population`**: district sums are consistently 52–87% of the national total across all five years (2019–2023) — plausible and internally consistent.
- **Car, 2019–2021**: district sums are **133–148% of the national total** — logically impossible if both figures measure the same real-world quantity.
- **Three-wheeler, 2022**: district sum is **~12.4x the national total** — an extreme, logically impossible discrepancy in the single year with the most severe vehicle-import restrictions in the underlying data.

**Impact:** These specific (vehicle_type, year) combinations cannot be trusted at face value as `new_registrations` predictors/targets without this caveat; a model trained naively on them could learn a distorted signal for Car and Three-wheeler in the affected years.

**Mitigation:** Flagged (not corrected or hidden) in `data/processed/modelling_base_*.csv` via `data_quality_flag = "district_sum_exceeds_dmt_national_total_for_new_registrations"` (100 of 375 rows — every district's Car 2019/2020/2021 and Three-wheeler 2022 row). DEV-005/DEV-006 must decide, with this flag visible, whether to exclude, down-weight, or simply disclose these rows when assembling the modelling dataset. DEV-016 must disclose this limitation in the technical documentation and error-analysis report rather than presenting the dataset as fully reconciled with DMT.

**Owning spec:** DEV-003 (validation performed and reported here); DEV-005/DEV-006 (modelling-time disposition); DEV-016 (disclosure).

### 5.2 Real 2020-2022 vehicle-registration collapse dominates naive baseline error

Discovered 2026-08-15 while evaluating DEV-007's baselines. Several high-volume districts show an extreme, multi-year drop in `new_registrations` starting 2020-2021 - e.g. Gampaha Motorcycle: 32,698 (2019) -> 17,615 (2020) -> 909 (2021) -> 1,170 (2022) -> 2,956 (2023); Kurunegala Motorcycle shows the same pattern. This is consistent with Sri Lanka's real 2020-2022 economic crisis and vehicle-import restrictions (also the likely driver of the DMT reconciliation gap in Section 5.1) - a genuine regime shift in the underlying market, not an extraction or cleaning defect.

**Impact:** Any baseline (or model) that assumes trend continuity from pre-2021 data is badly wrong across this shift. Concretely: the `baseline_moving_average` and `baseline_linear_trend` baselines (DEV-007), both of which lean on 2019-2020 training-period levels, produce validation/test MAE roughly 15-25x worse than the naive `baseline_previous_period` baseline, and the linear trend baseline additionally extrapolates to physically impossible negative predictions for the large majority of scored rows (see REF-009 ADR-010). `baseline_previous_period` (simple persistence) is comparatively far more robust here precisely because it only ever carries forward the single most recent actual observation, which already reflects the post-shift regime by the time validation/test periods are reached.

**Mitigation:** Disclosed, not corrected - the collapse is a real observation and must not be smoothed, clipped, or excluded. DEV-007's `reports/baseline_metrics.json` records `n_negative_predictions` alongside MAE/RMSE/R² so the scale of this effect is visible per baseline per split. DEV-008/DEV-009 should expect the same regime-shift difficulty and must not be tuned in a way that implicitly assumes trend continuity across 2020-2022 (e.g. by weighting older, pre-shift years more heavily without justification). DEV-014's evaluation report and DEV-016's documentation must state plainly that a large part of any model's apparent error is attributable to this real, sudden market disruption, not to a modelling defect.

**Owning spec:** DEV-007 (discovered and quantified here); DEV-008/DEV-009 (must not silently assume trend continuity through this period); DEV-014/DEV-016 (disclosure).

### 5.3 XGBoost does not outperform the naive persistence baseline on the test period

Discovered 2026-08-15 while evaluating DEV-008. Tuned XGBoost (972-combination grid search, selected on validation MAE, refit on train+validation, evaluated once on the untouched test period - REF-009 ADR-012) scores test MAE 312.9 (RMSE 696.8, R² 0.14) on the full 47-row test set. DEV-007's `baseline_previous_period` (naive persistence) scores test MAE 230.5 (RMSE 555.8, R² 0.49) on the 42 test rows it can score. On the identical 42-row matched subset, XGBoost's MAE is 306.4 - still clearly worse than the baseline's 230.5.

**Impact:** On this dataset's test period, the simplest possible baseline beats the tuned primary model. This is a real, direct consequence of Section 5.2's collapse combined with an extremely small training set (102 rows): a persistence forecast is unusually strong exactly when the most recent observation already reflects a regime shift that a tree-based model, trained on only 102-151 rows, cannot reliably generalize from. It is not evidence of an implementation defect - the model tests (DEV-008 Section 26.2) pass, the tuning search never touched the test period, and REF-009 ADR-012 documents a defensible, honest selection methodology.

**Mitigation:** Disclosed plainly, not hidden or re-tuned until it looks better (which would itself be a test-set-leakage violation). DEV-008's Acceptance Criteria explicitly allow for "outperforms (or is honestly reported not to outperform)" - this is the "not outperform" case, and it is reported as such in `models/xgboost_v1/metadata.json`'s `baseline_comparison` block. DEV-014's consolidated evaluation report and DEV-016's documentation/viva material must state this result plainly, and should discuss it alongside Section 5.2 (the collapse) and REF-006's existing "Short annual time series" risk rather than presenting XGBoost as the presumptively better model. DEV-012 (Ranking) and DEV-013 (Dashboard) should still use XGBoost as the production model per Section 13's component table (XGBoost is the documented "Core" tabular model, not an experiment to be swapped out based on one thin test period) but must not overstate its accuracy relative to a naive forecast.

**Owning spec:** DEV-008 (discovered and evaluated here); DEV-014/DEV-016 (disclosure, comparison report).

### 5.4 LSTM conditionality check confirms the "short annual time series" risk empirically, resulting in a skip decision

Discovered 2026-08-15 while running DEV-009's mandatory pre-build conditionality check (`src/models/lstm_model.py::assess_sequence_density()`) against the real frozen dataset. This section's own risk table already anticipated this ("Short annual time series | LSTM may overfit or be unjustified | Prefer XGBoost; use LSTM only when sequence length is sufficient") - DEV-009 quantifies exactly how far short the real data falls: `month` is null for 100% of rows (no monthly data exists at all, so Section 15.1's documented "sliding window of previous 6 or 12 months" construction is inapplicable on its own terms), and even under a generous yearly reinterpretation of that window, 0 of 75 district x vehicle_type series reach the minimum 7 consecutive periods needed for a single training sequence, because the dataset spans only 5 distinct years in total (2019-2023).

**Impact:** LSTM cannot be built, not even as a token "experimental" model, without either fabricating periods (Hard Rule violation) or shrinking the lookback window so far below the documented 6-12 range that the result would carry no more information than DEV-007's already-weak linear-trend baseline (REF-009 ADR-010) - i.e., a model that is technically present but scientifically empty.

**Mitigation:** Not built. Documented as a legitimate, evidence-based outcome (REF-009 ADR-013), not a shortfall - DEV-009's own Definition of Done explicitly allows for exactly this conclusion. XGBoost (DEV-008) remains the sole production model; DEV-012 (Ranking) and DEV-013 (Dashboard) proceed unblocked on the XGBoost path (DEV-PLAN.md Section 2). DEV-014's evaluation report and DEV-016's viva material must state plainly that LSTM was assessed and skipped, with the quantitative evidence (`reports/lstm_sequence_density_assessment.json`) available to cite, rather than omitting LSTM from the documentation without explanation.

**Owning spec:** DEV-009 (assessed and decided here); DEV-014/DEV-016 (disclosure).

### 5.5 SBERT: longer, naturally-phrased queries can score lower than short ones

Discovered 2026-08-15 while tuning DEV-011's similarity threshold. Sentence-embedding cosine similarity tends to fall as a query grows longer and includes more generic surrounding words - the source doc's own Section 16.1 example query, "I repair motorcycles. Which district should I consider next month?", scores only 0.423 top-category similarity (Motorcycle) with a 0.043 margin over the second-best category, versus 0.55-0.73 for short, topic-dense queries like "bike repair" or "car mechanic here". This is normal `all-MiniLM-L6-v2` behavior, not a bug (REF-009 ADR-017).

**Impact:** Some realistically-phrased, unambiguous user queries will land in the "ambiguous" safe-fallback path (prompting manual category selection) rather than routing confidently, purely because of sentence length/phrasing rather than genuine topical ambiguity.

**Mitigation:** Accepted as a safety-first tradeoff, not tuned away - REF-009 ADR-017 explicitly declined to loosen the ambiguous-margin threshold far enough to force this one example through, since doing so would weaken the same check's ability to catch genuinely ambiguous queries elsewhere. DEV-013's dashboard must present the "ambiguous" fallback as a normal, low-friction interaction (pick from the manual selector), not as an error, since it is expected to occur for verbosely-phrased real queries.

**Owning spec:** DEV-011 (discovered and decided here); DEV-013 (must present the fallback path as routine, not exceptional).

### 5.6 XGBoost's ranking quality varies sharply by vehicle type

Discovered 2026-08-15 while computing DEV-014's Section 23.3 ranking metrics (Spearman rank correlation, top-3 overlap) on the test period, per vehicle_type. Motorcycle rankings correlate well with the real proxy target (Spearman ρ=0.705, p=0.001, n=19, top-3 overlap 0.67); Car rankings are weak and not statistically significant (ρ=0.228, p=0.334, n=20, top-3 overlap 0.33); Three-wheeler rankings are effectively uncorrelated (ρ=0.048, p=0.910, n=8, top-3 overlap 0.33).

**Impact:** The dashboard (DEV-013) and ranking engine (DEV-012) present all three vehicle categories through the same interface with the same apparent confidence, but the model's actual district-ordering quality for Car and (especially) Three-wheeler mechanics is not meaningfully better than chance on this test period. Three-wheeler's result is additionally unstable simply from having only 8 test rows (REF-006's own "Small dataset" risk, directly realized).

**Mitigation:** Disclosed in `reports/model_evaluation.md`/`.json` (DEV-014) rather than presented as uniform model quality across categories. DEV-016's documentation and viva material should be able to state this per-category breakdown plainly if asked "how good is the model," not just cite an aggregate MAE/R². No corrective action (e.g. down-weighting Car/Three-wheeler predictions) was taken, since doing so without more data would just be a different, undocumented way of overstating confidence in one direction or another.

**Owning spec:** DEV-014 (discovered and quantified here); DEV-016 (disclosure).
