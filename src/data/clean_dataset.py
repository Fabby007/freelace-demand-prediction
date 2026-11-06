"""Data cleaning, normalization, and validation (DEV-004).

Reads the raw long-format interim observations produced by DEV-003
(src/data/extract_dcs_handbook.py) and produces the cleaned, wide-format
processed dataset conforming to REF-001 (extended per Section 6 with
per-metric provenance columns - see module docstring below for rationale).

Implements source doc Section 11 (Data Cleaning and Preprocessing):
- District normalisation (already canonical at acquisition time - see
  extract_dcs_handbook.py; this module only defensively validates it).
- Vehicle-category normalisation via configs/vehicle_category_lookup.csv;
  categories outside the documented scope (Motorcycle/Car/Three-wheeler)
  are excluded, never silently folded into a canonical category.
- Duplicate handling via a documented source-priority rule (most recent
  handbook edition wins for a given district-year-vehicle_type-metric key).
- Missing values investigated, never auto-zeroed - see the "-" vs "n/r"
  handling note below and REF-009 ADR-005.
- Outlier review: flagged, not silently removed.
- Numeric conversion preserving the raw text (already archived by DEV-003;
  preserved again here in *_raw columns on the processed file itself).
- Chronological sort before any lag-feature construction (owned by DEV-005,
  but this module guarantees the processed file is already sorted).
"""
from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

CANONICAL_DISTRICTS_CSV = CONFIGS_DIR / "district_lookup.csv"
VEHICLE_CATEGORY_LOOKUP_CSV = CONFIGS_DIR / "vehicle_category_lookup.csv"

METRIC_TO_COLUMN = {
    "new_registrations": "new_registrations",
    "vehicle_stock": "vehicle_population",
}


def load_vehicle_category_lookup() -> dict[str, str]:
    with open(VEHICLE_CATEGORY_LOOKUP_CSV, newline="", encoding="utf-8") as f:
        return {row["raw_name"]: row["canonical_name"] for row in csv.DictReader(f)}


def load_canonical_districts() -> set[str]:
    with open(CANONICAL_DISTRICTS_CSV, newline="", encoding="utf-8") as f:
        return {row["canonical_name"] for row in csv.DictReader(f)}


def _to_numeric_and_note(value_raw: str) -> tuple[float | None, str | None]:
    """Convert a raw cell value to a numeric value plus a data-quality note.

    Per REF-009 ADR-005: "-" and "n/r" are both preserved as missing (NaN)
    rather than assumed to be zero, per Section 11's explicit "do not
    automatically convert blanks to zero" rule - even though a circumstantial
    real-world cross-check (Sri Lanka's 2020-2022 vehicle import
    restrictions) is *consistent with* "-" meaning a genuine zero for some
    rows, that is not confirmation for every row/table, so the conservative,
    spec-compliant choice is taken. XGBoost (DEV-008) handles missing
    values natively, so this does not block modelling.
    """
    value_raw = value_raw.strip()
    if value_raw == "-":
        return None, "reported_as_dash"
    if value_raw.lower() == "n/r":
        return None, "not_reported"
    try:
        return float(value_raw.replace(",", "")), None
    except ValueError:
        return None, "unparseable_raw_value"


def clean_raw_observations(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize vehicle-category labels, convert values, and report
    (not silently drop) anything that fails normalization or parsing."""
    vehicle_lookup = load_vehicle_category_lookup()
    canonical_districts = load_canonical_districts()

    df = raw_df.copy()

    unknown_districts = set(df["district_canonical"]) - canonical_districts
    if unknown_districts:
        raise ValueError(
            f"Unknown district name(s) after normalization: {sorted(unknown_districts)}. "
            "Update configs/district_lookup.csv (REF-002) rather than silently dropping these rows."
        )

    df["vehicle_type"] = df["vehicle_type_raw"].map(vehicle_lookup)
    out_of_scope_mask = df["vehicle_type"].isna()
    n_out_of_scope = int(out_of_scope_mask.sum())
    if n_out_of_scope:
        dropped_labels = sorted(df.loc[out_of_scope_mask, "vehicle_type_raw"].unique())
        logger.info(
            "Excluding %d rows with vehicle_type_raw not in configs/vehicle_category_lookup.csv "
            "(out of documented scope - Motorcycle/Car/Three-wheeler only, or an extraction "
            "artifact for a specific district; not silently folded into a canonical category): %s",
            n_out_of_scope, dropped_labels,
        )
    df = df[~out_of_scope_mask].copy()

    numeric_and_notes = df["value_raw"].astype(str).map(_to_numeric_and_note)
    df["value_numeric"] = [v for v, _ in numeric_and_notes]
    df["value_quality_note"] = [n for _, n in numeric_and_notes]

    n_missing = int(df["value_numeric"].isna().sum())
    if n_missing:
        logger.info(
            "%d of %d values are missing after conversion (reported as '-' or 'n/r') - "
            "preserved as NaN, not zero-filled (Section 11).",
            n_missing, len(df),
        )

    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Source-priority rule (REF-009 ADR-025): for a given
    (district, year, vehicle_type, metric) key spanning *different* handbook
    editions, the most recent handbook_edition_year wins - a no-op on the
    current single-edition dataset, but implemented generally for when
    multiple editions are acquired (Section 11 "Duplicate handling").

    A duplicate key within the *same* edition is not a legitimate
    multi-edition overlap - it means the same row was parsed twice. If both
    copies agree, keep one (harmless double-parse). If they disagree, this
    is an unresolved extraction ambiguity (observed: Trincomalee, likely
    from a district-specific PDF layout quirk) - exclude both rather than
    silently guessing which value is correct, and log it loudly so it can
    be manually investigated against the source PDF.
    """
    key = ["district_canonical", "year", "vehicle_type", "metric"]

    same_edition_dupe_mask = df.duplicated(subset=key + ["handbook_edition_year"], keep=False)
    same_edition_dupes = df[same_edition_dupe_mask]
    if not same_edition_dupes.empty:
        conflicting_keys = []
        for group_key, group in same_edition_dupes.groupby(key):
            if group["value_raw"].nunique() > 1:
                conflicting_keys.append(group_key)
        if conflicting_keys:
            logger.warning(
                "%d district-year-vehicle_type-metric key(s) were parsed more than once "
                "within the same handbook edition with DISAGREEING raw values - excluding "
                "them rather than guessing which is correct. Needs manual review against "
                "the source PDF: %s",
                len(conflicting_keys), conflicting_keys,
            )
            conflict_mask = df.set_index(key).index.isin(conflicting_keys)
            df = df[~conflict_mask].copy()

    before = len(df)
    df = df.sort_values("handbook_edition_year", ascending=False).drop_duplicates(subset=key, keep="first")
    n_dropped = before - len(df)
    if n_dropped:
        logger.info("Dropped %d duplicate district-year-vehicle_type-metric rows "
                     "(kept the most recent handbook edition, or an agreeing repeat).", n_dropped)
    return df


def flag_outliers(wide_df: pd.DataFrame) -> pd.DataFrame:
    """Section 11: compare extreme values against the source before
    removing/winsorising. Observed pattern: some districts' vehicle_population
    (Table 9.3) repeats the identical value for 2022 and 2023, suggesting the
    2023 column was not yet refreshed at publication time. Flagged, not
    removed - the value is still genuinely what the source publication
    states."""
    wide_df = wide_df.sort_values(["district", "vehicle_type", "year"]).copy()
    wide_df["data_quality_flag"] = None
    grouped = wide_df.groupby(["district", "vehicle_type"])["vehicle_population"]
    prev_value = grouped.shift(1)
    prev_year = wide_df.groupby(["district", "vehicle_type"])["year"].shift(1)
    same_as_prior_year = (
        (wide_df["vehicle_population"].notna())
        & (wide_df["vehicle_population"] == prev_value)
        & (wide_df["year"] == prev_year + 1)
    )
    wide_df.loc[same_as_prior_year, "data_quality_flag"] = "vehicle_population_identical_to_prior_year"
    n_flagged = int(same_as_prior_year.sum())
    if n_flagged:
        logger.info(
            "Flagged %d rows where vehicle_population is identical to the prior year "
            "(possible not-yet-refreshed publication data - REF-001/data source register note).",
            n_flagged,
        )
    return wide_df


def pivot_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """One row per district x year x vehicle_type (REF-001 schema), with
    new_registrations and vehicle_population as separate columns, each
    carrying its own provenance (since the two metrics come from different
    source tables - Table 9.4 vs Table 9.3 - this is a documented extension
    of REF-001, see REF-001 Section 6)."""
    pieces = []
    for metric, value_col in METRIC_TO_COLUMN.items():
        sub = df[df["metric"] == metric][
            ["district_canonical", "year", "vehicle_type", "value_numeric", "value_raw",
             "value_quality_note", "source_id", "source_url", "retrieved_date"]
        ].rename(columns={
            "district_canonical": "district",
            "value_numeric": value_col,
            "value_raw": f"{value_col}_raw",
            "value_quality_note": f"{value_col}_quality_note",
            "source_id": f"{value_col}_source_id",
            "source_url": f"{value_col}_source_url",
        })
        pieces.append(sub)

    # retrieved_date is the same handbook-download date for every row in
    # this run; keep it once (from the first metric piece) rather than
    # merging it in again per metric, which would create a spurious
    # retrieved_date_x/_y column pair.
    wide = pieces[0]
    for piece in pieces[1:]:
        wide = wide.merge(
            piece.drop(columns=["retrieved_date"]),
            on=["district", "year", "vehicle_type"],
            how="outer",
        )

    # An outer-join row with no matching source row at all for a given
    # metric (e.g. a district-year-vehicle_type combination absent from
    # that table, or excluded upstream as an unresolved same-edition
    # conflict - see deduplicate()) must never be left as an unexplained
    # NaN: every missing value carries a quality note (Section 11: missing
    # values must be reported, never silently unexplained).
    for value_col in METRIC_TO_COLUMN.values():
        note_col = f"{value_col}_quality_note"
        no_source_row = wide[value_col].isna() & wide[note_col].isna()
        wide.loc[no_source_row, note_col] = "no_matching_source_row"

    # REF-001 columns not yet populated by this extraction pass (population,
    # population_density require DCS Chapter 2 tables - registered in
    # data/source_register.csv but not yet downloaded, see DEV-003 TODO).
    wide["month"] = None
    wide["population"] = None
    wide["population_density"] = None

    return wide


def run(interim_csv: Path, out_path: Path) -> Path:
    logging.basicConfig(level=logging.INFO)
    raw_df = pd.read_csv(interim_csv, dtype={"value_raw": str})
    cleaned = clean_raw_observations(raw_df)
    cleaned = deduplicate(cleaned)
    wide = pivot_to_wide(cleaned)
    wide = flag_outliers(wide)
    wide = wide.sort_values(["district", "vehicle_type", "year"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(out_path, index=False)
    logger.info("Wrote %d processed rows to %s", len(wide), out_path)
    return out_path


if __name__ == "__main__":
    run(
        INTERIM_DIR / "dcs_multi_district_2024_raw.csv",
        PROCESSED_DIR / f"modelling_base_{date.today().isoformat()}.csv",
    )
