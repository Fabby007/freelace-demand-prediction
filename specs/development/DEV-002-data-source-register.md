# DEV-002 — Data Source Register & Target-Variable Decision

## Specification ID
DEV-002

## Feature/Module Name
Data Source Register & Target-Variable Decision

## Purpose
Formally register every candidate data source before any download happens, and make (and record) the Preferred-vs-Fallback target-variable decision that governs the entire modelling approach.

## Background/Context
Source doc Section 7 (Data Collection Strategy), Section 10 step 1 ("Create a source register before downloading data"), Section 7.3 (Kaggle evaluation criteria), and Section 8 (Prediction Target and Scientific Framing) define this work. This is one of the most consequential specs in the project: it determines whether the system predicts a real mechanic-demand target (Preferred path) or a proxy vehicle-market variable (Fallback path), and that decision propagates through every downstream spec's wording, disclaimers, and evaluation approach.

## Related Requirements
- FR-01 (import real vehicle and district data from documented sources)
- Section 7 (Data Collection Strategy), Section 8 (Prediction Target and Scientific Framing), Section 10 step 1
- Hard Rule: no fabricated data (MASTER_PROMPT.md Section 0)

## User Roles
None (backend/data-governance spec, no end-user interaction).

## Preconditions
DEV-001 complete (folder structure and configs/ exist).

## User Stories/Use Cases
- As the developer, I need a register of every data source (name, URL, expected variables, geography, time range, file type) before downloading anything, so provenance is traceable from the start (Section 10 step 1).
- As the developer, I need explicit criteria for evaluating Kaggle datasets so I don't use one "simply because it is convenient" (Section 7.3).
- As the developer, I need to decide and document whether a real mechanic-demand target exists or whether the project must fall back to a proxy target, because this decision changes the wording and framing used throughout the dashboard and reports (Section 8).

## Functional Requirements
1. Create a source register (e.g. `data/source_register.csv` or `configs/source_register.yaml`) with, at minimum, per source: source name, publication title, URL, expected variables, geography, time range, file type, licence, download date (once downloaded).
2. Register the DCS District Statistical Handbook editions to be used (Section 7.1): record exact observation years present in the Transport chapter's "New Vehicle Registrations" tables, handbook edition, table/page reference.
3. Register DMT publications to be used for cross-validation (Section 7.2), noting explicitly that a national table is not district-level data unless the publication contains an explicit district breakdown.
4. Evaluate candidate Kaggle datasets (Section 7.3) against: original source, geography, licence, time coverage, variables, row count, missing-value profile, and — critically — whether the target genuinely represents mechanic demand. Record this evaluation even for datasets ultimately rejected, so the decision is auditable.
5. Register supporting district features under consideration (Section 7.5): population/population density, total vehicle population by type, historical registrations by type, YoY growth, district income/economic indicators where clearly related to vehicle ownership/service capacity, road/transport indicators. Note: rainfall is explicitly not a priority for the first implementation.
6. If web scraping is a candidate source (Section 7.4), record the target site's terms of service / robots.txt status before any scraping is implemented (implementation itself is DEV-003).
7. Make and record the formal **Preferred vs. Fallback target decision** (Section 8.1–8.2):
   - Preferred: a real dataset contains repair requests, service bookings, completed jobs, workshop visits, maintenance transactions, or another credible mechanic-demand signal → that becomes `target_value`; vehicle registrations/stock/district features become predictors.
   - Fallback: no such target is found → forecast a real observable vehicle-market variable (e.g. future motorcycle registrations) as `target_value`, and every downstream output must be framed as a proxy-based opportunity indicator, never as a measured job count.
8. Record the decision, its rationale, and the sources considered in this spec file's "Target Decision Record" (add a dated entry once made — see Section "Data Requirements" below for the template).

## Business Rules
- Do not use a Kaggle dataset "simply because it is convenient" — it must match the research question (Section 7.3, verbatim).
- Do not create arbitrary job counts, and do not assign random High/Medium/Low labels to train a classifier (Section 8.3) — these are Hard Rule violations regardless of what convenience they offer.
- A national DMT table must never be treated as district-level data unless the publication explicitly contains a district breakdown (Section 7.2).

## Data Requirements
Target Decision Record (completed):
```
### Target Decision Record: Dataset v2 addition (2026-11-07)
Dataset v2 uses next-year revenue licences as its proxy target, still under the Fallback path (REF-009 ADR-037). The project author reports lecturer approval. Lecturer approval date: not yet provided. Lecturer approval method: not yet provided. The record below remains in force for Dataset v1 and for `configs/target_config.yaml`.

### Target Decision Record
- Date decided: 2026-08-15
- Path chosen: Fallback (proxy forecast)
- Target dataset/source (if Preferred): N/A - no real demand target was found
- Proxy variable chosen (if Fallback): new_registrations (Table 9.4-equivalent "New Vehicle Registrations in District" from DCS District Statistical Handbooks, cross-checked against DMT national totals). vehicle_population is populated from the DCS "Revenue License" table (Table 9.3-equivalent) as a supporting predictor/context feature, not the target.
- Rationale: A genuine search was carried out across all four source categories named in Section 7 (DCS handbooks, DMT publications, Kaggle, Sri Lanka's open government data portal). No dataset was found containing real repair requests, service bookings, completed mechanic jobs, workshop visits, or maintenance transactions for Sri Lanka - the only candidate "repair/service" datasets on Kaggle were either explicitly synthetic or had no confirmed Sri Lanka-specific, real-world provenance (see rejected entries in data/source_register.csv). Meanwhile, real, verifiable, district-level DCS vehicle-registration data (Table 9.4) was confirmed to exist and to be reliably acquirable (see DEV-003 proof-of-concept). Per Section 8.2, the project therefore forecasts a real observable vehicle-market variable (new_registrations) and frames every output as a relative service-opportunity proxy, never as a measured job count.
- Sources considered and rejected, with reason: see data/source_register.csv rows Kaggle_MotorVehicleRepairTowing (synthetic, not Sri Lanka-specific), Kaggle_VehicleServiceRepairAnalysis (no confirmed real/Sri Lanka provenance), Kaggle_VehicleAdsDataset_LK (real but represents used-vehicle resale ads, not registrations or repair demand - does not meet the Preferred-path bar). SriLankaOpenDataPortal_Transport remains unresolved (site unreachable at time of check, SSL certificate expired) rather than rejected - may be revisited in a later session; the Fallback decision does not depend on it.
- Re-evaluation trigger: if a future session gains access to data.gov.lk or finds a genuine real mechanic-service-demand dataset for Sri Lanka, this decision must be revisited before further modelling work proceeds on the assumption of a fixed proxy target (do not silently keep the Fallback path if a Preferred-path dataset becomes available).
```

This decision is also recorded in `configs/target_config.yaml`.

## Database/Schema Changes
Introduces the source register file itself (not part of the modelling dataset schema — see REF-001 for the modelling dataset schema, which references `source_id` back to this register).

## API Requirements
None.

## Backend Behavior
N/A at this stage (no extraction code yet — that is DEV-003).

## Frontend Behavior
N/A. (The dashboard's "data-source and model-version information" panel, built in DEV-013, reads from this register.)

## UI States
N/A.

## Validation
- Every registered source must have: name, URL, expected variables, geography, time range, file type before DEV-003 downloads it (Section 10 step 1 order is mandatory — register before download).
- Kaggle datasets must be validated against Section 7.3 criteria before being marked "approved for use."

## Permissions
N/A.

## Error Cases
- A candidate source with no clear licence/usage terms — do not use it; escalate/flag rather than silently proceeding (per REF-005 governance rules).

## Edge Cases
- A Kaggle dataset with plausible-looking demand data but unclear real-world provenance (e.g. synthetic or unverifiable) must be rejected per Section 8.3 and REF-006.
- A source that only publishes national-level (non-district) figures may still be registered for cross-validation (Section 7.2) but must be flagged as not usable for district-level rows.

## Security Considerations
- No personal data collection (REF-005). Kaggle/web sources must be checked for personal vehicle-owner information and excluded if present.

## Dependencies
- DEV-001 (Project Foundation)
- REF-005 (Ethical, Legal & Data-Governance Rules), REF-006 (Risks, Assumptions & Limitations)

## Testing Requirements
- Manual review checklist confirming every source in the register has the required fields populated before DEV-003 begins downloading.

## Acceptance Criteria
- [x] Source register created and populated with DCS handbook editions, DMT publications, and any Kaggle candidates — `data/source_register.csv`, 12 sources registered.
- [x] Kaggle evaluation criteria applied and recorded for every candidate dataset (approved or rejected) — 3 datasets evaluated, all rejected (synthetic and/or not Sri Lanka-specific and/or not a demand/registration signal).
- [x] Target Decision Record completed with an explicit Preferred/Fallback choice and rationale — **Fallback** path chosen; see Target Decision Record below and `configs/target_config.yaml`.
- [x] Supporting district features under consideration are listed with intended source — population/density (DCS Chapter 2) and vehicle stock (DCS Table 9.3) confirmed available; income/road indicators not located, left open (not blocking).

## Definition of Done
Source register exists and is complete for all sources used later; the Target Decision Record is filled in and matches the direction taken by DEV-006 (Target Definition); no download has occurred for any source not present in the register.
