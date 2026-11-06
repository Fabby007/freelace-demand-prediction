"""Baseline evaluation on Dataset v2 (REF-009 ADR-039).

Compares simple forecasts of next-year revenue licences using chronological
rolling-origin folds. Nothing is fitted: each prediction for year t + 1 uses only
values up to year t, and error scales use only years up to the fold's origin.

Target year 2023 is held back as the final test. `evaluate()` refuses it unless
`include_final_test=True`, and the default run never asks for it.

Dataset v1, its models and its results are not read or changed.

Run with: python -m src.evaluation.baseline_evaluation_v2
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_YAML = REPO_ROOT / "configs" / "baseline_v2.yaml"
DATASET_CSV = REPO_ROOT / "data" / "processed" / "v2" / "modelling_dataset_v2.csv"
CELLS_CSV = REPO_ROOT / "data" / "interim" / "dcs_extracted_cells_2024_v2.csv"
OUTPUT_DIR = REPO_ROOT / "reports" / "baseline_v2"

VEHICLES = ["Motorcycle", "Car", "Three-wheeler"]
GROUP_ALL = "All"
SERIES = ["district", "vehicle_type"]
FROZEN_2019 = "frozen_2019_order"
METRICS = ["mae", "mase", "mape", "median_ape"]
CHANGE_DECIMALS = 9


def load_config(path: Path = CONFIG_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_dataset(path: Path = DATASET_CSV, expected_sha256: str | None = None) -> pd.DataFrame:
    """Read-only. Stops if the file is not the frozen Dataset v2."""
    if expected_sha256 is not None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise ValueError(f"{path.name} is not the frozen Dataset v2: {actual[:12]}")
    df = pd.read_csv(path)
    df["licence_flag_ids"] = df["licence_flag_ids"].fillna("")
    return df


# --- Predictions --------------------------------------------------------------

def add_predictions(df: pd.DataFrame) -> pd.DataFrame:
    """One forecast of target_licence_count per model, for each row of year t.

    - previous_year: this year's count.
    - moving_average: mean over t-2 to t (needs at least two observed years).
    - growth_series: this year's count, grown by this series' latest growth.
    - growth_vehicle_median: this year's count, grown by the median district growth
      for the same vehicle type in year t. Less noisy than one series' own growth.
    """
    out = df.copy()
    out["previous_year"] = out["licence_count"]
    out["moving_average"] = out["licence_rolling_mean_3"]
    out["growth_series"] = out["licence_count"] * np.exp(out["licence_growth_log"])
    median_growth = out.groupby(["vehicle_type", "year"])["licence_growth_log"].transform("median")
    out["growth_vehicle_median"] = out["licence_count"] * np.exp(median_growth)
    return out


def _fold_rows(predictions: pd.DataFrame, fold: dict, models: list[str]) -> pd.DataFrame:
    """Rows of one fold that have a target and every model's prediction, so that
    all models are compared on identical rows."""
    rows = predictions[(predictions["year"] == fold["origin_year"]) & (predictions["target_year"] == fold["target_year"])]
    return rows.dropna(subset=["target_licence_count"] + models).copy()


def candidate_keys(config: dict) -> set[tuple]:
    return {(c["district"], c["vehicle_type"], c["year"]) for c in config["outlier_candidates"]}


def add_candidate_columns(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Marks rows whose target or inputs (t-2 to t) include an EDA outlier candidate."""
    keys = candidate_keys(config)
    out = df.copy()

    def touches(row) -> bool:
        years = [row.year - 2, row.year - 1, row.year, row.year + 1]
        return any((row.district, row.vehicle_type, year) in keys for year in years)

    out["touches_outlier_candidate"] = [touches(r) for r in out.itertuples()]
    return out


def scenario_mask(rows: pd.DataFrame, scenario: str) -> pd.Series:
    """Which rows a sensitivity scenario keeps. Nothing is altered or filled in."""
    if scenario == "all_rows":
        return pd.Series(True, index=rows.index)
    if scenario == "no_flagged_target":
        return ~rows["target_flagged"]
    if scenario == "no_flagged_target_or_input":
        return ~rows["target_flagged"] & ~rows["features_use_flagged_licence"]
    if scenario == "also_no_outlier_candidates":
        return ~rows["target_flagged"] & ~rows["features_use_flagged_licence"] & ~rows["touches_outlier_candidate"]
    raise ValueError(f"Unknown scenario: {scenario}")


def _excluded_history(df: pd.DataFrame, scenario: str, config: dict) -> pd.Series:
    """Values that a scenario also leaves out of the error scale."""
    if scenario in ("all_rows", "no_flagged_target"):
        return pd.Series(False, index=df.index)
    excluded = df["licence_flagged"].copy()
    if scenario == "also_no_outlier_candidates":
        keys = candidate_keys(config)
        excluded |= pd.Series([(r.district, r.vehicle_type, r.year) in keys for r in df.itertuples()], index=df.index)
    return excluded


def history_scale(df: pd.DataFrame, origin_year: int, vehicle_type: str | None = None, excluded: pd.Series | None = None) -> float:
    """MASE scale: mean absolute one-year change, using only years up to origin_year.
    Pooled over series, because each series has too few years for its own scale."""
    history = df[df["year"] <= origin_year].copy()
    if vehicle_type is not None:
        history = history[history["vehicle_type"] == vehicle_type]
    values = history["licence_count"]
    if excluded is not None:
        values = values.where(~excluded.reindex(history.index))
    changes = values.groupby([history["district"], history["vehicle_type"]]).diff().abs().dropna()
    return float(changes.mean())


# --- Metrics ------------------------------------------------------------------

def accuracy_metrics(actual: pd.Series, predicted: pd.Series, scale: float) -> dict:
    errors = (predicted - actual).abs()
    pct = errors / actual * 100
    return {
        "n": int(len(actual)),
        "mae": float(errors.mean()),
        "mase": float(errors.mean() / scale),
        "mape": float(pct.mean()),
        "median_ape": float(pct.median()),
    }


def top_n_overlap(actual: pd.Series, predicted: pd.Series, n: int) -> float:
    """Share of the actual top n also in the predicted top n."""
    return len(set(actual.nlargest(n).index) & set(predicted.nlargest(n).index)) / n


def ranking_metrics(rows: pd.DataFrame, model: str, top_n: list[int], change_top_n: int) -> dict:
    """Ranking quality within one vehicle type and target year."""
    actual, predicted = rows["target_licence_count"], rows[model]
    out = {f"top_{n}_overlap": top_n_overlap(actual, predicted, n) for n in top_n}
    out["spearman_level"] = float(stats.spearmanr(actual, predicted).statistic)
    actual_change = actual / rows["licence_count"]
    predicted_change = predicted / rows["licence_count"]
    # Rounded first: a change that is really the same for all districts can differ in the
    # last floating-point digits, which would otherwise look like a ranking.
    rounded_change = predicted_change.round(CHANGE_DECIMALS)
    # previous_year and growth_vehicle_median give every district the same change, so
    # they cannot rank change. These metrics stay empty for them rather than scoring noise.
    ranks_change = rounded_change.nunique() > 1
    out["spearman_change"] = float(stats.spearmanr(actual_change, predicted_change).statistic) if ranks_change else np.nan
    out[f"change_top_{change_top_n}_overlap"] = top_n_overlap(actual_change, predicted_change, change_top_n) if ranks_change else np.nan
    # Direction only needs a predicted direction, which previous_year does not have.
    moved = (actual_change != 1) & (rounded_change != 1)
    out["direction_accuracy"] = float(((predicted_change - 1)[moved] * (actual_change - 1)[moved] > 0).mean()) if moved.any() else np.nan
    return out


def evaluate(predictions: pd.DataFrame, config: dict, include_final_test: bool = False) -> dict[str, pd.DataFrame]:
    """All metrics for every fold, scenario, vehicle type and model."""
    folds = list(config["development_folds"])
    if include_final_test:
        folds.append(config["final_test_fold"])
    final_year = config["final_test_fold"]["target_year"]
    if not include_final_test and any(f["target_year"] >= final_year for f in folds):
        raise ValueError("A development fold reaches the final test year.")

    models = config["models"]
    accuracy, ranking, row_table = [], [], []
    for fold in folds:
        rows = add_candidate_columns(_fold_rows(predictions, fold, models), config)
        if rows.empty:
            raise ValueError(f"{fold['name']} has no rows.")
        row_table.append(rows.assign(fold=fold["name"]))
        for scenario in [s["name"] for s in config["scenarios"]]:
            kept = rows[scenario_mask(rows, scenario)]
            excluded = _excluded_history(predictions, scenario, config)
            for group in [GROUP_ALL] + VEHICLES:
                part = kept if group == GROUP_ALL else kept[kept["vehicle_type"] == group]
                scale = history_scale(predictions, fold["origin_year"], None if group == GROUP_ALL else group, excluded)
                for model in models:
                    accuracy.append({"fold": fold["name"], "target_year": fold["target_year"], "scenario": scenario, "group": group,
                                     "model": model, "scale": scale, **accuracy_metrics(part["target_licence_count"], part[model], scale)})
            for vehicle in VEHICLES:
                part = kept[kept["vehicle_type"] == vehicle]
                for model in models:
                    ranking.append({"fold": fold["name"], "target_year": fold["target_year"], "scenario": scenario, "vehicle_type": vehicle,
                                    "model": model, "n": len(part), **ranking_metrics(part, model, config["top_n"], config["change_top_n"])})
    return {"accuracy": pd.DataFrame(accuracy), "ranking": pd.DataFrame(ranking), "rows": pd.concat(row_table, ignore_index=True)}


def summarise(results: dict[str, pd.DataFrame], config: dict) -> dict[str, pd.DataFrame]:
    """Means across folds, weighting each fold equally, plus skill against the reference."""
    accuracy = results["accuracy"].groupby(["scenario", "group", "model"], sort=False)[METRICS + ["n"]].mean().reset_index()
    reference = accuracy[accuracy["model"] == config["reference_model"]].set_index(["scenario", "group"])["mae"]
    accuracy["mae_relative_to_reference"] = accuracy["mae"] / [reference[(s, g)] for s, g in zip(accuracy["scenario"], accuracy["group"])]
    columns = [c for c in results["ranking"].columns if c not in ("fold", "target_year", "scenario", "vehicle_type", "model", "n")]
    ranking_by_vehicle = results["ranking"].groupby(["scenario", "vehicle_type", "model"], sort=False)[columns].mean().reset_index()
    ranking = results["ranking"].groupby(["scenario", "model"], sort=False)[columns].mean().reset_index()
    return {"accuracy": accuracy, "ranking": ranking, "ranking_by_vehicle": ranking_by_vehicle}


def bootstrap_against_reference(rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    """95% intervals for MAE and absolute percentage error against the reference.
    Whole series are resampled, because rows from one series are related."""
    generator = np.random.default_rng(config["bootstrap_seed"])
    reference = config["reference_model"]
    output = []
    for scenario in [s["name"] for s in config["scenarios"]]:
        kept = rows[scenario_mask(rows, scenario)]
        series = kept.groupby(SERIES, sort=True).ngroup().to_numpy()
        n_series = series.max() + 1
        weights = generator.multinomial(n_series, np.full(n_series, 1 / n_series), size=config["bootstrap_resamples"])
        counts = np.bincount(series, minlength=n_series)
        for model in config["models"]:
            if model == reference:
                continue
            per_model = {}
            for name in (model, reference):
                error = (kept[name] - kept["target_licence_count"]).abs().to_numpy()
                pct = error / kept["target_licence_count"].to_numpy() * 100
                per_model[name] = (np.bincount(series, error, minlength=n_series), np.bincount(series, pct, minlength=n_series))
            denominator = weights @ counts
            ratio = (weights @ per_model[model][0]) / (weights @ per_model[reference][0])
            mape_gap = ((weights @ per_model[model][1]) - (weights @ per_model[reference][1])) / denominator
            output.append({
                "scenario": scenario, "model": model, "reference": reference, "n_rows": len(kept), "n_series": int(n_series),
                "mae_ratio": per_model[model][0].sum() / per_model[reference][0].sum(),
                "mae_ratio_low": np.percentile(ratio, 2.5), "mae_ratio_high": np.percentile(ratio, 97.5),
                "mape_gap_points": (per_model[model][1].sum() - per_model[reference][1].sum()) / counts.sum(),
                "mape_gap_low": np.percentile(mape_gap, 2.5), "mape_gap_high": np.percentile(mape_gap, 97.5),
            })
    return pd.DataFrame(output)


def district_table(rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Absolute percentage error by district, vehicle type and model, across development folds."""
    records = []
    for model in config["models"]:
        ape = (rows[model] - rows["target_licence_count"]).abs() / rows["target_licence_count"] * 100
        records.append(rows.assign(model=model, ape=ape, ae=(rows[model] - rows["target_licence_count"]).abs()))
    long = pd.concat(records, ignore_index=True)
    return long.groupby(["district", "vehicle_type", "model"], sort=True).agg(
        n=("ape", "size"), mae=("ae", "mean"), mape=("ape", "mean"),
        any_flag=("target_flagged", "max"), any_input_flag=("features_use_flagged_licence", "max"),
    ).reset_index()


def flagged_comparison(rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Errors on rows with and without a flagged target or input, using the same rows for every model."""
    any_flag = rows["target_flagged"] | rows["features_use_flagged_licence"]
    records = []
    for model in config["models"]:
        ape = (rows[model] - rows["target_licence_count"]).abs() / rows["target_licence_count"] * 100
        for flagged, label in ((False, "no_flagged_target_or_input"), (True, "flagged_target_or_input")):
            part = ape[any_flag == flagged]
            records.append({"model": model, "rows": label, "n": len(part), "mape": part.mean(), "median_ape": part.median(), "max_ape": part.max()})
    return pd.DataFrame(records)


def rank_structure(predictions: pd.DataFrame, rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Does ranking on levels mostly repeat a fixed order? Compares this year's order
    with the order frozen at 2019, on rows where both exist, and measures rank change."""
    frozen = predictions[predictions["year"] == 2019].set_index(SERIES)["licence_count"].rename(FROZEN_2019)
    table = rows.join(frozen, on=SERIES).dropna(subset=[FROZEN_2019])
    output = []
    for (fold, vehicle), part in table.groupby(["fold", "vehicle_type"], sort=False):
        if len(part) < max(config["top_n"]):
            continue
        actual = part["target_licence_count"]
        actual_rank, previous_rank = actual.rank(ascending=False), part["licence_count"].rank(ascending=False)
        record = {"fold": fold, "vehicle_type": vehicle, "n": len(part),
                  "spearman_previous_year": stats.spearmanr(actual, part["previous_year"]).statistic,
                  "spearman_frozen_2019": stats.spearmanr(actual, part[FROZEN_2019]).statistic,
                  "share_districts_changing_rank": float((actual_rank != previous_rank).mean()),
                  "mean_absolute_rank_change": float((actual_rank - previous_rank).abs().mean())}
        for n in config["top_n"]:
            record[f"top_{n}_previous_year"] = top_n_overlap(actual, part["previous_year"], n)
            record[f"top_{n}_frozen_2019"] = top_n_overlap(actual, part[FROZEN_2019], n)
        output.append(record)
    return pd.DataFrame(output)


def review_outlier_candidates(df: pd.DataFrame, cells: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Evidence for each EDA candidate: the printed value, and whether the rest of the
    table moved the same way. The judgement is the recorded reading of the PDF page."""
    table_cells = cells[cells["metric"] == "vehicle_population"]
    output = []
    for candidate in config["outlier_candidates"]:
        district, vehicle, year = candidate["district"], candidate["vehicle_type"], candidate["year"]
        row = df[(df["district"] == district) & (df["vehicle_type"] == vehicle) & (df["year"] == year)].iloc[0]
        previous = df[(df["district"] == district) & (df["vehicle_type"] == vehicle) & (df["year"] == year - 1)].iloc[0]
        table = table_cells[table_cells["district"] == district]
        now = table[table["year"] == year].set_index("row_label")["number"]
        before = table[table["year"] == year - 1].set_index("row_label")["number"]
        categories = now.drop("Total").index
        change = (now[categories] / before[categories] - 1) * 100
        own_change = (row["licence_count_printed"] / previous["licence_count_printed"] - 1) * 100
        same_direction = int(((change > 0) == (own_change > 0)).sum())
        output.append({
            "district": district, "vehicle_type": vehicle, "year": year,
            "value_in_dataset": row["licence_count"], "value_printed": row["licence_count_printed"], "matches_pdf_extraction": bool(row["licence_count"] == row["licence_count_printed"]),
            "previous_year_value": previous["licence_count_printed"], "change_pct": round(float(own_change), 1),
            "table_rows_moving_same_way": same_direction, "table_rows": len(categories),
            "table_total_change_pct": round(float((now["Total"] / before["Total"] - 1) * 100), 1),
            "source_pdf": row["licence_source_file"], "source_page": row["licence_source_page"],
            "pattern": candidate["pattern"], "assessment": candidate["assessment"], "recommendation": candidate["recommendation"],
            "value_changed": False,
        })
    return pd.DataFrame(output)


# --- Charts -------------------------------------------------------------------

def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "axes.edgecolor": "#c3c2b7", "axes.labelcolor": "#52514e", "axes.titlecolor": "#0b0b0b", "axes.titlesize": 11.5,
        "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.7,
        "xtick.color": "#52514e", "ytick.color": "#52514e", "xtick.bottom": False, "ytick.left": False, "legend.frameon": False,
    })
    return plt


MODEL_COLOURS = {"previous_year": "#2a78d6", "moving_average": "#eb6834", "growth_series": "#1baf7a", "growth_vehicle_median": "#eda100"}
MODEL_LABELS = {"previous_year": "Previous year", "moving_average": "Moving average", "growth_series": "Growth (own series)", "growth_vehicle_median": "Growth (vehicle median)"}


def _grouped_bars(ax, table: pd.DataFrame, categories: list, category_col: str, value: str, models: list[str], fmt: str = "{:.1f}"):
    width = 0.8 / len(models)
    for i, model in enumerate(models):
        values = [table[(table[category_col] == c) & (table["model"] == model)][value].iloc[0] for c in categories]
        positions = np.arange(len(categories)) + (i - (len(models) - 1) / 2) * width
        bars = ax.bar(positions, values, width * 0.92, color=MODEL_COLOURS[model], label=MODEL_LABELS[model])
        ax.bar_label(bars, labels=[fmt.format(v) if pd.notna(v) else "" for v in values], fontsize=7.5, color="#52514e", padding=1.5)
    ax.set_xticks(range(len(categories)))
    ax.grid(axis="x", visible=False)


def write_figures(results: dict, summary: dict, districts: pd.DataFrame, structure: pd.DataFrame, config: dict, figure_dir: Path) -> list[str]:
    plt = _style()
    figure_dir.mkdir(parents=True, exist_ok=True)
    models = config["models"]
    written = []

    def save(fig, name):
        fig.savefig(figure_dir / name, dpi=160, bbox_inches="tight")
        plt.close(fig)
        written.append(name)

    accuracy = results["accuracy"]
    all_rows = accuracy[(accuracy["scenario"] == "all_rows") & (accuracy["group"] == GROUP_ALL)]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
    folds = [f["name"] for f in config["development_folds"]]
    for ax, metric, title in zip(axes, ("mape", "median_ape"), ("Mean absolute % error", "Median absolute % error")):
        _grouped_bars(ax, all_rows, folds, "fold", metric, models)
        ax.set_xticklabels([f"Target {f['target_year']} (n = {all_rows[all_rows['fold'] == f['name']]['n'].iloc[0]})" for f in config["development_folds"]])
        ax.set(title=title, ylabel="%")
    axes[1].legend(loc="upper left", bbox_to_anchor=(1.01, 1))
    save(fig, "fig01_error_by_fold.png")

    summary_accuracy = summary["accuracy"]
    fig, ax = plt.subplots(figsize=(9, 3.9))
    part = summary_accuracy[(summary_accuracy["scenario"] == "all_rows") & summary_accuracy["group"].isin(VEHICLES)]
    _grouped_bars(ax, part, VEHICLES, "group", "mape", models)
    ax.set_xticklabels(VEHICLES)
    ax.set(title="Mean absolute % error by vehicle type (mean of two folds)", ylabel="%")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1))
    save(fig, "fig02_error_by_vehicle.png")

    scenarios = [s["name"] for s in config["scenarios"]]
    labels = ["All rows", "No flagged\ntarget", "No flagged target\nor input", "Also no outlier\ncandidates"]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
    part = summary_accuracy[summary_accuracy["group"] == GROUP_ALL]
    for ax, metric, title in zip(axes, ("mape", "mae"), ("Mean absolute % error", "MAE (licences)")):
        for model in models:
            values = [part[(part["scenario"] == s) & (part["model"] == model)][metric].iloc[0] for s in scenarios]
            ax.plot(range(len(scenarios)), values, marker="o", markersize=6, linewidth=2, color=MODEL_COLOURS[model], label=MODEL_LABELS[model])
        ax.set_xticks(range(len(scenarios)))
        ax.set_xticklabels(labels, fontsize=8.5)
        ax.set(title=title, ylim=(0, None))
        ax.grid(axis="x", visible=False)
    axes[1].legend(loc="upper left", bbox_to_anchor=(1.01, 1))
    save(fig, "fig03_sensitivity_to_flagged_rows.png")

    ranking = summary["ranking_by_vehicle"]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
    part = ranking[ranking["scenario"] == "all_rows"]
    _grouped_bars(axes[0], part, VEHICLES, "vehicle_type", "spearman_level", models, "{:.2f}")
    axes[0].set_xticklabels(VEHICLES)
    axes[0].set(title="Ranking next year's LEVEL", ylabel="Spearman correlation", ylim=(0, 1.1))
    change_models = [m for m in models if part[part["model"] == m]["spearman_change"].notna().any()]
    _grouped_bars(axes[1], part, VEHICLES, "vehicle_type", "spearman_change", change_models, "{:.2f}")
    axes[1].set_xticklabels(VEHICLES)
    axes[1].axhline(0, color="#898781", linewidth=1)
    axes[1].set(title="Ranking next year's CHANGE (only these two can)", ylim=(-1, 1.1))
    axes[0].legend(loc="upper center", bbox_to_anchor=(1.05, -0.1), ncol=4, fontsize=9)
    save(fig, "fig04_ranking_level_vs_change.png")

    table = districts[districts["model"] == config["reference_model"]].copy()
    summary_by_district = table.groupby("district").agg(mape=("mape", "mean"), flagged=("any_flag", "max"), input_flag=("any_input_flag", "max")).sort_values("mape")
    fig, ax = plt.subplots(figsize=(7.6, 6.6))
    colours = ["#eb6834" if (a or b) else "#2a78d6" for a, b in zip(summary_by_district["flagged"], summary_by_district["input_flag"])]
    ax.barh(summary_by_district.index, summary_by_district["mape"], color=colours, height=0.76)
    ax.set(title="Previous-year error by district (mean of its series and folds)", xlabel="Mean absolute % error", ylabel="")
    ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color="#2a78d6"), plt.Rectangle((0, 0), 1, 1, color="#eb6834")]
    ax.legend(handles, ["No flagged target or input", "Has a flagged target or input"], loc="lower right")
    save(fig, "fig05_error_by_district.png")

    fig, ax = plt.subplots(figsize=(7.8, 3.8))
    means = structure.groupby("vehicle_type")[["spearman_previous_year", "spearman_frozen_2019"]].mean().loc[VEHICLES]
    positions = np.arange(len(VEHICLES))
    for offset, column, colour, label in ((-0.2, "spearman_previous_year", "#2a78d6", "Previous year's order"), (0.2, "spearman_frozen_2019", "#eb6834", "Order frozen at 2019")):
        bars = ax.bar(positions + offset, means[column], 0.36, color=colour, label=label)
        ax.bar_label(bars, fmt="%.3f", fontsize=8.5, color="#52514e", padding=1.5)
    ax.set_xticks(positions)
    ax.set_xticklabels(VEHICLES)
    ax.set(title="A ranking frozen in 2019 almost matches next year's order", ylabel="Spearman with actual", ylim=(0, 1.1))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2)
    ax.grid(axis="x", visible=False)
    save(fig, "fig06_rank_structure.png")
    return written


# --- Pipeline -----------------------------------------------------------------

def run(
    dataset_csv: Path = DATASET_CSV,
    cells_csv: Path = CELLS_CSV,
    output_dir: Path = OUTPUT_DIR,
    include_final_test: bool = False,
) -> dict:
    """Evaluate the baselines and write results under output_dir only."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    df = load_dataset(dataset_csv, config["expected_dataset_sha256"])
    cells = pd.read_csv(cells_csv, dtype=str, keep_default_na=False)
    cells["year"] = cells["year"].astype(int)
    cells["number"] = pd.to_numeric(cells["value_numeric"], errors="coerce")

    predictions = add_predictions(df)
    results = evaluate(predictions, config, include_final_test=include_final_test)
    summary = summarise(results, config)
    rows = results["rows"]
    bootstrap = bootstrap_against_reference(rows, config)
    districts = district_table(rows, config)
    structure = rank_structure(predictions, rows, config)
    candidates = review_outlier_candidates(df, cells, config)
    flagged = flagged_comparison(rows, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    keep = ["fold", "district", "vehicle_type", "year", "target_year", "licence_count", "target_licence_count"] + config["models"] + [
        "target_flagged", "features_use_flagged_licence", "touches_outlier_candidate"]
    tables = {
        "predictions.csv": rows[keep], "metrics_by_fold.csv": results["accuracy"], "metrics_summary.csv": summary["accuracy"],
        "ranking_by_fold.csv": results["ranking"], "ranking_summary.csv": summary["ranking"], "ranking_by_vehicle.csv": summary["ranking_by_vehicle"],
        "bootstrap_against_previous_year.csv": bootstrap, "errors_by_district.csv": districts, "rank_structure.csv": structure, "flagged_vs_unflagged.csv": flagged,
        "outlier_candidate_review.csv": candidates, "feature_selection.csv": pd.DataFrame(config["feature_selection"]),
    }
    for name, table in tables.items():
        table.round(4).to_csv(output_dir / name, index=False, lineterminator="\n")
    figures = write_figures(results, summary, districts, structure, config, output_dir / "figures")

    manifest = {
        "run_date": date.today().isoformat(),
        "dataset_sha256": hashlib.sha256(dataset_csv.read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(CONFIG_YAML.read_bytes()).hexdigest(),
        "folds_evaluated": sorted(rows["fold"].unique().tolist()),
        "target_years_evaluated": sorted(int(y) for y in rows["target_year"].unique()),
        "final_test_evaluated": bool(include_final_test),
        "evaluation_rows": int(len(rows)),
        "tables": sorted(tables),
        "figures": figures,
    }
    (output_dir / "baseline_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("Evaluated %d rows; final test used: %s", len(rows), include_final_test)
    return manifest


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
