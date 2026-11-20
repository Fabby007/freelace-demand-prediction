# Model Evaluation Report (DEV-014)

Generated: 2026-08-15  
Dataset version: `modelling_dataset_v1_1310eaead622`  
Random seed: 42

## Time-aware validation (Section 23.4)
Chronological split only, reused verbatim from DEV-006 - no random train/test splitting. Train covers target_year 2020-2021, validation target_year 2022, test target_year 2023 (REF-009 ADR-008). No boundary was altered for this report.

## Regression metrics (Section 23.2) - identical computation across models

| Model | Split | n_scored / n_total | MAE | RMSE | R² | Negative predictions |
|---|---|---|---|---|---|---|
| baseline_previous_period | validation | 43/49 | 130.8 | 442.6 | -1.399 | 0 |
| baseline_moving_average | validation | 45/49 | 4161.2 | 7293.6 | -669.906 | 0 |
| baseline_linear_trend | validation | 39/49 | 2690.1 | 5151.2 | -305.152 | 32 |
| baseline_previous_period | test | 42/47 | 230.5 | 555.8 | 0.491 | 0 |
| baseline_moving_average | test | 45/47 | 2714.6 | 4641.0 | -35.784 | 0 |
| baseline_linear_trend | test | 40/47 | 5576.9 | 10484.8 | -172.466 | 37 |
| xgboost_v1 | validation | 49/49 | 125.2 | 218.5 | 0.366 | n/a |
| xgboost_v1 | test | 47/47 | 312.9 | 696.8 | 0.145 | 1 |
| xgboost_v1_matched_subset | test | 42/42 | 306.4 | 710.0 | 0.170 | 1 |
| baseline_previous_period_matched_subset | test | 42/42 | 230.5 | 555.8 | 0.491 | 0 |

**Headline finding, stated plainly:** on the untouched test period, `baseline_previous_period` (MAE 230.5) outperforms tuned XGBoost (matched-subset MAE 306.4, full-coverage MAE 312.9) on the identical 42 rows both can score. This is not hidden or re-tuned away - see 'Known limitations' below for why.

## Ranking metrics (Section 23.3) - proxy target, per vehicle_type
Computed against `target_value` (the Fallback-path proxy - future new_registrations), **not** a real observed mechanic-demand ranking (no such data exists for this project, DEV-002 Target Decision Record). Read the Three-wheeler row especially cautiously - only 8 test rows.

| Vehicle type | n_scored | Spearman ρ | p-value | Top-3 overlap |
|---|---|---|---|---|
| Motorcycle | 19 | 0.705 | 0.001 | 0.67 (k=3) |
| Car | 20 | 0.228 | 0.334 | 0.33 (k=3) |
| Three-wheeler | 8 | 0.048 | 0.910 | 0.33 (k=3) |

## LSTM (Section 23.5)
**Decision: skip.** Section 15.1's sequence window is defined in months ('sliding window of previous 6 or 12 months'), written for monthly-cadence data. The frozen dataset's `month` column is null for every row (0% monthly coverage, yearly-only granularity per REF-001 Section 5) - the documented sequence construction does not apply at all, independent of row count. Even granting an undocumented reinterpretation of the window as 6 yearly periods instead of months, a series needs 7 consecutive non-null yearly observations to form even one (input-window, target) training pair. The real data's longest consecutive run across all 75 district x vehicle_type series is 5 year(s) (the dataset only spans 5 distinct years, 2019-2023, at all); 0/75 series meet the 7-period threshold.

**Production-model recommendation, stated plainly: XGBoost** (DEV-008) - the only trained model in this project, per Section 23.5's own rule that a skipped/absent LSTM leaves XGBoost as the recommended production model by default. This is not a comparison between two trained models where XGBoost happened to win; LSTM was never built because the conditionality check failed (see above).

## Known limitations
- Fallback-path proxy target: target_value is future new_registrations, not a real observed mechanic-demand signal (DEV-002 Target Decision Record) - every metric in this report, including the ranking metrics below, describes how well the model forecasts vehicle registrations, not measured mechanic job demand.
- DCS/DMT reconciliation gap (REF-006 Section 5.1): Car (2019-2021) and Three-wheeler (2022) district-summed new_registrations exceed the DMT national total - 100/375 rows flagged (`data_quality_flag`), not excluded or corrected.
- Real 2020-2022 vehicle-registration collapse (REF-006 Section 5.2): several high-volume districts show an extreme, genuine multi-year drop (e.g. Gampaha Motorcycle 32,698 -> 909 registrations, 2019-2021) consistent with Sri Lanka's economic crisis and import restrictions - this regime shift, not a modelling defect, explains most of the error below.
- XGBoost does not outperform the naive persistence baseline on the test period (REF-006 Section 5.3) - reported plainly, not hidden: baseline_previous_period test MAE 230.5 vs. XGBoost's matched-subset test MAE 306.4 on the identical 42 rows.
- LSTM was assessed and skipped (REF-006 Section 5.4, REF-009 ADR-013): the dataset is yearly-only (0% monthly coverage) and spans only 5 distinct years, so 0/75 series can form even one training sequence at the documented minimum 6-period lookback - not a resourcing shortfall, a categorical data-density failure.
- SBERT similarity margins can be tight for naturally-phrased (longer) queries (REF-006 Section 5.5) - not a regression-model finding, included for completeness of the pipeline's documented limitations.
- Thin validation/test periods: validation covers a single target-year (49 rows), test covers a single target-year (47 rows, 20 Car / 19 Motorcycle / 8 Three-wheeler) - R^2 and ranking metrics on these splits, and especially per-vehicle-type ranking metrics on the 8-row Three-wheeler slice, must be read as indicative, not statistically robust (Edge Case, REF-006 'Small dataset / many features' risk).
- Negative-prediction findings: DEV-007's linear-trend baseline produces physically impossible negative predictions for 82-93% of its scored rows (REF-009 ADR-010); XGBoost's test predictions include 1 negative value out of 47 - both disclosed via `n_negative_predictions`, never clipped.

## Reproducibility
- Dataset version: `modelling_dataset_v1_1310eaead622`
- Random seed: 42
- XGBoost feature columns (exact order): `['new_registrations', 'vehicle_population', 'reg_lag_1', 'reg_lag_2', 'reg_growth_pct', 'change_from_lag_2', 'rolling_mean_3', 'rolling_std_3', 'vehicle_type_Motorcycle', 'vehicle_type_Car', 'vehicle_type_Three-wheeler']`
- XGBoost selected hyperparameters: `{'n_estimators': 500, 'learning_rate': 0.01, 'max_depth': 5, 'min_child_weight': 3, 'subsample': 1.0, 'colsample_bytree': 1.0}`
- Full experiment run log: `mlruns/` (MLflow, local file store) or `reports/experiment_tracking_fallback/` if MLflow was unavailable at run time.
