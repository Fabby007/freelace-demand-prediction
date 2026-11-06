"""DEV-003 Section 10 step 6: validate extracted totals against DMT
national statistics. Tests that the cross-check runs and correctly flags
the known logically-impossible discrepancies (district sum > national
total) rather than silently passing them through.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest

from src.data.build_processed_dataset import build
from src.data.validate_against_dmt import cross_check, flag_implausible_rows

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"
_PROCESSED_CSV = Path(__file__).resolve().parents[1] / "data" / "processed" / "modelling_base_2024.csv"

pytestmark = pytest.mark.skipif(
    not _INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def processed_df() -> pd.DataFrame:
    # Canonical pipeline entry point - see src/data/build_processed_dataset.py
    # and REF-009 ADR-006.
    build(_INTERIM_CSV, _PROCESSED_CSV)
    return pd.read_csv(_PROCESSED_CSV)


def test_cross_check_covers_all_vehicle_type_year_metric_combinations(processed_df):
    result = cross_check(processed_df)
    assert len(result) == 3 * 5 * 2  # 3 vehicle types x 5 years x 2 metrics


def test_vehicle_population_never_exceeds_national_total(processed_df):
    result = cross_check(processed_df)
    pop = result[result["metric"] == "vehicle_population"]
    assert not pop["exceeds_national_total"].any()


def test_known_implausible_combinations_are_flagged(processed_df):
    """Car 2019-2021 and Three-wheeler 2022 new_registrations district sums
    exceed the DMT national total - a logically impossible outcome that
    must be surfaced, not hidden (see reports/dmt_cross_validation.md)."""
    result = cross_check(processed_df)
    reg = result[result["metric"] == "new_registrations"]
    flagged = set(
        zip(reg.loc[reg["exceeds_national_total"], "vehicle_type"],
            reg.loc[reg["exceeds_national_total"], "year"])
    )
    assert ("Car", 2019) in flagged
    assert ("Car", 2020) in flagged
    assert ("Car", 2021) in flagged
    assert ("Three-wheeler", 2022) in flagged


def test_flag_implausible_rows_marks_processed_rows(processed_df):
    result = cross_check(processed_df)
    flagged_df = flag_implausible_rows(processed_df, result)
    car_2019 = flagged_df[(flagged_df["vehicle_type"] == "Car") & (flagged_df["year"] == 2019)]
    assert (car_2019["data_quality_flag"] == "district_sum_exceeds_dmt_national_total_for_new_registrations").all()
