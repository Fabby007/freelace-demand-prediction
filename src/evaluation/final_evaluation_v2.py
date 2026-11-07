"""Final evaluation on target year 2023 under a frozen plan (REF-009 ADR-041).

The plan in configs/final_evaluation_v2.yaml is fixed before any 2023 result exists:

1. `--freeze` records hashes of the plan, code, configs and dataset.
2. `--run-final-test` checks them, creates a one-shot lock, and evaluates once.

Every forecast is made from a blind copy of the data with all 2023 values removed.
Real 2023 targets are used only for scoring, after forecasts are complete. A second
run is refused, and nothing here tunes or selects a model.

Run with: python -m src.evaluation.final_evaluation_v2 --freeze
          python -m src.evaluation.final_evaluation_v2 --run-final-test
With no option, it only runs the pre-flight checks, which read no 2023 value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.evaluation.baseline_evaluation_v2 import (
    DATASET_CSV,
    add_candidate_columns,
    add_predictions,
    bootstrap_against_reference,
    district_table,
    evaluate,
    flagged_comparison,
    load_dataset,
    rank_structure,
    summarise,
)
from src.evaluation.baseline_evaluation_v2 import load_config as load_baseline_config
from src.evaluation.experiment_tracking import log_run
from src.models.ml_experiments_v2 import (
    MLRUNS_V2_DIR,
    add_model_inputs,
    decode_prediction,
    encode_target,
    make_ridge,
    size_rule_change_ranking,
    success_criteria,
    training_rows,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_YAML = REPO_ROOT / "configs" / "final_evaluation_v2.yaml"
OUTPUT_DIR = REPO_ROOT / "reports" / "final_evaluation_v2"
LOCK_NAME = "final_test_lock.json"
FREEZE_NAME = "freeze_record.json"

# Everything first known in the final target year.
TARGET_COLUMNS = ["target_licence_count", "has_target", "has_target_and_level", "target_status"]
YEAR_COLUMNS = ["licence_count", "licence_count_printed", "licence_lag_1", "licence_lag_2", "licence_growth_log",
                "licence_rolling_mean_3", "licence_rolling_std_3", "total_registrations", "total_registrations_printed",
                "total_registrations_lag_1", "total_registrations_growth_log"]


def load_plan(path: Path = PLAN_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def blind_copy(df: pd.DataFrame, plan: dict) -> pd.DataFrame:
    """A copy with every value from the final target year removed, including the
    targets of the origin-year rows. Forecasts are made only from this."""
    final_year = plan["final_fold"]["target_year"]
    blind = df.copy()
    blind.loc[blind["target_year"] >= final_year, "target_licence_count"] = np.nan
    columns = [c for c in YEAR_COLUMNS if c in blind.columns]
    blind.loc[blind["year"] >= final_year, columns] = np.nan
    return blind


def fit_final_ridge(blind: pd.DataFrame, plan: dict) -> dict:
    """Fit the frozen Ridge on rows whose target year is before the final year, and
    forecast the origin-year rows. The penalty comes from the plan and is not tuned."""
    spec = plan["ridge"]
    origin = plan["final_fold"]["origin_year"]
    inputs = list(spec["numeric_inputs"])
    columns = inputs + list(spec["categorical_inputs"])
    prepared = add_model_inputs(blind)
    train = training_rows(prepared, origin, inputs, spec["training_rows_rule"])
    if train["target_year"].max() >= plan["final_fold"]["target_year"]:
        raise ValueError("Training rows reach the final target year.")
    model = make_ridge(inputs, spec["alpha"]).fit(train[columns], encode_target(train, spec["target"]))
    test = prepared[prepared["year"] == origin].dropna(subset=inputs)
    predictions = pd.Series(decode_prediction(model.predict(test[columns]), test, spec["target"]), index=test.index)
    names = list(model.named_steps["prepare"].get_feature_names_out())
    coefficients = pd.DataFrame({"term": ["intercept"] + names, "coefficient": [model.named_steps["ridge"].intercept_] + list(model.named_steps["ridge"].coef_)})
    return {"predictions": predictions, "coefficients": coefficients, "train_rows": len(train),
            "train_target_years": sorted(int(y) for y in train["target_year"].unique())}


def build_forecasts(df: pd.DataFrame, plan: dict) -> tuple[pd.DataFrame, dict]:
    """All forecasts, from the blind copy. Real targets are joined back only for scoring."""
    blind = blind_copy(df, plan)
    forecasts = add_predictions(blind)
    ridge = fit_final_ridge(blind, plan)
    wide = add_predictions(df)
    for model in ("previous_year", "moving_average"):
        wide[model] = forecasts[model]
    wide[plan["ridge"]["column"]] = ridge["predictions"]
    return wide, ridge


def preflight(df: pd.DataFrame, plan: dict) -> dict:
    """Checks the frozen expectations. Reads availability and flags, never a 2023 value."""
    blind = blind_copy(df, plan)
    wide = add_predictions(blind)
    ridge = fit_final_ridge(blind, plan)
    wide[plan["ridge"]["column"]] = ridge["predictions"]
    origin = df["year"] == plan["final_fold"]["origin_year"]
    has_target = df["target_status"] == "available"
    scored = wide[origin & has_target].dropna(subset=plan["models"])
    report = {
        "training_rows": ridge["train_rows"], "training_target_years": ridge["train_target_years"],
        "evaluation_rows": len(scored), "flagged_targets": int(df.loc[scored.index, "target_flagged"].sum()),
    }
    differences = {k: (report[k], plan["expected"][k]) for k in report if report[k] != plan["expected"][k]}
    if differences:
        raise ValueError(f"Pre-flight checks do not match the plan: {differences}")
    return report


def evaluate_final(wide: pd.DataFrame, plan: dict, baseline_config: dict) -> dict:
    """Every metric on target year 2023, using the baseline evaluation's own code."""
    config = {**baseline_config, "models": plan["models"], "reference_model": plan["reference_model"],
              "development_folds": [], "final_test_fold": plan["final_fold"]}
    results = evaluate(wide, config, include_final_test=True)
    summary = summarise(results, config)
    bootstrap = bootstrap_against_reference(results["rows"], config)
    evaluation = {"results": results, "summary": summary, "bootstrap": bootstrap, "config": config}
    rows = results["rows"]
    return {
        **evaluation,
        "criteria": success_criteria(evaluation, "final_test"),
        "districts": district_table(rows, config),
        "flagged": flagged_comparison(rows, config),
        "structure": rank_structure(wide, rows, config),
        "size_rule": size_rule_change_ranking(rows),
    }


def file_hashes(plan: dict, repo_root: Path = REPO_ROOT) -> dict:
    return {name: hashlib.sha256((repo_root / name).read_bytes()).hexdigest() for name in plan["frozen_files"]}


def write_freeze_record(output_dir: Path = OUTPUT_DIR, dataset_csv: Path = DATASET_CSV, plan_path: Path = PLAN_YAML) -> dict:
    """Records the plan before any result exists. Refused once the final test has started."""
    if (output_dir / LOCK_NAME).exists():
        raise RuntimeError("The final test has already started, so the plan cannot be frozen again.")
    plan = load_plan(plan_path)
    df = load_dataset(dataset_csv, plan["expected_dataset_sha256"])
    checks = preflight(df, plan)
    record = {"plan_version": plan["plan_version"], "frozen_at": datetime.now().isoformat(timespec="seconds"),
              "dataset_sha256": plan["expected_dataset_sha256"], "file_sha256": file_hashes(plan), "preflight": checks}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / FREEZE_NAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return record


def verify_freeze(output_dir: Path, plan: dict) -> dict:
    """Stops unless the plan, code and configs are exactly as frozen."""
    path = output_dir / FREEZE_NAME
    if not path.exists():
        raise RuntimeError("No freeze record exists. Freeze the plan first.")
    record = json.loads(path.read_text(encoding="utf-8"))
    current = file_hashes(plan)
    changed = sorted(name for name in record["file_sha256"] if current.get(name) != record["file_sha256"][name])
    if changed or set(current) != set(record["file_sha256"]):
        raise RuntimeError(f"Files changed since the freeze: {changed}")
    return record


def _acquire_lock(output_dir: Path, plan: dict) -> None:
    """Exclusive creation, so a second run cannot start even if the first one failed."""
    path = output_dir / LOCK_NAME
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            json.dump({"plan_version": plan["plan_version"], "started_at": datetime.now().isoformat(timespec="seconds")}, f, indent=2)
    except FileExistsError as error:
        raise RuntimeError("The final test has already run. It may only run once.") from error


def run_final_test(output_dir: Path = OUTPUT_DIR, dataset_csv: Path = DATASET_CSV, mlruns_dir: Path = MLRUNS_V2_DIR, plan_path: Path = PLAN_YAML) -> dict:
    """The single final evaluation. Writes only to output_dir and mlruns_dir."""
    logging.basicConfig(level=logging.INFO)
    if (output_dir / LOCK_NAME).exists():
        raise RuntimeError("The final test has already run. It may only run once.")
    plan = load_plan(plan_path)
    verify_freeze(output_dir, plan)
    df = load_dataset(dataset_csv, plan["expected_dataset_sha256"])
    preflight(df, plan)
    _acquire_lock(output_dir, plan)

    baseline_config = load_baseline_config()
    wide, ridge = build_forecasts(df, plan)
    final = evaluate_final(wide, plan, baseline_config)
    rows = add_candidate_columns(final["results"]["rows"], baseline_config)

    keep = ["district", "vehicle_type", "year", "target_year", "licence_count", "target_licence_count"] + plan["models"] + [
        "target_flagged", "features_use_flagged_licence", "touches_outlier_candidate", "licence_flag_ids", "target_flag_ids"]
    tables = {
        "predictions.csv": rows[keep],
        "metrics_final.csv": final["results"]["accuracy"],
        "ranking_final.csv": final["results"]["ranking"],
        "ranking_summary.csv": final["summary"]["ranking"],
        "metrics_summary.csv": final["summary"]["accuracy"],
        "bootstrap_against_previous_year.csv": final["bootstrap"],
        "success_criteria.csv": final["criteria"],
        "errors_by_district.csv": final["districts"],
        "flagged_vs_unflagged.csv": final["flagged"],
        "rank_structure.csv": final["structure"],
        "size_rule_change_ranking.csv": final["size_rule"],
        "ridge_coefficients.csv": ridge["coefficients"],
    }
    for name, table in tables.items():
        table.round(4).to_csv(output_dir / name, index=False, lineterminator="\n")

    accuracy = final["results"]["accuracy"]
    overall = accuracy[(accuracy["scenario"] == "all_rows") & (accuracy["group"] == "All")].set_index("model")
    log_run(
        run_name="final_test_2023",
        params={"plan_version": plan["plan_version"], "models": plan["models"], "ridge_alpha": plan["ridge"]["alpha"], "dataset_sha256": plan["expected_dataset_sha256"][:12]},
        metrics={f"mae_{m}": overall.loc[m, "mae"] for m in plan["models"]} | {f"mape_{m}": overall.loc[m, "mape"] for m in plan["models"]},
        tags={"dataset": "v2", "final_test_used": "true"},
        mlruns_dir=mlruns_dir, fallback_log_dir=output_dir / "tracking_fallback",
    )
    manifest = {
        "plan_version": plan["plan_version"], "completed_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_sha256": hashlib.sha256(dataset_csv.read_bytes()).hexdigest(), "file_sha256": file_hashes(plan),
        "target_year": plan["final_fold"]["target_year"], "evaluation_rows": len(rows),
        "training_rows": ridge["train_rows"], "training_target_years": ridge["train_target_years"], "tables": sorted(tables),
    }
    (output_dir / "final_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--freeze", action="store_true", help="Record the frozen plan.")
    group.add_argument("--run-final-test", action="store_true", help="Run the single final evaluation.")
    arguments = parser.parse_args()
    if arguments.freeze:
        print(json.dumps(write_freeze_record(), indent=2))
    elif arguments.run_final_test:
        print(json.dumps(run_final_test(), indent=2))
    else:
        plan = load_plan()
        print(json.dumps(preflight(load_dataset(DATASET_CSV, plan["expected_dataset_sha256"]), plan), indent=2))


if __name__ == "__main__":
    main()
