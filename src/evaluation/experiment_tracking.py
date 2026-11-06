"""Experiment tracking helper (DEV-014, Section 24).

`src/evaluation/` is a new top-level module beyond Appendix B's original
folder list, introduced because DEV-014's own Backend Behavior explicitly
anticipates this ("a small src/evaluation/-style module if warranted") and
because evaluation/tracking is conceptually distinct from both `src/models/`
(training) and `src/explainability/` (SHAP) - see REF-009 ADR-023.

MLflow (not Weights & Biases) is used - REF-009 ADR-022: `requirements.txt`
has pinned `mlflow==2.13.0` since DEV-001 and REF-009 ADR-002/ADR-004 already
treat "the MLflow choice" as made; this module is where that choice is
finally given its own formal rationale, per DEV-014's explicit instruction
("log as an ADR if not already decided"). Tracking is local and file-based
(`mlruns/`, already gitignored) - no cloud account, API key, or network
dependency, keeping the whole pipeline reproducible offline.

Error Case (DEV-014): "Experiment-tracking backend unavailable at run time -
training must not silently proceed unlogged." `log_run()` catches any MLflow
failure and falls back to a local JSON log file under
`reports/experiment_tracking_fallback/`, tagging the run's `tracked_via` as
`"local_fallback"` rather than `"mlflow"` so a fallback run is never
presented as equally reproducible/queryable as a real MLflow run.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MLRUNS_DIR = REPO_ROOT / "mlruns"
FALLBACK_LOG_DIR = REPO_ROOT / "reports" / "experiment_tracking_fallback"

EXPERIMENT_NAME = "mechanic-demand-prediction"

TRACKED_VIA_MLFLOW = "mlflow"
TRACKED_VIA_FALLBACK = "local_fallback"


def _flatten(d: dict, prefix: str = "") -> dict:
    """MLflow params must be flat scalars - flattens nested dicts (e.g. a
    tuning search space) into dotted-key strings rather than dropping them."""
    flat: dict[str, Any] = {}
    for key, value in d.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{full_key}."))
        elif isinstance(value, (list, tuple)):
            flat[full_key] = str(value)
        else:
            flat[full_key] = value
    return flat


def log_run(
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float | None],
    tags: dict[str, str] | None = None,
    artifact_paths: list[Path] | None = None,
    mlruns_dir: Path = MLRUNS_DIR,
    fallback_log_dir: Path = FALLBACK_LOG_DIR,
) -> dict:
    """Logs one training/assessment run's parameters, metrics, tags, and
    artifacts (Section 24). Never raises - a tracking-backend failure
    degrades to a local fallback log rather than silently losing the run or
    crashing the training script it's called from."""
    tags = dict(tags or {})
    artifact_paths = list(artifact_paths or [])
    numeric_metrics = {k: float(v) for k, v in metrics.items() if v is not None}

    record: dict[str, Any] = {
        "run_name": run_name,
        "params": params,
        "metrics": numeric_metrics,
        "tags": tags,
        "logged_date": date.today().isoformat(),
    }

    try:
        import mlflow

        mlflow.set_tracking_uri(mlruns_dir.resolve().as_uri())
        mlflow.set_experiment(EXPERIMENT_NAME)
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_params(_flatten(params))
            if numeric_metrics:
                mlflow.log_metrics(numeric_metrics)
            mlflow.set_tags(tags)
            for artifact_path in artifact_paths:
                if Path(artifact_path).exists():
                    mlflow.log_artifact(str(artifact_path))
            record["mlflow_run_id"] = run.info.run_id
        record["tracked_via"] = TRACKED_VIA_MLFLOW
        return record

    except Exception:
        logger.exception(
            "MLflow logging failed for run %r - falling back to a local JSON log (Error Case).", run_name,
        )
        record["tracked_via"] = TRACKED_VIA_FALLBACK
        fallback_log_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_log_dir / f"{run_name}.json"
        with open(fallback_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
        record["fallback_path"] = str(fallback_path)
        return record
