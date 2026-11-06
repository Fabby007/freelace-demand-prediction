"""DEV-004 / DEV-015 Section 26.1 data tests, run against a cleaned processed
dataset rebuilt into a temporary folder from the real interim file (see
tests/conftest.py), never against or over data/processed/ itself.

Skipped entirely when no processed file exists locally (fresh clone
without having run the pipeline / without network access to re-acquire
the source PDFs).
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest

from src.data.clean_dataset import REPO_ROOT, clean_raw_observations, load_canonical_districts

INTERIM_CSV = REPO_ROOT / "data" / "interim" / "dcs_multi_district_2024_raw.csv"

pytestmark = pytest.mark.skipif(
    not INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def processed_df(isolated_processed_csv) -> pd.DataFrame:
    # Built by the canonical pipeline entry point (clean + DMT cross-validate),
    # not clean_dataset.run() alone - see src/data/build_processed_dataset.py
    # and REF-009 ADR-006 for why calling clean_dataset.run() in isolation
    # would silently wipe the DMT cross-validation flags. The build goes to a
    # temporary folder (tests/conftest.py, REF-009 ADR-035).
    return pd.read_csv(isolated_processed_csv)


def test_no_unknown_district_names(processed_df):
    canonical = load_canonical_districts()
    assert set(processed_df["district"]) <= canonical


def test_no_unknown_vehicle_categories(processed_df):
    assert set(processed_df["vehicle_type"]) == {"Motorcycle", "Car", "Three-wheeler"}


def test_no_duplicated_district_year_vehicle_type_key(processed_df):
    key_cols = ["district", "year", "vehicle_type"]
    assert not processed_df.duplicated(subset=key_cols).any()


def test_numeric_fields_non_negative_where_present(processed_df):
    for col in ["new_registrations", "vehicle_population"]:
        values = processed_df[col].dropna()
        assert (values >= 0).all(), f"{col} contains negative value(s)"


def test_observation_years_match_source_range(processed_df):
    assert set(processed_df["year"].unique()) <= {2019, 2020, 2021, 2022, 2023}


def test_missing_values_reported_not_silently_replaced(processed_df):
    # Every row with a NaN new_registrations must carry a quality note
    # explaining why (never a silent/unexplained NaN).
    missing = processed_df[processed_df["new_registrations"].isna()]
    assert missing["new_registrations_quality_note"].notna().all()


def test_source_id_exists_for_every_processed_row(processed_df):
    has_source_id = (
        processed_df["new_registrations_source_id"].notna()
        | processed_df["vehicle_population_source_id"].notna()
    )
    assert has_source_id.all()


def test_out_of_scope_categories_excluded_not_folded_in():
    """REF-002: categories outside Motorcycle/Car/Three-wheeler must be
    excluded, never silently mapped into one of the three canonical
    categories."""
    raw_df = pd.read_csv(INTERIM_CSV, dtype={"value_raw": str})
    cleaned = clean_raw_observations(raw_df)
    assert set(cleaned["vehicle_type"].unique()) == {"Motorcycle", "Car", "Three-wheeler"}
    assert len(cleaned) < len(raw_df)
