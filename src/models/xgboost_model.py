"""XGBoost Primary Prediction Model (DEV-008).

Trains, tunes, selects, and persists the primary tabular prediction model
against the DEV-006 frozen modelling dataset and its exact chronological
train/validation/test split (source doc Section 14, Section 14.2's 6-step
approach - steps 1-2 already done in DEV-006/DEV-007, this module does
steps 3-6).

Feature set (Section 14.1, config-driven via configs/feature_list.yaml, never
hardcoded inline): every `base_columns` and `engineered_columns` entry, plus
one-hot-encoded `vehicle_type` (REF-002 canonical categories: Motorcycle,
Car, Three-wheeler - a single combined model across vehicle types, per
DEV-005's default). Numeric feature columns that are 100% null across every
labeled (train/validation/test) row - currently `population`,
`population_density`, `quarter`, `month_sin`, `month_cos`,
`vehicles_per_1000_people`, all null for the same acquisition-gap/yearly-only
reasons documented in DEV-005/REF-001 - are automatically excluded from the
actual training matrix and recorded as `excluded_all_null_features` in the
saved metadata (see REF-009 ADR-011): passing a column with zero real values
into "the exact feature list" a model registry cites would misrepresent what
the model actually learned from. XGBoost's native missing-value handling
(no imputation - consistent with REF-009 ADR-005) is used for every
partially-null numeric feature that IS kept.

Tuning (FR4): a full grid search over configs/model_params.yaml's
`xgboost.tuning_search_space` (972 combinations), fit on `train` rows only,
scored on `validation` rows only by MAE (REF-009 ADR-011 - MAE chosen as the
selection metric since RMSE is dominated by the extreme outlier districts
described in REF-006 Section 5.2). The test period is never touched during
this search (Business Rule / Hard Rule).

Final model (FR5): the best-by-validation-MAE hyperparameters are refit on
train+validation combined (REF-009 ADR-011) before the single, final
evaluation on the untouched test period - maximizing use of an already very
small dataset for the production model while keeping test-period evaluation
genuinely one-shot.

Persistence (FR6): `models/xgboost_v1/model.json` (native XGBoost format),
`models/xgboost_v1/onehot_encoder.joblib` (the fitted vehicle_type
preprocessing object), `models/xgboost_v1/metadata.json` (exact feature
column list and order, dataset_version, hyperparameters, random seed,
validation/test metrics, DEV-007 baseline comparison).
"""
from __future__ import annotations

import itertools
import json
import logging
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import yaml
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.preprocessing import OneHotEncoder

from src.evaluation.experiment_tracking import MLRUNS_DIR as DEFAULT_MLRUNS_DIR, log_run

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR = REPO_ROOT / "models" / "xgboost_v1"

FROZEN_CSV = PROCESSED_DIR / "modelling_dataset_v1.csv"
FEATURE_LIST_YAML = CONFIGS_DIR / "feature_list.yaml"
MODEL_PARAMS_YAML = CONFIGS_DIR / "model_params.yaml"
SPLIT_CONFIG_YAML = CONFIGS_DIR / "split_config.yaml"
BASELINE_PREDICTIONS_CSV = PROCESSED_DIR / "baseline_predictions_v1.csv"

MODEL_JSON = MODELS_DIR / "model.json"
ENCODER_JOBLIB = MODELS_DIR / "onehot_encoder.joblib"
METADATA_JSON = MODELS_DIR / "metadata.json"

# REF-002 canonical vehicle-category labels - fixed so the one-hot column set
# never depends on which categories happen to appear in a given split.
VEHICLE_CATEGORIES = ["Motorcycle", "Car", "Three-wheeler"]

TARGET_COLUMN = "target_value"
CATEGORICAL_COLUMN = "vehicle_type"

# Validation metric used to select hyperparameters (REF-009 ADR-011).
SELECTION_METRIC = "val_mae"

# Best single DEV-007 baseline (see REF-006 Section 5.2 / DEV-007 results) -
# used as the head-to-head comparison baseline (FR: honest comparison).
COMPARISON_BASELINE_COLUMN = "baseline_previous_period"

TOP_N_TUNING_RESULTS_PERSISTED = 10


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def candidate_numeric_features(feature_list_config: dict) -> list[str]:
    """Section 14.1 inputs, read from configs/feature_list.yaml (never
    hardcoded): base + engineered columns. Excludes identifier, provenance,
    data-quality, and target columns - those are not model predictors."""
    return list(feature_list_config["base_columns"]) + list(feature_list_config["engineered_columns"])


def drop_all_null_features(df: pd.DataFrame, numeric_features: list[str], labeled_mask: pd.Series) -> tuple[list[str], list[str]]:
    """Splits candidate numeric features into (active, excluded) based on
    whether each has at least one non-null value across every labeled
    (train/validation/test) row - see module docstring."""
    active, excluded = [], []
    for col in numeric_features:
        if df.loc[labeled_mask, col].notna().any():
            active.append(col)
        else:
            excluded.append(col)
    return active, excluded


def fit_vehicle_type_encoder(train_df: pd.DataFrame) -> OneHotEncoder:
    encoder = OneHotEncoder(categories=[VEHICLE_CATEGORIES], handle_unknown="ignore", sparse_output=False)
    encoder.fit(train_df[[CATEGORICAL_COLUMN]])
    return encoder


def build_feature_matrix(df: pd.DataFrame, numeric_features: list[str], encoder: OneHotEncoder) -> pd.DataFrame:
    """Assembles X in a fixed column order: numeric_features (config order),
    then one-hot vehicle_type columns (VEHICLE_CATEGORIES order) - this exact
    order is what gets persisted to metadata.json as `feature_columns`."""
    X_numeric = df[numeric_features].astype(float).reset_index(drop=True)
    encoded = encoder.transform(df[[CATEGORICAL_COLUMN]])
    encoded_cols = [f"{CATEGORICAL_COLUMN}_{c}" for c in encoder.categories_[0]]
    X_categorical = pd.DataFrame(encoded, columns=encoded_cols).reset_index(drop=True)
    return pd.concat([X_numeric, X_categorical], axis=1)


def evaluate_predictions(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    """Section 23.2 metrics (MAE, RMSE, R^2) plus coverage and an impossible-
    value check (Section 26.2: 'predictions checked for impossible values
    when the target is non-negative') - mirrors src/models/baseline.py's
    evaluate_baselines() so XGBoost and baseline metrics are computed
    identically (DEV-007/DEV-008 Testing Requirements)."""
    y_true = pd.Series(y_true).reset_index(drop=True)
    y_pred = pd.Series(np.asarray(y_pred)).reset_index(drop=True)
    n_total = len(y_true)
    mask = y_true.notna()
    n_scored = int(mask.sum())

    if n_scored == 0:
        return {"n_total": n_total, "n_scored": 0, "mae": None, "rmse": None, "r2": None, "n_negative_predictions": 0}

    y_true_s, y_pred_s = y_true[mask], y_pred[mask]
    return {
        "n_total": n_total,
        "n_scored": n_scored,
        "mae": float(mean_absolute_error(y_true_s, y_pred_s)),
        "rmse": float(root_mean_squared_error(y_true_s, y_pred_s)),
        "r2": float(r2_score(y_true_s, y_pred_s)) if n_scored >= 2 else None,
        "n_negative_predictions": int((y_pred_s < 0).sum()),
    }


def tune_hyperparameters(
    X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
    search_space: dict, random_seed: int,
) -> tuple[dict, list[dict]]:
    """FR4: full grid search over the configured search space, fit on train
    only, scored on validation only by MAE. The test period never appears in
    this function's arguments at all - structurally impossible to leak into
    tuning (Business Rule)."""
    keys = list(search_space.keys())
    combos = list(itertools.product(*[search_space[k] for k in keys]))
    logger.info("Tuning XGBoost over %d hyperparameter combinations (train=%d, validation=%d rows)",
                len(combos), len(X_train), len(X_val))

    results = []
    for combo in combos:
        params = dict(zip(keys, combo))
        model = xgb.XGBRegressor(
            **params, random_state=random_seed, objective="reg:squarederror", n_jobs=-1,
        )
        model.fit(X_train, y_train)
        preds = model.predict(X_val)
        val_metrics = evaluate_predictions(y_val, preds)
        results.append({"params": params, "val_mae": val_metrics["mae"], "val_rmse": val_metrics["rmse"], "val_r2": val_metrics["r2"]})

    results.sort(key=lambda entry: entry[SELECTION_METRIC])
    best = results[0]

    # Error Case: a degenerate best model (identical predictions for every
    # validation row) must be flagged, not silently accepted.
    if best["val_rmse"] is not None and best["val_mae"] is not None and best["val_rmse"] == 0 and best["val_mae"] == 0:
        logger.warning("Best-by-validation-MAE XGBoost configuration produced a degenerate (zero-error) "
                        "fit on validation - investigate before trusting this result: %s", best["params"])

    return best, results


def compare_against_baseline(
    test_df: pd.DataFrame, xgb_test_predictions: np.ndarray, baseline_predictions_csv: Path = BASELINE_PREDICTIONS_CSV,
) -> dict:
    """Honest head-to-head comparison against DEV-007's strongest baseline
    (`baseline_previous_period`, see REF-006 Section 5.2). Because the
    baseline has coverage gaps (some test rows have no baseline prediction -
    see DEV-007), this reports XGBoost's metrics twice: on the FULL test set
    (`xgboost_full_coverage`) and on exactly the subset of rows the baseline
    could also score (`xgboost_matched_subset` vs. `baseline_matched_subset`)
    - the matched-subset pair is the only truly apples-to-apples comparison
    (DEV-008 Testing Requirements: "both computed identically")."""
    baseline_df = pd.read_csv(baseline_predictions_csv)

    merged = test_df[["district", "vehicle_type", "year", TARGET_COLUMN]].reset_index(drop=True).copy()
    merged["xgboost_prediction"] = xgb_test_predictions
    merged = merged.merge(
        baseline_df[["district", "vehicle_type", "year", COMPARISON_BASELINE_COLUMN]],
        on=["district", "vehicle_type", "year"], how="left",
    )

    full_coverage = evaluate_predictions(merged[TARGET_COLUMN], merged["xgboost_prediction"])

    matched = merged.dropna(subset=[TARGET_COLUMN, COMPARISON_BASELINE_COLUMN, "xgboost_prediction"])
    return {
        "xgboost_full_coverage": full_coverage,
        "n_matched_with_baseline": len(matched),
        "xgboost_matched_subset": evaluate_predictions(matched[TARGET_COLUMN], matched["xgboost_prediction"]),
        "baseline_matched_subset": evaluate_predictions(matched[TARGET_COLUMN], matched[COMPARISON_BASELINE_COLUMN]),
    }


def save_model(model: xgb.XGBRegressor, encoder: OneHotEncoder, metadata: dict, models_dir: Path = MODELS_DIR) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    model.get_booster().save_model(str(models_dir / "model.json"))
    joblib.dump(encoder, models_dir / "onehot_encoder.joblib")
    with open(models_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def load_model(models_dir: Path = MODELS_DIR) -> tuple[xgb.XGBRegressor, OneHotEncoder, dict]:
    """Error Case: raises (blocking, not a warning) if the reloaded model's
    feature schema does not match its own recorded metadata."""
    with open(models_dir / "metadata.json", encoding="utf-8") as f:
        metadata = json.load(f)

    model = xgb.XGBRegressor()
    model.load_model(str(models_dir / "model.json"))
    encoder = joblib.load(models_dir / "onehot_encoder.joblib")

    reloaded_features = list(model.get_booster().feature_names or [])
    expected_features = metadata["feature_columns"]
    if reloaded_features and reloaded_features != expected_features:
        raise ValueError(
            f"Reloaded XGBoost model's feature schema does not match its own metadata.json: "
            f"model has {reloaded_features}, metadata expects {expected_features}."
        )
    return model, encoder, metadata


def run(
    frozen_csv: Path = FROZEN_CSV,
    feature_list_path: Path = FEATURE_LIST_YAML,
    model_params_path: Path = MODEL_PARAMS_YAML,
    split_config_path: Path = SPLIT_CONFIG_YAML,
    baseline_predictions_csv: Path = BASELINE_PREDICTIONS_CSV,
    models_dir: Path = MODELS_DIR,
    mlruns_dir: Path = DEFAULT_MLRUNS_DIR,
) -> dict:
    logging.basicConfig(level=logging.INFO)

    df = pd.read_csv(frozen_csv)
    feature_list_config = _read_yaml(feature_list_path)
    model_params = _read_yaml(model_params_path)
    split_config = _read_yaml(split_config_path)

    numeric_candidates = candidate_numeric_features(feature_list_config)
    labeled_mask = df["split"].isin(["train", "validation", "test"])
    active_numeric, excluded_all_null = drop_all_null_features(df, numeric_candidates, labeled_mask)
    if excluded_all_null:
        logger.info("Excluding all-null-in-labeled-data features from the model: %s", excluded_all_null)

    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df = df[df["split"] == "validation"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    encoder = fit_vehicle_type_encoder(train_df)
    X_train = build_feature_matrix(train_df, active_numeric, encoder)
    X_val = build_feature_matrix(val_df, active_numeric, encoder)
    X_test = build_feature_matrix(test_df, active_numeric, encoder)
    feature_columns = list(X_train.columns)

    y_train, y_val, y_test = train_df[TARGET_COLUMN], val_df[TARGET_COLUMN], test_df[TARGET_COLUMN]

    random_seed = model_params["random_seed"]
    search_space = model_params["xgboost"]["tuning_search_space"]
    best, tuning_results = tune_hyperparameters(X_train, y_train, X_val, y_val, search_space, random_seed)

    # Refit on train+validation with the selected hyperparameters (REF-009
    # ADR-011), then evaluate exactly once on the untouched test period.
    X_trainval = pd.concat([X_train, X_val], ignore_index=True)
    y_trainval = pd.concat([y_train, y_val], ignore_index=True).reset_index(drop=True)

    final_model = xgb.XGBRegressor(
        **best["params"], random_state=random_seed, objective="reg:squarederror", n_jobs=-1,
    )
    final_model.fit(X_trainval, y_trainval)

    test_predictions = final_model.predict(X_test)
    test_metrics = evaluate_predictions(y_test, test_predictions)
    baseline_comparison = compare_against_baseline(test_df, test_predictions, baseline_predictions_csv)

    metadata = {
        "dataset_version": split_config.get("dataset_version"),
        "generated_date": date.today().isoformat(),
        "random_seed": random_seed,
        "feature_columns": feature_columns,
        "active_numeric_features": active_numeric,
        "excluded_all_null_features": excluded_all_null,
        "categorical_feature": CATEGORICAL_COLUMN,
        "categorical_categories": VEHICLE_CATEGORIES,
        "target_column": TARGET_COLUMN,
        "train_rows": len(X_train),
        "validation_rows": len(X_val),
        "test_rows": len(X_test),
        "selection_metric": SELECTION_METRIC,
        "tuning_search_space": search_space,
        "n_tuning_combinations_evaluated": len(tuning_results),
        "selected_hyperparameters": best["params"],
        "top_tuning_results": tuning_results[:TOP_N_TUNING_RESULTS_PERSISTED],
        "validation_metrics_at_selection": {"mae": best["val_mae"], "rmse": best["val_rmse"], "r2": best["val_r2"]},
        "test_metrics": test_metrics,
        "baseline_comparison": baseline_comparison,
        "refit_on_train_plus_validation": True,
    }

    save_model(final_model, encoder, metadata, models_dir)
    logger.info(
        "XGBoost trained: selected params %s, test MAE=%.2f (baseline_previous_period matched-subset MAE=%s), saved to %s",
        best["params"], test_metrics["mae"],
        baseline_comparison["baseline_matched_subset"]["mae"], models_dir,
    )

    # Section 24 experiment tracking (DEV-014).
    log_run(
        run_name="xgboost_v1",
        params={
            **best["params"],
            "random_seed": random_seed,
            "selection_metric": SELECTION_METRIC,
            "n_tuning_combinations_evaluated": len(tuning_results),
            "dataset_version": metadata["dataset_version"],
            "feature_columns": feature_columns,
            "excluded_all_null_features": excluded_all_null,
        },
        metrics={
            "validation_mae": best["val_mae"], "validation_rmse": best["val_rmse"], "validation_r2": best["val_r2"],
            "test_mae": test_metrics["mae"], "test_rmse": test_metrics["rmse"], "test_r2": test_metrics["r2"],
            "test_n_negative_predictions": test_metrics["n_negative_predictions"],
            "baseline_matched_subset_mae": baseline_comparison["baseline_matched_subset"]["mae"],
            "xgboost_matched_subset_mae": baseline_comparison["xgboost_matched_subset"]["mae"],
        },
        tags={"model_type": "xgboost", "dataset_version": str(metadata["dataset_version"])},
        artifact_paths=[models_dir / "model.json", models_dir / "onehot_encoder.joblib", models_dir / "metadata.json"],
        mlruns_dir=mlruns_dir,
    )

    return metadata


if __name__ == "__main__":
    run()
