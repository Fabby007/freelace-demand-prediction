# Dataset v2: Data Dictionary

Generated from `configs/dataset_v2.yaml`. One row per district, year and vehicle type.

Year t means the row's own year. Features use years up to t only; only the target uses t+1.

## Row key

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `district` | string | base |  | Canonical district name (REF-002). |

## Time

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `year` | integer | base |  | Observation year t of the row. |

## Model features

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `vehicle_type` | category | base |  | Motorcycle, Car or Three-wheeler. Categorical input; part of the row key. |
| `licence_count` | numeric, nullable | base |  | Revenue licences for year t after approved corrections: licence_count_printed, or empty where set to missing. A proxy for active vehicles, not an exact count. |
| `total_registrations` | numeric, nullable | base |  | Printed Total if its status is verified or verified_with_year_caveat; empty if flagged_not_verified. Secondary signal of fleet inflow. |
| `licence_lag_1` | numeric, nullable | engineered | `licence_count at t-1` | Previous year's licences for the same series. Empty for 2019 or where that value is missing. |
| `licence_lag_2` | numeric, nullable | engineered | `licence_count at t-2` | Licences two years earlier. Empty for 2019-2020 or where that value is missing. |
| `licence_growth_log` | numeric, nullable | engineered | `ln(licence_count at t / licence_count at t-1)` | Year-on-year growth. A log difference does not explode on small bases. Empty if either year is missing; it never bridges a gap. |
| `licence_rolling_mean_3` | numeric, nullable | engineered | `mean of licence_count over t-2, t-1, t` | Three-year mean including the latest year. Needs at least 2 observed values, and skips missing years. |
| `licence_rolling_std_3` | numeric, nullable | engineered | `sample standard deviation of licence_count over t-2, t-1, t` | Three-year variability including the latest year. Needs at least 2 observed values. |
| `total_registrations_lag_1` | numeric, nullable | engineered | `total_registrations at t-1` | Previous year's verified Total. Empty for 2019 or where that Total is not verified. |
| `total_registrations_growth_log` | numeric, nullable | engineered | `ln(total_registrations at t / total_registrations at t-1)` | Year-on-year growth in verified Totals. Empty if either Total is not verified. |

## Target

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `target_licence_count` | numeric, nullable | engineered | `licence_count at t+1` | PREDICTION TARGET: next year's revenue licences for the same district and vehicle type. A proxy for relative service opportunity, not a job count. |
| `target_year` | integer | engineered | `t+1` | The year being predicted. Later validation splits should be keyed on this. |

## Data quality

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `licence_value_status` | category | base |  | value, or set_missing where an approved correction removed a clearly incorrect value. |
| `licence_correction_id` | string, nullable | base |  | Corrections file entry that set this value to missing (L01 or L02). |
| `licence_flagged` | boolean | base |  | True if the value for year t is uncertain and kept for review. |
| `licence_flag_ids` | string, nullable | base |  | Corrections file entries behind the flag, separated by semicolons. |
| `total_registrations_status` | category | base |  | verified, verified_with_year_caveat (2021 as a whole slightly exceeds DMT) or flagged_not_verified. See total_registrations_verification.csv. |
| `licence_window_observations` | integer | engineered | `count of observed licence_count over t-2, t-1, t` | Observed values behind the rolling statistics (0-3), because early years and missing values shorten the window. |
| `target_status` | category | engineered |  | available, set_missing_next_year (next year's value was rejected), or no_next_year (2023 rows, kept for future predictions). |
| `target_flagged` | boolean | engineered |  | True if the target value is an uncertain value kept for review. Allows evaluation with and without such rows. |
| `target_flag_ids` | string, nullable | engineered |  | Corrections file entries behind the target flag. |
| `features_use_flagged_licence` | boolean | engineered |  | True if licences at t, t-1 or t-2 are flagged, so this row's lag or rolling inputs rest on an uncertain value. |
| `has_target` | boolean | engineered |  | True if target_licence_count is present. |
| `has_target_and_level` | boolean | engineered |  | True if both target_licence_count and licence_count are present. |

## Audit only, never model inputs

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `licence_row_label` | string | base |  | Row label as printed in Table 9.3, such as Motor Bicycles. |
| `licence_count_printed` | integer | base |  | Revenue licences exactly as printed for year t. Never a model input, because it still holds values rejected as clearly incorrect. |
| `total_registrations_printed` | integer | base |  | District Total Registrations exactly as printed in Table 9.4 for year t. All vehicle types, so the same on each of a district's three rows. Never a model input. |

## Provenance

| Column | Type | Stage | Calculation | Description |
|---|---|---|---|---|
| `licence_source_id` | string | base |  | Source table identifier for the licence value. |
| `licence_source_file` | string | base |  | Original PDF of Table 9.3. |
| `licence_source_page` | integer | base |  | PDF page holding the licence value. |
| `licence_source_url` | string | base |  | URL the PDF was downloaded from. |
| `licence_pdf_sha256` | string | base |  | SHA-256 of the PDF that was read. |
| `licence_source_note` | string | base |  | Source line printed under the table. Kurunegala cites DMT; all others cite Divisional Secretariats. |
| `registrations_source_id` | string | base |  | Source table identifier for the Total. |
| `registrations_source_file` | string | base |  | Original PDF of Table 9.4. |
| `registrations_source_page` | integer | base |  | PDF page holding the Total. |
| `retrieved_date` | date | base |  | Date the PDFs were downloaded. |

## Deliberately excluded

| Columns | Reason |
|---|---|
| month, quarter, month_sin, month_cos | The data is annual, so these can never be filled. |
| new_registrations (by category), reg_lag_1, reg_lag_2, reg_growth_pct, change_from_lag_2 | Category registrations are unreliable (corrections R01-R06, R10). Replaced by licence features and verified Totals. |
| rolling_mean_3, rolling_std_3 (v1) | v1 computed them on registrations and excluded the latest year. Replaced by licence versions covering t-2 to t. |
| population, population_density, vehicles_per_1000_people | DCS Chapter 2 has not been acquired, so these would be entirely empty. Add them when real data exists. v1's vehicles_per_1000_people also used registrations rather than vehicles. |
| split | Rolling-origin validation is designed at the modelling stage, keyed on target_year. |
