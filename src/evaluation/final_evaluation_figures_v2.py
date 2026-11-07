"""Charts for the final evaluation, drawn only from its saved results.

Kept apart from the frozen evaluation code, because a chart's layout cannot change
any result. This module reads saved tables and computes no model or metric.

Run with: python -m src.evaluation.final_evaluation_figures_v2
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.baseline_evaluation_v2 import VEHICLES, _style
from src.evaluation.final_evaluation_v2 import OUTPUT_DIR

MODELS = ["previous_year", "moving_average", "ridge_log_change_level"]
LABELS = {"previous_year": "Previous year", "moving_average": "Moving average", "ridge_log_change_level": "Ridge, log change"}
COLOURS = {"previous_year": "#2a78d6", "moving_average": "#eb6834", "ridge_log_change_level": "#1baf7a"}
SCENARIOS = ["all_rows", "no_flagged_target", "no_flagged_target_or_input", "also_no_outlier_candidates"]
SCENARIO_LABELS = ["All rows", "No flagged\ntarget", "No flagged target\nor input", "Also no outlier\ncandidates"]


def write_figures(output_dir: Path = OUTPUT_DIR) -> list[str]:
    plt = _style()
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def save(fig, name):
        fig.savefig(figure_dir / name, dpi=160, bbox_inches="tight")
        plt.close(fig)
        written.append(name)

    metrics = pd.read_csv(output_dir / "metrics_final.csv")
    overall = metrics[metrics["group"] == "All"]

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9))
    for ax, column, title in zip(axes, ("mape", "mae"), ("MAPE (%)", "MAE (licences)")):
        for model in MODELS:
            values = [overall[(overall["scenario"] == s) & (overall["model"] == model)][column].iloc[0] for s in SCENARIOS]
            ax.plot(range(len(SCENARIOS)), values, marker="o", markersize=6, linewidth=2, color=COLOURS[model], label=LABELS[model])
        ax.set_xticks(range(len(SCENARIOS)))
        ax.set_xticklabels(SCENARIO_LABELS, fontsize=8.5)
        ax.set(title=title, ylim=(0, None))
        ax.grid(axis="x", visible=False)
    axes[1].legend(loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.suptitle("Target year 2023: error by model and rows scored", x=0.01, ha="left", fontsize=11.5, fontweight="semibold")
    fig.tight_layout()
    save(fig, "fig01_error_by_scenario.png")

    part = metrics[(metrics["scenario"] == "all_rows") & metrics["group"].isin(VEHICLES)]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9))
    width = 0.8 / len(MODELS)
    for ax, column, title in zip(axes, ("mape", "mase"), ("MAPE (%) by vehicle type", "MASE by vehicle type")):
        for i, model in enumerate(MODELS):
            values = [part[(part["group"] == v) & (part["model"] == model)][column].iloc[0] for v in VEHICLES]
            bars = ax.bar(np.arange(len(VEHICLES)) + (i - 1) * width, values, width * 0.92, color=COLOURS[model], label=LABELS[model])
            ax.bar_label(bars, fmt="%.2f", fontsize=8, color="#52514e", padding=1.5)
        ax.set_xticks(range(len(VEHICLES)))
        ax.set_xticklabels(VEHICLES)
        ax.set(title=title)
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper center", bbox_to_anchor=(1.1, -0.1), ncol=3)
    save(fig, "fig02_error_by_vehicle.png")

    bootstrap = pd.read_csv(output_dir / "bootstrap_against_previous_year.csv")
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    shown = bootstrap[bootstrap["scenario"].isin(["all_rows", "no_flagged_target_or_input"])]
    labels, y = [], 0
    for model in MODELS[1:]:
        for scenario, name in (("all_rows", "all rows"), ("no_flagged_target_or_input", "no flagged rows")):
            row = shown[(shown["model"] == model) & (shown["scenario"] == scenario)].iloc[0]
            ax.errorbar(row["mae_ratio"], y, xerr=[[row["mae_ratio"] - row["mae_ratio_low"]], [row["mae_ratio_high"] - row["mae_ratio"]]], fmt="o", color=COLOURS[model], markersize=6, linewidth=1.8)
            labels.append(f"{LABELS[model]}, {name}")
            y += 1
    ax.axvline(1, color="#52514e", linewidth=1)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set(title="MAE ratio to previous year, with 95% interval (below 1 is better)", xlabel="MAE ratio")
    ax.grid(axis="y", visible=False)
    save(fig, "fig03_mae_ratio_intervals.png")

    ranking = pd.read_csv(output_dir / "ranking_final.csv")
    ranking = ranking[ranking["scenario"] == "all_rows"]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9))
    for i, model in enumerate(MODELS):
        values = [ranking[(ranking["vehicle_type"] == v) & (ranking["model"] == model)]["spearman_level"].iloc[0] for v in VEHICLES]
        bars = axes[0].bar(np.arange(len(VEHICLES)) + (i - 1) * width, values, width * 0.92, color=COLOURS[model], label=LABELS[model])
        axes[0].bar_label(bars, fmt="%.3f", fontsize=8, color="#52514e", padding=1.5)
    axes[0].set(title="Ranking next year's level (Spearman)", ylim=(0, 1.12))
    for i, model in enumerate(MODELS[1:]):
        values = [ranking[(ranking["vehicle_type"] == v) & (ranking["model"] == model)]["spearman_change"].iloc[0] for v in VEHICLES]
        bars = axes[1].bar(np.arange(len(VEHICLES)) + (i - 0.5) * width, values, width * 0.92, color=COLOURS[model])
        axes[1].bar_label(bars, fmt="%.2f", fontsize=8, color="#52514e", padding=1.5)
    axes[1].axhline(0, color="#52514e", linewidth=1)
    axes[1].set(title="Ranking next year's change (Spearman)", ylim=(-1, 1))
    for ax in axes:
        ax.set_xticks(range(len(VEHICLES)))
        ax.set_xticklabels(VEHICLES)
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper center", bbox_to_anchor=(1.1, -0.1), ncol=3)
    save(fig, "fig04_ranking.png")

    districts = pd.read_csv(output_dir / "errors_by_district.csv")
    table = districts.pivot_table(index="district", columns="model", values="mape")[MODELS].sort_values("previous_year")
    fig, ax = plt.subplots(figsize=(8.4, 7))
    y = np.arange(len(table))
    for i, model in enumerate(MODELS):
        ax.scatter(table[model], y, s=26, color=COLOURS[model], label=LABELS[model], zorder=3, edgecolor="#fcfcfb", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(table.index)
    ax.set(title="MAPE by district, mean of its vehicle types, target 2023", xlabel="MAPE (%)")
    ax.legend(loc="lower right")
    save(fig, "fig05_error_by_district.png")
    return written


if __name__ == "__main__":
    print(write_figures())
