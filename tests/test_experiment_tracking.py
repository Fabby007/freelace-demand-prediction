"""DEV-014 / DEV-015 tests for src/evaluation/experiment_tracking.py.

Covers DEV-014's Testing Requirements ("test that an MLflow/W&B run log
exists for every completed training run") and Error Case ("experiment-
tracking backend unavailable at run time - training must not silently
proceed unlogged").
"""
from pathlib import Path
from unittest.mock import patch

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pytest

from src.evaluation.experiment_tracking import (
    TRACKED_VIA_FALLBACK,
    TRACKED_VIA_MLFLOW,
    _flatten,
    log_run,
)


def test_flatten_handles_nested_dicts_and_lists():
    flat = _flatten({"a": 1, "b": {"x": 2, "y": [3, 4]}, "c": "text"})
    assert flat == {"a": 1, "b.x": 2, "b.y": "[3, 4]", "c": "text"}


def test_log_run_via_real_mlflow_returns_run_id(tmp_path):
    record = log_run(
        run_name="test_run_real",
        params={"seed": 42, "nested": {"a": 1}},
        metrics={"mae": 1.5, "unused_none": None},
        tags={"model_type": "test"},
        mlruns_dir=tmp_path / "mlruns",
    )
    assert record["tracked_via"] == TRACKED_VIA_MLFLOW
    assert record["mlflow_run_id"]
    assert record["metrics"] == {"mae": 1.5}  # None metrics dropped, never logged as 0/fabricated


def test_log_run_logs_artifacts_that_exist_and_skips_missing_ones(tmp_path):
    existing = tmp_path / "exists.json"
    existing.write_text("{}", encoding="utf-8")
    missing = tmp_path / "does_not_exist.json"

    record = log_run(
        run_name="test_run_artifacts",
        params={"a": 1}, metrics={"mae": 1.0}, tags={},
        artifact_paths=[existing, missing],
        mlruns_dir=tmp_path / "mlruns",
    )
    assert record["tracked_via"] == TRACKED_VIA_MLFLOW  # missing artifact must not fail the whole run


def test_log_run_falls_back_to_local_json_when_mlflow_unavailable(tmp_path):
    with patch("mlflow.set_tracking_uri", side_effect=RuntimeError("backend unavailable")):
        record = log_run(
            run_name="test_run_fallback",
            params={"a": 1}, metrics={"mae": 2.0}, tags={"model_type": "test"},
            mlruns_dir=tmp_path / "mlruns", fallback_log_dir=tmp_path / "fallback",
        )

    assert record["tracked_via"] == TRACKED_VIA_FALLBACK
    assert "mlflow_run_id" not in record
    fallback_path = Path(record["fallback_path"])
    assert fallback_path.exists()
    assert fallback_path.name == "test_run_fallback.json"


def test_log_run_never_raises_on_backend_failure(tmp_path):
    """Error Case: a tracking-backend failure must never crash the calling
    training script."""
    with patch("mlflow.start_run", side_effect=RuntimeError("simulated failure")):
        record = log_run(
            run_name="test_run_no_raise",
            params={}, metrics={}, mlruns_dir=tmp_path / "mlruns", fallback_log_dir=tmp_path / "fallback",
        )
    assert record["tracked_via"] == TRACKED_VIA_FALLBACK
