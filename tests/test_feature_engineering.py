"""DEV-005 / DEV-015 tests for the feature engineering pipeline.

Covers DEV-005's three Testing Requirements: the leakage unit test, a
feature-value correctness test against a hand-computed sample, and a
config-driven feature list test.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.features.build_features import ENGINEERED_COLUMNS, FEATURE_LIST_YAML, build_features

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"

pytestmark = pytest.mark.skipif(
    not _INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def processed_df(isolated_processed_csv) -> pd.DataFrame:
    return pd.read_csv(isolated_processed_csv)


@pytest.fixture(scope="module")
def featured_df(processed_df) -> pd.DataFrame:
    return build_features(processed_df.copy())


# --- Leakage test -----------------------------------------------------

def test_no_leakage_mutating_future_period_does_not_change_past_features():
    """Section 12.1: 'When predicting year t, every feature must be
    computable using information available before year t.' Construct a
    small synthetic series, compute features, then mutate every value at
    year >= t for some t, recompute, and assert every feature at years < t
    is bit-for-bit unchanged."""
    df = pd.DataFrame({
        "district": ["TestDistrict"] * 5,
        "vehicle_type": ["Motorcycle"] * 5,
        "year": [2019, 2020, 2021, 2022, 2023],
        "month": [None] * 5,
        "population": [None] * 5,
        "new_registrations": [100.0, 150.0, 120.0, 200.0, 90.0],
    })
    original_features = build_features(df.copy())

    for t in [2020, 2021, 2022, 2023]:
        mutated = df.copy()
        mutated.loc[mutated["year"] >= t, "new_registrations"] = 999999.0
        mutated_features = build_features(mutated)

        before_t_original = original_features[original_features["year"] < t].reset_index(drop=True)
        before_t_mutated = mutated_features[mutated_features["year"] < t].reset_index(drop=True)

        for col in ENGINEERED_COLUMNS:
            pd.testing.assert_series_equal(
                before_t_original[col], before_t_mutated[col],
                check_names=False,
                obj=f"feature '{col}' for years < {t} after mutating years >= {t}",
            )


def test_leakage_across_multiple_groups_independent():
    """A mutation in one (district, vehicle_type) group must not affect
    features computed for a different group."""
    df = pd.DataFrame({
        "district": ["A", "A", "A", "B", "B", "B"],
        "vehicle_type": ["Motorcycle"] * 6,
        "year": [2019, 2020, 2021, 2019, 2020, 2021],
        "month": [None] * 6,
        "population": [None] * 6,
        "new_registrations": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })
    original = build_features(df.copy())

    mutated = df.copy()
    mutated.loc[(mutated["district"] == "A") & (mutated["year"] == 2021), "new_registrations"] = 999999.0
    mutated_features = build_features(mutated)

    group_b_original = original[original["district"] == "B"].reset_index(drop=True)
    group_b_mutated = mutated_features[mutated_features["district"] == "B"].reset_index(drop=True)
    for col in ENGINEERED_COLUMNS:
        pd.testing.assert_series_equal(
            group_b_original[col], group_b_mutated[col], check_names=False,
        )


# --- Feature-value correctness test -----------------------------------

def test_kandy_motorcycle_hand_computed_values(featured_df):
    """Regression test against values hand-computed from the real Kandy
    Motorcycle series (new_registrations = [755, 492, 214, NaN, 813] for
    2019-2023, where 2022 is genuinely missing - see REF-009 ADR-005)."""
    sub = featured_df[
        (featured_df["district"] == "Kandy") & (featured_df["vehicle_type"] == "Motorcycle")
    ].sort_values("year").reset_index(drop=True)

    assert sub.loc[0, "reg_lag_1"] is None or pd.isna(sub.loc[0, "reg_lag_1"])  # 2019: no prior period
    assert sub.loc[1, "reg_lag_1"] == 755.0  # 2020's lag_1 is 2019's value
    assert sub.loc[2, "reg_lag_1"] == 492.0  # 2021's lag_1 is 2020's value
    assert sub.loc[2, "reg_lag_2"] == 755.0  # 2021's lag_2 is 2019's value

    assert sub.loc[1, "reg_growth_pct"] == pytest.approx((492 - 755) / 755 * 100)
    assert sub.loc[2, "reg_growth_pct"] == pytest.approx((214 - 492) / 492 * 100)

    assert sub.loc[2, "change_from_lag_2"] == pytest.approx(214 - 755)
    assert sub.loc[4, "change_from_lag_2"] == pytest.approx(813 - 214)  # 2023 vs 2021 (2022 missing)

    assert sub.loc[1, "rolling_mean_3"] == pytest.approx(755.0)  # only 1 prior value available
    assert sub.loc[2, "rolling_mean_3"] == pytest.approx((755 + 492) / 2)
    assert sub.loc[3, "rolling_mean_3"] == pytest.approx((755 + 492 + 214) / 3)  # 2022: last 3 prior
    assert sub.loc[4, "rolling_mean_3"] == pytest.approx((492 + 214) / 2)  # 2023: 2022 was NaN, excluded


def test_short_series_produces_null_not_fabricated_values():
    """Error Case: a series too short to compute reg_lag_2/rolling features
    must leave them null, never fabricate a value."""
    df = pd.DataFrame({
        "district": ["Solo"], "vehicle_type": ["Car"], "year": [2023],
        "month": [None], "population": [None], "new_registrations": [50.0],
    })
    result = build_features(df)
    assert pd.isna(result.loc[0, "reg_lag_1"])
    assert pd.isna(result.loc[0, "reg_lag_2"])
    assert pd.isna(result.loc[0, "reg_growth_pct"])
    assert pd.isna(result.loc[0, "rolling_mean_3"])


def test_yearly_only_dataset_leaves_month_features_null_not_fabricated(featured_df):
    """Edge Case: this dataset is yearly-only (no month column populated) -
    quarter/month_sin/month_cos must be null, never fabricated from an
    absent month value."""
    assert featured_df["quarter"].isna().all()
    assert featured_df["month_sin"].isna().all()
    assert featured_df["month_cos"].isna().all()


def test_demand_lag_1_not_present_on_fallback_path(featured_df):
    """DEV-002 Target Decision Record: Fallback path, no real demand
    series exists to lag."""
    assert "demand_lag_1" not in featured_df.columns


# --- Config-driven feature list test -----------------------------------

def test_engineered_columns_match_config():
    with open(FEATURE_LIST_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_engineered = [c.strip() for c in config["engineered_columns"]]
    assert config_engineered == ENGINEERED_COLUMNS


def test_all_engineered_columns_present_in_output(featured_df):
    for col in ENGINEERED_COLUMNS:
        assert col in featured_df.columns
