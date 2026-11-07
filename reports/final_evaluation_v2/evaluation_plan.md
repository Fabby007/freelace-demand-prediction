# Final Evaluation Plan, Target Year 2023

**Plan version:** `final_evaluation_v2_plan_1`
**Frozen:** 2026-11-07, before any 2023 result was computed.
**Machine-readable copy:** `configs/final_evaluation_v2.yaml`. Hashes are in `freeze_record.json`.

This plan cannot change after results are seen. If a result is disappointing, it is reported as it is. No further experiment follows from it.

## 1. Models

Chosen on development results and project-author approval, not on 2023 results.

| Model | Forecast for 2023 | Fitted? |
|---|---|---|
| Previous year (reference) | `licence_count` in 2022 | No |
| Moving average | Mean of `licence_count` over 2020, 2021 and 2022, skipping missing years | No |
| Ridge, log change | See below | Yes, on data before 2023 |

## 2. Frozen Ridge configuration

| Item | Value |
|---|---|
| Source experiment | `ridge__level__log_change__train_all` (Step 6) |
| Target | Log next-year change, `ln(next year / this year)` |
| Numeric input | Log `licence_count` |
| Categorical input | `vehicle_type` |
| Preprocessing | `StandardScaler` and `OneHotEncoder`, fitted on training rows only |
| Penalty | `alpha = 100`, as chosen by cross-validation in both Step 6 folds. **Not tuned again** |
| Converting back | `licence_count × exp(prediction)`, with no bias adjustment |

This is not a claim that Ridge is expected to win. In Step 6 it did not beat the previous-year baseline.

## 3. Training data available before 2023

| Target year | Row year | Rows |
|---|---|---:|
| 2020 | 2019 | 72 |
| 2021 | 2020 | 74 |
| 2022 | 2021 | 74 |
| **Total** | | **220** |

- Rows with a missing licence value or target are left out, and nothing is imputed.
- Flagged rows **stay in** training, as in the selected experiment.
- **Rows from 2022 are not training rows,** because their target is the 2023 value.

## 4. Evaluation rows

- **Rows:** year 2022 rows with a 2023 target and a forecast from all three models. **Expected: 75**, the same for every model.
- **No imputation:** rejected values stay missing, and Dataset v2 is unchanged.
- **Blind forecasts:** every forecast is made from a copy with all 2023 values removed.
- **Scale:** the MASE scale uses one-year changes up to 2022 only.

## 5. Missing and flagged records

| Rows scored | Rule | Purpose |
|---|---|---|
| All rows | All 75 | **Primary result** |
| No flagged target | Removes rows whose 2023 target is flagged (9 rows expected) | Sensitivity |
| No flagged target or input | Also removes rows whose inputs (2020-2022) are flagged | Sensitivity, and the second row set in the decision rule |
| Also no outlier candidates | Also removes rows touching the eight EDA candidates | Sensitivity |

Flags are not changed or added for this evaluation. The same rows are removed for every model.

## 6. Metrics

- **Accuracy:** MAE, MASE, MAPE, median absolute percentage error.
- **Ranking,** per vehicle type: Spearman on level, top-5 overlap, also top-3 and top-10.
- **Change:** Spearman on change, top-5 overlap of change, direction accuracy. The previous-year forecast has no predicted change, so these do not apply to it.
- **By vehicle type:** motorcycles, cars and three-wheelers separately.
- **Uncertainty:** 95% intervals from 5,000 bootstrap resamples of whole series (seed 42). These describe variation across districts, not years.
- **Context, not rival models:** rank order frozen at 2019, and the "smaller districts change more" rule.

The code is the same as in the baseline evaluation and Step 6.

## 7. Decision rules

Fixed in the baseline evaluation, and applied here without change.

- **Meaningful accuracy improvement:** lower MAE and MAPE than the previous-year forecast on all rows and on rows with no flagged target or input, **and** a 95% MAE ratio interval entirely below 1 on both.
- **Ranking not worse:** Spearman and top-5 on levels no lower than the previous-year forecast on all rows.
- **Any claim about change:** a positive Spearman (change) in every vehicle type.
- **Best-performing:** the lowest MAE and the lowest MAPE on all rows, reported separately if they differ. This describes one year, and does not itself show a meaningful improvement.

## 8. Safeguards

- **Hash check:** the run stops if the plan, frozen code, configs or dataset differ from the freeze record.
- **One run only:** a lock is created before scoring, and a second run is refused. It is not removed if a run fails, as any restart would need disclosing and approving.
- **No tests on real 2023 scores before the run.** Tests use artificial data, and only read saved results afterwards.
- **After the run,** the code does not tune, select or try another model. Corrections to a mistake, if any, would be disclosed in the report.

## 9. What is already known about 2023

The final test year is **not truly unseen**, and this must be stated with any result.

- EDA and data cleaning displayed 2023 licence values.
- EDA reported rank stability from 2022 to 2023.
- Kandy's 2023 values are known to repeat 2022 exactly, so a previous-year forecast has zero error on those 3 rows.
- Other flagged 2023 values are known: Kalutara (3), Kilinochchi cars, Kurunegala motorcycles and Mannar three-wheelers.
- The outlier review read Mannar's 2023 column.

No model parameter, feature or penalty was chosen using 2023 **targets**. Awareness of these values still influenced how the project was designed, so the result is a stronger check than the development folds, but not a fully independent one.

## 10. Interpretation limits

Revenue-licence counts are a **proxy** for active vehicles. They are not actual mechanic-service demand, so no result here measures jobs, customers or income. A single target year also cannot show that a result holds in other years.
