"""Ridge and gated XGBoost experiments on Dataset v2 (REF-009 ADR-040).

Predicts next-year revenue licences on the same chronological folds and rows as the
baseline evaluation, and scores them with the same code. Each model is fitted only
on rows whose target year is no later than the fold's origin year. Scaling, encoding
and the penalty are all fitted inside those rows. Target year 2023 is never used.

Dataset v1, its models and its results are not read or changed.

Run with: python -m src.models.ml_experiments_v2
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

from src.evaluation.baseline_evaluation_v2 import (
    DATASET_CSV,
    GROUP_ALL,
    VEHICLES,
    _style,
    add_predictions,
    bootstrap_against_reference,
    evaluate,
    load_dataset,
    summarise,
)
from src.evaluation.baseline_evaluation_v2 import load_config as load_baseline_config
from src.evaluation.experiment_tracking import log_run

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_YAML = REPO_ROOT / "configs" / "ml_v2.yaml"
OUTPUT_DIR = REPO_ROOT / "reports" / "ml_v2"
MLRUNS_V2_DIR = REPO_ROOT / "mlruns_v2"

REFERENCE = "previous_year"
CONTEXT_MODELS = ["previous_year", "moving_average"]
CLEAN_SCENARIO = "no_flagged_target_or_input"
ALL_SCENARIO = "all_rows"
GROUP_BOTH_FOLDS = "both_folds_level_features"
GROUP_FOLD_2 = "fold_2_licence_features"
GROUP_REGISTRATIONS = "fold_2_with_registrations"


def load_config(path: Path = CONFIG_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def add_model_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Log inputs, for year t only. Missing values stay missing."""
    out = df.copy()
    out["log_licence_count"] = np.log(out["licence_count"])
    out["log_licence_rolling_std_3"] = np.log(out["licence_rolling_std_3"].where(out["licence_rolling_std_3"] > 0))
    out["log_total_registrations"] = np.log(out["total_registrations"])
    return out


def encode_target(frame: pd.DataFrame, target: str) -> pd.Series:
    if target == "raw_count":
        return frame["target_licence_count"]
    if target == "log_count":
        return np.log(frame["target_licence_count"])
    if target == "log_change":
        return np.log(frame["target_licence_count"] / frame["licence_count"])
    raise ValueError(f"Unknown target: {target}")


def decode_prediction(values: np.ndarray, frame: pd.DataFrame, target: str) -> np.ndarray:
    """Back to licence counts. On a log scale this gives a typical (median-like) value,
    with no adjustment for retransformation."""
    if target == "raw_count":
        return values
    if target == "log_count":
        return np.exp(values)
    if target == "log_change":
        return frame["licence_count"].to_numpy() * np.exp(values)
    raise ValueError(f"Unknown target: {target}")


def numeric_inputs(feature_set: dict, target: str, config: dict) -> list[str]:
    inputs = list(feature_set["numeric"])
    if target == "raw_count":
        inputs[inputs.index("log_licence_count")] = config["raw_count_level_input"]
    return inputs


def training_rows(df: pd.DataFrame, origin_year: int, inputs: list[str], flag_rule: str) -> pd.DataFrame:
    """Rows known by the origin year: the target year must not pass it. No imputation:
    rows missing an input or target are left out."""
    rows = df[df["target_year"] <= origin_year].dropna(subset=inputs + ["target_licence_count", "licence_count"])
    if flag_rule == "no_flagged":
        rows = rows[~rows["target_flagged"] & ~rows["features_use_flagged_licence"]]
    elif flag_rule != "all":
        raise ValueError(f"Unknown training rows rule: {flag_rule}")
    return rows


def make_ridge(inputs: list[str], alpha: float) -> Pipeline:
    """Fitted as one unit, so scaling and encoding only ever learn from training rows."""
    prepare = ColumnTransformer([
        ("numeric", StandardScaler(), inputs),
        ("vehicle", OneHotEncoder(categories=[VEHICLES], handle_unknown="error"), ["vehicle_type"]),
    ])
    return Pipeline([("prepare", prepare), ("ridge", Ridge(alpha=alpha))])


def select_alpha(rows: pd.DataFrame, inputs: list[str], target: str, config: dict) -> tuple[float, pd.DataFrame]:
    """Penalty with the lowest error in licences, by cross-validation across districts,
    inside the training rows. Ties go to the larger penalty."""
    splitter = GroupKFold(n_splits=config["ridge"]["cv_folds"])
    records = []
    columns = inputs + ["vehicle_type"]
    y = encode_target(rows, target)
    for alpha in config["ridge"]["alpha_grid"]:
        errors = []
        for train_index, test_index in splitter.split(rows, groups=rows["district"]):
            model = make_ridge(inputs, alpha).fit(rows.iloc[train_index][columns], y.iloc[train_index])
            held = rows.iloc[test_index]
            predicted = decode_prediction(model.predict(held[columns]), held, target)
            errors.append(np.abs(predicted - held["target_licence_count"].to_numpy()))
        records.append({"alpha": alpha, "cv_mae": float(np.concatenate(errors).mean())})
    table = pd.DataFrame(records)
    best = table.sort_values(["cv_mae", "alpha"], ascending=[True, False]).iloc[0]
    return float(best["alpha"]), table


def make_xgboost(inputs: list[str], params: dict, config: dict) -> Pipeline:
    prepare = ColumnTransformer([
        ("numeric", "passthrough", inputs),
        ("vehicle", OneHotEncoder(categories=[VEHICLES], handle_unknown="error"), ["vehicle_type"]),
    ])
    model = XGBRegressor(objective="reg:squarederror", random_state=config["random_seed"], n_jobs=1, tree_method="exact",
                         **config["xgboost"]["fixed"], **params)
    return Pipeline([("prepare", prepare), ("xgboost", model)])


def select_xgboost_params(rows: pd.DataFrame, inputs: list[str], target: str, config: dict) -> dict:
    """Same procedure as select_alpha, inside the training rows. Ties go to the simpler model."""
    splitter = GroupKFold(n_splits=config["ridge"]["cv_folds"])
    grid = config["xgboost"]["grid"]
    columns = inputs + ["vehicle_type"]
    y = encode_target(rows, target)
    records = []
    for depth, trees in itertools.product(grid["max_depth"], grid["n_estimators"]):
        params = {"max_depth": depth, "n_estimators": trees}
        errors = []
        for train_index, test_index in splitter.split(rows, groups=rows["district"]):
            model = make_xgboost(inputs, params, config).fit(rows.iloc[train_index][columns], y.iloc[train_index])
            held = rows.iloc[test_index]
            errors.append(np.abs(decode_prediction(model.predict(held[columns]), held, target) - held["target_licence_count"].to_numpy()))
        records.append({**params, "cv_mae": float(np.concatenate(errors).mean())})
    best = pd.DataFrame(records).sort_values(["cv_mae", "max_depth", "n_estimators"]).iloc[0]
    return {"max_depth": int(best["max_depth"]), "n_estimators": int(best["n_estimators"])}


def experiment_name(feature_set: str, target: str, flag_rule: str, model: str = "ridge") -> str:
    return f"{model}__{feature_set}__{target}__train_{flag_rule}"


def fit_fold(df: pd.DataFrame, fold: dict, feature_set_name: str, target: str, flag_rule: str, config: dict) -> dict:
    """Fit on rows up to the origin and predict that origin year's rows."""
    feature_set = config["feature_sets"][feature_set_name]
    inputs = numeric_inputs(feature_set, target, config)
    columns = inputs + ["vehicle_type"]
    train = training_rows(df, fold["origin_year"], inputs, flag_rule)
    alpha, cv_table = select_alpha(train, inputs, target, config)
    model = make_ridge(inputs, alpha).fit(train[columns], encode_target(train, target))

    test = df[df["year"] == fold["origin_year"]].dropna(subset=inputs)
    predicted = decode_prediction(model.predict(test[columns]), test, target)
    names = list(model.named_steps["prepare"].get_feature_names_out())
    coefficients = pd.DataFrame({"term": ["intercept"] + names, "coefficient": [model.named_steps["ridge"].intercept_] + list(model.named_steps["ridge"].coef_)})
    return {
        "predictions": pd.Series(predicted, index=test.index), "alpha": alpha, "cv_table": cv_table, "coefficients": coefficients,
        "train_rows": len(train), "train_target_years": sorted(int(y) for y in train["target_year"].unique()), "inputs": inputs,
    }


def fit_xgboost_fold(df: pd.DataFrame, fold: dict, feature_set_name: str, flag_rule: str, config: dict) -> dict:
    target = config["xgboost"]["target"]
    inputs = numeric_inputs(config["feature_sets"][feature_set_name], target, config)
    columns = inputs + ["vehicle_type"]
    train = training_rows(df, fold["origin_year"], inputs, flag_rule)
    params = select_xgboost_params(train, inputs, target, config)
    model = make_xgboost(inputs, params, config).fit(train[columns], encode_target(train, target))
    test = df[df["year"] == fold["origin_year"]].dropna(subset=inputs)
    predicted = decode_prediction(model.predict(test[columns]), test, target)
    return {"predictions": pd.Series(predicted, index=test.index), "params": params, "train_rows": len(train),
            "train_target_years": sorted(int(y) for y in train["target_year"].unique()), "inputs": inputs}


def run_xgboost_experiments(wide: pd.DataFrame, config: dict, baseline_config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adds one prediction column per XGBoost experiment. Only called if the gate is open."""
    folds = {f["name"]: f for f in baseline_config["development_folds"]}
    target = config["xgboost"]["target"]
    log, new_columns = [], {}
    for feature_set_name in config["xgboost"]["feature_sets"]:
        for flag_rule in config["training_rows"]:
            name = experiment_name(feature_set_name, target, flag_rule, "xgboost")
            column = pd.Series(np.nan, index=wide.index)
            for fold_name in config["feature_sets"][feature_set_name]["folds"]:
                fold = folds[fold_name]
                result = fit_xgboost_fold(wide, fold, feature_set_name, flag_rule, config)
                column.loc[result["predictions"].index] = result["predictions"]
                log.append({
                    "experiment": name, "model": "xgboost", "feature_set": feature_set_name, "target": target, "training_rows": flag_rule,
                    "fold": fold_name, "predicts_target_year": fold["target_year"], "train_rows": result["train_rows"],
                    "train_target_years": " ".join(map(str, result["train_target_years"])), "inputs": " ".join(result["inputs"]) + " vehicle_type",
                    "hyperparameters": json.dumps({**result["params"], **config["xgboost"]["fixed"]}), "alpha_at_grid_edge": False,
                    "negative_predictions": int((result["predictions"] < 0).sum()),
                })
            new_columns[name] = column
    return pd.concat([wide, pd.DataFrame(new_columns)], axis=1), pd.DataFrame(log)


def size_rule_change_ranking(rows: pd.DataFrame) -> pd.DataFrame:
    """How well does "smaller districts change more" alone rank next-year change? No
    fitting: a level-only log model can only ever produce this order or its reverse."""
    records = []
    for (fold, vehicle), part in rows.groupby(["fold", "vehicle_type"], sort=False):
        change = part["target_licence_count"] / part["licence_count"]
        records.append({"fold": fold, "vehicle_type": vehicle, "n": len(part),
                        "spearman_change_smaller_is_higher": float(stats.spearmanr(change, -part["licence_count"]).statistic)})
    return pd.DataFrame(records)


def run_ridge_experiments(df: pd.DataFrame, config: dict, baseline_config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Adds one prediction column per experiment. Returns (wide table, experiment log, coefficients)."""
    wide = add_predictions(df)
    wide = add_model_inputs(wide)
    folds = {f["name"]: f for f in baseline_config["development_folds"]}
    log, coefficient_tables = [], []
    new_columns = {}
    for feature_set_name, targets in config["experiments"].items():
        for target in targets:
            for flag_rule in config["training_rows"]:
                name = experiment_name(feature_set_name, target, flag_rule)
                column = pd.Series(np.nan, index=wide.index)
                for fold_name in config["feature_sets"][feature_set_name]["folds"]:
                    fold = folds[fold_name]
                    result = fit_fold(wide, fold, feature_set_name, target, flag_rule, config)
                    column.loc[result["predictions"].index] = result["predictions"]
                    log.append({
                        "experiment": name, "model": "ridge", "feature_set": feature_set_name, "target": target, "training_rows": flag_rule,
                        "fold": fold_name, "predicts_target_year": fold["target_year"], "train_rows": result["train_rows"],
                        "train_target_years": " ".join(map(str, result["train_target_years"])), "inputs": " ".join(result["inputs"]) + " vehicle_type",
                        "hyperparameters": json.dumps({"alpha": result["alpha"]}), "alpha_at_grid_edge": result["alpha"] in (min(config["ridge"]["alpha_grid"]), max(config["ridge"]["alpha_grid"])),
                        "negative_predictions": int((result["predictions"] < 0).sum()),
                    })
                    coefficient_tables.append(result["coefficients"].assign(experiment=name, fold=fold_name))
                new_columns[name] = column
    wide = pd.concat([wide, pd.DataFrame(new_columns)], axis=1)
    return wide, pd.DataFrame(log), pd.concat(coefficient_tables, ignore_index=True)


def comparison_groups(config: dict, include_xgboost: bool = False) -> dict[str, dict]:
    """Which experiments are compared together, on which folds, so rows are identical."""
    names = {set_name: [experiment_name(set_name, t, r) for t in targets for r in config["training_rows"]] for set_name, targets in config["experiments"].items()}
    if include_xgboost:
        for set_name in config["xgboost"]["feature_sets"]:
            names[set_name] = names[set_name] + [experiment_name(set_name, config["xgboost"]["target"], r, "xgboost") for r in config["training_rows"]]
    licence_sets = names["level"] + names["level_growth"] + names["level_growth_volatility"]
    return {
        GROUP_BOTH_FOLDS: {"folds": ["fold_1", "fold_2"], "experiments": names["level"]},
        GROUP_FOLD_2: {"folds": ["fold_2"], "experiments": licence_sets},
        GROUP_REGISTRATIONS: {"folds": ["fold_2"], "experiments": names["level"] + names["level_growth"] + names["level_growth_registrations"]},
    }


def evaluate_group(wide: pd.DataFrame, group: dict, baseline_config: dict) -> dict:
    """Uses the baseline evaluation's own code, so metrics and row rules are the same."""
    group_config = {**baseline_config, "models": CONTEXT_MODELS + group["experiments"],
                    "development_folds": [f for f in baseline_config["development_folds"] if f["name"] in group["folds"]]}
    results = evaluate(wide, group_config)
    summary = summarise(results, group_config)
    bootstrap = bootstrap_against_reference(results["rows"], group_config)
    return {"results": results, "summary": summary, "bootstrap": bootstrap, "config": group_config}


def success_criteria(evaluation: dict, group_name: str) -> pd.DataFrame:
    """The criteria fixed in the baseline report, applied to each experiment."""
    accuracy = evaluation["summary"]["accuracy"]
    accuracy = accuracy[accuracy["group"] == GROUP_ALL].set_index(["scenario", "model"])
    ranking = evaluation["summary"]["ranking"].set_index(["scenario", "model"])
    by_fold = evaluation["results"]["ranking"]
    bootstrap = evaluation["bootstrap"].set_index(["scenario", "model"])
    output = []
    for model in evaluation["config"]["models"]:
        if model == REFERENCE:
            continue
        row = {"comparison": group_name, "model": model}
        for scenario in (ALL_SCENARIO, CLEAN_SCENARIO):
            row[f"mae_ratio_{scenario}"] = bootstrap.loc[(scenario, model), "mae_ratio"]
            row[f"mae_ratio_low_{scenario}"] = bootstrap.loc[(scenario, model), "mae_ratio_low"]
            row[f"mae_ratio_high_{scenario}"] = bootstrap.loc[(scenario, model), "mae_ratio_high"]
            row[f"mape_{scenario}"] = accuracy.loc[(scenario, model), "mape"]
            row[f"mape_reference_{scenario}"] = accuracy.loc[(scenario, REFERENCE), "mape"]
        lower = [
            accuracy.loc[(s, model), "mae"] < accuracy.loc[(s, REFERENCE), "mae"] and accuracy.loc[(s, model), "mape"] < accuracy.loc[(s, REFERENCE), "mape"]
            for s in (ALL_SCENARIO, CLEAN_SCENARIO)
        ]
        row["c1_lower_mae_and_mape_both_row_sets"] = all(lower)
        row["c2_interval_below_one_both_row_sets"] = all(bootstrap.loc[(s, model), "mae_ratio_high"] < 1 for s in (ALL_SCENARIO, CLEAN_SCENARIO))
        row["c3_ranking_not_lower"] = bool(
            ranking.loc[(ALL_SCENARIO, model), "spearman_level"] >= ranking.loc[(ALL_SCENARIO, REFERENCE), "spearman_level"]
            and ranking.loc[(ALL_SCENARIO, model), "top_5_overlap"] >= ranking.loc[(ALL_SCENARIO, REFERENCE), "top_5_overlap"])
        change = by_fold[(by_fold["scenario"] == ALL_SCENARIO) & (by_fold["model"] == model)]["spearman_change"]
        row["c4_positive_change_ranking_every_vehicle_and_fold"] = bool(change.notna().all() and (change > 0).all())
        row["passes_all_accuracy_criteria"] = row["c1_lower_mae_and_mape_both_row_sets"] and row["c2_interval_below_one_both_row_sets"] and row["c3_ranking_not_lower"]
        output.append(row)
    return pd.DataFrame(output)


def xgboost_gate(criteria: pd.DataFrame) -> dict:
    """The rule fixed before Ridge results were seen. Only Ridge models can open it."""
    ridge = criteria[criteria["model"].str.startswith("ridge__")]
    accuracy_pass = ridge[ridge["c1_lower_mae_and_mape_both_row_sets"]]
    change_pass = ridge[ridge["c4_positive_change_ranking_every_vehicle_and_fold"]]
    return {
        "open": bool(len(accuracy_pass) or len(change_pass)),
        "ridge_lower_mae_and_mape_both_row_sets": sorted(set(accuracy_pass["model"])),
        "ridge_positive_change_ranking_every_vehicle_and_fold": sorted(set(change_pass["model"])),
    }


def _label(name: str) -> str:
    if "__" not in name:
        return {"previous_year": "Previous year", "moving_average": "Moving average"}.get(name, name)
    model, feature_set, target, train = name.split("__")
    display = {"ridge": "Ridge", "xgboost": "XGBoost"}[model]
    return f"{display}: {target} | {feature_set}" + (" | clean train" if train == "train_no_flagged" else "")


def write_figures(evaluations: dict, figure_dir: Path) -> list[str]:
    plt = _style()
    figure_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def save(fig, name):
        fig.savefig(figure_dir / name, dpi=160, bbox_inches="tight")
        plt.close(fig)
        written.append(name)

    both = evaluations[GROUP_BOTH_FOLDS]
    accuracy = both["summary"]["accuracy"]
    part = accuracy[(accuracy["group"] == GROUP_ALL) & accuracy["model"].isin(["previous_year", "moving_average"] + [m for m in both["config"]["models"] if m.endswith("train_all")])]
    models = list(dict.fromkeys(part["model"]))
    colours = {m: "#eb6834" if m == REFERENCE else "#2a78d6" for m in models}
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4))
    for ax, scenario, title in zip(axes, (ALL_SCENARIO, CLEAN_SCENARIO), ("All rows", "No flagged target or input")):
        values = part[part["scenario"] == scenario].set_index("model").loc[models]
        ax.barh([_label(m) for m in models][::-1], values["mape"][::-1], color=[colours[m] for m in models][::-1], height=0.7)
        for y, v in enumerate(values["mape"][::-1]):
            ax.text(v, y, f" {v:.2f}", va="center", fontsize=8.5, color="#52514e")
        ax.set(title=title, xlabel="MAPE (%), mean of two folds")
        ax.grid(axis="y", visible=False)
    axes[1].set_yticklabels([])
    fig.tight_layout()
    save(fig, "fig01_models_vs_baseline_both_folds.png")

    fold_2 = evaluations[GROUP_FOLD_2]
    table = fold_2["bootstrap"]
    table = table[(table["scenario"] == ALL_SCENARIO) | (table["scenario"] == CLEAN_SCENARIO)]
    keep = [m for m in fold_2["config"]["models"] if m.endswith("train_all") or m == "moving_average"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    for ax, scenario, title in zip(axes, (ALL_SCENARIO, CLEAN_SCENARIO), ("All rows", "No flagged target or input")):
        part = table[(table["scenario"] == scenario) & table["model"].isin(keep)].set_index("model").loc[keep[::-1]]
        y = np.arange(len(part))
        ax.errorbar(part["mae_ratio"], y, xerr=[part["mae_ratio"] - part["mae_ratio_low"], part["mae_ratio_high"] - part["mae_ratio"]], fmt="o", color="#2a78d6", ecolor="#86b6ef", markersize=5, linewidth=1.6)
        ax.axvline(1, color="#52514e", linewidth=1)
        ax.set_yticks(y)
        ax.set_yticklabels([_label(m) for m in part.index], fontsize=8.5)
        ax.set(title=title, xlabel="MAE ratio to previous year, target 2022 (below 1 is better)")
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    save(fig, "fig02_mae_ratio_intervals_fold_2.png")

    ranking = fold_2["results"]["ranking"]
    ranking = ranking[(ranking["scenario"] == ALL_SCENARIO) & ranking["model"].isin(keep)]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = [_label(m) for m in keep]
    colours = dict(zip(VEHICLES, ["#2a78d6", "#eb6834", "#1baf7a"]))
    for vehicle, offset in zip(VEHICLES, (-0.22, 0, 0.22)):
        part = ranking[ranking["vehicle_type"] == vehicle].set_index("model").loc[keep]
        ax.barh(np.arange(len(keep))[::-1] + offset, part["spearman_change"], 0.2, color=colours[vehicle], label=vehicle)
    ax.axvline(0, color="#52514e", linewidth=1)
    ax.set_yticks(np.arange(len(keep))[::-1])
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set(title="Ranking next-year change, target 2022", xlabel="Spearman correlation with actual change", xlim=(-1, 1))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3)
    save(fig, "fig03_change_ranking_fold_2.png")
    return written


def _write_tables(evaluations: dict, log: pd.DataFrame, coefficients: pd.DataFrame, criteria: pd.DataFrame, size_rule: pd.DataFrame, output_dir: Path) -> list[str]:
    def combined(getter):
        return pd.concat([getter(e).assign(comparison=name) for name, e in evaluations.items()], ignore_index=True)

    tables = {
        "experiments.csv": log,
        "coefficients.csv": coefficients,
        "metrics_by_fold.csv": combined(lambda e: e["results"]["accuracy"]),
        "metrics_summary.csv": combined(lambda e: e["summary"]["accuracy"]),
        "ranking_by_fold.csv": combined(lambda e: e["results"]["ranking"]),
        "ranking_summary.csv": combined(lambda e: e["summary"]["ranking"]),
        "ranking_by_vehicle.csv": combined(lambda e: e["summary"]["ranking_by_vehicle"]),
        "bootstrap_against_previous_year.csv": combined(lambda e: e["bootstrap"]),
        "success_criteria.csv": criteria,
        "size_rule_change_ranking.csv": size_rule,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.round(4).to_csv(output_dir / name, index=False, lineterminator="\n")
    return sorted(tables)


def _log_to_mlflow(criteria: pd.DataFrame, log: pd.DataFrame, config_hash: str, dataset_hash: str, mlruns_dir: Path, fallback_dir: Path) -> None:
    """One run per experiment, in a v2-only store. The v1 mlruns/ store is not touched."""
    both = criteria[criteria["comparison"] == GROUP_FOLD_2].set_index("model")
    first = criteria.drop_duplicates("model").set_index("model")
    for name, part in log.groupby("experiment", sort=False):
        row = both.loc[name] if name in both.index else first.loc[name]
        log_run(
            run_name=name,
            params={"model": part["model"].iloc[0], "feature_set": part["feature_set"].iloc[0], "target": part["target"].iloc[0], "training_rows": part["training_rows"].iloc[0],
                    "hyperparameters_by_fold": {r.fold: r.hyperparameters for r in part.itertuples()}, "config_sha256": config_hash[:12], "dataset_sha256": dataset_hash[:12]},
            metrics={"mae_ratio_all_rows": row[f"mae_ratio_{ALL_SCENARIO}"], "mae_ratio_clean_rows": row[f"mae_ratio_{CLEAN_SCENARIO}"],
                     "mape_all_rows": row[f"mape_{ALL_SCENARIO}"], "mape_clean_rows": row[f"mape_{CLEAN_SCENARIO}"]},
            tags={"dataset": "v2", "comparison": row["comparison"], "final_test_used": "false"},
            mlruns_dir=mlruns_dir, fallback_log_dir=fallback_dir,
        )


def run(dataset_csv: Path = DATASET_CSV, output_dir: Path = OUTPUT_DIR, mlruns_dir: Path = MLRUNS_V2_DIR) -> dict:
    """Run the experiments. Writes only to output_dir and mlruns_dir."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    baseline_config = load_baseline_config()
    df = load_dataset(dataset_csv, baseline_config["expected_dataset_sha256"])

    wide, log, coefficients = run_ridge_experiments(df, config, baseline_config)
    evaluations = {name: evaluate_group(wide, group, baseline_config) for name, group in comparison_groups(config).items()}
    criteria = pd.concat([success_criteria(e, name) for name, e in evaluations.items()], ignore_index=True)
    # Decided from Ridge results alone, before any XGBoost model exists.
    gate = xgboost_gate(criteria)
    if gate["open"]:
        wide, xgboost_log = run_xgboost_experiments(wide, config, baseline_config)
        log = pd.concat([log, xgboost_log], ignore_index=True)
        evaluations = {name: evaluate_group(wide, group, baseline_config) for name, group in comparison_groups(config, include_xgboost=True).items()}
        criteria = pd.concat([success_criteria(e, name) for name, e in evaluations.items()], ignore_index=True)
    size_rule = size_rule_change_ranking(evaluations[GROUP_BOTH_FOLDS]["results"]["rows"])

    tables = _write_tables(evaluations, log, coefficients, criteria, size_rule, output_dir)
    figures = write_figures(evaluations, output_dir / "figures")
    config_hash = hashlib.sha256(CONFIG_YAML.read_bytes()).hexdigest()
    dataset_hash = hashlib.sha256(dataset_csv.read_bytes()).hexdigest()
    _log_to_mlflow(criteria, log, config_hash, dataset_hash, mlruns_dir, output_dir / "tracking_fallback")

    years = sorted(int(y) for e in evaluations.values() for y in e["results"]["rows"]["target_year"].unique())
    manifest = {
        "run_date": date.today().isoformat(), "dataset_sha256": dataset_hash, "config_sha256": config_hash,
        "experiments": int(log["experiment"].nunique()), "fits": len(log), "target_years_evaluated": sorted(set(years)), "final_test_evaluated": False,
        "rows_by_comparison": {name: int(len(e["results"]["rows"])) for name, e in evaluations.items()},
        "xgboost_gate": gate, "xgboost_run": bool(gate["open"]), "tables": tables, "figures": figures,
    }
    (output_dir / "ml_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("Ran %d experiments. XGBoost gate open: %s", manifest["experiments"], gate["open"])
    return manifest


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
