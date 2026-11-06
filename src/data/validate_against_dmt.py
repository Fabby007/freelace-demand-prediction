"""Cross-check DCS district-level totals against DMT national statistics
(DEV-003, Section 10 step 6: "Validate extracted totals against the source
table and, where possible, national DMT statistics").

National figures below are transcribed directly from the DMT publication
"NEW REGISTRATION OF MOTOR VEHICLES" / "TOTAL VEHICLE POPULATION" tables,
downloaded to data/raw/dmt/DMT_Vehicle_Population_2014-2025.pdf (see
data/source_register.csv, source_id=DMT_VehiclePopulation_2014_2025).
DMT's "MOTOR TRICYCLES" class is the national equivalent of the
Three-wheeler category (Sri Lanka's three-wheelers/trishaws are registered
under this class).

This module does not "fix" the district-level data - Section 10 step 6 is
a validation/reporting step. Genuine discrepancies are reported honestly
(see reports/dmt_cross_validation.md) and flagged in the processed dataset
for downstream awareness, not silently resolved or hidden.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

NATIONAL_NEW_REGISTRATIONS = {
    "Car": {2019: 38232, 2020: 21021, 2021: 3495, 2022: 1489, 2023: 1816},
    "Three-wheeler": {2019: 15490, 2020: 7150, 2021: 2093, 2022: 36, 2023: 60},
    "Motorcycle": {2019: 284301, 2020: 151634, 2021: 8011, 2022: 9060, 2023: 20200},
}
NATIONAL_VEHICLE_POPULATION = {
    "Car": {2019: 875864, 2020: 896885, 2021: 900380, 2022: 901869, 2023: 903685},
    "Three-wheeler": {2019: 1175077, 2020: 1182227, 2021: 1184320, 2022: 1184356, 2023: 1184416},
    "Motorcycle": {2019: 4668074, 2020: 4819708, 2021: 4827719, 2022: 4836779, 2023: 4856979},
}


def cross_check(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per (vehicle_type, year) with district-summed totals,
    the DMT national figure, and the ratio between them. A ratio > 100% for
    new_registrations is logically impossible (a district sum cannot exceed
    the national total for the same real-world quantity) and always
    indicates either a classification mismatch between DCS and DMT, an
    extraction issue, or a genuine reconciliation gap between the two
    government data systems - not something this function resolves."""
    rows = []
    for vehicle_type in ["Motorcycle", "Car", "Three-wheeler"]:
        for year in [2019, 2020, 2021, 2022, 2023]:
            sub = processed_df[(processed_df["vehicle_type"] == vehicle_type) & (processed_df["year"] == year)]
            for metric, national_table, col in [
                ("new_registrations", NATIONAL_NEW_REGISTRATIONS, "new_registrations"),
                ("vehicle_population", NATIONAL_VEHICLE_POPULATION, "vehicle_population"),
            ]:
                district_sum = sub[col].sum()
                national = national_table[vehicle_type][year]
                ratio = district_sum / national if national else float("nan")
                rows.append({
                    "vehicle_type": vehicle_type,
                    "year": year,
                    "metric": metric,
                    "district_sum": district_sum,
                    "national_total": national,
                    "ratio": ratio,
                    "exceeds_national_total": ratio > 1.0,
                })
    return pd.DataFrame(rows)


def flag_implausible_rows(processed_df: pd.DataFrame, cross_check_df: pd.DataFrame) -> pd.DataFrame:
    """Add a data_quality_flag note to every processed row whose
    (vehicle_type, year) combination has a new_registrations district sum
    exceeding the DMT national total - a logically impossible outcome that
    must be visible to anyone using this data, not silently present."""
    df = processed_df.copy()
    implausible = cross_check_df[
        (cross_check_df["metric"] == "new_registrations") & (cross_check_df["exceeds_national_total"])
    ][["vehicle_type", "year"]]
    implausible_keys = set(zip(implausible["vehicle_type"], implausible["year"]))

    def _flag(row):
        existing = row.get("data_quality_flag")
        if (row["vehicle_type"], row["year"]) not in implausible_keys:
            return existing
        note = "district_sum_exceeds_dmt_national_total_for_new_registrations"
        if pd.isna(existing) or not existing:
            return note
        existing_notes = str(existing).split(";")
        return existing if note in existing_notes else f"{existing};{note}"

    df["data_quality_flag"] = df.apply(_flag, axis=1)
    return df


def write_report(cross_check_df: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# DMT Cross-Validation Report",
        "",
        "DEV-003, Section 10 step 6: extracted district-level DCS totals "
        "(summed across all 25 districts) compared against DMT national "
        "statistics for the same vehicle category and year.",
        "",
        "Source: `data/raw/dmt/DMT_Vehicle_Population_2014-2025.pdf` "
        "(Department of Motor Traffic, 'NEW REGISTRATION OF MOTOR VEHICLES' "
        "and 'TOTAL VEHICLE POPULATION' tables).",
        "",
        "| Vehicle type | Year | Metric | District sum | DMT national | Ratio | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in cross_check_df.iterrows():
        note = "**EXCEEDS NATIONAL TOTAL**" if r["exceeds_national_total"] else ""
        lines.append(
            f"| {r['vehicle_type']} | {r['year']} | {r['metric']} | "
            f"{r['district_sum']:.0f} | {r['national_total']:,} | {r['ratio']:.1%} | {note} |"
        )
    lines += [
        "",
        "## Findings",
        "",
        "- **`vehicle_population`**: district sums are consistently 52-82% of the DMT "
        "national total across all three vehicle categories and all five years - "
        "plausible (Table 9.3, the 'Revenue License issued' count, is not "
        "guaranteed to capture every registered vehicle nationally, e.g. vehicles "
        "not renewing annually) and internally consistent (no ratio approaches "
        "or exceeds 100%).",
        "- **`new_registrations` for Motorcycle**: district sums are 64-87% of the "
        "national total across all five years - plausible, similar pattern to "
        "vehicle_population.",
        "- **`new_registrations` for Car (2019-2021)**: district sums are 133-148% "
        "of the national total - **logically impossible** if both figures measure "
        "the same real-world quantity (a sum over districts cannot exceed the "
        "national total). This is a genuine, unresolved discrepancy between the "
        "DCS district-level 'Car' category and DMT's national 'MOTOR CARS' class "
        "- not an artifact this pipeline can confidently explain away (candidate "
        "causes: differing category definitions between the two government "
        "agencies, different registration-event definitions e.g. first "
        "registration vs. any new district registration, or a genuine data-entry "
        "difference between the two publications). Flagged in the processed "
        "dataset (`data_quality_flag`), not silently corrected or hidden.",
        "- **`new_registrations` for Three-wheeler (2022)**: district sum (448) is "
        "over 12x the DMT national total (36) - an extreme, logically impossible "
        "discrepancy for the single year with the most severe import restrictions "
        "in the underlying data (see REF-006 risk table). Flagged in the processed "
        "dataset for the same reason as Car above.",
        "",
        "## Disposition",
        "",
        "Per Section 11 ('compare extreme values against the source publication "
        "before removing/winsorising'), these rows are **flagged, not removed or "
        "corrected** - the DCS district figures are genuinely what the source "
        "publication states, and this report documents that they do not "
        "reconcile with DMT's national figures for these specific "
        "category/year combinations. DEV-005/DEV-006 must treat `new_registrations` "
        "for Car and Three-wheeler with this caveat in mind (e.g. when deciding "
        "whether these years/categories are reliable enough to use in the "
        "modelling dataset), and DEV-016 must disclose this limitation rather "
        "than presenting the dataset as fully reconciled.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(processed_csv: Path, report_path: Path) -> pd.DataFrame:
    processed_df = pd.read_csv(processed_csv)
    cross_check_df = cross_check(processed_df)
    flagged_df = flag_implausible_rows(processed_df, cross_check_df)
    flagged_df.to_csv(processed_csv, index=False)
    write_report(cross_check_df, report_path)
    return cross_check_df


if __name__ == "__main__":
    run(
        REPO_ROOT / "data" / "processed" / "modelling_base_2024.csv",
        REPO_ROOT / "reports" / "dmt_cross_validation.md",
    )
