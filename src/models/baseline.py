"""Baseline Forecasting Model (DEV-007).

Implements the three canonical baselines from source doc Section 23.1 -
previous-period, moving-average, and simple linear regression "when
appropriate" - against the DEV-006 frozen modelling dataset and its
chronological train/validation/test split, so DEV-008/DEV-009 have a
concrete, honestly-evaluated bar to beat rather than an assumed one
(Section 14.2 step 2, Section 23.1).

All three baselines predict `target_value` (DEV-006: next-period
`new_registrations` for the same district x vehicle_type series) using only
information available strictly before the target period - the same
leakage rule enforced throughout DEV-005/DEV-006.

1. Previous-period ("naive"/persistence) baseline: predicted target_value at
   row t = target_value at the prior row in the same series (`shift(1)` on
   `target_value`, grouped by district x vehicle_type, sorted by year). By
   construction this equals the row's own current-period `new_registrations`
   (target_value(t-1) = new_registrations(t) - see DEV-006), i.e. "assume
   next period looks like this period" - the standard persistence forecast.

2. Moving-average baseline: reuses DEV-005's `rolling_mean_3` column
   directly wherever the configured window (`configs/model_params.yaml`,
   `baseline.moving_average_window`) matches the window it was computed
   with (3); if the config is ever changed to a different window, this
   module recomputes the rolling mean directly with the new window rather
   than silently reusing a mismatched column.

3. Simple linear regression ("linear trend") baseline: per (district,
   vehicle_type) series, fits a degree-1 polynomial of `new_registrations`
   vs. `year` using ONLY that series' rows in the `train` split, then
   extrapolates the fitted line to each row's `target_year` to produce a
   prediction. A series needs at least 2 distinct training-period years
   with a non-null `new_registrations` value to fit a line at all; series
   below that threshold get a null prediction, never a fabricated one
   (DEV-007 Error Case). See the module-level `LINEAR_TREND_APPROPRIATENESS_NOTE`
   REF-009 ADR-010 for why this baseline is real but statistically weak on
   this dataset: with only 2 candidate training years per series,
   45/75 (60%) series have exactly a 2-point line (zero residual degrees of
   freedom - a naive trend extrapolation, not a fitted model with genuine
   statistical support), and 30/75 (40%) cannot be fit at all and are
   honestly null.

Metrics (MAE, RMSE, R^2 - Section 23.2) are computed separately on the
`validation` and `test` splits for each baseline, over only the rows where
both `target_value` and that baseline's prediction are non-null (scored-row
coverage is recorded alongside every metric, never silently assumed to be
100%).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

from src.evaluation.experiment_tracking import MLRUNS_DIR as DEFAULT_MLRUNS_DIR, log_run

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REPORTS_DIR = REPO_ROOT / "reports"

FROZEN_CSV = PROCESSED_DIR / "modelling_dataset_v1.csv"
SPLIT_CONFIG_YAML = CONFIGS_DIR / "split_config.yaml"
MODEL_PARAMS_YAML = CONFIGS_DIR / "model_params.yaml"

PREDICTIONS_CSV = PROCESSED_DIR / "baseline_predictions_v1.csv"
METRICS_JSON = REPORTS_DIR / "baseline_metrics.json"

GROUP_KEYS = ["district", "vehicle_type"]

# The window DEV-005's rolling_mean_3 column was computed with - see
# src/features/build_features.py. Must match configs/model_params.yaml's
# baseline.moving_average_window for the "reuse rolling_mean_3" fast path.
ROLLING_MEAN_3_WINDOW = 3

BASELINE_COLUMNS = [
    "baseline_previous_period",
    "baseline_moving_average",
    "baseline_linear_trend",
]

IDENTIFIER_COLUMNS = ["district", "vehicle_type", "year", "target_year", "split"]
CARRY_FORWARD_COLUMNS = ["target_value", "target_data_quality_flag"]


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def add_previous_period_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """FR1: predicted target_value(t) = target_value(t-1) within each
    (district, vehicle_type) series, sorted by year. No leakage: only ever
    reads a strictly earlier row's already-realized target."""
    df = df.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
    df["baseline_previous_period"] = df.groupby(GROUP_KEYS, sort=False)["target_value"].shift(1)
    return df


def add_moving_average_baseline(df: pd.DataFrame, moving_average_window: int) -> pd.DataFrame:
    """FR2: reuse DEV-005's `rolling_mean_3` column directly when the
    configured window matches how it was computed (3); otherwise recompute
    a fresh backward-only rolling mean with the configured window so the
    baseline never silently reuses a mismatched column."""
    if moving_average_window == ROLLING_MEAN_3_WINDOW:
        df["baseline_moving_average"] = df["rolling_mean_3"]
    else:
        logger.warning(
            "configs/model_params.yaml baseline.moving_average_window=%d differs "
            "from the window rolling_mean_3 was computed with (%d) - recomputing "
            "the moving-average baseline directly instead of reusing rolling_mean_3.",
            moving_average_window, ROLLING_MEAN_3_WINDOW,
        )
        df = df.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
        grouped = df.groupby(GROUP_KEYS, sort=False)["new_registrations"]
        df["baseline_moving_average"] = grouped.transform(
            lambda s: s.shift(1).rolling(window=moving_average_window, min_periods=1).mean()
        )
    return df


def add_linear_trend_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """FR3: per (district, vehicle_type) series, fit new_registrations ~ year
    on that series' `train`-split rows only, then extrapolate to each row's
    target_year. Left null (never fabricated) where a series has fewer than
    2 distinct non-null training-period years - see module docstring."""
    df["baseline_linear_trend"] = np.nan

    for _, group in df.groupby(GROUP_KEYS, sort=False):
        train_points = group[(group["split"] == "train") & group["new_registrations"].notna()]
        if train_points["year"].nunique() < 2:
            continue

        slope, intercept = np.polyfit(train_points["year"], train_points["new_registrations"], deg=1)

        predictable = group[group["target_year"].notna()]
        predicted = slope * predictable["target_year"].astype(float) + intercept
        df.loc[predictable.index, "baseline_linear_trend"] = predicted

    return df


def add_baseline_predictions(df: pd.DataFrame, model_params: dict) -> pd.DataFrame:
    df = add_previous_period_baseline(df)
    df = add_moving_average_baseline(df, model_params["baseline"]["moving_average_window"])
    df = add_linear_trend_baseline(df)
    return df


def evaluate_baselines(df: pd.DataFrame) -> dict:
    """Section 23.2 metrics (MAE, RMSE, R^2), computed separately on the
    `validation` and `test` splits for each baseline. Scored only over rows
    where both target_value and the baseline's prediction are non-null;
    n_total vs. n_scored is always recorded so coverage gaps are visible,
    never silently assumed away."""
    results: dict = {}
    for split_name in ("validation", "test"):
        split_df = df[df["split"] == split_name]
        results[split_name] = {}
        for baseline_col in BASELINE_COLUMNS:
            scored = split_df.dropna(subset=["target_value", baseline_col])
            n_total, n_scored = len(split_df), len(scored)

            if n_scored == 0:
                results[split_name][baseline_col] = {
                    "n_total": n_total, "n_scored": 0, "mae": None, "rmse": None, "r2": None,
                    "n_negative_predictions": 0,
                }
                continue

            y_true, y_pred = scored["target_value"], scored[baseline_col]
            results[split_name][baseline_col] = {
                "n_total": n_total,
                "n_scored": n_scored,
                "mae": float(mean_absolute_error(y_true, y_pred)),
                "rmse": float(root_mean_squared_error(y_true, y_pred)),
                # R^2 needs >=2 scored points to be defined.
                "r2": float(r2_score(y_true, y_pred)) if n_scored >= 2 else None,
                # new_registrations/target_value is a non-negative count; a naive
                # baseline (esp. unconstrained linear extrapolation) can still
                # predict below zero - recorded honestly, never clipped/hidden,
                # since it is itself informative about that baseline's fitness
                # (REF-009 ADR-010).
                "n_negative_predictions": int((y_pred < 0).sum()),
            }
    return results


def run(
    frozen_csv: Path = FROZEN_CSV,
    model_params_path: Path = MODEL_PARAMS_YAML,
    split_config_path: Path = SPLIT_CONFIG_YAML,
    predictions_csv: Path = PREDICTIONS_CSV,
    metrics_json: Path = METRICS_JSON,
    mlruns_dir: Path = DEFAULT_MLRUNS_DIR,
) -> dict:
    logging.basicConfig(level=logging.INFO)

    df = pd.read_csv(frozen_csv)
    model_params = _read_yaml(model_params_path)
    df = add_baseline_predictions(df, model_params)

    metrics = evaluate_baselines(df)

    predictions_csv.parent.mkdir(parents=True, exist_ok=True)
    df[IDENTIFIER_COLUMNS + CARRY_FORWARD_COLUMNS + BASELINE_COLUMNS].to_csv(predictions_csv, index=False)

    split_config = _read_yaml(split_config_path)
    report = {
        "dataset_version": split_config.get("dataset_version"),
        "generated_date": date.today().isoformat(),
        "moving_average_window": model_params["baseline"]["moving_average_window"],
        "metrics": metrics,
    }
    metrics_json.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Wrote baseline predictions to %s and metrics to %s", predictions_csv, metrics_json)

    # Section 24 experiment tracking (DEV-014) - one run covering all three
    # baselines, since they are a single deterministic (non-tuned) step.
    flat_metrics = {
        f"{split_name}_{baseline_col}_{metric_name}": value
        for split_name, baseline_metrics in metrics.items()
        for baseline_col, entry in baseline_metrics.items()
        for metric_name, value in entry.items()
        if metric_name != "n_total"  # n_total is constant across baselines within a split - redundant as a metric
    }
    log_run(
        run_name="baselines",
        params={
            "moving_average_window": model_params["baseline"]["moving_average_window"],
            "random_seed": model_params["random_seed"],
            "dataset_version": report["dataset_version"],
        },
        metrics=flat_metrics,
        tags={"model_type": "baseline", "dataset_version": str(report["dataset_version"])},
        artifact_paths=[predictions_csv, metrics_json],
        mlruns_dir=mlruns_dir,
    )

    return report


if __name__ == "__main__":
    run()
