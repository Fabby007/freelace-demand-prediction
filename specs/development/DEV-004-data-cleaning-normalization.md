# DEV-004 — Data Cleaning, Normalization & Validation

## Specification ID
DEV-004

## Feature/Module Name
Data Cleaning, Normalization & Validation

## Purpose
Turn raw/interim extracted observations into a clean, validated, provenance-tagged processed dataset conforming to REF-001's schema, ready for feature engineering.

## Background/Context
Source doc Section 11 (Data Cleaning and Preprocessing) and Section 26.1 (Data tests). This spec also owns confirming the final canonical district list (REF-002) against the actual handbook spellings encountered during DEV-003 extraction.

## Related Requirements
- FR-02 (clean and normalize district and vehicle-category names)
- Section 11, Section 26.1
- REF-001 (Data Dictionary), REF-002 (Canonical Lists)

## User Roles
None (backend pipeline).

## Preconditions
DEV-003 complete: interim extracted data exists in `data/interim/`.

## User Stories/Use Cases
- As the developer, I need every raw district/vehicle-category spelling mapped to one canonical value so downstream grouping/joins are correct.
- As the developer, I need missing values investigated and preserved as missing (never auto-zeroed) so the model doesn't learn a false signal from fabricated zeros.
- As the developer, I need every processed row traceable to its source so the dataset is defensible in the viva (Section 26.1: "source_id exists for every processed row").

## Functional Requirements
Implements Section 11 rules:
1. **District normalisation:** map spelling variations to the 25 official district names (REF-002). Confirm/finalize REF-002's canonical spellings against the actual DCS handbook text encountered; update REF-002 if a correction is needed (log the correction, don't silently diverge).
2. **Vehicle-category normalisation:** map "Motor Cycle," "Motorcycle," etc. to one canonical category (REF-002 Section 4).
3. **Duplicate handling:** retain one observation per district-year (per vehicle category) across multiple handbook editions using a documented source-priority rule (e.g. most recent handbook edition wins, or the edition explicitly covering that observation year as primary — document the exact rule chosen here once decided, and log the choice as an ADR in REF-009 since the source doc leaves the exact tie-break rule to be defined).
4. **Missing values:** investigate why a value is missing; do not automatically convert blanks to zero. Missing values must be surfaced (e.g. left as NaN with a logged count), never silently replaced.
5. **Outliers:** compare extreme values against the source publication before removing/winsorising; do not remove an outlier just because it looks unusual without checking the source.
6. **Numeric conversion:** remove commas/footnote markers while preserving the original raw text in the source archive (`data/raw/` is untouched; conversions happen only in `data/interim/`/`data/processed/`).
7. **Time sorting:** sort each district/vehicle-category series chronologically before any lag-feature construction (used later by DEV-005).
8. **Scaling:** not applied here — XGBoost normally does not require feature standardisation; LSTM input scaling (fit on training data only) is owned by DEV-009.
9. **Categorical encoding:** not applied here — encoding for model input is owned by DEV-008/DEV-009 as needed.
10. **Train-test separation ordering:** the chronological split itself is DEV-006's responsibility, but this spec must ensure no cleaning step (e.g. an outlier threshold, an imputation value) is derived using full-dataset statistics that include future periods relative to any given district/vehicle series — cleaning transformations must not leak future information forward.
11. Append source metadata (`source_id`, `source_url`, `retrieved_date`) to every row (carried through from DEV-003, verified/finalized here).
12. Write cleaned data to `data/processed/` as CSV/Parquet.
13. Implement and run automated validation tests on the processed dataset (Section 26.1 list — see DEV-015; written here incrementally per DEV-PLAN.md Section 5).

## Business Rules
- Never auto-zero a missing value (Hard Rule-adjacent; Section 11 explicit rule).
- Never silently drop an "unknown" district/category name — it must fail the normalization step visibly (Section 26.1 test: "no unknown district names after normalization").
- Duplicate resolution must follow one documented, consistent rule — not ad hoc per-district judgment calls.

## Data Requirements
Output conforms to REF-001 Section 3 (Appendix A) column set at minimum: `district`, `year`, `month` (nullable), `vehicle_type`, `new_registrations`, `vehicle_population` (nullable), `population` (nullable), `population_density` (nullable), `source_id`, `source_url`, `retrieved_date`. Engineered columns (`reg_lag_1`, etc.) are added in DEV-005, not here.

## Database/Schema Changes
Establishes the processed dataset file(s) under `data/processed/` per REF-001.

## API Requirements
None.

## Backend Behavior
- Cleaning/normalization logic lives in `src/data/` (shared module, not duplicated per district or vehicle type — Maintainability NFR, MASTER_PROMPT.md Section 9 "no copy-pasted logic across district/vehicle-category handling").
- Lookup tables (district, vehicle-category) are data files under `configs/`, not hardcoded in Python, so they can be corrected without a code change.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
Section 26.1 Data tests (implemented here, consolidated in DEV-015):
- No unknown district names after normalization.
- No duplicated district-time-vehicle key unless explicitly justified.
- Numeric fields contain valid ranges (e.g. non-negative registration counts).
- Observation years match source tables.
- Missing values are reported, not silently replaced.
- `source_id` exists for every processed row.

## Permissions
N/A.

## Error Cases
- An unmappable district/category string — validation must fail loudly (raise/flag), not silently drop the row or guess a mapping.
- A duplicate district-year-vehicle key with conflicting values and no clear source-priority winner — flag for manual review rather than averaging or arbitrarily picking one.

## Edge Cases
- A district present in only some handbook editions — retain what's genuinely observed; do not backfill/interpolate at this stage.
- A table with an obvious transcription/outlier value (e.g. a registration count 100x neighbors) — compare against the source publication before deciding to keep, correct, or flag as missing.

## Security Considerations
None beyond REF-005 (no personal data should have entered the pipeline by this stage; if it has, it must be removed here).

## Dependencies
- DEV-003 (Data Acquisition & Extraction Pipeline)
- REF-001 (Data Dictionary), REF-002 (Canonical Lists & Normalization Rules)

## Testing Requirements
See Validation section above; implemented as automated tests under `tests/` (owned/consolidated by DEV-015, written incrementally here).

## Acceptance Criteria
- [x] All district names normalized to the 25 canonical names (REF-002 confirmed/updated against real handbook spellings) — already canonical at acquisition; defensively validated (raises on any unknown district).
- [x] All vehicle-category names normalized to Motorcycle/Car/Three-wheeler — `configs/vehicle_category_lookup.csv`; out-of-scope/garbled labels excluded and logged, never folded in.
- [x] Duplicate district-year-vehicle rows resolved via a documented source-priority rule — most-recent-edition-wins for genuine duplicates; same-edition *conflicts* (extraction artifacts) are excluded and logged for manual review rather than guessed.
- [x] Missing values investigated and preserved as missing (not zero-filled), with counts reported — REF-009 ADR-005; 80/697 raw values preserved as NaN with a distinct quality note.
- [x] Outliers reviewed against source publications before any correction/removal — the 2022/2023 identical-`vehicle_population` pattern flagged via `data_quality_flag`, not altered.
- [x] Every processed row has non-null `source_id`, `source_url`, `retrieved_date` — satisfied per the REF-001 Section 6 schema extension (at least one of the two per-metric source_id columns is non-null on every row); tested.
- [x] Processed dataset written to `data/processed/` conforming to REF-001 — `data/processed/modelling_base_2024.csv`, 375 rows.
- [x] Section 26.1 data tests pass — `tests/test_data_cleaning.py`, 8/8 passing.

## Definition of Done
All acceptance criteria met; processed dataset is ready for DEV-005 feature engineering; all Section 26.1 data tests pass on the processed dataset.
