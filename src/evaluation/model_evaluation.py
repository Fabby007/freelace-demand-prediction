"""Model Evaluation & Experiment Tracking - consolidated report (DEV-014).

Reuses DEV-007's baseline metrics, DEV-008's saved XGBoost model, and
DEV-009's LSTM conditionality assessment EXACTLY as those specs produced
them - this module recomputes nothing that would change any of their
results (Business Rule: "no repeated test-set peeking"). It reloads the
already-saved XGBoost model (`load_model()`) purely to derive two ADDITIONAL
read-only statistics not persisted by DEV-008 (per-vehicle-type ranking
metrics, Section 23.3) - it never retrains, retunes, or re-selects
hyperparameters against the test set.

Section 23.2 regression metrics (MAE/RMSE/R^2) for baseline/XGBoost are
taken verbatim from `reports/baseline_metrics.json` and
`models/xgboost_v1/metadata.json` - computed identically in both places via
the shared `evaluate_predictions`-shaped dict (same keys: n_total, n_scored,
mae, rmse, r2, n_negative_predictions), so the comparison in this report is
apples-to-apples by construction, not just by narrative claim.

Section 23.3 ranking metrics (Spearman rank correlation, top-k overlap) are
computed here for the first time, per vehicle_type, on the XGBoost test-set
predictions vs. the real `target_value` (the Fallback-path proxy target,
DEV-002) - explicitly labelled as evaluated against the proxy, not real
demand (FR 23.3), since no real demand target exists in this project
(configs/target_config.yaml: is_real_demand_target=false).
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from src.evaluation.experiment_tracking import MLRUNS_DIR as DEFAULT_MLRUNS_DIR, log_run
from src.models.baseline import METRICS_JSON as BASELINE_METRICS_JSON
from src.models.lstm_model import ASSESSMENT_JSON as LSTM_ASSESSMENT_JSON
from src.models.xgboost_model import (
    FROZEN_CSV,
    MODELS_DIR,
    TARGET_COLUMN,
    VEHICLE_CATEGORIES,
    build_feature_matrix,
    load_model,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"

EVALUATION_REPORT_JSON = REPORTS_DIR / "model_evaluation.json"
EVALUATION_REPORT_MD = REPORTS_DIR / "model_evaluation.md"

TOP_K = 3
BEST_BASELINE_COLUMN = "baseline_previous_period"

# REF-006 - known limitations this report must disclose, not omit.
KNOWN_LIMITATIONS = [
    "Fallback-path proxy target: target_value is future new_registrations, not a real observed "
    "mechanic-demand signal (DEV-002 Target Decision Record) - every metric in this report, "
    "including the ranking metrics below, describes how well the model forecasts vehicle "
    "registrations, not measured mechanic job demand.",
    "DCS/DMT reconciliation gap (REF-006 Section 5.1): Car (2019-2021) and Three-wheeler (2022) "
    "district-summed new_registrations exceed the DMT national total - 100/375 rows flagged "
    "(`data_quality_flag`), not excluded or corrected.",
    "Real 2020-2022 vehicle-registration collapse (REF-006 Section 5.2): several high-volume "
    "districts show an extreme, genuine multi-year drop (e.g. Gampaha Motorcycle 32,698 -> 909 "
    "registrations, 2019-2021) consistent with Sri Lanka's economic crisis and import "
    "restrictions - this regime shift, not a modelling defect, explains most of the error below.",
    "XGBoost does not outperform the naive persistence baseline on the test period (REF-006 "
    "Section 5.3) - reported plainly, not hidden: baseline_previous_period test MAE 230.5 vs. "
    "XGBoost's matched-subset test MAE 306.4 on the identical 42 rows.",
    "LSTM was assessed and skipped (REF-006 Section 5.4, REF-009 ADR-013): the dataset is "
    "yearly-only (0% monthly coverage) and spans only 5 distinct years, so 0/75 series can form "
    "even one training sequence at the documented minimum 6-period lookback - not a resourcing "
    "shortfall, a categorical data-density failure.",
    "SBERT similarity margins can be tight for naturally-phrased (longer) queries (REF-006 "
    "Section 5.5) - not a regression-model finding, included for completeness of the pipeline's "
    "documented limitations.",
    "Thin validation/test periods: validation covers a single target-year (49 rows), test covers "
    "a single target-year (47 rows, 20 Car / 19 Motorcycle / 8 Three-wheeler) - R^2 and ranking "
    "metrics on these splits, and especially per-vehicle-type ranking metrics on the 8-row "
    "Three-wheeler slice, must be read as indicative, not statistically robust (Edge Case, "
    "REF-006 'Small dataset / many features' risk).",
    "Negative-prediction findings: DEV-007's linear-trend baseline produces physically impossible "
    "negative predictions for 82-93% of its scored rows (REF-009 ADR-010); XGBoost's test "
    "predictions include 1 negative value out of 47 - both disclosed via `n_negative_predictions`, "
    "never clipped.",
]


def load_baseline_metrics(path: Path = BASELINE_METRICS_JSON) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_lstm_assessment(path: Path = LSTM_ASSESSMENT_JSON) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_test_predictions(models_dir: Path = MODELS_DIR, frozen_csv: Path = FROZEN_CSV) -> pd.DataFrame:
    """Reloads the already-saved, already-selected XGBoost model (no
    retraining/retuning) purely to attach its test-set predictions to the
    real test rows, for the ranking-metric computation below."""
    model, encoder, metadata = load_model(models_dir)
    df = pd.read_csv(frozen_csv)
    test_df = df[df["split"] == "test"].reset_index(drop=True)
    X_test = build_feature_matrix(test_df, metadata["active_numeric_features"], encoder)
    return test_df.assign(xgb_predicted_value=model.predict(X_test))


def compute_ranking_metrics(test_df_with_predictions: pd.DataFrame, top_k: int = TOP_K) -> dict:
    """Section 23.3: Spearman rank correlation and top-k overlap, computed
    per vehicle_type (predictions/targets are not comparable across
    categories with very different scales - REF-009 ADR-018 makes the same
    per-vehicle-type argument for opportunity bands). Evaluated against the
    real `target_value` used for training - the Fallback-path proxy, never a
    fabricated ground-truth ranking (Business Rule)."""
    results = {}
    for vehicle_type in VEHICLE_CATEGORIES:
        group = test_df_with_predictions[test_df_with_predictions["vehicle_type"] == vehicle_type]
        scored = group.dropna(subset=[TARGET_COLUMN])
        n_scored = len(scored)

        if n_scored < 2:
            results[vehicle_type] = {
                "n_scored": n_scored, "spearman_r": None, "spearman_p": None,
                "top_k_overlap": None, "k": None,
            }
            continue

        rho, p_value = spearmanr(scored[TARGET_COLUMN], scored["xgb_predicted_value"])
        k = min(top_k, n_scored)
        actual_top = set(scored.sort_values(TARGET_COLUMN, ascending=False).head(k)["district"])
        predicted_top = set(scored.sort_values("xgb_predicted_value", ascending=False).head(k)["district"])
        overlap = len(actual_top & predicted_top) / k

        results[vehicle_type] = {
            "n_scored": n_scored,
            "spearman_r": float(rho) if not np.isnan(rho) else None,
            "spearman_p": float(p_value) if not np.isnan(p_value) else None,
            "top_k_overlap": overlap,
            "k": k,
        }
    return results


def build_regression_comparison_table(baseline_metrics: dict, xgboost_metadata: dict) -> list[dict]:
    """One row per model per split - MAE/RMSE/R^2/coverage, all computed via
    the identical evaluate_predictions()-shaped schema (Validation
    requirement: 'metrics computed identically ... for fair comparison')."""
    rows = []
    for split_name in ("validation", "test"):
        for baseline_col, entry in baseline_metrics["metrics"][split_name].items():
            rows.append({"model": baseline_col, "split": split_name, **entry})

    rows.append({
        "model": "xgboost_v1", "split": "validation",
        "mae": xgboost_metadata["validation_metrics_at_selection"]["mae"],
        "rmse": xgboost_metadata["validation_metrics_at_selection"]["rmse"],
        "r2": xgboost_metadata["validation_metrics_at_selection"]["r2"],
        "n_total": xgboost_metadata["validation_rows"], "n_scored": xgboost_metadata["validation_rows"],
        "n_negative_predictions": None,
    })
    rows.append({"model": "xgboost_v1", "split": "test", **xgboost_metadata["test_metrics"]})
    rows.append({
        "model": "xgboost_v1_matched_subset", "split": "test",
        **xgboost_metadata["baseline_comparison"]["xgboost_matched_subset"],
    })
    rows.append({
        "model": f"{BEST_BASELINE_COLUMN}_matched_subset", "split": "test",
        **xgboost_metadata["baseline_comparison"]["baseline_matched_subset"],
    })
    return rows


def build_markdown_report(report: dict) -> str:
    lines = [
        "# Model Evaluation Report (DEV-014)",
        "",
        f"Generated: {report['generated_date']}  ",
        f"Dataset version: `{report['dataset_version']}`  ",
        f"Random seed: {report['random_seed']}",
        "",
        "## Time-aware validation (Section 23.4)",
        "Chronological split only, reused verbatim from DEV-006 - no random train/test splitting. "
        "Train covers target_year 2020-2021, validation target_year 2022, test target_year 2023 "
        "(REF-009 ADR-008). No boundary was altered for this report.",
        "",
        "## Regression metrics (Section 23.2) - identical computation across models",
        "",
        "| Model | Split | n_scored / n_total | MAE | RMSE | R² | Negative predictions |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["regression_comparison"]:
        mae = f"{row['mae']:.1f}" if row["mae"] is not None else "n/a"
        rmse = f"{row['rmse']:.1f}" if row["rmse"] is not None else "n/a"
        r2 = f"{row['r2']:.3f}" if row["r2"] is not None else "n/a"
        neg = row.get("n_negative_predictions")
        neg_str = str(neg) if neg is not None else "n/a"
        lines.append(
            f"| {row['model']} | {row['split']} | {row['n_scored']}/{row['n_total']} | {mae} | {rmse} | {r2} | {neg_str} |"
        )

    lines += [
        "",
        "**Headline finding, stated plainly:** on the untouched test period, "
        f"`{BEST_BASELINE_COLUMN}` (MAE {report['headline']['baseline_test_mae']:.1f}) "
        f"outperforms tuned XGBoost (matched-subset MAE {report['headline']['xgboost_matched_subset_mae']:.1f}, "
        f"full-coverage MAE {report['headline']['xgboost_full_coverage_mae']:.1f}) on the identical "
        f"{report['headline']['n_matched']} rows both can score. This is not hidden or re-tuned away - "
        "see 'Known limitations' below for why.",
        "",
        "## Ranking metrics (Section 23.3) - proxy target, per vehicle_type",
        "Computed against `target_value` (the Fallback-path proxy - future new_registrations), "
        "**not** a real observed mechanic-demand ranking (no such data exists for this project, "
        "DEV-002 Target Decision Record). Read the Three-wheeler row especially cautiously - only "
        "8 test rows.",
        "",
        "| Vehicle type | n_scored | Spearman ρ | p-value | Top-3 overlap |",
        "|---|---|---|---|---|",
    ]
    for vehicle_type, m in report["ranking_metrics"].items():
        rho = f"{m['spearman_r']:.3f}" if m["spearman_r"] is not None else "n/a"
        p = f"{m['spearman_p']:.3f}" if m["spearman_p"] is not None else "n/a"
        overlap = f"{m['top_k_overlap']:.2f} (k={m['k']})" if m["top_k_overlap"] is not None else "n/a"
        lines.append(f"| {vehicle_type} | {m['n_scored']} | {rho} | {p} | {overlap} |")

    lines += [
        "",
        "## LSTM (Section 23.5)",
        f"**Decision: {report['lstm']['decision']}.** " + " ".join(report["lstm"]["reasoning"]),
        "",
        "**Production-model recommendation, stated plainly: XGBoost** (DEV-008) - the only "
        "trained model in this project, per Section 23.5's own rule that a skipped/absent LSTM "
        "leaves XGBoost as the recommended production model by default. This is not a comparison "
        "between two trained models where XGBoost happened to win; LSTM was never built because "
        "the conditionality check failed (see above).",
        "",
        "## Known limitations",
    ]
    lines += [f"- {item}" for item in report["known_limitations"]]

    lines += [
        "",
        "## Reproducibility",
        f"- Dataset version: `{report['dataset_version']}`",
        f"- Random seed: {report['random_seed']}",
        f"- XGBoost feature columns (exact order): `{report['xgboost_feature_columns']}`",
        f"- XGBoost selected hyperparameters: `{report['xgboost_selected_hyperparameters']}`",
        "- Full experiment run log: `mlruns/` (MLflow, local file store) or "
        "`reports/experiment_tracking_fallback/` if MLflow was unavailable at run time.",
        "",
    ]
    return "\n".join(lines)


def run(
    baseline_metrics_path: Path = BASELINE_METRICS_JSON,
    lstm_assessment_path: Path = LSTM_ASSESSMENT_JSON,
    models_dir: Path = MODELS_DIR,
    frozen_csv: Path = FROZEN_CSV,
    report_json_path: Path = EVALUATION_REPORT_JSON,
    report_md_path: Path = EVALUATION_REPORT_MD,
    mlruns_dir: Path = DEFAULT_MLRUNS_DIR,
) -> dict:
    logging.basicConfig(level=logging.INFO)

    baseline_metrics = load_baseline_metrics(baseline_metrics_path)
    lstm_assessment = load_lstm_assessment(lstm_assessment_path)
    _, _, xgboost_metadata = load_model(models_dir)

    test_df_with_predictions = compute_test_predictions(models_dir, frozen_csv)
    ranking_metrics = compute_ranking_metrics(test_df_with_predictions)

    regression_comparison = build_regression_comparison_table(baseline_metrics, xgboost_metadata)

    report = {
        "generated_date": date.today().isoformat(),
        "dataset_version": xgboost_metadata["dataset_version"],
        "random_seed": xgboost_metadata["random_seed"],
        "xgboost_feature_columns": xgboost_metadata["feature_columns"],
        "xgboost_selected_hyperparameters": xgboost_metadata["selected_hyperparameters"],
        "regression_comparison": regression_comparison,
        "ranking_metrics": ranking_metrics,
        "lstm": {"decision": lstm_assessment["decision"], "reasoning": lstm_assessment["reasoning"]},
        "headline": {
            "baseline_test_mae": xgboost_metadata["baseline_comparison"]["baseline_matched_subset"]["mae"],
            "xgboost_matched_subset_mae": xgboost_metadata["baseline_comparison"]["xgboost_matched_subset"]["mae"],
            "xgboost_full_coverage_mae": xgboost_metadata["test_metrics"]["mae"],
            "n_matched": xgboost_metadata["baseline_comparison"]["n_matched_with_baseline"],
        },
        "known_limitations": KNOWN_LIMITATIONS,
        "production_model_recommendation": "XGBoost",
    }

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    markdown = build_markdown_report(report)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    # Section 24: "Model registry folder - final model, preprocessing
    # objects, feature schema, evaluation report." The first three already
    # live in models_dir (DEV-008's save_model()); copy the evaluation
    # report alongside them so the registry folder is self-contained -
    # reports/model_evaluation.* remains the canonical, generated copy.
    shutil.copy(report_json_path, models_dir / "evaluation_report.json")
    shutil.copy(report_md_path, models_dir / "evaluation_report.md")

    log_run(
        run_name="model_evaluation",
        params={"dataset_version": report["dataset_version"], "random_seed": report["random_seed"]},
        metrics={
            f"ranking_{vt}_spearman_r": m["spearman_r"] for vt, m in ranking_metrics.items() if m["spearman_r"] is not None
        },
        tags={"model_type": "evaluation_report", "production_model": "xgboost"},
        artifact_paths=[report_json_path, report_md_path, models_dir / "evaluation_report.json", models_dir / "evaluation_report.md"],
        mlruns_dir=mlruns_dir,
    )

    logger.info("Wrote consolidated evaluation report to %s and %s", report_json_path, report_md_path)
    return report


if __name__ == "__main__":
    run()
