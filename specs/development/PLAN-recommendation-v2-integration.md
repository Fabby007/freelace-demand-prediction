# Recommendation System Integration Plan (Dataset v2)

**Status:** approved by the project author on 2026-11-07 (Step 8). Decisions are recorded in Section 9, REF-009 ADR-042 and ADR-043. The author approved the switch on 2026-11-07, so v2 is now the default; v1 stays available for rollback.
**Date:** 2026-11-07
**Based on:** `reports/final_evaluation_v2/final_evaluation_report.md`, commit `4e7a691`, dataset `modelling_dataset_v2_04eaecafd7e1`.

## 1. Recommendation

Replace the model output shown to users with a plain, read-only indicator of **where licensed vehicles are**, built from Dataset v2, using the previous-year baseline that won the final evaluation.

- **No model is loaded or trained.** The next-year estimate equals the latest licence count.
- **The change is additive.** The v1 engine, model and tests stay. A single config setting chooses which one the dashboard and Opportunity Insights use, so rollback is one line.
- **The rest of the marketplace is not touched.**

## 2. What exists now

| Part | Today | Issue for this plan |
|---|---|---|
| `src/recommendation/ranking_engine.py` | Loads `models/xgboost_v1` and Dataset v1, returns ranked districts, bands and SHAP factors | Forecasts **new registrations** with a model that had test R² 0.14 and one negative prediction, on the older extraction |
| `dashboard/` (Streamlit) | One `cached_rank` feeds map, table and detail panel | Good structure. Labels say "demand", "predicted" and "XGBoost (tuned)", and the trend shows registrations |
| `app/routes/insights.py` | The only `app/` to `src/` link, with a lazy singleton and a 503 fallback | Good structure. Calls `RankingEngine` and describes XGBoost and SHAP |
| Marketplace (search, profiles, reviews, admin) | Independent of the ML system | No change needed |

Website users therefore see a different quantity, from a weaker pipeline, than the one the research now supports. This plan closes that gap.

## 3. Architecture

```
data/processed/v2/modelling_dataset_v2.csv     data/corrections/source_anomalies_v2.csv
        |   (read only, hash checked)                   |   (flag reasons)
        v                                               v
src/recommendation/fleet_opportunity_v2.py   <-- configs/recommendation_v2.yaml (NEW)
        |   rank(vehicle_type, period, top_n), same dict shape as RankingEngine
        v
src/recommendation/active_engine.py  (NEW: reads the setting, returns v1 or v2 engine)
        |                                  |
        v                                  v
dashboard/data_access.py            app/routes/insights.py  (still the only app-to-src link)
```

- **Same shape.** `rank()` returns the existing keys, so map, table, CSV download, fallback states and most tests keep working. `predicted_value` holds the estimate, and the factor lists are empty. New keys: `indicator_type`, `share_pct`, `reliability`, `flag_reasons`, `explanation_facts`.
- **Same helpers.** It exposes `frozen_df`, `canonical_districts`, `config`, `metadata` and `rank_from_query`, which the callers already use.
- **Fail clearly.** If the dataset hash does not match the config, loading raises an error and the existing error page appears. It never serves unverified numbers.
- **Boundaries kept.** `src/` and `dashboard/` never import `app/`, marketplace data never enters `data/` or any model, and the indicator writes nothing.

### How Dataset v2 and the baseline connect

| Dataset v2 column | Use |
|---|---|
| `licence_count` | The indicator value, rank, share and band |
| `licence_flagged`, `licence_flag_ids` | Reliability label and reason |
| `features_use_flagged_licence` | Caution on the recent-change text only |
| `total_registrations`, `total_registrations_status` | Optional context, shown only when verified. Never used in ranking |

The baseline rule is one line: **estimate for year t+1 = licence count in year t.** The latest year is 2023, so the 2024 estimate equals the 2023 count. Showing it as a separate forecast would suggest independent information that does not exist, so the page leads with the 2023 count.

## 4. The indicator

**Name:** Relative Vehicle-Fleet Opportunity Indicator. Calculated separately for each vehicle type.

| Output | Rule |
|---|---|
| Licensed vehicles | `licence_count` for the selected year |
| Share of category | District count divided by the total of reporting districts |
| Rank | Highest count first. Ties: district name A to Z |
| Band | Quartiles of that vehicle type and year: Low, Moderate, High, Very High |
| Reliability | `Reported`, or `Uncertain value` with the reason from the anomaly register |
| Recent change | Previous year to selected year, labelled as history. Not used in rank or band |
| Missing value | No rank or band, listed as "no reported value", never zero |

**Deliberately left out**
- **No composite score or weights.** No job data exists to justify any weighting, so weights would be invented.
- **No growth ranking.** Growth ranks did not persist (-0.581 to +0.060) and reduce to "smaller districts change more".
- **No per-capita measure.** Population is not in the dataset.
- **No removal or correction of flagged values, and no outlier filter.** Flagged values stay visible, and the eight outlier candidates stay sensitivity only.

**Bands are relative by construction.** Quartiles place about a quarter of districts in each band (7, 6, 6, 6 for 2023), so "Low" means fewer vehicles than other districts, not little work.

### Why broad bands are defensible

These checks used existing dataset values and saved forecasts. No model was run.

| Check | Car | Motorcycle | Three-wheeler |
|---|---|---:|---:|
| Band changed between consecutive years, 2019 to 2023 | 5 of 99 | 11 of 97 | 10 of 99 |
| Typical year-to-year change (median, target years 2021-2023) | 4.6% | 2.8% | 3.9% |
| 1 in 10 changes exceeded | 18.6% | 12.6% | 15.7% |
| Adjacent 2023 ranks closer than the typical change, all 24 pairs | 7 | 3 | 5 |
| Adjacent ranks closer than the typical change, top 5 (4 pairs) | 0 | 0 | 0 |
| Districts within the typical change of a band boundary, 2023 | 6 of 25 | 3 of 25 | 8 of 25 |

So bands are mostly stable and the top five are separated by more than a typical change, but many mid-table positions and some band edges are not firm. The display should say so.

### Flagged values at 2023

Nine values are flagged. Three of them are in a top-five list.

| District and type | 2023 | Rank | Band | Note |
|---|---:|---:|---|---|
| Kurunegala, Motorcycle | 394,975 | 1 | Very High | **First place rests on this value.** On 2022 values it ranked 2nd, behind Gampaha |
| Kandy, Car | 52,858 | 3 | Very High | Identical to 2022 |
| Kandy, Three-wheeler | 78,853 | 3 | Very High | Identical to 2022 |
| Kandy, Motorcycle | 120,945 | 9 | High | Identical to 2022 |
| Kalutara, Car | 20,737 | 6 | Very High | Flag L09 |
| Kalutara, Motorcycle | 98,598 | 13 | Moderate | Flag L09 |
| Kalutara, Three-wheeler | 34,165 | 11 | High | Flag L09 |
| Kilinochchi, Car | 2,356 | 22 | Low | Flag L08. 569 in 2022 |
| Mannar, Three-wheeler | 1,365 | 24 | Low | Flag L16 |

All nine sit in the same band as they did in 2022, which supports showing bands first. For Kandy this is automatic, because its values repeat.

## 5. Fleet opportunity is not mechanic-service demand

| | Vehicle-fleet opportunity (what we show) | Mechanic-service demand (what we do not have) |
|---|---|---|
| Measures | Revenue licences issued per district and vehicle type | Repairs, bookings, jobs, spending |
| Source | DCS handbook tables | No such dataset was found |
| Can be validated against the target | Yes, against later licence counts | No |
| Valid claim | "More licensed motorcycles are recorded here than in most districts" | "There is more mechanic work here" (**not supported**) |

**Unknown and not implied:** servicing frequency, vehicle age, competition from existing garages, prices, and where vehicles are actually used, since licences show where they were licensed.

**Wording rules for v2 mode**

| Replace | With |
|---|---|
| Predicted value | Licensed vehicles (2023) |
| Predicted opportunity by district | Relative vehicle-fleet opportunity by district |
| Why this prediction? | Why this district ranks here |
| Historical registration trend | Licensed vehicles over time |
| Production model: XGBoost (tuned) | Method: previous-year value (no machine-learning model) |
| Mechanic Service Demand Opportunity (dashboard title) | Vehicle-Fleet Service Opportunity |

Never use "demand", "jobs", "customers", "best district" or "guaranteed" to describe the output.

**Standard text, on every view that shows a ranking**
- The required disclaimer, verbatim: "Predictions are based on available historical and proxy data. They indicate relative service opportunity and do not guarantee customer numbers, employment or income."
- Meaning note: "This shows how many vehicles hold a revenue licence in each district. It does not measure mechanic jobs."
- Evidence note: "On the 2023 evaluation, machine-learning models did not beat last year's value, so this page uses last year's value."

The marketplace review disclaimer stays separate and is never merged with these.

**Example recommendation:** "For motorcycle mechanics, Anuradhapura had 186,540 licensed motorcycles in 2023, ranking 5th of 25 districts and in the Very High band. This describes fleet size, not mechanic work."

## 6. Display

| Item | Recommendation |
|---|---|
| Vehicle categories | Vehicle type chosen first. Results are never combined across types. SBERT only selects the type, and unsupported queries keep today's safe fallback |
| Map | Coloured by **band**, not exact count, from the same output as the table |
| Ranking table | Rank, district, band, licensed vehicles, share, reliability. Whole numbers only |
| Rank positions | Top 5 named with reasons. Below that, lead with the band and note that nearby positions can swap |
| Flagged values | Badge with icon and text (not colour alone), with the reason. Top-five flags are also stated in the summary line |
| Trend | Licence counts 2019-2023, flagged years marked, gaps for missing years |
| Missing data | Clear message naming the districts: Ampara in 2019 (all three types), Jaffna motorcycles in 2021 |
| Period selector | Years 2019-2023. Only 2023 shows the 2024 estimate. Earlier years are labelled as history |
| Uncertainty | One note per vehicle type using the table above, for example "Motorcycle counts typically change about 3% a year, but 1 in 10 changed by more than 13%". No per-district ± range, as these are past changes, not prediction intervals |
| Data panel | Dataset version, data cut-off (2023), source register, evaluation results, licence coverage (57-85% of the DMT national population, by vehicle type) |
| CSV download | Includes band, reliability and flag reasons |

## 7. Reuse and changes

**Reused unchanged**
- SBERT router, district lookup, GeoJSON and map builder
- Sidebar controls and form validation
- Source register panel, disclaimer constants
- Lazy singleton, 503 fallback and no-data states
- Every marketplace feature, plus login and access rules on the Insights page

**New**
- `src/recommendation/fleet_opportunity_v2.py`
- `src/recommendation/active_engine.py`
- `configs/recommendation_v2.yaml`
- Tests for all of the above

**Modified (in v2 mode only; v1 output stays as it is)**

| File | Change |
|---|---|
| `dashboard/data_access.py` | Load the active engine. History reads licences in v2 mode. Metadata comes from the engine |
| `dashboard/views.py` | Trend labels and flag markers, version panel fields, band-coloured map |
| `dashboard/app.py` | Titles, explanation panel, notes, period labels |
| `app/routes/insights.py` | Use the active engine. `_model_info` reports method and evaluation |
| `app/templates/insights/opportunity_insights.html` | Column names, factors replaced by facts, notes, flag badges |

**Not changed:** Dataset v1 and v2, `models/`, `ranking_engine.py`, final evaluation outputs, `app/models`, the database, and all other routes and templates.

## 8. Phases

Each phase ends with a review. Nothing is committed without approval.

| Phase | Work | Done when |
|---|---|---|
| 0. Decisions | Answer Section 9, then record ADRs and update DEV-012, DEV-013 and DEV-023 | ADRs accepted |
| 1. Indicator | New module, config and tests. No interface change | Results match hand-checked values, and the full suite passes |
| 2. Dashboard | Connect behind the setting, default still v1 | Same values in map, table and detail panel, with v1 mode unchanged |
| 3. Insights page | Connect behind the setting, default still v1 | v2 page works through the real route, with marketplace tests unchanged |
| 4. Switch default | Change the default to v2, pin v1-specific tests to v1 mode | Full suite passes, both modes run, rollback tested |

**Tests to add**
- Rank, band and share recalculated separately from the dataset
- Missing values never become zero or a rank
- Dataset hash mismatch refuses to load
- Flagged rows always carry a reason
- `rank()` keys match what the callers need
- No model file is opened in v2 mode
- Disclaimer text is exact, and banned wording is absent
- Map and table values are identical
- No `app/` import from `src/` or `dashboard/`
- Dataset and model checksums unchanged after a run

76 existing tests touch these surfaces. With v1 as default through Phase 3, they should keep passing without edits.

## 9. Open Questions / Conflicts

All three decisions were made by the project author on 2026-11-07.

### Decision 1: the SHAP rule conflicts with the evaluation result

**Resolved: option A, recorded as ADR-042.** v2 uses rule-based explanations. SHAP and the original XGBoost implementation stay unchanged for Dataset v1.

**Conflict.** CLAUDE.md Section 20, MASTER_PROMPT Section 0 and DEV-012 require a SHAP-based explanation with every top-ranked recommendation, calling this non-negotiable. The previous-year baseline has no fitted model, so there is nothing for SHAP to explain.

| Option | Assessment |
|---|---|
| **A. Rule-based explanation in v2 mode, SHAP kept in v1 mode and the research record (recommended)** | Honest: the reason a district ranks highly really is its licence count. Needs an ADR, because it changes a documented rule |
| B. Keep XGBoost v1 with SHAP as the recommendation | Keeps the rule, but presents a model the research did not support, for a different target |
| C. Show SHAP from a Ridge or XGBoost model beside the baseline | Would explain a model that is not producing the numbers, which is misleading. Could also require new training |

Under option A, the explanation states the count, share, rank, band and any flag. All of it comes directly from the data. SHAP, XGBoost and the evaluations stay in the project as completed work, and the change is recorded, not silently dropped. Because the documentation calls this rule non-negotiable, you may also want to raise it with your lecturer.

### Decision 2: when to make v2 the default

**Resolved.** v1 stays the default, with a config switch to enable v2. v2 becomes the default only after all integration tests pass and the project author approves the switch. Phase 4 is therefore not part of Step 9. After a switch, v1 remains available as a research record, not as a recommendation.

**Update 2026-11-07:** all integration tests passed and the project author approved the switch. `active_engine` is now `v2`. Setting it back to `v1` and restarting both apps rolls back.

### Decision 3: user-facing name

**Resolved.** "Vehicle-Fleet Service Opportunity" is the interface label. The official project title is preserved, and the page text explains the difference.

## 11. Implementation notes

- **Period meaning matches v1.** `rank(vehicle_type, period)` takes the estimate year and reads the previous year's count, exactly as v1 reads `period - 1`. The selector is labelled by data year, for example "2023 data (2024 estimate)". Earlier years are shown as history.
- **Share.** "Vehicle-category share" means a district's share of that vehicle type's licences across reporting districts, as defined in Section 4.
- **Historical change.** Compares the selected year with the year before it, and is empty when either count is missing.

## 10. Limitations

**Research**
1. **Proxy only.** Licences are not mechanic demand, and this cannot be validated against job data.
2. **One final year.** The result rests on target year 2023, which was not fully unseen because EDA and cleaning displayed its values.
3. **Short history.** Five years, overlapping a structural break.
4. **Rankings describe size.** They reflect stable fleet size and add no forecasting advantage.
5. **Missing context.** No population, vehicle age, price, usage or competition data.
6. **Administrative effects.** Licences reflect renewals and where vehicles are licensed. They cover 57-85% of the DMT national population by vehicle type.
7. **Lecturer approval.** The date and method of the target approval are still "not yet provided".

**Technical and data**
8. **Data cut-off is 2023.** The 2024 estimate is unvalidated and assumes no change, and the data is about three years old at the time of writing. A newer handbook is not part of this plan.
9. **Flagged values remain.** 9 of 75 values at 2023 are uncertain, with causes unconfirmed, including the top motorcycle rank.
10. **Band-edge sensitivity.** 3 to 8 of 25 districts per type sit within a typical change of a boundary.
11. **Outdated document.** The Research Brief still has old figures (2.51M, "198 usable") and needs updating separately.
12. **Backups.** All backups are on one machine, with no off-site copy. The newest needs the v1 backup for v1 files, and a fresh environment install has not been tested.
