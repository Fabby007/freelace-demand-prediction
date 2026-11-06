# DMT Cross-Validation Report

DEV-003, Section 10 step 6: extracted district-level DCS totals (summed across all 25 districts) compared against DMT national statistics for the same vehicle category and year.

Source: `data/raw/dmt/DMT_Vehicle_Population_2014-2025.pdf` (Department of Motor Traffic, 'NEW REGISTRATION OF MOTOR VEHICLES' and 'TOTAL VEHICLE POPULATION' tables).

| Vehicle type | Year | Metric | District sum | DMT national | Ratio | Note |
|---|---|---|---|---|---|---|
| Motorcycle | 2019 | new_registrations | 198235 | 284,301 | 69.7% |  |
| Motorcycle | 2019 | vehicle_population | 2507701 | 4,668,074 | 53.7% |  |
| Motorcycle | 2020 | new_registrations | 97143 | 151,634 | 64.1% |  |
| Motorcycle | 2020 | vehicle_population | 2630952 | 4,819,708 | 54.6% |  |
| Motorcycle | 2021 | new_registrations | 5948 | 8,011 | 74.2% |  |
| Motorcycle | 2021 | vehicle_population | 2496724 | 4,827,719 | 51.7% |  |
| Motorcycle | 2022 | new_registrations | 6571 | 9,060 | 72.5% |  |
| Motorcycle | 2022 | vehicle_population | 2654963 | 4,836,779 | 54.9% |  |
| Motorcycle | 2023 | new_registrations | 17498 | 20,200 | 86.6% |  |
| Motorcycle | 2023 | vehicle_population | 2964236 | 4,856,979 | 61.0% |  |
| Car | 2019 | new_registrations | 52052 | 38,232 | 136.1% | **EXCEEDS NATIONAL TOTAL** |
| Car | 2019 | vehicle_population | 563806 | 875,864 | 64.4% |  |
| Car | 2020 | new_registrations | 27980 | 21,021 | 133.1% | **EXCEEDS NATIONAL TOTAL** |
| Car | 2020 | vehicle_population | 552952 | 896,885 | 61.7% |  |
| Car | 2021 | new_registrations | 5161 | 3,495 | 147.7% | **EXCEEDS NATIONAL TOTAL** |
| Car | 2021 | vehicle_population | 551886 | 900,380 | 61.3% |  |
| Car | 2022 | new_registrations | 1367 | 1,489 | 91.8% |  |
| Car | 2022 | vehicle_population | 562433 | 901,869 | 62.4% |  |
| Car | 2023 | new_registrations | 1765 | 1,816 | 97.2% |  |
| Car | 2023 | vehicle_population | 587937 | 903,685 | 65.1% |  |
| Three-wheeler | 2019 | new_registrations | 6071 | 15,490 | 39.2% |  |
| Three-wheeler | 2019 | vehicle_population | 963918 | 1,175,077 | 82.0% |  |
| Three-wheeler | 2020 | new_registrations | 2342 | 7,150 | 32.8% |  |
| Three-wheeler | 2020 | vehicle_population | 878152 | 1,182,227 | 74.3% |  |
| Three-wheeler | 2021 | new_registrations | 843 | 2,093 | 40.3% |  |
| Three-wheeler | 2021 | vehicle_population | 860119 | 1,184,320 | 72.6% |  |
| Three-wheeler | 2022 | new_registrations | 448 | 36 | 1244.4% | **EXCEEDS NATIONAL TOTAL** |
| Three-wheeler | 2022 | vehicle_population | 849588 | 1,184,356 | 71.7% |  |
| Three-wheeler | 2023 | new_registrations | 54 | 60 | 90.0% |  |
| Three-wheeler | 2023 | vehicle_population | 913529 | 1,184,416 | 77.1% |  |

## Findings

- **`vehicle_population`**: district sums are consistently 52-82% of the DMT national total across all three vehicle categories and all five years - plausible (Table 9.3, the 'Revenue License issued' count, is not guaranteed to capture every registered vehicle nationally, e.g. vehicles not renewing annually) and internally consistent (no ratio approaches or exceeds 100%).
- **`new_registrations` for Motorcycle**: district sums are 64-87% of the national total across all five years - plausible, similar pattern to vehicle_population.
- **`new_registrations` for Car (2019-2021)**: district sums are 133-148% of the national total - **logically impossible** if both figures measure the same real-world quantity (a sum over districts cannot exceed the national total). This is a genuine, unresolved discrepancy between the DCS district-level 'Car' category and DMT's national 'MOTOR CARS' class - not an artifact this pipeline can confidently explain away (candidate causes: differing category definitions between the two government agencies, different registration-event definitions e.g. first registration vs. any new district registration, or a genuine data-entry difference between the two publications). Flagged in the processed dataset (`data_quality_flag`), not silently corrected or hidden.
- **`new_registrations` for Three-wheeler (2022)**: district sum (448) is over 12x the DMT national total (36) - an extreme, logically impossible discrepancy for the single year with the most severe import restrictions in the underlying data (see REF-006 risk table). Flagged in the processed dataset for the same reason as Car above.

## Disposition

Per Section 11 ('compare extreme values against the source publication before removing/winsorising'), these rows are **flagged, not removed or corrected** - the DCS district figures are genuinely what the source publication states, and this report documents that they do not reconcile with DMT's national figures for these specific category/year combinations. DEV-005/DEV-006 must treat `new_registrations` for Car and Three-wheeler with this caveat in mind (e.g. when deciding whether these years/categories are reliable enough to use in the modelling dataset), and DEV-016 must disclose this limitation rather than presenting the dataset as fully reconciled.