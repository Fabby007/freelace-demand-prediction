"""DEV-014 / DEV-015 tests for src/evaluation/model_evaluation.py.

Covers DEV-014's Testing Requirements (metric-computation correctness
against a hand-computed sample) and Acceptance Criteria (regression +
ranking metrics computed identically/correctly, LSTM stated plainly, known
limitations disclosed, no re-tuning against the test set, split untouched).
"""
import shutil
from pathlib import Path
from unittest.mock import patch

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.models.xgboost_model import MODELS_DIR, VEHICLE_CATEGORIES
from src.evaluation.model_evaluation import (
    KNOWN_LIMITATIONS,
    build_markdown_report,
    build_regression_comparison_table,
    compute_ranking_metrics,
    compute_test_predictions,
    run,
)

pytestmark = pytest.mark.skipif(
    not (MODELS_DIR / "model.json").exists(), reason="DEV-008 saved model not present locally"
)


# --- Ranking metrics: hand-computed correctness -----------------------------

def test_ranking_metrics_hand_computed_perfect_correlation():
    """A perfectly-ordered prediction (predicted rank == actual rank) must
    give Spearman rho = 1.0 and top-k overlap = 1.0."""
    df = pd.DataFrame({
        "vehicle_type": ["Motorcycle"] * 5,
        "district": ["A", "B", "C", "D", "E"],
        "target_value": [10.0, 20.0, 30.0, 40.0, 50.0],
        "xgb_predicted_value": [11.0, 22.0, 33.0, 44.0, 55.0],  # same order, different scale
    })
    result = compute_ranking_metrics(df, top_k=3)
    assert result["Motorcycle"]["spearman_r"] == pytest.approx(1.0)
    assert result["Motorcycle"]["top_k_overlap"] == pytest.approx(1.0)
    assert result["Motorcycle"]["n_scored"] == 5


def test_ranking_metrics_hand_computed_perfect_anti_correlation():
    df = pd.DataFrame({
        "vehicle_type": ["Car"] * 4,
        "district": ["A", "B", "C", "D"],
        "target_value": [10.0, 20.0, 30.0, 40.0],
        "xgb_predicted_value": [40.0, 30.0, 20.0, 10.0],
    })
    result = compute_ranking_metrics(df, top_k=2)
    assert result["Car"]["spearman_r"] == pytest.approx(-1.0)
    assert result["Car"]["top_k_overlap"] == pytest.approx(0.0)  # top-2 actual = {C,D}, top-2 predicted = {A,B}


def test_ranking_metrics_top_k_overlap_hand_computed_partial():
    df = pd.DataFrame({
        "vehicle_type": ["Three-wheeler"] * 4,
        "district": ["A", "B", "C", "D"],
        "target_value": [10.0, 20.0, 30.0, 40.0],  # actual top-2 = {D, C}
        "xgb_predicted_value": [5.0, 40.0, 10.0, 35.0],  # predicted top-2 = {B, D}
    })
    result = compute_ranking_metrics(df, top_k=2)
    assert result["Three-wheeler"]["top_k_overlap"] == pytest.approx(0.5)  # {D} in common / k=2


def test_ranking_metrics_returns_none_not_fabricated_for_too_few_rows():
    """Error/Edge Case: fewer than 2 scored rows can't support a
    correlation - must be None, never a fabricated 0.0 or 1.0."""
    df = pd.DataFrame({
        "vehicle_type": ["Car"], "district": ["A"],
        "target_value": [10.0], "xgb_predicted_value": [12.0],
    })
    result = compute_ranking_metrics(df, top_k=3)
    assert result["Car"]["spearman_r"] is None
    assert result["Car"]["top_k_overlap"] is None


def test_ranking_metrics_excludes_null_target_rows():
    df = pd.DataFrame({
        "vehicle_type": ["Motorcycle"] * 4,
        "district": ["A", "B", "C", "D"],
        "target_value": [10.0, 20.0, None, None],
        "xgb_predicted_value": [11.0, 22.0, 33.0, 44.0],
    })
    result = compute_ranking_metrics(df, top_k=3)
    assert result["Motorcycle"]["n_scored"] == 2


def test_ranking_metrics_covers_all_vehicle_categories_even_if_absent():
    df = pd.DataFrame({
        "vehicle_type": ["Motorcycle", "Motorcycle"], "district": ["A", "B"],
        "target_value": [10.0, 20.0], "xgb_predicted_value": [11.0, 22.0],
    })
    result = compute_ranking_metrics(df, top_k=3)
    assert set(result.keys()) == set(VEHICLE_CATEGORIES)
    assert result["Car"]["n_scored"] == 0
    assert result["Car"]["spearman_r"] is None


# --- Regression comparison table: identical schema across models -----------

def test_regression_comparison_table_uses_identical_schema_across_models():
    baseline_metrics = {
        "metrics": {
            "validation": {"baseline_previous_period": {"n_total": 49, "n_scored": 43, "mae": 130.8, "rmse": 442.6, "r2": -1.4, "n_negative_predictions": 0}},
            "test": {"baseline_previous_period": {"n_total": 47, "n_scored": 42, "mae": 230.5, "rmse": 555.8, "r2": 0.49, "n_negative_predictions": 0}},
        }
    }
    xgboost_metadata = {
        "validation_rows": 49,
        "validation_metrics_at_selection": {"mae": 125.2, "rmse": 218.5, "r2": 0.37},
        "test_metrics": {"n_total": 47, "n_scored": 47, "mae": 312.9, "rmse": 696.8, "r2": 0.14, "n_negative_predictions": 1},
        "baseline_comparison": {
            "xgboost_matched_subset": {"n_total": 42, "n_scored": 42, "mae": 306.4, "rmse": 710.0, "r2": 0.17, "n_negative_predictions": 1},
            "baseline_matched_subset": {"n_total": 42, "n_scored": 42, "mae": 230.5, "rmse": 555.8, "r2": 0.49, "n_negative_predictions": 0},
        },
    }
    rows = build_regression_comparison_table(baseline_metrics, xgboost_metadata)
    metric_keys = {"mae", "rmse", "r2", "n_total", "n_scored", "n_negative_predictions"}
    for row in rows:
        assert metric_keys.issubset(row.keys())


def test_regression_comparison_includes_matched_subset_rows_for_fair_comparison():
    baseline_metrics = {"metrics": {"validation": {}, "test": {}}}
    xgboost_metadata = {
        "validation_rows": 10,
        "validation_metrics_at_selection": {"mae": 1.0, "rmse": 1.0, "r2": 1.0},
        "test_metrics": {"n_total": 5, "n_scored": 5, "mae": 2.0, "rmse": 2.0, "r2": 0.5, "n_negative_predictions": 0},
        "baseline_comparison": {
            "xgboost_matched_subset": {"n_total": 4, "n_scored": 4, "mae": 3.0, "rmse": 3.0, "r2": 0.4, "n_negative_predictions": 0},
            "baseline_matched_subset": {"n_total": 4, "n_scored": 4, "mae": 4.0, "rmse": 4.0, "r2": 0.3, "n_negative_predictions": 0},
        },
    }
    rows = build_regression_comparison_table(baseline_metrics, xgboost_metadata)
    model_names = {r["model"] for r in rows}
    assert "xgboost_v1_matched_subset" in model_names
    assert "baseline_previous_period_matched_subset" in model_names


# --- Known limitations must be disclosed, not hidden ------------------------

def test_known_limitations_include_required_topics():
    joined = " ".join(KNOWN_LIMITATIONS).lower()
    assert "proxy" in joined  # Fallback-path target
    assert "collapse" in joined or "2020-2022" in joined  # regime shift
    assert "does not outperform" in joined or "outperform" in joined  # honest XGBoost-vs-baseline finding
    assert "lstm" in joined and "skip" in joined
    assert "negative predictions" in joined.replace("-", " ") or "negative" in joined


# --- Full run(): real artifacts, no re-tuning, split untouched -------------
#
# Every test below redirects models_dir/report paths/mlruns_dir to tmp_path -
# run() must never overwrite the real reports/model_evaluation.*,
# models/xgboost_v1/evaluation_report.*, or append entries to the real
# mlruns/ store as a side effect of running the test suite (a real bug found
# during the DEV-015 audit: these tests previously called run() with every
# default real path, silently mutating production artifacts and growing
# mlruns/ by one run per test invocation, indefinitely).

@pytest.fixture(scope="module")
def isolated_registry(tmp_path_factory) -> Path:
    """A tmp copy of the real models/xgboost_v1/ registry folder - read-only
    source data (model.json, onehot_encoder.joblib, metadata.json) copied so
    run()'s evaluation_report.* copy step never touches the real folder."""
    tmp_models_dir = tmp_path_factory.mktemp("models") / "xgboost_v1"
    shutil.copytree(MODELS_DIR, tmp_models_dir)
    return tmp_models_dir


def _run_isolated(isolated_registry, tmp_path_factory, **overrides) -> dict:
    tmp_dir = tmp_path_factory.mktemp("eval")
    kwargs = {
        "models_dir": isolated_registry,
        "report_json_path": tmp_dir / "model_evaluation.json",
        "report_md_path": tmp_dir / "model_evaluation.md",
        "mlruns_dir": tmp_dir / "mlruns",
    }
    kwargs.update(overrides)
    return run(**kwargs)


def test_run_does_not_call_tune_hyperparameters(isolated_registry, tmp_path_factory):
    """Business Rule: no repeated test-set peeking / re-tuning. Evaluation
    must only reload the already-saved model, never retrain it."""
    with patch("src.models.xgboost_model.tune_hyperparameters") as mock_tune:
        report = _run_isolated(isolated_registry, tmp_path_factory)
    mock_tune.assert_not_called()
    assert report["production_model_recommendation"] == "XGBoost"


def test_run_produces_complete_report_with_real_artifacts(isolated_registry, tmp_path_factory):
    report = _run_isolated(isolated_registry, tmp_path_factory)
    assert report["dataset_version"]
    assert report["random_seed"] == 42
    assert report["lstm"]["decision"] == "skip"
    assert set(report["ranking_metrics"].keys()) == set(VEHICLE_CATEGORIES)
    assert len(report["known_limitations"]) == len(KNOWN_LIMITATIONS)

    # Headline finding matches the real, previously-established result
    # (DEV-007/DEV-008) - baseline beats XGBoost on the matched subset.
    assert report["headline"]["baseline_test_mae"] < report["headline"]["xgboost_matched_subset_mae"]


def test_run_uses_the_real_dev006_split_sizes_unaltered(isolated_registry, tmp_path_factory):
    report = _run_isolated(isolated_registry, tmp_path_factory)
    test_rows = [r for r in report["regression_comparison"] if r["model"] == "xgboost_v1" and r["split"] == "test"]
    assert len(test_rows) == 1
    # n_total for the full-coverage XGBoost test row must equal the real
    # frozen dataset's test-split row count - proves the split was reused,
    # not re-derived or shrunk/altered for this report.
    df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "processed" / "modelling_dataset_v1.csv")
    real_test_count = int((df["split"] == "test").sum())
    assert test_rows[0]["n_total"] == real_test_count


def test_markdown_report_states_headline_finding_plainly(isolated_registry, tmp_path_factory):
    report = _run_isolated(isolated_registry, tmp_path_factory)
    markdown = build_markdown_report(report)
    assert "outperforms tuned XGBoost" in markdown or "does not outperform" in markdown.lower()
    assert "XGBoost" in markdown
    assert "## Known limitations" in markdown
    assert "## Reproducibility" in markdown


def test_evaluation_report_written_to_model_registry_folder(isolated_registry, tmp_path_factory):
    _run_isolated(isolated_registry, tmp_path_factory)
    assert (isolated_registry / "evaluation_report.json").exists()
    assert (isolated_registry / "evaluation_report.md").exists()
    # And the REAL registry folder must be untouched by this test run.
    real_evaluation_report = MODELS_DIR / "evaluation_report.json"
    if real_evaluation_report.exists():
        real_mtime_before = real_evaluation_report.stat().st_mtime
        _run_isolated(isolated_registry, tmp_path_factory)
        assert real_evaluation_report.stat().st_mtime == real_mtime_before
