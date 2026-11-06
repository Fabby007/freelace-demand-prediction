# DCS Extraction v2: Results, Decisions and Open Data Problems

**Status:** extraction finalized and decisions approved on 2026-11-07. Dataset v2 has not been built, so no decision has been applied to any dataset yet.
**Scope:** DCS District Statistical Handbook 2024, Tables 9.3 and 9.4, 25 districts, 2019-2023.

## 1. Summary

- The new extractor reads all 50 tables. **All 250 printed Totals (25 districts x 2 tables x 5 years) equal the sum of their categories.**
- **Anuradhapura is recovered:** 12 licence cells in the study categories, 32 across all its Table 9.3 rows.
- **Six districts had no Motor Cycle registration row in v1, and now do:** Ampara, Anuradhapura, Badulla, Nuwara Eliya, Trincomalee and Vavuniya.
- **The Total row is now extracted,** and every Table 9.4 Total has a verification status. 12 of the 125 could not be verified.
- **All 165 validation flags are linked to a documented decision.** The tests fail if a new flag has none.

## 2. Approved decisions

| Topic | Decision | Effect |
|---|---|---|
| Clearly incorrect licences | Set to missing in Dataset v2, with the original values on record | Ampara 2019 and Jaffna 2021 motorcycles: 4 study-category cells, plus those 2 printed Totals |
| Uncertain licences | Keep the value and flag it | Kandy 2023, Mullaitivu 2019, Badulla 2019 and the other L entries |
| Registrations | Use verified district Total Registrations as a secondary feature; do not use category figures | Category values stay in the extraction for audit only |
| Unverifiable Totals | Flag them; never invent a value | 12 Totals flagged (section 5) |
| Trincomalee "Grade A" | Not assumed to mean Car; stays unresolved | No Car registration figure for Trincomalee |
| `-` and blank | Stay missing unless the source confirms zero | No number is ever filled in |

"Clearly incorrect" follows the earlier review, which rated Ampara 2019 and Jaffna 2021 as clear errors and the other three as judgement calls.

With only those 4 cells removed, **299 of the 300 possible target rows keep a target, and 295 have both target and current value.** That count ignores flagged values, which Dataset v2 will still have to treat in some way.

The decisions are not yet applied: `dcs_extracted_cells_2024_v2.csv` stays as printed, including Ampara's 9,057. They take effect when Dataset v2 is built.

## 3. Files

| File | Contents | In git |
|---|---|---|
| `data/corrections/source_anomalies_v2.csv` | Every problem: original values, source PDF, reason, decision, date | Yes |
| `reports/extraction_v2/validation_flags.csv` | All 165 flags, each linked to its decision | Yes |
| `reports/extraction_v2/total_registrations_verification.csv` | Status of all 125 Table 9.4 Totals | Yes |
| `src/data/extract_dcs_tables_v2.py`, `src/data/validate_dcs_extraction.py` | Extractor and checks; local files only, never downloads | Yes |
| `configs/dcs_extraction_v2.yaml` | Expected rows, thresholds, DMT totals, flag-to-decision links | Yes |
| `tests/test_extract_dcs_tables_v2.py` | Tests, writing to temporary folders only | Yes |
| `data/interim/dcs_extracted_cells_2024_v2.csv` | All 3,370 cells as printed | No (generated data) |
| `reports/extraction_v2/v1_v2_cell_differences.csv` | Every cell that differs from v1 | No (generated data) |

To recreate the generated files: `python -m src.data.validate_dcs_extraction`

Unchanged: all PDFs, `dcs_multi_district_2024_raw.csv`, the v1 extractor and everything built from them.

## 4. Extraction problems fixed

| Problem in v1 | Effect | Fix in v2 |
|---|---|---|
| A value on a different text line from its label was lost | All Anuradhapura Table 9.3 values for 2019-2022 | Rows are taken from the PDF's ruling lines |
| Empty columns were filled with `-` | Lost values looked like printed dashes | Empty cells stay blank, and `-` means the PDF prints a dash |
| A repeated page header was read as data | Year labels stored as values in Anuradhapura, Trincomalee and Nuwara Eliya | The header is read separately on each page |
| Labels that wrap or share a line with values were split or attached to the wrong row | Wrong labels in Ampara, Anuradhapura, Badulla, Mullaitivu, Nuwara Eliya, Trincomalee and Vavuniya | Labels are matched to a fixed list of table rows; anything else is reported |
| `n.a` was not recognised | Became `-` | Kept as printed |
| The Total row was skipped | No way to check a table | Extracted and marked as a total, never as a vehicle category |

**This corrects the verification report.** Some problems it treated as source errors were v1 parser errors. In Badulla, for example, v1 had Three Wheeler 2019 = 103 where the PDF prints 690, and it had no Motor Cycle row although the PDF prints 6,559. v1's values for the study categories changed in Badulla, Nuwara Eliya and Trincomalee.

### Differences from v1

| Type | Cells | Where |
|---|---|---|
| Value recovered (v1 showed `-`) | 45 | 32 are Anuradhapura licences; 13 are registrations in Anuradhapura, Badulla, Nuwara Eliya and Trincomalee |
| Value changed | 85 | Registrations in Anuradhapura, Badulla, Mullaitivu, Nuwara Eliya and Trincomalee |
| Row only in v2 | 305 | Correct labels in 7 districts |
| Row only in v1 | 100 | Label fragments, such as a table title or "Hearse" alone |
| v1 `-` not printed as a dash | 9 | The PDF has a blank or `n.a` (Ampara, Monaragala, Mullaitivu) |

v1 and v2 agree on every cell in the other 17 districts, and Monaragala differs by one blank cell. All Table 9.3 values outside Anuradhapura also agree. The two parsers work differently, so this is a second check.

## 5. Verification of registration Totals

There is no independent district-level source, so **"verified" does not mean confirmed correct.** It means the Total equals the sum of its categories, is in line with other districts, and its year does not exceed DMT's national figure.

| Status | Totals | Meaning |
|---|---:|---|
| `verified` | 93 | Passes all three checks |
| `verified_with_year_caveat` | 20 | Passes for the district, but 2021 as a whole slightly exceeds DMT |
| `flagged_not_verified` | 12 | About 2.7 times or more from the median district |

**Not verified:**
- **Anuradhapura 2019, 2020, 2021 (R13):** this is the most serious case. It prints 3,452 in 2019 with 273,278 licences, about a fifth of the median district's rate. Then 2021 rises to 4,509 while almost every other district falls sharply. These Totals add up, but may be incomplete.
- **Others (R14):** Badulla 2022, Batticaloa 2021, Kegalle 2021 and 2022, Mannar 2023, Mullaitivu 2021 and 2023, Nuwara Eliya 2022, Vavuniya 2021. All are small counts in years of very low registrations, so real variation is plausible.

### District Totals vs DMT national, all vehicles

| Year | Sum of district Totals | DMT national | Share |
|---|---:|---:|---:|
| 2019 | 342,064 | 367,303 | 93.1% |
| 2020 | 186,475 | 202,628 | 92.0% |
| 2021 | 34,261 | 33,850 | 101.2% |
| 2022 | 20,488 | 20,511 | 99.9% |
| 2023 | 27,871 | 27,890 | 99.9% |

Category sums do not reconcile: Car reaches 140%, 138% and 153% of DMT in 2019-2021, and Three-wheeler reaches 1,153% in 2022 (415 vs 36). So category labels are the unreliable part, not the Totals.

The 2019-2020 shortfall of about 7-8% is unexplained. Anuradhapura's low Totals may be part of it, but that is not confirmed.

## 6. Review of all validation flags

The earlier 153 flags were reviewed one by one, and the new Total check added 12, giving 165. Every flag links to one entry in the corrections file. A check only raises a flag; it never changes a value.

| Outcome | Flags | What it covers |
|---|---:|---|
| Keep missing | 71 | Dashes (70) and a blank (1) in study-category registrations (D01) |
| Category figures not used | 38 | Largest registration row is not Motor Cycle, and Puttalam's Car against licences (R01-R06, R12) |
| Set to missing | 11 | Ampara 2019 and Jaffna 2021, including year-on-year flags they cause (L01, L02) |
| Keep and flag for review | 25 | Uncertain licence values (L03-L17) |
| Total flagged, not verified | 12 | R13, R14 |
| Total Registrations used instead | 4 | Category sums above DMT (R10) |
| 2021 caveat | 1 | R11 |
| Missing rows, no action needed | 2 | Hambantota Ambulance, Trincomalee Motor Lorry (R08, R09) |
| Unresolved | 1 | Trincomalee Grade A (R07) |

**A limit of these checks:** the year-on-year check does not flag Kurunegala's +21% motorcycle jump in 2023. It is documented by hand as L11, along with that table's different source citation.

## 7. How the extraction was checked

| Check | Result |
|---|---|
| Categories add up to the printed Total | 250 of 250 |
| Compared by eye with rendered PDF pages | Anuradhapura T9.3, Anuradhapura T9.4 page 1, Badulla T9.4 page 1, Trincomalee T9.4 page 1: every cell shown matches |
| Fragment gaps | Parts of one number are at most 0.1pt apart; separate columns at least 18.9pt |
| Corrections file | A test confirms every quoted value matches the PDF extraction |

**What these checks cannot prove:**
- A column adding up does not show that each value is on the right row in the source.
- Jaffna 2021 shows this: its printed Total is consistent with the suspect value.
- Only the four pages above were compared by eye. The others rely on the sum and the agreement with v1.

## 8. Remaining data issues

1. **Unverified Totals:** 12 of 125, especially Anuradhapura 2019-2021. Dataset v2 must decide how a flagged Total enters the feature.
2. **Uncertain licences kept as printed:** Kandy 2023, Mullaitivu 2019 and Badulla 2019 stay in. Kandy 2023 affects the latest target year, and Mullaitivu 2019 is an exact copy of Kilinochchi 2020. They may affect results, so model evaluation should test with and without them.
3. **Causes are unconfirmed:** "dropped digit", "not updated" and "wrong row" are the likeliest explanations. Only DCS could confirm them.
4. **Possible errors the checks cannot see:** a wrong value that fits its row, its Total and its neighbours would not be flagged.
5. **Trincomalee Grade A:** unresolved. This has no effect while category registrations are unused.
6. **Short series:** five years and four target years. Earlier handbook editions are not downloaded, and may use a different layout.
7. **Population data:** DCS Chapter 2 is missing, so per-capita features cannot be built.
8. **Research Brief figure:** the Brief says motorcycle licences rose from about 2.51M to 2.96M. As printed, with Anuradhapura recovered, it is 2.69M to 2.96M (+10.2%), and that still includes Ampara's and Badulla's doubtful 2019. Without those two districts it is **+4.4%**, and also without Kurunegala and Mullaitivu it is +1.5%. The Brief has not been changed.
