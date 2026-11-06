# REF-002 — District & Vehicle-Category Canonical Lists / Normalization Rules

**Status:** Approved reference specification (district list is a **candidate list pending confirmation** — see Section 2 note)
**Source:** Section 5, Section 11 of the Final Project Documentation.

---

## 1. Purpose

Single canonical source for (a) the 25 official Sri Lankan district names and (b) the canonical vehicle-category labels, plus the normalization mapping rules used by DEV-004 to clean raw extracted names. DEV specs must reference this file rather than re-listing district/category names locally.

## 2. Canonical district list (25 districts)

The source documentation states: "The design supports all 25 districts, subject to consistent data availability" (Section 5) and that district normalisation maps "spelling variations to the 25 official district names" (Section 11), with the list itself "to be enumerated/confirmed during DEV-004" (MASTER_PROMPT.md Section 6).

The following is the standard list of Sri Lanka's 25 administrative districts, grouped by province, provided here as the **working canonical list**. It must be cross-checked against the exact spellings used in the actual DCS District Statistical Handbook editions acquired under DEV-003, and any correction must be logged as an update to this file (not silently changed elsewhere) during DEV-004.

| Province | Districts |
|---|---|
| Western | Colombo, Gampaha, Kalutara |
| Central | Kandy, Matale, Nuwara Eliya |
| Southern | Galle, Matara, Hambantota |
| Northern | Jaffna, Kilinochchi, Mannar, Vavuniya, Mullaitivu |
| Eastern | Trincomalee, Batticaloa, Ampara |
| North Western | Kurunegala, Puttalam |
| North Central | Anuradhapura, Polonnaruwa |
| Uva | Badulla, Monaragala |
| Sabaragamuwa | Ratnapura, Kegalle |

Total: 25 districts.

**Confirmation status (2026-08-15):** the DCS handbook index page (`https://www.statistics.gov.lk/ref/HandbookDictionary`) was fetched directly and its raw HTML inspected. It confirms handbooks exist for all 25 districts above and reveals real spelling inconsistencies **in the website's own URL scheme** (not necessarily inside the PDF table text itself): `Kalutura` (for Kalutara), `Nuwara-Eliya` (for Nuwara Eliya), `Mullativue`/`Mullaitivu` (both used, inconsistently across years), `Killinochchi`/`Kilinochchi` (both used, inconsistently across years), `Kurunagala`/`Kurunegala` (both used, inconsistently across years), `Polonnoruwa` (for Polonnaruwa, used for every year seen), `Rathnapura`/`Ratnapura` (both used, inconsistently across years). These acquisition-time URL-segment variants are recorded separately in `configs/dcs_district_url_segments.csv` (owned by DEV-003, since they affect how the acquisition script constructs a download URL, not how table *content* is normalized). This file (REF-002) and `configs/district_lookup.csv` remain the canonical list used to normalize **data values** (e.g. text found inside extracted tables) during DEV-004; DEV-004 must independently verify whether the in-table spellings match the canonical list or introduce their own variants requiring additional lookup entries.

## 3. District normalization rule (Section 11)

"District normalisation: map spelling variations to the 25 official district names." Implementation guidance:
- Maintain a lookup table (`configs/district_lookup.csv` or equivalent) mapping every observed raw spelling/variant found in source tables to exactly one canonical name from Section 2 above.
- Do not guess-match fuzzy district names silently; every mapping must be explicit and reviewable.
- Any raw district name that cannot be confidently mapped must fail validation (Section 26.1 data test: "no unknown district names after normalization") rather than being dropped or guessed silently.

## 4. Canonical vehicle-category labels

Per the source documentation, the initial vehicle category is **Motorcycle**, with **Car** and **Three-wheeler** supported by the same architecture where data quality is sufficient (Section 5). The canonical labels are:

- `Motorcycle`
- `Car`
- `Three-wheeler`

## 5. Vehicle-category normalization rule (Section 11)

"Vehicle-category normalisation: map 'Motor Cycle,' 'Motorcycle,' etc. to one canonical category." Implementation guidance:
- Maintain a lookup table mapping observed raw category strings (e.g. "Motor Cycle", "M/Cycle", "Motor Cycles", "Three Wheelers", "Trishaw") to exactly one of the three canonical labels in Section 4.
- Categories outside the documented scope (e.g. buses, lorries) are out of scope for the current build (Section 5, Section 31) and must not be silently folded into one of the three canonical categories.

## 6. Related specs

- DEV-004 (Data Cleaning, Normalization & Validation) — owns the actual lookup-table implementation and the confirmation step against real handbook spellings.
- REF-001 (Data Dictionary) — `district` and `vehicle_type` columns.
