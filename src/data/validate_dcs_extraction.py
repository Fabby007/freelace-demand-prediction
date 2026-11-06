"""Validation checks and versioned outputs for the v2 DCS extraction.

Every check only raises a flag. No value is changed, dropped or filled here.
What is done about each flag is recorded separately, as a reviewed decision, in
`data/corrections/source_anomalies_v2.csv` (REF-009 ADR-036).

Run with: python -m src.data.validate_dcs_extraction
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.data.extract_dcs_tables_v2 import (
    RAW_DIR,
    REPO_ROOT,
    STATUS_VALUE,
    V1_INTERIM_CSV,
    V2_CELLS_CSV,
    extract_all,
    load_config,
    write_cells_csv,
)
from src.data.validate_against_dmt import NATIONAL_NEW_REGISTRATIONS, NATIONAL_VEHICLE_POPULATION

logger = logging.getLogger(__name__)

REPORT_DIR = REPO_ROOT / "reports" / "extraction_v2"
FLAGS_CSV = REPORT_DIR / "validation_flags.csv"
V1_DIFF_CSV = REPORT_DIR / "v1_v2_cell_differences.csv"
TOTALS_CSV = REPORT_DIR / "total_registrations_verification.csv"
CORRECTIONS_CSV = REPO_ROOT / "data" / "corrections" / "source_anomalies_v2.csv"

METRIC_LICENCES = "vehicle_population"
METRIC_REGISTRATIONS = "new_registrations"
CATEGORIES = ["Motorcycle", "Car", "Three-wheeler"]
FLAG_COLUMNS = ["check_id", "severity", "district", "metric", "year", "row_label", "value", "evidence", "source_file", "page"]
TOTAL_VERIFIED = "verified"
TOTAL_YEAR_CAVEAT = "verified_with_year_caveat"
TOTAL_FLAGGED = "flagged_not_verified"
# How a v1 cell compares with the same cell in v2.
RECOVERED = "recovered_value_v1_lost"
CHANGED = "value_changed"
V1_ONLY = "row_only_in_v1"
V2_ONLY = "row_only_in_v2"
PLACEHOLDER = "v1_dash_is_not_printed"


def _flag(check_id: str, severity: str, district: str = "ALL", metric: str = "", year: int | str = "",
          row_label: str = "", value: object = "", evidence: str = "", source_file: str = "", page: object = "") -> dict:
    return dict(zip(FLAG_COLUMNS, [check_id, severity, district, metric, year, row_label, value, evidence, source_file, page]))


def _with_numbers(cells: pd.DataFrame) -> pd.DataFrame:
    df = cells.copy()
    df["number"] = pd.to_numeric(df["value_numeric"], errors="coerce")
    df["is_total_row"] = df["is_total_row"].astype(str).str.lower() == "true"
    return df


def check_sum_to_total(df: pd.DataFrame, tolerance: float) -> list[dict]:
    """Categories must add up to the printed Total. Non-numeric cells count as 0
    for this arithmetic only; they stay missing in the data."""
    flags = []
    for (district, metric, year), group in df.groupby(["district", "metric", "year"]):
        total = group.loc[group["is_total_row"], "number"]
        source_file = group["source_file"].iloc[0]
        if total.empty or total.isna().all():
            flags.append(_flag("total_row_unusable", "high", district, metric, year, "Total", "",
                               "No usable printed Total to check against.", source_file))
            continue
        printed = total.iloc[0]
        categories_sum = group.loc[~group["is_total_row"], "number"].sum()
        if abs(categories_sum - printed) > tolerance:
            flags.append(_flag("sum_differs_from_total", "high", district, metric, year, "Total", int(printed),
                               f"Categories sum to {int(categories_sum)}, printed Total is {int(printed)}.", source_file))
    return flags


def check_missing_category_cells(df: pd.DataFrame) -> list[dict]:
    """Non-numeric cells in the three study categories, by what the PDF shows."""
    flags = []
    subset = df[df["vehicle_type"].isin(CATEGORIES) & (df["cell_status"] != STATUS_VALUE)]
    for row in subset.itertuples():
        severity = "high" if row.metric == METRIC_LICENCES else "low"
        flags.append(_flag(f"missing_cell_{row.cell_status}", severity, row.district, row.metric, row.year,
                           row.row_label, row.value_raw,
                           f"Printed as {row.cell_status}; kept as missing, not converted to zero.",
                           row.source_file, row.page))
    return flags


def check_identical_year_columns(df: pd.DataFrame, min_values: int) -> list[dict]:
    """Two years of one table with identical values: a likely unrefreshed column."""
    flags = []
    for (district, metric), group in df[~df["is_total_row"]].groupby(["district", "metric"]):
        columns = {
            year: dict(zip(g["row_label"], g["number"]))
            for year, g in group.groupby("year")
        }
        years = sorted(columns)
        for earlier, later in zip(years, years[1:]):
            shared = [
                label for label, value in columns[earlier].items()
                if pd.notna(value) and value > 0 and columns[later].get(label) == value
            ]
            populated = sum(1 for v in columns[later].values() if pd.notna(v) and v > 0)
            if len(shared) >= min_values and len(shared) == populated:
                flags.append(_flag("identical_year_columns", "high", district, metric, later, "", "",
                                   f"All {len(shared)} non-zero values equal {earlier}.",
                                   group["source_file"].iloc[0]))
    return flags


def check_identical_columns_across_districts(df: pd.DataFrame, min_values: int) -> list[dict]:
    """A Table 9.3 column identical to another district's. Reported for both sides."""
    seen: dict[tuple, list[tuple[str, int, str]]] = {}
    subset = df[(df["metric"] == METRIC_LICENCES) & ~df["is_total_row"]]
    for (district, year), group in subset.groupby(["district", "year"]):
        numbers = group.dropna(subset=["number"])
        numbers = numbers[numbers["number"] > 0]
        if len(numbers) >= min_values:
            key = tuple(sorted(zip(numbers["row_label"], numbers["number"])))
            seen.setdefault(key, []).append((district, year, group["source_file"].iloc[0]))
    flags = []
    for entries in seen.values():
        if len({district for district, _, _ in entries}) > 1:
            for district, year, source_file in entries:
                others = ", ".join(f"{d} {y}" for d, y, _ in entries if (d, y) != (district, year))
                flags.append(_flag("column_identical_to_other_district", "high", district, METRIC_LICENCES, year, "", "",
                                   f"Every value is identical to {others}.", source_file))
    return flags


def check_licences_copied_from_registrations(df: pd.DataFrame, min_shared: int, min_value: float) -> list[dict]:
    """A Table 9.3 column repeating that year's Table 9.4 values, ignoring row labels."""
    flags = []
    body = df[~df["is_total_row"] & df["number"].notna() & (df["number"] >= min_value)]
    for (district, year), group in body.groupby(["district", "year"]):
        licences = group[group["metric"] == METRIC_LICENCES]
        registrations = group[group["metric"] == METRIC_REGISTRATIONS]
        shared = set(licences["number"]) & set(registrations["number"])
        if len(shared) >= min_shared:
            values = ", ".join(str(int(v)) for v in sorted(shared))
            flags.append(_flag("licences_match_registrations", "high", district, METRIC_LICENCES, year, "", "",
                               f"Table 9.3 repeats these Table 9.4 values for {year}: {values}.",
                               licences["source_file"].iloc[0]))
    return flags


def _licence_series(df: pd.DataFrame) -> pd.DataFrame:
    subset = df[(df["metric"] == METRIC_LICENCES) & (df["vehicle_type"].isin(CATEGORIES) | df["is_total_row"])].copy()
    subset["series"] = subset["vehicle_type"].where(~subset["is_total_row"], "Total")
    return subset


def check_year_on_year_against_national_pattern(df: pd.DataFrame, threshold: float, min_base: float) -> list[dict]:
    """Licence changes that differ from the same-year median across districts. Compared
    with the median, not a fixed limit, because 2020-2022 moved all districts together."""
    subset = _licence_series(df).sort_values(["district", "series", "year"])
    subset["previous"] = subset.groupby(["district", "series"])["number"].shift(1)
    subset = subset[subset["previous"].notna() & (subset["previous"] >= min_base) & (subset["number"] > 0)].copy()
    subset["log_change"] = (subset["number"] / subset["previous"]).map(math.log)
    subset["median_change"] = subset.groupby(["series", "year"])["log_change"].transform("median")
    flags = []
    for row in subset[(subset["log_change"] - subset["median_change"]).abs() > threshold].itertuples():
        change = math.exp(row.log_change) - 1
        typical = math.exp(row.median_change) - 1
        flags.append(_flag("yoy_against_national_pattern", "medium", row.district, row.metric, row.year, row.row_label,
                           int(row.number),
                           f"{int(row.previous)} to {int(row.number)} ({change:+.1%}); median district {typical:+.1%}.",
                           row.source_file, row.page))
    return flags


def check_dips_and_spikes(df: pd.DataFrame, dip_ratio: float) -> list[dict]:
    """A value far from both neighbouring years, e.g. a lost digit."""
    flags = []
    for (district, series), group in _licence_series(df).groupby(["district", "series"]):
        group = group.sort_values("year").reset_index(drop=True)
        for i in range(1, len(group) - 1):
            before, value, after = group.loc[i - 1, "number"], group.loc[i, "number"], group.loc[i + 1, "number"]
            if pd.isna(before) or pd.isna(value) or pd.isna(after) or value <= 0:
                continue
            kind = "dip" if value < dip_ratio * min(before, after) else "spike" if value * dip_ratio > max(before, after) else ""
            if kind:
                row = group.loc[i]
                flags.append(_flag(f"{kind}_between_neighbours", "high", district, row["metric"], row["year"], row["row_label"],
                                   int(value), f"{int(before)} then {int(value)} then {int(after)}.",
                                   row["source_file"], row["page"]))
    return flags


def check_registrations_against_licences(df: pd.DataFrame, ratio: float) -> list[dict]:
    """New registrations too large for the licensed fleet of the same category."""
    body = df[df["vehicle_type"].isin(CATEGORIES)]
    key = ["district", "year", "vehicle_type"]
    registrations = body[body["metric"] == METRIC_REGISTRATIONS]
    licences = body[body["metric"] == METRIC_LICENCES][key + ["number"]].rename(columns={"number": "licences"})
    joined = registrations.merge(licences, on=key)
    flags = []
    for row in joined[joined["licences"] > 0].itertuples():
        if pd.notna(row.number) and row.number / row.licences > ratio:
            flags.append(_flag("registrations_high_vs_licences", "high", row.district, row.metric, row.year, row.row_label,
                               int(row.number),
                               f"{int(row.number)} new registrations vs {int(row.licences)} licences "
                               f"({row.number / row.licences:.0%}).", row.source_file, row.page))
    return flags


def check_largest_registration_category(df: pd.DataFrame) -> list[dict]:
    """Motorcycles are nationally the largest category in every year 2019-2023. A
    different largest row is a possible label error, not proof of one: import
    restrictions make a real difference plausible, especially in 2021-2022."""
    flags = []
    body = df[(df["metric"] == METRIC_REGISTRATIONS) & ~df["is_total_row"] & df["number"].notna()]
    for (district, year), group in body.groupby(["district", "year"]):
        top = group.loc[group["number"].idxmax()]
        if top["vehicle_type"] != "Motorcycle" and top["number"] > 0:
            motorcycle = group.loc[group["vehicle_type"] == "Motorcycle", "number"]
            motorcycle_text = str(int(motorcycle.iloc[0])) if not motorcycle.empty else "not numeric"
            severity = "medium" if year in (2019, 2020) else "low"
            flags.append(_flag("largest_registration_not_motorcycle", severity, district, top["metric"], year, top["row_label"],
                               int(top["number"]),
                               f"{top['row_label']} = {int(top['number'])}; Motor Cycle = {motorcycle_text}.",
                               top["source_file"], top["page"]))
    return flags


def check_against_dmt_national(df: pd.DataFrame) -> list[dict]:
    """District sums must not exceed the DMT national figure for the same quantity."""
    flags = []
    tables = [(METRIC_REGISTRATIONS, NATIONAL_NEW_REGISTRATIONS), (METRIC_LICENCES, NATIONAL_VEHICLE_POPULATION)]
    for metric, national in tables:
        for category, by_year in national.items():
            for year, national_value in by_year.items():
                total = df[(df["metric"] == metric) & (df["vehicle_type"] == category) & (df["year"] == year)]["number"].sum()
                if total > national_value:
                    flags.append(_flag("district_sum_exceeds_dmt", "high", "ALL", metric, year, category, int(total),
                                       f"District sum {int(total)} exceeds DMT national {national_value} "
                                       f"({total / national_value:.0%})."))
    return flags


def check_totals_against_dmt_national(df: pd.DataFrame, national_totals: dict[int, int]) -> list[dict]:
    """Printed Table 9.4 Totals, summed over districts, must not exceed DMT's
    all-vehicle national figure."""
    flags = []
    totals = df[(df["metric"] == METRIC_REGISTRATIONS) & df["is_total_row"]]
    for year, national_value in national_totals.items():
        total = totals[totals["year"] == year]["number"].sum()
        if total > national_value:
            flags.append(_flag("district_totals_exceed_dmt", "medium", "ALL", METRIC_REGISTRATIONS, year, "Total", int(total),
                               f"District Totals sum to {int(total)}, DMT national all-vehicle figure is "
                               f"{national_value} ({total / national_value:.1%})."))
    return flags


def _total_registrations_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per district and year: printed Table 9.4 Total, the sum of its
    categories, and how it compares with other districts.

    The licence base is the district's median licence Total, so that one bad
    licence year (e.g. Ampara 2019) cannot make a registration Total look wrong.
    """
    registrations = df[df["metric"] == METRIC_REGISTRATIONS]
    key = ["district", "year"]
    table = registrations[registrations["is_total_row"]][key + ["number", "source_file", "page"]].rename(
        columns={"number": "printed_total"})
    table = table.merge(
        registrations[~registrations["is_total_row"]].groupby(key)["number"].sum().rename("categories_sum").reset_index(),
        on=key, how="left",
    )
    licences = df[(df["metric"] == METRIC_LICENCES) & df["is_total_row"]]
    table = table.merge(licences.groupby("district")["number"].median().rename("licence_base").reset_index(), on="district", how="left")

    table = table.sort_values(key).reset_index(drop=True)
    rate = (table["printed_total"] / table["licence_base"]).map(math.log)
    table["rate_vs_median"] = rate - rate.groupby(table["year"]).transform("median")
    change = table["printed_total"].map(math.log) - table.groupby("district")["printed_total"].shift(1).map(math.log)
    table["change_vs_median"] = change - change.groupby(table["year"]).transform("median")
    return table


def check_total_registrations_against_peers(df: pd.DataFrame, threshold: float) -> list[dict]:
    """A Total can add up and still be wrong. Flag Totals far from other districts
    in the same year, by size relative to licences or by year-on-year change."""
    flags = []
    for row in _total_registrations_table(df).itertuples():
        reasons = []
        if abs(row.rate_vs_median) > threshold:
            reasons.append(f"{math.exp(row.rate_vs_median):.2f} times the median district's registrations per licence")
        if pd.notna(row.change_vs_median) and abs(row.change_vs_median) > threshold:
            reasons.append(f"year-on-year change {math.exp(row.change_vs_median):.2f} times the median district's")
        if reasons:
            flags.append(_flag("total_registrations_against_peers", "medium", row.district, METRIC_REGISTRATIONS, row.year,
                               "Total", int(row.printed_total), "; ".join(reasons) + ".", row.source_file, row.page))
    return flags


def verify_total_registrations(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Verification status of every printed Table 9.4 Total. No independent
    district-level source exists, so "verified" means: it equals the sum of its
    categories, is in line with other districts, and its year does not exceed
    DMT's national figure. It does not mean confirmed correct."""
    threshold = config["validation"]["total_peer_log_threshold"]
    national = config["dmt_national_new_registrations_all_vehicles"]
    table = _total_registrations_table(df)
    year_sum = table.groupby("year")["printed_total"].transform("sum")
    table["dmt_national"] = table["year"].map(national)
    table["year_share_of_dmt"] = (year_sum / table["dmt_national"]).round(4)
    table["sum_matches"] = table["printed_total"] == table["categories_sum"]
    table["_outlier"] = (table["rate_vs_median"].abs() > threshold) | (table["change_vs_median"].abs() > threshold)

    def status(row) -> str:
        if not row["sum_matches"] or row["_outlier"] or pd.isna(row["printed_total"]):
            return TOTAL_FLAGGED
        return TOTAL_YEAR_CAVEAT if row["year_share_of_dmt"] > 1 else TOTAL_VERIFIED

    table["verification_status"] = table.apply(status, axis=1)
    return table[["district", "year", "printed_total", "categories_sum", "sum_matches", "rate_vs_median", "change_vs_median",
                  "dmt_national", "year_share_of_dmt", "verification_status", "source_file", "page"]].round(
        {"rate_vs_median": 3, "change_vs_median": 3})


def review_flags(flags: pd.DataFrame, rules: list[dict], corrections: pd.DataFrame) -> pd.DataFrame:
    """Attach to each flag the documented anomaly and decision it belongs to. The
    first matching rule wins. A flag with no rule keeps an empty anomaly_id, which
    the tests treat as an undocumented problem."""
    def match(flag) -> str:
        for rule in rules:
            fields = [f for f in ("check_id", "district", "year", "row_label") if f in rule]
            if all(str(flag[f]) == str(rule[f]) for f in fields):
                return rule["anomaly_id"]
        return ""

    decisions = dict(zip(corrections["anomaly_id"], corrections["decision_status"]))
    anomaly_ids = flags.apply(match, axis=1) if len(flags) else pd.Series(dtype=str)
    return flags.assign(anomaly_id=anomaly_ids, decision_status=anomaly_ids.map(decisions).fillna(""))


def check_source_attribution(df: pd.DataFrame) -> list[dict]:
    """Table 9.3 normally cites Divisional Secretary's offices."""
    flags = []
    subset = df[df["metric"] == METRIC_LICENCES].drop_duplicates(["district"])
    for row in subset.itertuples():
        if "divisional" not in str(row.source_note).lower():
            flags.append(_flag("licence_source_differs", "medium", row.district, row.metric, "", "", "",
                               f"Table 9.3 cites: {row.source_note}", row.source_file))
    return flags


def validate(cells: pd.DataFrame, structural_issues: list[dict], config: dict | None = None) -> pd.DataFrame:
    """Run every check. Returns one row per flag, most severe first. `cells` is not modified."""
    config = config or load_config()
    settings = config["validation"]
    df = _with_numbers(cells)

    flags = [
        _flag(issue["check_id"], "high", issue["district"], issue["metric"], row_label=str(issue["detail"]),
              evidence="Structural check on the PDF table.", source_file=issue["source_file"])
        for issue in structural_issues
    ]
    flags += check_sum_to_total(df, settings["sum_tolerance"])
    flags += check_missing_category_cells(df)
    flags += check_identical_year_columns(df, settings["min_matching_values"])
    flags += check_identical_columns_across_districts(df, settings["min_matching_values"])
    flags += check_licences_copied_from_registrations(
        df, settings["cross_table_min_shared_values"], settings["cross_table_min_value"])
    flags += check_year_on_year_against_national_pattern(
        df, settings["yoy_relative_log_threshold"], settings["yoy_min_base"])
    flags += check_dips_and_spikes(df, settings["dip_ratio"])
    flags += check_registrations_against_licences(df, settings["registration_to_stock_ratio"])
    flags += check_largest_registration_category(df)
    flags += check_against_dmt_national(df)
    flags += check_totals_against_dmt_national(df, config["dmt_national_new_registrations_all_vehicles"])
    flags += check_total_registrations_against_peers(df, settings["total_peer_log_threshold"])
    flags += check_source_attribution(df)

    result = pd.DataFrame(flags, columns=FLAG_COLUMNS)
    rank = result["severity"].map({"high": 0, "medium": 1, "low": 2})
    return result.assign(_rank=rank).sort_values(["_rank", "check_id", "district", "year"], key=lambda s: s.astype(str)).drop(columns="_rank")


def compare_with_v1(cells: pd.DataFrame, v1_csv: Path = V1_INTERIM_CSV) -> pd.DataFrame:
    """Every cell that differs between the v1 raw extraction and v2."""
    v1 = pd.read_csv(v1_csv, dtype=str, keep_default_na=False).drop_duplicates()
    v1 = v1.rename(columns={"district_canonical": "district", "vehicle_type_raw": "row_label", "value_raw": "value_v1"})
    v1["year"] = v1["year"].astype(int)
    # The v1 raw file names Table 9.3's metric differently; it is the same table.
    v1["metric"] = v1["metric"].replace({"vehicle_stock": METRIC_LICENCES})
    v1 = v1[["district", "metric", "year", "row_label", "value_v1"]]
    # v1 can hold several values for one cell (e.g. repeated page headers read as data); keep them all visible.
    v1 = v1.groupby(["district", "metric", "year", "row_label"], as_index=False).agg(value_v1=("value_v1", " | ".join))

    v2 = cells[cells["is_total_row"].astype(str).str.lower() != "true"]
    v2 = v2.rename(columns={"value_raw": "value_v2"})[
        ["district", "metric", "year", "row_label", "vehicle_type", "value_v2", "cell_status"]]
    v2 = v2.assign(year=v2["year"].astype(int))

    merged = v1.merge(v2, how="outer", on=["district", "metric", "year", "row_label"], indicator=True)

    def classify(row) -> str:
        if row["_merge"] == "left_only":
            return V1_ONLY
        if row["_merge"] == "right_only":
            return V2_ONLY
        if str(row["value_v1"]).replace(",", "") == str(row["value_v2"]).replace(",", ""):
            return ""
        if row["value_v1"] == "-" and row["cell_status"] == STATUS_VALUE:
            return RECOVERED
        if row["value_v1"] == "-" and row["value_v2"] in ("", "n.a"):
            return PLACEHOLDER
        return CHANGED

    merged["difference"] = merged.apply(classify, axis=1)
    differences = merged[merged["difference"] != ""].drop(columns="_merge")
    return differences.sort_values(["difference", "district", "metric", "row_label", "year"])


def run(
    raw_dir: Path = RAW_DIR,
    cells_csv: Path = V2_CELLS_CSV,
    flags_csv: Path = FLAGS_CSV,
    v1_diff_csv: Path = V1_DIFF_CSV,
    v1_csv: Path = V1_INTERIM_CSV,
    totals_csv: Path = TOTALS_CSV,
    corrections_csv: Path = CORRECTIONS_CSV,
) -> dict:
    """Extract, validate and write the v2 outputs. Reads the PDFs and the v1 CSV
    only; writes nothing else."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    cell_objects, issues = extract_all(raw_dir, config, v1_csv)
    write_cells_csv(cell_objects, cells_csv)

    cells = pd.DataFrame([asdict(c) for c in cell_objects])
    corrections = pd.read_csv(corrections_csv, dtype=str, keep_default_na=False)
    flags = review_flags(validate(cells, issues, config), config["flag_review"], corrections)
    totals = verify_total_registrations(_with_numbers(cells), config)
    differences = compare_with_v1(cells, v1_csv)

    for path, frame in [(flags_csv, flags), (v1_diff_csv, differences), (totals_csv, totals)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    return {
        "cells": len(cells),
        "flags": len(flags),
        "flags_by_check": flags.groupby(["severity", "check_id"]).size().to_dict(),
        "flags_without_decision": int((flags["anomaly_id"] == "").sum()),
        "total_registrations": totals["verification_status"].value_counts().to_dict(),
        "differences_from_v1": differences["difference"].value_counts().to_dict(),
    }


if __name__ == "__main__":
    print(run())
