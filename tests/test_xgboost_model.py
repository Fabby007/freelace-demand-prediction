"""DEV-008 / DEV-015 tests for the XGBoost primary prediction model.

Covers DEV-008's Testing Requirements (Section 26.2 model tests): expected
feature columns/order, no future-period/test-period leakage during tuning,
reload consistency, impossible-value (negative-prediction) checking, and an
honest, identically-computed comparison against DEV-007's baseline metrics.
"""
import inspect
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.features.build_features import build_features
from src.features.assemble_modelling_dataset import SPLIT_CONFIG_YAML, add_target, assign_split
from src.models.baseline import add_baseline_predictions, MODEL_PARAMS_YAML as BASELINE_MODEL_PARAMS_YAML
from src.models.xgboost_model import (
    CATEGORICAL_COLUMN,
    VEHICLE_CATEGORIES,
    build_feature_matrix,
    candidate_numeric_features,
    compare_against_baseline,
    drop_all_null_features,
    evaluate_predictions,
    fit_vehicle_type_encoder,
    load_model,
    run,
    save_model,
    tune_hyperparameters,
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
def assembled_df(split_config, isolated_processed_csv) -> pd.DataFrame:
    processed = pd.read_csv(isolated_processed_csv)
    featured = build_features(processed)
    df = add_target(featured)
    return assign_split(df, split_config)


@pytest.fixture(scope="module")
def baselined_df(assembled_df) -> pd.DataFrame:
    with open(BASELINE_MODEL_PARAMS_YAML, encoding="utf-8") as f:
        model_params = yaml.safe_load(f)
    return add_baseline_predictions(assembled_df.copy(), model_params)


# --- Feature construction --------------------------------------------------

def test_drop_all_null_features_excludes_only_fully_null_columns():
    df = pd.DataFrame({
        "split": ["train", "validation", "test"],
        "always_null": [np.nan, np.nan, np.nan],
        "partially_null": [1.0, np.nan, 3.0],
        "never_null": [1.0, 2.0, 3.0],
    })
    labeled_mask = df["split"].isin(["train", "validation", "test"])
    active, excluded = drop_all_null_features(df, ["always_null", "partially_null", "never_null"], labeled_mask)
    assert active == ["partially_null", "never_null"]
    assert excluded == ["always_null"]


def test_build_feature_matrix_has_fixed_column_order_regardless_of_row_order():
    df = pd.DataFrame({
        CATEGORICAL_COLUMN: ["Three-wheeler", "Motorcycle", "Car"],
        "feat_a": [1.0, 2.0, 3.0],
        "feat_b": [4.0, 5.0, 6.0],
    })
    encoder = fit_vehicle_type_encoder(df)
    X = build_feature_matrix(df, ["feat_a", "feat_b"], encoder)
    assert list(X.columns) == [
        "feat_a", "feat_b",
        f"{CATEGORICAL_COLUMN}_Motorcycle", f"{CATEGORICAL_COLUMN}_Car", f"{CATEGORICAL_COLUMN}_Three-wheeler",
    ]


def test_build_feature_matrix_one_hot_encodes_correctly():
    df = pd.DataFrame({CATEGORICAL_COLUMN: ["Car"], "feat_a": [1.0]})
    encoder = fit_vehicle_type_encoder(pd.DataFrame({CATEGORICAL_COLUMN: VEHICLE_CATEGORIES}))
    X = build_feature_matrix(df, ["feat_a"], encoder)
    assert X[f"{CATEGORICAL_COLUMN}_Car"].iloc[0] == 1.0
    assert X[f"{CATEGORICAL_COLUMN}_Motorcycle"].iloc[0] == 0.0
    assert X[f"{CATEGORICAL_COLUMN}_Three-wheeler"].iloc[0] == 0.0


def test_candidate_numeric_features_is_config_driven_not_hardcoded():
    config = {"base_columns": ["a", "b"], "engineered_columns": ["c"]}
    assert candidate_numeric_features(config) == ["a", "b", "c"]


# --- Tuning: structural no-leakage guarantee --------------------------------

def test_tune_hyperparameters_signature_has_no_test_period_argument():
    """The test period must be structurally impossible to pass into tuning -
    tune_hyperparameters() only accepts train/validation arguments."""
    params = set(inspect.signature(tune_hyperparameters).parameters)
    assert not any("test" in p for p in params)
    assert {"X_train", "y_train", "X_val", "y_val"}.issubset(params)


def test_tune_hyperparameters_selects_by_validation_mae():
    X_train = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]})
    y_train = pd.Series([1.0, 2.0, 3.0, 4.0])
    X_val = pd.DataFrame({"x": [5.0, 6.0]})
    y_val = pd.Series([5.0, 6.0])
    search_space = {"n_estimators": [10, 50], "learning_rate": [0.3], "max_depth": [2],
                     "min_child_weight": [1], "subsample": [1.0], "colsample_bytree": [1.0]}
    best, results = tune_hyperparameters(X_train, y_train, X_val, y_val, search_space, random_seed=42)
    assert len(results) == 2
    assert results == sorted(results, key=lambda r: r["val_mae"])
    assert best["val_mae"] == results[0]["val_mae"]


# --- Evaluation metrics ------------------------------------------------------

def test_evaluate_predictions_reports_negative_prediction_count():
    y_true = pd.Series([10.0, 20.0, 30.0])
    y_pred = np.array([-5.0, 20.0, 25.0])
    result = evaluate_predictions(y_true, y_pred)
    assert result["n_negative_predictions"] == 1
    assert result["n_scored"] == 3
    assert result["mae"] == pytest.approx((15 + 0 + 5) / 3)


def test_evaluate_predictions_handles_null_targets_without_fabrication():
    y_true = pd.Series([10.0, np.nan, 30.0])
    y_pred = np.array([9.0, 999.0, 29.0])
    result = evaluate_predictions(y_true, y_pred)
    assert result["n_total"] == 3
    assert result["n_scored"] == 2


# --- Save / reload consistency (Section 26.2) -------------------------------

def test_save_and_reload_model_produces_identical_predictions(tmp_path):
    import xgboost as xgb

    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [4.0, 3.0, 2.0, 1.0]})
    y = pd.Series([10.0, 20.0, 30.0, 40.0])
    model = xgb.XGBRegressor(n_estimators=10, max_depth=2, random_state=42)
    model.fit(X, y)

    metadata = {"feature_columns": list(X.columns)}
    save_model(model, fit_vehicle_type_encoder(pd.DataFrame({CATEGORICAL_COLUMN: VEHICLE_CATEGORIES})), metadata, tmp_path)

    reloaded_model, reloaded_encoder, reloaded_metadata = load_model(tmp_path)
    np.testing.assert_array_almost_equal(model.predict(X), reloaded_model.predict(X))
    assert reloaded_metadata["feature_columns"] == list(X.columns)


def test_load_model_raises_on_feature_schema_mismatch(tmp_path):
    import xgboost as xgb

    X = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    y = pd.Series([1.0, 2.0])
    model = xgb.XGBRegressor(n_estimators=5, max_depth=2, random_state=42)
    model.fit(X, y)

    # Metadata claims a DIFFERENT feature schema than the model was actually trained on.
    bad_metadata = {"feature_columns": ["a", "b", "c_extra"]}
    save_model(model, fit_vehicle_type_encoder(pd.DataFrame({CATEGORICAL_COLUMN: VEHICLE_CATEGORIES})), bad_metadata, tmp_path)

    with pytest.raises(ValueError):
        load_model(tmp_path)


# --- Baseline comparison (identical computation) ----------------------------

def test_compare_against_baseline_computes_identically(tmp_path):
    baseline_csv = tmp_path / "baseline_predictions_v1.csv"
    pd.DataFrame({
        "district": ["A", "B", "C"],
        "vehicle_type": ["Motorcycle"] * 3,
        "year": [2022, 2022, 2022],
        "baseline_previous_period": [100.0, np.nan, 300.0],
    }).to_csv(baseline_csv, index=False)

    test_df = pd.DataFrame({
        "district": ["A", "B", "C"],
        "vehicle_type": ["Motorcycle"] * 3,
        "year": [2022, 2022, 2022],
        "target_value": [110.0, 210.0, 290.0],
    })
    xgb_predictions = np.array([105.0, 205.0, 295.0])

    result = compare_against_baseline(test_df, xgb_predictions, baseline_csv)
    assert result["xgboost_full_coverage"]["n_scored"] == 3
    assert result["n_matched_with_baseline"] == 2  # row B has no baseline prediction
    assert result["baseline_matched_subset"]["n_scored"] == 2
    assert result["xgboost_matched_subset"]["n_scored"] == 2
    assert result["baseline_matched_subset"]["mae"] == pytest.approx((10 + 10) / 2)


# --- Full pipeline integration (small search space for speed) --------------

@pytest.fixture(scope="module")
def small_model_params(tmp_path_factory) -> Path:
    """A tiny 1-combination search space so the full run() pipeline can be
    exercised end-to-end in tests without paying for the real 972-combination
    grid search (which the module-level run() performs by design against the
    real configs/model_params.yaml - already exercised manually, not repeated
    here for speed)."""
    path = tmp_path_factory.mktemp("config") / "model_params.yaml"
    path.write_text(
        "random_seed: 42\n"
        "baseline:\n  moving_average_window: 3\n"
        "xgboost:\n"
        "  tuning_search_space:\n"
        "    n_estimators: [50]\n"
        "    learning_rate: [0.1]\n"
        "    max_depth: [3]\n"
        "    min_child_weight: [1]\n"
        "    subsample: [0.8]\n"
        "    colsample_bytree: [0.8]\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="module")
def run_result(assembled_df, baselined_df, small_model_params, split_config, tmp_path_factory):
    frozen_csv = tmp_path_factory.mktemp("data") / "modelling_dataset_v1.csv"
    assembled_df.to_csv(frozen_csv, index=False)
    baseline_csv = tmp_path_factory.mktemp("baseline") / "baseline_predictions_v1.csv"
    baselined_df.to_csv(baseline_csv, index=False)
    models_dir = tmp_path_factory.mktemp("models")

    from src.features.build_features import FEATURE_LIST_YAML

    return run(
        frozen_csv=frozen_csv,
        feature_list_path=FEATURE_LIST_YAML,
        model_params_path=small_model_params,
        split_config_path=SPLIT_CONFIG_YAML,
        baseline_predictions_csv=baseline_csv,
        models_dir=models_dir,
        mlruns_dir=tmp_path_factory.mktemp("mlruns"),
    ), models_dir


def test_run_produces_complete_metadata(run_result):
    metadata, _ = run_result
    required_keys = {
        "dataset_version", "feature_columns", "active_numeric_features", "excluded_all_null_features",
        "selected_hyperparameters", "validation_metrics_at_selection", "test_metrics", "baseline_comparison",
        "random_seed", "train_rows", "validation_rows", "test_rows",
    }
    assert required_keys.issubset(metadata.keys())
    assert metadata["excluded_all_null_features"] == [
        "population", "population_density", "quarter", "month_sin", "month_cos", "vehicles_per_1000_people",
    ]
    assert metadata["random_seed"] == 42


def test_run_saves_a_reloadable_model(run_result):
    _, models_dir = run_result
    model, encoder, metadata = load_model(models_dir)
    assert list(model.get_booster().feature_names) == metadata["feature_columns"]


def test_run_test_metrics_have_full_coverage(run_result):
    """Unlike the DEV-007 baselines (which have coverage gaps from missing
    lag history), XGBoost predicts every test row - n_scored == n_total."""
    metadata, _ = run_result
    assert metadata["test_metrics"]["n_scored"] == metadata["test_metrics"]["n_total"]
