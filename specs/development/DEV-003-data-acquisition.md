# DEV-003 — Data Acquisition & Extraction Pipeline

## Specification ID
DEV-003

## Feature/Module Name
Data Acquisition & Extraction Pipeline

## Purpose
Acquire and extract real vehicle-registration and district-context data from the sources registered in DEV-002, following the documented 9-step workflow, starting from a Kandy proof-of-concept and scaling to all districts.

## Background/Context
Source doc Section 10 (Data Acquisition and Extraction Workflow) and Section 10.1 (proof-of-concept approach), Section 7.1–7.4 (source-specific guidance), Section 33 steps 3–6 (Immediate Implementation Steps).

## Related Requirements
- FR-01 (import real vehicle and district data from documented sources)
- Section 10 steps 1–9, Section 10.1
- Hard Rule: no fabricated data; respect scraping ToS/robots (Section 0, REF-005)

## User Roles
None (batch/offline pipeline; no end-user interaction).

## Preconditions
DEV-002 complete: source register exists and the sources to acquire are registered.

## User Stories/Use Cases
- As the developer, I need a repeatable extraction script per source type (DCS handbook PDF/HTML, DMT publication, Kaggle CSV) so extraction is not manual, one-off work that can't be re-run when new handbook editions are published.
- As the developer, I need a Kandy proof-of-concept before scaling to all 25 districts, so structural issues are caught early and cheaply (Section 10.1).

## Functional Requirements
Implements Section 10's 9-step workflow:
1. (Covered by DEV-002) Source register exists before any download.
2. Download and store the original PDF/CSV/XLSX/HTML snapshot in `data/raw/` **without editing it**.
3. Extract the required table using a repeatable method (table extraction library / carefully validated parser); use source-specific extraction rules if structure changes across handbook editions.
4. Normalize district names and vehicle-category names using the controlled lookup table (REF-002) — normalization *logic* is owned by DEV-004, but extraction here must pass raw names through unmodified into the interim layer so DEV-004 has the true raw values to normalize.
5. Convert numeric strings to numeric values; preserve missing values as missing, not zero (this rule is enforced again in DEV-004, but extraction scripts must not pre-emptively zero-fill).
6. Validate extracted totals against the source table and, where possible, national DMT statistics.
7. Append source metadata (`source_id`, `source_url`, `retrieved_date`) to each observation.
8. Write cleaned observations to `data/processed/` as CSV/Parquet (final write is owned by DEV-004; DEV-003 writes raw/interim extraction output to `data/interim/`).
9. (Owned by DEV-004/DEV-015) Run automated validation tests before using the dataset for modelling.

### 10.1 Proof-of-concept and scale-up sequence
1. Extract Kandy motorcycle registrations for several consecutive years into a small CSV.
2. Once correct, repeat for 2–3 additional districts to confirm table structure/naming consistency.
3. Only then scale extraction across all 25 districts.

### Source-specific acquisition
- **DCS District Statistical Handbooks (Section 7.1):** inspect the Transport chapter for "New Vehicle Registrations" tables; record exact observation years present in each table (not assumed from the handbook title); capture district, observation year, vehicle category, registration count, handbook edition, table/page reference, source URL.
- **DMT publications (Section 7.2):** acquire national vehicle-population/registration context for cross-checking totals and trend validation.
- **Kaggle (Section 7.3):** download only datasets approved in the DEV-002 evaluation.
- **Web scraping (Section 7.4), if used:** respect website terms, robots guidance, and request-rate limits; store source URLs and extraction timestamps; do not collect personal information when aggregate statistics suffice.

## Business Rules
- Never edit a raw downloaded file in place — `data/raw/` is an unedited archive; all transformation happens on copies in `data/interim/`/`data/processed/`.
- Every extraction script must be traceable to a specific registered source (DEV-002).
- Scraping (if used) must respect robots.txt/ToS and rate limits (REF-005).

## Data Requirements
- Raw files land in `data/raw/<source_id>/...` preserving original filenames/format.
- Extracted (pre-normalization) tables land in `data/interim/` with columns matching Appendix A field names as closely as possible, prior to DEV-004 cleaning.

## Database/Schema Changes
None beyond the `data/raw/` and `data/interim/` file layout; final schema is REF-001, applied by DEV-004.

## API Requirements
None (unless a scraper needs a lightweight internal fetch/parse module — no external API service).

## Backend Behavior
- Extraction scripts organized under `src/data/` (one module per source type, per Maintainability NFR — no copy-pasted logic across district/vehicle-category handling per MASTER_PROMPT.md Section 9).
- Light logging on extraction runs (industry-standard addition per MASTER_PROMPT.md Section 9 — log as ADR in REF-009) so failures during batch extraction are diagnosable.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
- Extracted totals cross-checked against the source publication and, where possible, DMT statistics (Section 10 step 6).
- Table structure/naming consistency confirmed on the Kandy proof-of-concept and 2–3 additional districts before scaling (Section 10.1).

## Permissions
N/A.

## Error Cases
- Handbook table structure differs across editions/districts — handled with source-specific parser rules and manual validation samples (REF-006 mitigation), not by forcing a one-size-fits-all parser.
- Scraper blocked by robots.txt/ToS — do not bypass; prefer official downloadable files instead (REF-006).

## Edge Cases
- A handbook table spans years that don't match the handbook's cover-year title — record actual observation years found in the table, not assumed ones (Section 7.1).
- A district's data is missing from a given handbook edition entirely — leave missing, do not interpolate or zero-fill at extraction time (that decision belongs to DEV-004's documented missing-value investigation).

## Security Considerations
- No personal data collection during scraping (REF-005).
- No credentials committed to the repository (e.g. Kaggle API tokens).

## Dependencies
- DEV-002 (Data Source Register & Target-Variable Decision)
- REF-002 (Canonical Lists), REF-005 (Ethical/Legal/Governance)

## Testing Requirements
- Structural consistency test across the proof-of-concept districts before scale-up.
- Spot-check validation of extracted totals against source tables for a sample of districts/years.

## Acceptance Criteria
- [x] Raw files for all registered sources are archived unedited in `data/raw/` — `data/raw/dcs_handbooks/` (53 PDFs) and `data/raw/dmt/` (1 PDF, downloaded 2026-08-15 to close the acceptance criterion below). No Kaggle dataset was downloaded — none was approved (DEV-002 Fallback decision); the Sri Lanka Open Data Portal source remains access-blocked (SSL issue) and unresolved, tracked in `data/source_register.csv`, not silently dropped.
- [x] Kandy motorcycle proof-of-concept CSV produced and validated — `data/interim/dcs_kandy_2024_raw.csv`, values hand-verified against the source PDF (`tests/test_data_extraction.py::test_kandy_2024_t9_4_matches_manually_verified_values`).
- [x] Structure validated on 2–3 additional districts before scaling — Colombo, Galle, Jaffna, Batticaloa (`tests/test_data_extraction.py::test_structure_consistent_across_validation_districts`); this validation pass caught and fixed several real parser bugs (a PDF number-splitting artifact, an "n/r" not-reported marker, Tamil-majority-district layout variants) before scale-up, exactly as Section 10.1 intends.
- [x] Extraction scaled to all 25 districts (subject to source availability) — `data/interim/dcs_multi_district_2024_raw.csv`, 2940 raw observations, zero structural warnings on the final run.
- [x] Every extracted observation carries `source_id`, `source_url`, `retrieved_date` — present on every row.
- [x] Extracted totals cross-checked against source tables / DMT statistics — **completed 2026-08-15** (previously left open; resolved rather than deferred, since Section 10 step 6 and this spec's own "DMT publications" functional requirement place this squarely in DEV-003's scope, not DEV-004/DEV-014's). `data/raw/dmt/DMT_Vehicle_Population_2014-2025.pdf` downloaded; `src/data/validate_against_dmt.py` sums the processed district-level totals per (vehicle_type, year) and compares against the DMT national figures for the same category/year; full results in `reports/dmt_cross_validation.md`. Finding: `vehicle_population` and Motorcycle `new_registrations` reconcile plausibly (district sums are 52-87% of national, never exceeding it); Car (2019-2021) and Three-wheeler (2022) `new_registrations` district sums **exceed** the DMT national total (133-148% and ~1244% respectively) — a genuine, logically-impossible discrepancy between DCS and DMT that this pipeline documents rather than silently resolves. Flagged in the processed dataset (`data_quality_flag`) and logged as a new risk in REF-006 Section 5.1 for DEV-005/DEV-006/DEV-016 to account for. Tested: `tests/test_dmt_cross_validation.py`.

## Definition of Done
All acceptance criteria met; `data/interim/` contains extraction output ready for DEV-004 cleaning; extraction is repeatable via script (not manual one-off edits) for every source used; the one open sub-item (Sri Lanka Open Data Portal access) is explicitly tracked in `data/source_register.csv` as unresolved rather than silently dropped, and does not block this spec's completion since it was never a required source (DCS/DMT alone satisfy Section 10).
