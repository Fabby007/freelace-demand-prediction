# Dataset v2: Report

**Status:** approved by the project author on 2026-11-07. No model has been trained on it.
**Lecturer approval of the target:** reported by the project author. Date: not yet provided. Method: not yet provided.
**Version:** `modelling_dataset_v2_04eaecafd7e1`
**Target:** next-year revenue-licence count per district and vehicle type. This is a proxy for relative service opportunity; it is not a count of mechanic jobs.

## 1. Size

| Item | Value |
|---|---:|
| Rows (25 districts x 5 years x 3 vehicle types) | 375 |
| Columns | 39 |
| Model features | 10 |
| Years | 2019-2023 |

## 2. Usable rows

| Rows with | Count | By target year |
|---|---:|---|
| A target | **299** | 2020: 75, 2021: 74, 2022: 75, 2023: 75 |
| Target and current licences | 295 | 2020: 72, 2021: 74, 2022: 74, 2023: 75 |
| Target and all licence features except `licence_lag_2` | 219 | 2021: 71, 2022: 74, 2023: 74 |
| The above plus `licence_lag_2` | 145 | 2022: 71, 2023: 74 |
| Target, licence features except `licence_lag_2`, and all registration features | 180 | 2021: 68, 2022: 59, 2023: 53 |

- The 76 rows with no target are the 75 rows for 2023, kept for future predictions, and Jaffna motorcycles 2020, whose next-year value was rejected.
- **The usable size depends on the features.** Lag and growth features need earlier years, so a model using them has about 219 rows rather than 299.

## 3. Applied corrections

The full cell-by-cell log, with original value, source PDF, page, URL, reason and decision, is `applied_corrections_v2.csv`.

| Action | Cells | Details |
|---|---:|---|
| Set to missing | 6 | Ampara 2019: Motor Cars 389, Motor Bicycles 9,057, Three Weelers 575, Total 10,152. Jaffna 2021: Motor Bicycles 13,091, Total 47,133 |
| Total left missing in features | 12 | Anuradhapura 2019-2021; Badulla 2022; Batticaloa 2021; Kegalle 2021-2022; Mannar 2023; Mullaitivu 2021 and 2023; Nuwara Eliya 2022; Vavuniya 2021 |
| Kept and flagged | 30 cells (31 log entries) | Uncertain licence values, such as Kandy 2023 and Mullaitivu 2019. One cell has two entries |

Only 4 of the 6 set-to-missing cells appear in the dataset. The 2 licence Totals are recorded for completeness and are not a dataset column.

Original printed values stay in the audit columns `licence_count_printed` and `total_registrations_printed`. These are never model inputs.

## 4. Missing values

No value was filled, estimated or converted to zero.

| Column | Empty | Why |
|---|---:|---|
| `licence_count` | 4 | Approved corrections |
| `licence_lag_1` | 79 | 75 for 2019 (no earlier year), plus the corrections |
| `licence_lag_2` | 154 | 150 for 2019-2020, plus the corrections |
| `licence_growth_log` | 80 | 75 for 2019, plus either year rejected |
| `licence_rolling_mean_3`, `licence_rolling_std_3` | 78 | Fewer than 2 observed values: 2019, and Ampara 2020 |
| `total_registrations` | 36 | 12 unverified Totals x 3 rows |
| `total_registrations_lag_1` | 105 | 75 for 2019, plus unverified Totals |
| `total_registrations_growth_log` | 129 | Either year unverified |
| `target_licence_count` | 76 | 75 for 2023, plus Jaffna 2020 |

## 5. Suspicious values still in the dataset

| Measure | Count |
|---|---:|
| Flagged licence values | 30 of 375 |
| Rows with a flagged target | 24 of 299 (Three-wheeler 13, Car 6, Motorcycle 5) |
| Rows whose lag or rolling window includes a flagged value | 56 |
| Rows with a target and current licences, and no flagged value in the target or inputs | 236 |

Totals have 60 rows (20 district-years) with `verified_with_year_caveat`, because 2021 as a whole is 101.2% of DMT's national figure.

The quality columns let later evaluation run with and without flagged rows. Kandy 2023 needs particular care: it is identical to 2022, so a "same as last year" forecast gets it exactly right.

## 6. Features

| Change | Columns |
|---|---|
| **Added** | `licence_lag_1`, `licence_lag_2`, `licence_growth_log`, `licence_rolling_mean_3`, `licence_rolling_std_3`, `total_registrations`, `total_registrations_lag_1`, `total_registrations_growth_log` |
| **Kept** | `licence_count` (v1's `vehicle_population`, now corrected), `vehicle_type` |
| **Removed: monthly** | `month`, `quarter`, `month_sin`, `month_cos` |
| **Removed: unreliable** | `new_registrations` by category, `reg_lag_1`, `reg_lag_2`, `reg_growth_pct`, `change_from_lag_2`, v1 `rolling_mean_3`, `rolling_std_3` |
| **Removed: no data yet** | `population`, `population_density`, `vehicles_per_1000_people` |

Every column is described in `data_dictionary_v2.md`.

**No future leakage:** features for year t use years up to t only, and a test confirms that changing later years leaves them unchanged. Unlike v1, the rolling statistics now include year t, because it is known when predicting t+1.

## 7. Integrity checks

- One row per district, year and vehicle type; all 75 series have all 5 years.
- Every licence value equals the printed value or is an approved missing value. A test confirms this from the extracted cells, independently of the build code.
- All targets were recomputed independently and match.
- Every row has provenance, and every source PDF exists.
- The build stops if a decision names a cell that was not extracted, or if a check fails. Rebuilding gives a byte-identical file.

## 8. Limitations

1. **Proxy target:** licences approximate active vehicles, and cannot be validated against real mechanic demand. Counts reflect renewals, which can fall during hardship even if vehicles are still in use.
2. **Partial coverage:** district licences sum to 57-85% of DMT's national vehicle population in the years compared (2019 and 2023), by vehicle type.
3. **Very stable target:** the median year-on-year change is about 4%, and the rank correlation of districts between consecutive years is 0.94-0.995. A "same as last year" baseline will be very hard to beat, and rankings may mostly mean "biggest districts". Scoring growth as well as level would make later evaluation more meaningful.
4. **Short series:** only four target years, and only three with full licence features, which limits rolling-origin validation to a few folds. 2020-2022 also includes a structural break.
5. **Uncertain values remain:** causes such as "not updated" or "copied" are unconfirmed and only DCS could confirm them. Errors that fit their row, Total and neighbours would not be detected.
6. **Screening used hindsight:** corrections and Total verification looked at all years, including later ones. For example, Jaffna 2021 was identified using 2022. No later value enters any feature, but which values are missing was decided retrospectively. This would not be possible when forecasting live, and should be disclosed.
7. **Verified does not mean confirmed:** no independent district-level source exists for Totals (see the extraction report).
8. **Repeated Total values:** the Total is the same on a district's three rows, because it covers all vehicle types. It cannot separate categories within a district.
9. **Different source:** Kurunegala's Table 9.3 cites DMT rather than Divisional Secretariats, so its basis may differ.
10. **Not yet in the data:** population (DCS Chapter 2) and earlier handbook editions.
11. **No split yet:** chronological rolling-origin validation is built at the modelling stage, keyed on `target_year`. The target stays as raw counts, and a log transform is considered then.
12. **Different from v1:** v1 results are not comparable with anything built on v2, because the target changed.

## 9. Files

| File | Contents | In git |
|---|---|---|
| `data/processed/v2/modelling_base_v2.csv` | Corrected values, before features | No (generated data) |
| `data/processed/v2/modelling_dataset_v2.csv` | The dataset | No (generated data) |
| `reports/dataset_v2/applied_corrections_v2.csv` | Every affected value and why | Yes |
| `reports/dataset_v2/data_dictionary_v2.md` | Every column | Yes |
| `reports/dataset_v2/dataset_v2_manifest.json` | Version, hash and inputs | Yes |

To rebuild from the PDFs and documented corrections:

```
python -m src.data.validate_dcs_extraction
python -m src.features.build_dataset_v2
```

The PDFs are not in git. The extractor also reads source URLs and download dates from `data/interim/dcs_multi_district_2024_raw.csv`, which is not in git either.
