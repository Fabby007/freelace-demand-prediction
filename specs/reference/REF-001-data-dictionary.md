# REF-001 — Data Dictionary & Dataset Schema

**Status:** Approved reference specification
**Source:** Appendix A and Section 9 of the Final Project Documentation (`Mechanic_Demand_Prediction_Project_Documentation.docx`), reproduced verbatim below.

---

## 1. Purpose

This is the canonical schema for the modelling dataset (the long-format district/time/vehicle_type table). Every development spec that reads or writes this dataset (DEV-003 through DEV-014) must conform to this schema rather than re-defining columns locally. Any new column introduced during implementation must be added here first, with an ADR in REF-009 if it deviates from or extends the documented schema.

## 2. Dataset shape

One row per **district, time period (year, and month where available), and vehicle category** (long format) — see Section 9 of the source documentation.

## 3. Appendix A — Suggested Data Dictionary (verbatim)

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

## 4. Section 9 — Proposed Dataset Design, example row (verbatim)

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

## 5. Granularity rule

"When monthly data does not exist consistently, prefer a clean yearly dataset over pretending to have monthly detail. Granularity is determined by the real source data." (Source doc, Section 9.) This is a **data-driven decision point**, not a defect — see `specs/COVERAGE.md`. The final chosen granularity must be recorded in DEV-006 once the real source coverage is known, and the `month` column left null (not fabricated) if only yearly data is reliably available.

## 5a. Dataset v2

This file describes the Dataset v1 schema. Dataset v2 has its own column list in `configs/dataset_v2.yaml`, published as `reports/dataset_v2/data_dictionary_v2.md` (REF-009 ADR-037). It leaves out `month`, `population` and related columns, for the reasons recorded there.

## 6. Columns beyond this dictionary

Additional engineered columns (e.g. `rolling_std_3`, `vehicles_per_1000_people`, cyclic `month_sin`/`month_cos`, `demand_lag_1`) are introduced by DEV-005 (Feature Engineering) per Section 12 of the source doc. They extend this dictionary rather than replace it. When DEV-005 finalizes the feature list, append the new columns to Section 3 of this file (with type, description, and "Engineered" status) rather than duplicating the table elsewhere.

**DEV-005 engineered columns (finalized 2026-08-15):** produced by `src/features/build_features.py` from the DEV-004 processed dataset, config-driven via `configs/feature_list.yaml` (kept in sync by `tests/test_feature_engineering.py::test_engineered_columns_match_config`).

| Column | Type | Description | Required? |
|---|---|---|---|
| reg_lag_1 | numeric/null | Previous-period (t-1) `new_registrations`, within district x vehicle_type | Engineered |
| reg_lag_2 | numeric/null | Two-period (t-2) lag of `new_registrations` | Engineered |
| reg_growth_pct | numeric/null | Percentage growth vs. `reg_lag_1`; null when `reg_lag_1` is null or zero | Engineered |
| change_from_lag_2 | numeric/null | `new_registrations` minus `reg_lag_2` | Engineered |
| rolling_mean_3 | numeric/null | Mean of the up-to-3 periods strictly before t (never includes t) | Engineered |
| rolling_std_3 | numeric/null | Std. dev. of the up-to-3 periods strictly before t (needs >=2 non-null) | Engineered |
| quarter | numeric/null | Null in the current dataset version - yearly-only, no `month` data (Section 5 granularity rule) | Engineered |
| month_sin | numeric/null | Cyclic month encoding; null for the same reason as `quarter` | Engineered |
| month_cos | numeric/null | Cyclic month encoding; null for the same reason as `quarter` | Engineered |
| vehicles_per_1000_people | numeric/null | `new_registrations` / `population` x 1000; null in the current dataset version since `population` is not yet populated (DEV-003 has not yet acquired DCS Chapter 2 population tables - see `data/source_register.csv`, `DCS_Kandy_2024_Chapter02_Population`) | Engineered |

`demand_lag_1` is **not** produced: `configs/target_config.yaml` records `is_real_demand_target: false` (Fallback path, DEV-002 Target Decision Record) — there is no real observed demand series to lag. If a future session locates a real demand dataset and revisits the DEV-002 decision (see its documented re-evaluation trigger), `demand_lag_1` must be implemented then, following the same leakage-safe pattern as `reg_lag_1`.

**DEV-006 target and split columns (finalized 2026-08-15):** produced by `src/features/assemble_modelling_dataset.py` from the DEV-005 feature-engineered dataset, written to `data/processed/modelling_dataset_v1.csv` (the frozen modelling dataset, versioned by content hash — see REF-009 ADR-009). Split boundaries are config-driven via `configs/split_config.yaml` (kept in sync by `tests/test_dataset_assembly.py::test_split_boundaries_are_config_driven_not_hardcoded`).

| Column | Type | Description | Required? |
|---|---|---|---|
| target_value | numeric/null | Fallback-path target: next-period (`year + 1`) `new_registrations` for the same district x vehicle_type series — a real, observable proxy forecast, never the row's own-period value. Null for the most recent observed year (no future observation exists yet) or where the underlying t+1 source observation is itself genuinely missing (see REF-009 ADR-005) — never fabricated. | Yes for training |
| target_year | integer/null | The year `target_value` was actually observed in (`row's year + 1`); null wherever `target_value` is null. | Engineered |
| target_data_quality_flag | string/null | The `data_quality_flag` (REF-006 Section 5.1) carried over from the row that supplied `target_value`, not the feature row's own flag — see REF-009 ADR-007 for why the target side is flagged separately from the feature side. | Engineered |
| split | string | One of `train` / `validation` / `test` / `unlabeled`. `unlabeled` rows have a null `target_value` and are excluded from every split (see REF-009 ADR-008) — retained in the frozen dataset because they are the exact rows a live dashboard would use for next-period inference. | Engineered |

**DEV-004 processed-schema extension (implemented 2026-08-15):** `new_registrations` and `vehicle_population` are sourced from two different DCS tables (Table 9.4 and Table 9.3 respectively), which can have different provenance per row. Rather than a single `source_id`/`source_url` pair, the actual processed file (`data/processed/modelling_base_*.csv`) carries one pair per metric: `new_registrations_source_id`, `new_registrations_source_url`, `vehicle_population_source_id`, `vehicle_population_source_url`, plus `new_registrations_raw`/`vehicle_population_raw` (archived raw text) and `new_registrations_quality_note`/`vehicle_population_quality_note` (missing-value provenance — see REF-009 ADR-005). A single shared `retrieved_date` is kept since both tables were downloaded in the same run. This is an implementation extension of this dictionary, not a contradiction of it — see `src/data/clean_dataset.py`.

## 7. Provenance requirement

Every row in the processed dataset must carry non-null `source_id`, `source_url`, and `retrieved_date` (Section 26.1 data test: "source_id exists for every processed row"). This is enforced by DEV-004 and tested by DEV-015. Per the Section 6 schema extension above, this is satisfied as "at least one of `new_registrations_source_id` / `vehicle_population_source_id` is non-null" in the actual processed file — tested by `tests/test_data_cleaning.py::test_source_id_exists_for_every_processed_row`.

## 8. Related specs

- DEV-003 (Data Acquisition & Extraction Pipeline)
- DEV-004 (Data Cleaning, Normalization & Validation)
- DEV-005 (Feature Engineering Pipeline)
- DEV-006 (Modelling Dataset Assembly & Target Definition)
- REF-002 (District & Vehicle-Category Canonical Lists)
