"""DEV-009 / DEV-015 tests for the LSTM sequence-density conditionality check.

Covers DEV-009's mandatory "Conditionality check (must run first)": the
assessment function must genuinely branch on real evidence (not be hardcoded
to a fixed answer), and must correctly conclude "skip" against the actual
frozen dataset, with the reasoning traceable to real, checkable numbers.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest
import yaml

from src.features.build_features import build_features
from src.features.assemble_modelling_dataset import SPLIT_CONFIG_YAML, add_target, assign_split
from src.models.lstm_model import (
    DECISION_EXPERIMENTAL,
    DECISION_PROCEED,
    DECISION_SKIP,
    MODEL_PARAMS_YAML,
    _longest_consecutive_run,
    assess_sequence_density,
)

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"

pytestmark = pytest.mark.skipif(
    not _INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def frozen_df(isolated_processed_csv) -> pd.DataFrame:
    processed = pd.read_csv(isolated_processed_csv)
    featured = build_features(processed)
    df = add_target(featured)
    with open(SPLIT_CONFIG_YAML, encoding="utf-8") as f:
        split_config = yaml.safe_load(f)
    return assign_split(df, split_config)


@pytest.fixture(scope="module")
def min_lookback_periods() -> int:
    with open(MODEL_PARAMS_YAML, encoding="utf-8") as f:
        model_params = yaml.safe_load(f)
    return model_params["lstm"]["lookback_months"]


# --- Longest-consecutive-run helper -----------------------------------------

def test_longest_consecutive_run_basic_cases():
    assert _longest_consecutive_run([]) == 0
    assert _longest_consecutive_run([2020]) == 1
    assert _longest_consecutive_run([2019, 2020, 2021]) == 3
    assert _longest_consecutive_run([2019, 2020, 2022, 2023]) == 2  # gap at 2021
    assert _longest_consecutive_run([2023, 2019, 2021, 2020]) == 3  # unsorted input, [2019,2020,2021]
    assert _longest_consecutive_run([2020, 2020, 2021]) == 2  # duplicates deduplicated first


# --- Real-data assessment: must conclude "skip" with correct evidence -------

def test_real_dataset_assessment_concludes_skip(frozen_df, min_lookback_periods):
    """The actual frozen DEV-006 dataset is yearly-only (no month data) and
    every series has at most 5 yearly observations - well below the
    documented 6-month minimum lookback. This must be reflected honestly."""
    assessment = assess_sequence_density(frozen_df, min_lookback_periods)

    assert assessment["decision"] == DECISION_SKIP
    assert assessment["month_populated"] is False
    assert assessment["n_distinct_years"] == 5
    assert assessment["max_consecutive_run"] <= 5
    assert assessment["n_series_meeting_yearly_threshold"] == 0
    assert len(assessment["reasoning"]) >= 1
    assert all(isinstance(r, str) and len(r) > 0 for r in assessment["reasoning"])


def test_real_dataset_assessment_is_json_serializable(frozen_df, min_lookback_periods):
    """The assessment is persisted to reports/lstm_sequence_density_assessment.json -
    every value must already be a plain Python type, not a numpy scalar."""
    import json
    assessment = assess_sequence_density(frozen_df, min_lookback_periods)
    json.dumps(assessment)  # raises TypeError if any value is a numpy int64/bool_/etc.


# --- The assessment function genuinely branches on evidence (not hardcoded) --

def test_assessment_returns_skip_when_no_monthly_data_regardless_of_row_count():
    df = pd.DataFrame({
        "district": ["A"] * 20, "vehicle_type": ["Motorcycle"] * 20,
        "year": list(range(2000, 2020)), "month": [None] * 20,
        "new_registrations": [float(i) for i in range(20)],
    })
    result = assess_sequence_density(df, min_lookback_periods=6)
    assert result["decision"] == DECISION_SKIP
    assert result["month_populated"] is False


def test_assessment_returns_skip_when_monthly_but_run_too_short():
    df = pd.DataFrame({
        "district": ["A"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2022, 2022, 2022], "month": [1, 2, 3],
        "new_registrations": [10.0, 20.0, 30.0],
    })
    result = assess_sequence_density(df, min_lookback_periods=6)
    assert result["decision"] == DECISION_SKIP
    assert result["month_populated"] is True
    assert result["max_consecutive_run"] == 3


def test_assessment_returns_proceed_when_all_series_meet_threshold():
    """Synthetic monthly data where every series has a long enough
    consecutive run - proves the function can reach 'proceed', it is not
    hardcoded to always return 'skip'."""
    months = list(range(1, 13)) * 2  # 24 consecutive months
    years = [2022] * 12 + [2023] * 12
    df = pd.DataFrame({
        "district": ["A"] * 24, "vehicle_type": ["Motorcycle"] * 24,
        "year": years, "month": months,
        "new_registrations": [float(i) for i in range(24)],
    })
    result = assess_sequence_density(df, min_lookback_periods=6)
    assert result["decision"] == DECISION_PROCEED
    assert result["max_consecutive_run"] == 24


def test_assessment_returns_experimental_when_only_some_series_qualify():
    long_series = pd.DataFrame({
        "district": ["A"] * 24, "vehicle_type": ["Motorcycle"] * 24,
        "year": [2022] * 12 + [2023] * 12, "month": list(range(1, 13)) * 2,
        "new_registrations": [float(i) for i in range(24)],
    })
    short_series = pd.DataFrame({
        "district": ["B"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2023, 2023, 2023], "month": [1, 2, 3],
        "new_registrations": [1.0, 2.0, 3.0],
    })
    df = pd.concat([long_series, short_series], ignore_index=True)
    result = assess_sequence_density(df, min_lookback_periods=6)
    assert result["decision"] == DECISION_EXPERIMENTAL
    assert result["n_series_meeting_yearly_threshold"] == 1
    assert result["n_series"] == 2


def test_assessment_handles_series_with_zero_observations():
    """A series with every new_registrations value null must count as a
    run of 0, not be silently excluded from the series count."""
    df = pd.DataFrame({
        "district": ["A"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2021, 2022, 2023], "month": [1, 2, 3],
        "new_registrations": [None, None, None],
    })
    result = assess_sequence_density(df, min_lookback_periods=6)
    assert result["n_series"] == 1
    assert result["max_consecutive_run"] == 0
    assert result["decision"] == DECISION_SKIP
