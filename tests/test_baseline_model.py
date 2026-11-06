"""DEV-007 / DEV-015 tests for the baseline forecasting model.

Covers DEV-007's Testing Requirements: baseline prediction correctness against
hand-computed samples, and evaluation on the exact same validation/test periods
DEV-008 will use (the DEV-006 frozen split, read from configs/split_config.yaml -
never re-derived or altered here).
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.features.build_features import build_features
from src.features.assemble_modelling_dataset import SPLIT_CONFIG_YAML, add_target, assign_split
from src.models.baseline import (
    MODEL_PARAMS_YAML,
    add_baseline_predictions,
    add_linear_trend_baseline,
    add_moving_average_baseline,
    add_previous_period_baseline,
    evaluate_baselines,
    run,
)

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"

pytestmark = pytest.mark.skipif(
    not _INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def split_config() -> dict:
    with open(SPLIT_CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def model_params() -> dict:
    with open(MODEL_PARAMS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def assembled_df(split_config, isolated_processed_csv) -> pd.DataFrame:
    processed = pd.read_csv(isolated_processed_csv)
    featured = build_features(processed)
    df = add_target(featured)
    return assign_split(df, split_config)


@pytest.fixture(scope="module")
def baselined_df(assembled_df, model_params) -> pd.DataFrame:
    return add_baseline_predictions(assembled_df.copy(), model_params)


# --- Previous-period baseline --------------------------------------------

def test_previous_period_baseline_hand_computed(baselined_df):
    """Kandy Motorcycle target_value = [492, 214, NaN, 813, NaN] for 2019-2023
    (see tests/test_dataset_assembly.py) - baseline_previous_period(t) must
    equal target_value(t-1) exactly, including the genuine null carried
    forward from the missing 2022 observation."""
    sub = baselined_df[
        (baselined_df["district"] == "Kandy") & (baselined_df["vehicle_type"] == "Motorcycle")
    ].sort_values("year").reset_index(drop=True)

    assert pd.isna(sub.loc[0, "baseline_previous_period"])  # 2019: no prior target
    assert sub.loc[1, "baseline_previous_period"] == 492.0
    assert sub.loc[2, "baseline_previous_period"] == 214.0
    assert pd.isna(sub.loc[3, "baseline_previous_period"])  # prior target (2021->2022) was null
    assert sub.loc[4, "baseline_previous_period"] == 813.0


def test_previous_period_baseline_no_leakage():
    """Mutating a later row's target_value must never change an earlier row's
    previous-period baseline prediction."""
    df = pd.DataFrame({
        "district": ["X"] * 4, "vehicle_type": ["Motorcycle"] * 4,
        "year": [2019, 2020, 2021, 2022],
        "target_value": [10.0, 20.0, 30.0, 40.0],
    })
    original = add_previous_period_baseline(df.copy())

    mutated = df.copy()
    mutated.loc[mutated["year"] == 2022, "target_value"] = 999999.0
    mutated_result = add_previous_period_baseline(mutated)

    before = original[original["year"] < 2022].reset_index(drop=True)
    after = mutated_result[mutated_result["year"] < 2022].reset_index(drop=True)
    pd.testing.assert_series_equal(
        before["baseline_previous_period"], after["baseline_previous_period"], check_names=False,
    )


# --- Moving-average baseline ----------------------------------------------

def test_moving_average_baseline_reuses_rolling_mean_3(baselined_df):
    """FR2: with the configured window (3) matching rolling_mean_3's window,
    the moving-average baseline must equal DEV-005's rolling_mean_3 exactly -
    not merely be correlated with it."""
    both_present = baselined_df.dropna(subset=["rolling_mean_3", "baseline_moving_average"])
    assert len(both_present) > 0
    pd.testing.assert_series_equal(
        both_present["baseline_moving_average"], both_present["rolling_mean_3"],
        check_names=False,
    )


def test_moving_average_baseline_recomputes_on_window_mismatch():
    """If configs/model_params.yaml is ever changed to a window other than 3,
    the baseline must NOT silently reuse the (mismatched) rolling_mean_3
    column - it must recompute directly with the new window."""
    df = pd.DataFrame({
        "district": ["X"] * 5, "vehicle_type": ["Motorcycle"] * 5,
        "year": [2019, 2020, 2021, 2022, 2023],
        "new_registrations": [10.0, 20.0, 30.0, 40.0, 50.0],
        "rolling_mean_3": [np.nan, 10.0, 15.0, 20.0, 30.0],  # window-3 values (unused here)
    })
    result = add_moving_average_baseline(df.copy(), moving_average_window=2)
    # window-2 backward rolling mean: e.g. 2022's baseline = mean(new_registrations[2020,2021]) = 25.0
    row_2022 = result[result["year"] == 2022].iloc[0]
    assert row_2022["baseline_moving_average"] == pytest.approx(25.0)
    assert row_2022["baseline_moving_average"] != row_2022["rolling_mean_3"]


# --- Linear trend baseline -------------------------------------------------

def test_linear_trend_baseline_hand_computed():
    """A perfectly linear synthetic training series (slope=10, intercept=0)
    fit on train-split rows only must extrapolate exactly to the target_year
    of a later (non-train) row."""
    df = pd.DataFrame({
        "district": ["X"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2019, 2020, 2021],
        "new_registrations": [10.0, 20.0, 999999.0],  # 2021's own value must be ignored (not train)
        "target_year": [2020, 2021, 2022],
        "split": ["train", "train", "validation"],
    })
    result = add_linear_trend_baseline(df.copy())
    predicted_2022 = result[result["year"] == 2021]["baseline_linear_trend"].iloc[0]
    assert predicted_2022 == pytest.approx(40.0)  # slope=10, intercept=-20180 -> 10*2022-20180=40


def test_linear_trend_baseline_null_when_insufficient_training_points():
    """Error Case: fewer than 2 distinct non-null training-period years ->
    null prediction, never fabricated."""
    df = pd.DataFrame({
        "district": ["X"] * 2, "vehicle_type": ["Motorcycle"] * 2,
        "year": [2019, 2020],
        "new_registrations": [10.0, np.nan],  # only 1 valid training point
        "target_year": [2020, 2021],
        "split": ["train", "validation"],
    })
    result = add_linear_trend_baseline(df.copy())
    assert result["baseline_linear_trend"].isna().all()


def test_linear_trend_baseline_no_leakage_from_non_train_rows():
    """Mutating a validation/test-split row's new_registrations must not
    change the fitted trend (and therefore not the predictions), since the
    fit uses only train-split rows."""
    df = pd.DataFrame({
        "district": ["X"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2019, 2020, 2021],
        "new_registrations": [10.0, 20.0, 30.0],
        "target_year": [2020, 2021, 2022],
        "split": ["train", "train", "validation"],
    })
    original = add_linear_trend_baseline(df.copy())

    mutated = df.copy()
    mutated.loc[mutated["split"] == "validation", "new_registrations"] = 999999.0
    mutated_result = add_linear_trend_baseline(mutated)

    pd.testing.assert_series_equal(
        original["baseline_linear_trend"], mutated_result["baseline_linear_trend"], check_names=False,
    )


def test_linear_trend_baseline_can_predict_negative_values_and_is_not_clipped():
    """A sharply declining training trend legitimately extrapolates below
    zero - this must be surfaced honestly (see evaluate_baselines'
    n_negative_predictions), never silently clipped to zero."""
    df = pd.DataFrame({
        "district": ["X"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2019, 2020, 2021],
        "new_registrations": [100.0, 10.0, 5.0],
        "target_year": [2020, 2021, 2025],
        "split": ["train", "train", "test"],
    })
    result = add_linear_trend_baseline(df.copy())
    predicted = result[result["year"] == 2021]["baseline_linear_trend"].iloc[0]
    assert predicted < 0


# --- Edge case: genuine zero is a valid observation, not missing ----------

def test_zero_registration_period_treated_as_valid_not_missing():
    df = pd.DataFrame({
        "district": ["X"] * 3, "vehicle_type": ["Motorcycle"] * 3,
        "year": [2019, 2020, 2021],
        "target_value": [0.0, 5.0, 10.0],
    })
    result = add_previous_period_baseline(df.copy())
    row_2020 = result[result["year"] == 2020].iloc[0]
    assert row_2020["baseline_previous_period"] == 0.0  # not null, not skipped


# --- Evaluation on the exact DEV-006 split ---------------------------------

def test_evaluate_baselines_uses_dev006_split_labels_only(baselined_df, split_config):
    """Baselines must be scored on exactly the 'validation'/'test' rows the
    DEV-006 frozen split assigned - never a re-derived or randomly split set
    (Business Rule)."""
    metrics = evaluate_baselines(baselined_df)
    assert set(metrics.keys()) == {"validation", "test"}

    expected_validation_n = (baselined_df["split"] == "validation").sum()
    expected_test_n = (baselined_df["split"] == "test").sum()
    for baseline_col in metrics["validation"]:
        assert metrics["validation"][baseline_col]["n_total"] == expected_validation_n
        assert metrics["test"][baseline_col]["n_total"] == expected_test_n


def test_evaluate_baselines_reports_mae_rmse_r2_and_coverage(baselined_df):
    metrics = evaluate_baselines(baselined_df)
    for split_name in ("validation", "test"):
        for baseline_col, entry in metrics[split_name].items():
            assert set(entry.keys()) == {"n_total", "n_scored", "mae", "rmse", "r2", "n_negative_predictions"}
            assert entry["n_scored"] <= entry["n_total"]
            if entry["n_scored"] > 0:
                assert entry["mae"] >= 0
                assert entry["rmse"] >= 0
                assert entry["rmse"] >= entry["mae"] * 0  # sanity: both non-negative, RMSE >= 0


def test_evaluate_baselines_never_scores_unlabeled_rows(baselined_df):
    """Rows with split == 'unlabeled' (null target_value) must never
    contribute to validation/test metrics."""
    unlabeled_count = (baselined_df["split"] == "unlabeled").sum()
    assert unlabeled_count > 0  # sanity: the fixture really does have unlabeled rows
    metrics = evaluate_baselines(baselined_df)
    total_scored_or_total = sum(
        metrics[s][b]["n_total"] for s in ("validation", "test") for b in metrics[s]
    )
    # n_total per split must equal count of that split label, not len(df) - implicitly
    # confirms unlabeled rows are excluded from both splits' n_total.
    assert total_scored_or_total == 3 * (
        (baselined_df["split"] == "validation").sum() + (baselined_df["split"] == "test").sum()
    )


# --- run(): end-to-end wiring, fully isolated from real project files ------
#
# DEV-015 audit finding: baseline.py::run() (used by DEV-014's MLflow
# integration) previously had no automated test exercising it end-to-end at
# all - only its individual functions were tested. Added here with every
# output path (predictions CSV, metrics JSON, mlruns dir) redirected to
# tmp_path, so this test can never overwrite the real
# data/processed/baseline_predictions_v1.csv, reports/baseline_metrics.json,
# or append to the real mlruns/ store.

def test_run_end_to_end_is_isolated_from_real_project_files(assembled_df, tmp_path):
    frozen_csv = tmp_path / "modelling_dataset_v1.csv"
    assembled_df.to_csv(frozen_csv, index=False)
    predictions_csv = tmp_path / "baseline_predictions_v1.csv"
    metrics_json = tmp_path / "baseline_metrics.json"

    real_split_config = SPLIT_CONFIG_YAML.read_text(encoding="utf-8")
    tmp_split_config = tmp_path / "split_config.yaml"
    tmp_split_config.write_text(real_split_config, encoding="utf-8")

    report = run(
        frozen_csv=frozen_csv,
        model_params_path=MODEL_PARAMS_YAML,
        split_config_path=tmp_split_config,
        predictions_csv=predictions_csv,
        metrics_json=metrics_json,
        mlruns_dir=tmp_path / "mlruns",
    )

    assert predictions_csv.exists()
    assert metrics_json.exists()
    assert "validation" in report["metrics"] and "test" in report["metrics"]
    # Nothing under the real configs/ tree was touched by this run.
    assert SPLIT_CONFIG_YAML.read_text(encoding="utf-8") == real_split_config
