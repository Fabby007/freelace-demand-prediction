"""Tests for the Dataset v2 baseline evaluation.

Calculation tests use small, clearly artificial tables that exist only to exercise
the formulas. Real-data tests read Dataset v2 and write only to tmp_path.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.evaluation.baseline_evaluation_v2 import (
    CELLS_CSV,
    CONFIG_YAML,
    DATASET_CSV,
    GROUP_ALL,
    OUTPUT_DIR,
    REPO_ROOT,
    VEHICLES,
    accuracy_metrics,
    add_candidate_columns,
    add_predictions,
    bootstrap_against_reference,
    evaluate,
    flagged_comparison,
    history_scale,
    load_config,
    load_dataset,
    ranking_metrics,
    review_outlier_candidates,
    run,
    scenario_mask,
    summarise,
    top_n_overlap,
)

REPORT = OUTPUT_DIR / "baseline_evaluation_report.md"
needs_data = pytest.mark.skipif(not (DATASET_CSV.exists() and CELLS_CSV.exists()), reason="Dataset v2 not present locally")


@pytest.fixture(scope="module")
def config():
    return load_config()


def synthetic_panel(districts=12, seed=0):
    """Artificial panel with every column the evaluation needs."""
    generator = np.random.default_rng(seed)
    rows = []
    for d in range(districts):
        for v, vehicle in enumerate(VEHICLES):
            level = 1000.0 * (d + 1) * (v + 1)
            for year in range(2019, 2024):
                rows.append({"district": f"D{d:02d}", "vehicle_type": vehicle, "year": year, "licence_count": level})
                level *= np.exp(generator.normal(0, 0.05))
    df = pd.DataFrame(rows).sort_values(["district", "vehicle_type", "year"]).reset_index(drop=True)
    group = df.groupby(["district", "vehicle_type"])["licence_count"]
    df["licence_growth_log"] = np.log(df["licence_count"] / group.shift(1))
    df["licence_rolling_mean_3"] = group.transform(lambda s: s.rolling(3, min_periods=2).mean())
    df["target_licence_count"] = group.shift(-1)
    df["target_year"] = df["year"] + 1
    for column in ("licence_flagged", "target_flagged", "features_use_flagged_licence"):
        df[column] = False
    return df


# --- Predictions --------------------------------------------------------------

def _one_series():
    return pd.DataFrame({
        "district": "A", "vehicle_type": "Car", "year": [2019, 2020, 2021],
        "licence_count": [100.0, 110.0, 121.0],
        "licence_rolling_mean_3": [np.nan, 105.0, 110.3333],
        "licence_growth_log": [np.nan, np.log(1.1), np.log(1.1)],
    })


def test_previous_year_is_this_years_count():
    assert add_predictions(_one_series())["previous_year"].tolist() == [100.0, 110.0, 121.0]


def test_moving_average_is_the_rolling_mean_including_this_year():
    assert add_predictions(_one_series())["moving_average"].iloc[2] == pytest.approx(110.3333)


def test_growth_series_continues_the_latest_growth():
    assert add_predictions(_one_series())["growth_series"].iloc[2] == pytest.approx(121 * 1.1)


def test_growth_vehicle_median_uses_same_vehicle_and_year_only():
    df = pd.DataFrame({
        "district": ["A", "B", "C", "D"], "vehicle_type": ["Car", "Car", "Car", "Motorcycle"], "year": 2020,
        "licence_count": [100.0, 200.0, 300.0, 400.0], "licence_rolling_mean_3": 1.0,
        "licence_growth_log": [np.log(1.1), np.log(1.2), np.log(1.3), np.log(2.0)],
    })
    predicted = add_predictions(df)["growth_vehicle_median"].tolist()
    assert predicted[:3] == pytest.approx([120.0, 240.0, 360.0])  # median growth among cars is 1.2
    assert predicted[3] == pytest.approx(800.0)  # motorcycles do not affect cars


def test_changing_later_years_leaves_earlier_predictions_unchanged():
    df = synthetic_panel()
    original = add_predictions(df)
    changed = df.copy()
    later = changed["year"] > 2020
    changed.loc[later, ["licence_count", "licence_growth_log", "licence_rolling_mean_3"]] *= 3
    mutated = add_predictions(changed)
    models = ["previous_year", "moving_average", "growth_series", "growth_vehicle_median"]
    pd.testing.assert_frame_equal(original.loc[~later, models], mutated.loc[~later, models])


# --- Metrics ------------------------------------------------------------------

def test_accuracy_metrics_match_hand_calculation():
    actual, predicted = pd.Series([100.0, 200.0, 400.0]), pd.Series([110.0, 180.0, 400.0])
    out = accuracy_metrics(actual, predicted, scale=20.0)
    assert out["mae"] == pytest.approx(10.0)
    assert out["mase"] == pytest.approx(0.5)
    assert out["mape"] == pytest.approx((10 + 10 + 0) / 3)
    assert out["median_ape"] == pytest.approx(10.0)


def test_top_n_overlap():
    actual = pd.Series([50, 40, 30, 20, 10], index=list("abcde"))
    predicted = pd.Series([50, 40, 10, 30, 20], index=list("abcde"))
    assert top_n_overlap(actual, predicted, 2) == 1.0
    assert top_n_overlap(actual, predicted, 3) == pytest.approx(2 / 3)


def test_mase_scale_uses_only_years_up_to_the_origin():
    df = pd.DataFrame({
        "district": "A", "vehicle_type": "Car", "year": [2019, 2020, 2021, 2022],
        "licence_count": [100.0, 110.0, 130.0, 9999.0],
    })
    assert history_scale(df, 2020) == pytest.approx(10.0)
    assert history_scale(df, 2021) == pytest.approx(15.0)


def test_mase_scale_skips_missing_values_rather_than_bridging_them():
    df = pd.DataFrame({
        "district": "A", "vehicle_type": "Car", "year": [2019, 2020, 2021, 2022],
        "licence_count": [100.0, np.nan, 130.0, 150.0],
    })
    assert history_scale(df, 2022) == pytest.approx(20.0)


def _ranking_rows(prediction):
    return pd.DataFrame({
        "licence_count": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        "target_licence_count": [110.0, 190.0, 330.0, 400.0, 540.0, 590.0],
        "model": prediction,
    })


def test_previous_year_has_no_change_ranking_or_direction():
    rows = _ranking_rows([100.0, 200.0, 300.0, 400.0, 500.0, 600.0])
    out = ranking_metrics(rows, "model", [3], 2)
    assert out["spearman_level"] > 0.9
    assert np.isnan(out["spearman_change"])
    assert np.isnan(out["change_top_2_overlap"])
    assert np.isnan(out["direction_accuracy"])


def test_equal_growth_cannot_rank_change_even_with_floating_point_noise():
    """Regression: rounding noise in an identical growth rate once scored as a ranking."""
    base = np.array([100.0, 200.0, 300.0, 400.0, 500.0, 600.0])
    rows = _ranking_rows(base * np.exp(0.03) + np.array([0, 1e-11, 0, -1e-11, 0, 1e-11]))
    out = ranking_metrics(rows, "model", [3], 2)
    assert np.isnan(out["spearman_change"])
    assert not np.isnan(out["direction_accuracy"])  # it does predict a direction


def test_direction_accuracy_hand_calculation():
    rows = _ranking_rows([120.0, 180.0, 310.0, 410.0, 510.0, 610.0])
    # Actual moves: up, down, up, none, up, down. Predicted: up, down, up, up, up, up.
    # Ignoring the row with no actual move: 4 of 5 correct.
    assert ranking_metrics(rows, "model", [3], 2)["direction_accuracy"] == pytest.approx(0.8)


# --- Rows and scenarios -------------------------------------------------------

def test_every_model_is_scored_on_identical_rows(config):
    results = evaluate(add_predictions(synthetic_panel()), config)
    counts = results["accuracy"].groupby(["fold", "scenario", "group"])["n"].nunique()
    assert (counts == 1).all()


def test_a_row_missing_one_prediction_is_removed_for_all_models(config):
    panel = synthetic_panel()
    panel.loc[(panel["district"] == "D00") & (panel["year"] == 2020), "licence_rolling_mean_3"] = np.nan
    results = evaluate(add_predictions(panel), config)
    fold_1 = results["accuracy"][(results["accuracy"]["fold"] == "fold_1") & (results["accuracy"]["scenario"] == "all_rows") & (results["accuracy"]["group"] == GROUP_ALL)]
    assert set(fold_1["n"]) == {12 * 3 - 3}


def test_scenarios_only_remove_rows():
    rows = pd.DataFrame({
        "target_flagged": [False, True, False, False], "features_use_flagged_licence": [False, False, True, False],
        "touches_outlier_candidate": [False, False, False, True],
    })
    assert scenario_mask(rows, "all_rows").tolist() == [True, True, True, True]
    assert scenario_mask(rows, "no_flagged_target").tolist() == [True, False, True, True]
    assert scenario_mask(rows, "no_flagged_target_or_input").tolist() == [True, False, False, True]
    assert scenario_mask(rows, "also_no_outlier_candidates").tolist() == [True, False, False, False]
    with pytest.raises(ValueError):
        scenario_mask(rows, "unknown")


def test_candidate_marks_cover_target_and_inputs_only(config):
    rows = pd.DataFrame({"district": "Kandy", "vehicle_type": "Motorcycle", "year": [2019, 2020, 2021, 2022, 2023]})
    # The Kandy candidate is 2022: a target for 2021, an input for 2022 and 2023.
    assert add_candidate_columns(rows, config)["touches_outlier_candidate"].tolist() == [False, False, True, True, True]


# --- Final test protection ----------------------------------------------------

def test_final_test_year_is_refused_by_default(config):
    results = evaluate(add_predictions(synthetic_panel()), config)
    assert set(results["accuracy"]["target_year"]) == {2021, 2022}
    assert set(results["rows"]["target_year"]) == {2021, 2022}


def test_final_test_runs_only_when_explicitly_asked(config):
    results = evaluate(add_predictions(synthetic_panel()), config, include_final_test=True)
    assert 2023 in set(results["rows"]["target_year"])


def test_a_development_fold_reaching_the_final_year_is_an_error(config):
    bad = {**config, "development_folds": [{"name": "bad", "origin_year": 2022, "target_year": 2023}]}
    with pytest.raises(ValueError, match="final test year"):
        evaluate(add_predictions(synthetic_panel()), bad)


def test_changing_2023_values_cannot_change_development_results(config):
    panel = synthetic_panel()
    original = evaluate(add_predictions(panel), config)["accuracy"]
    changed = panel.copy()
    changed.loc[changed["year"] == 2023, "licence_count"] *= 50
    changed.loc[changed["year"] == 2022, "target_licence_count"] *= 50
    pd.testing.assert_frame_equal(original, evaluate(add_predictions(changed), config)["accuracy"])


# --- Summary and bootstrap ----------------------------------------------------

def test_reference_model_scores_one_against_itself(config):
    results = evaluate(add_predictions(synthetic_panel()), config)
    summary = summarise(results, config)["accuracy"]
    assert (summary[summary["model"] == config["reference_model"]]["mae_relative_to_reference"] == 1).all()


def test_bootstrap_is_repeatable_and_brackets_the_estimate(config):
    rows = evaluate(add_predictions(synthetic_panel()), config)["rows"]
    first = bootstrap_against_reference(rows, config)
    pd.testing.assert_frame_equal(first, bootstrap_against_reference(rows, config))
    assert ((first["mae_ratio_low"] <= first["mae_ratio"]) & (first["mae_ratio"] <= first["mae_ratio_high"])).all()


def test_bootstrap_keeps_whole_series_together(config):
    rows = evaluate(add_predictions(synthetic_panel()), config)["rows"]
    table = bootstrap_against_reference(rows, config)
    assert set(table["n_series"]) == {36}
    assert set(table["n_rows"]) == {72}


# --- Real results -------------------------------------------------------------

@pytest.fixture(scope="module")
def real(config):
    df = load_dataset(expected_sha256=config["expected_dataset_sha256"])
    predictions = add_predictions(df)
    results = evaluate(predictions, config)
    return df, predictions, results, summarise(results, config)


@needs_data
def test_real_evaluation_uses_145_rows_and_no_2023_target(real):
    rows = real[2]["rows"]
    assert len(rows) == 145
    assert rows.groupby("fold").size().to_dict() == {"fold_1": 71, "fold_2": 74}
    assert set(rows["target_year"]) == {2021, 2022}


@needs_data
def test_previous_year_mae_recomputed_directly_from_the_dataset(real):
    """Independent of the pipeline: from the dataset's own columns."""
    df, _, results, _ = real
    required = ["licence_count", "target_licence_count", "licence_rolling_mean_3", "licence_growth_log"]
    for year, fold in ((2020, "fold_1"), (2021, "fold_2")):
        rows = df[df["year"] == year].dropna(subset=required)
        expected = (rows["licence_count"] - rows["target_licence_count"]).abs().mean()
        table = results["accuracy"]
        stored = table[(table["fold"] == fold) & (table["scenario"] == "all_rows") & (table["group"] == GROUP_ALL) & (table["model"] == "previous_year")]["mae"].iloc[0]
        assert stored == pytest.approx(expected)


@needs_data
def test_real_rows_hold_no_rejected_values(real):
    rows = real[2]["rows"]
    assert rows["licence_count"].notna().all() and rows["target_licence_count"].notna().all()
    assert not ((rows["district"] == "Jaffna") & (rows["vehicle_type"] == "Motorcycle") & (rows["year"] == 2020)).any()
    assert not ((rows["district"] == "Ampara") & (rows["year"] == 2019)).any()


@needs_data
def test_flagged_rows_are_counted_correctly(real):
    rows = real[2]["rows"]
    assert (rows["target_flagged"] | rows["features_use_flagged_licence"]).sum() == 29


@needs_data
def test_flagged_comparison_uses_same_rows_for_each_model(real, config):
    table = flagged_comparison(real[2]["rows"], config)
    assert set(table["n"]) == {116, 29}


@needs_data
def test_outlier_review_matches_the_extraction_and_changes_nothing(real, config):
    df = real[0]
    cells = pd.read_csv(CELLS_CSV, dtype=str, keep_default_na=False)
    cells["year"] = cells["year"].astype(int)
    cells["number"] = pd.to_numeric(cells["value_numeric"], errors="coerce")
    review = review_outlier_candidates(df, cells, config)
    assert len(review) == 8
    assert review["matches_pdf_extraction"].all()
    assert (~review["value_changed"]).all()
    for row in review.itertuples():
        cell = cells[(cells["district"] == row.district) & (cells["year"] == row.year) & (cells["vehicle_type"] == row.vehicle_type) & (cells["metric"] == "vehicle_population")]
        assert cell.iloc[0]["number"] == row.value_printed
        assert (REPO_ROOT / "data" / "raw" / "dcs_handbooks" / row.source_pdf).exists()


def test_candidates_match_the_eda_list(config):
    findings = json.loads((REPO_ROOT / "reports" / "eda_v2" / "eda_findings.json").read_text(encoding="utf-8"))
    assert sorted(findings["new_outlier_list"]) == sorted(f"{c['district']} {c['vehicle_type']} {c['year']}" for c in config["outlier_candidates"])


def test_feature_selection_covers_every_dataset_feature(config):
    dataset_config_text = (REPO_ROOT / "configs" / "dataset_v2.yaml").read_text(encoding="utf-8")
    import yaml

    features = {c["name"] for c in yaml.safe_load(dataset_config_text)["columns"] if c["role"] == "feature"}
    decided = {f["feature"] for f in config["feature_selection"]}
    assert features <= decided
    assert all(f["reason"] for f in config["feature_selection"])
    assert {f["decision"] for f in config["feature_selection"]} == {"core", "add_on", "excluded"}


def test_module_trains_no_models():
    source = Path(__file__).resolve().parents[1].joinpath("src", "evaluation", "baseline_evaluation_v2.py").read_text(encoding="utf-8")
    for forbidden in ["sklearn", "xgboost", "tensorflow", "torch", ".fit(", "modelling_dataset_v1", "src.models", "mlflow"]:
        assert forbidden not in source, forbidden


# --- Pipeline -----------------------------------------------------------------

@needs_data
def test_run_writes_only_to_its_folder_and_is_repeatable(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (DATASET_CSV, CONFIG_YAML)}
    manifest = run(output_dir=first)
    run(output_dir=second)
    assert manifest["final_test_evaluated"] is False
    assert manifest["target_years_evaluated"] == [2021, 2022]
    assert manifest["evaluation_rows"] == 145
    for name in manifest["tables"]:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    assert len(list((first / "figures").glob("*.png"))) == 6
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


@needs_data
def test_run_stops_on_a_different_dataset(tmp_path, config):
    altered = tmp_path / "altered.csv"
    altered.write_bytes(DATASET_CSV.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="not the frozen"):
        run(dataset_csv=altered, output_dir=tmp_path / "out")


# --- Saved outputs and report -------------------------------------------------

@pytest.mark.skipif(not (OUTPUT_DIR / "baseline_manifest.json").exists(), reason="results not generated")
def test_saved_results_hold_no_final_test_year():
    assert set(pd.read_csv(OUTPUT_DIR / "predictions.csv")["target_year"]) == {2021, 2022}
    assert set(pd.read_csv(OUTPUT_DIR / "metrics_by_fold.csv")["target_year"]) == {2021, 2022}
    manifest = json.loads((OUTPUT_DIR / "baseline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_test_evaluated"] is False


@pytest.mark.skipif(not REPORT.exists(), reason="report not written")
def test_report_quotes_the_saved_results():
    text = REPORT.read_text(encoding="utf-8")
    summary = pd.read_csv(OUTPUT_DIR / "metrics_summary.csv")
    labels = {"previous_year": "Previous year", "moving_average": "Moving average", "growth_series": "Growth (own series)", "growth_vehicle_median": "Growth (vehicle median)"}
    for scenario in ("all_rows", "no_flagged_target_or_input"):
        part = summary[(summary["scenario"] == scenario) & (summary["group"] == GROUP_ALL)]
        for row in part.itertuples():
            assert f"{row.mae:,.0f}" in text, (scenario, row.model, "mae")
            assert f"{row.mape:.2f}" in text, (scenario, row.model, "mape")
    bootstrap = pd.read_csv(OUTPUT_DIR / "bootstrap_against_previous_year.csv")
    for row in bootstrap[bootstrap["scenario"].isin(["all_rows", "no_flagged_target_or_input"])].itertuples():
        assert f"{row.mae_ratio:.2f} ({row.mae_ratio_low:.2f} to {row.mae_ratio_high:.2f})" in text, row.model
    assert all(label in text for label in labels.values())


@pytest.mark.skipif(not REPORT.exists(), reason="report not written")
def test_report_states_the_key_limitations():
    text = REPORT.read_text(encoding="utf-8")
    for phrase in ["2023 was not evaluated", "not truly unseen", "Claude read", "proxy", "success criteria"]:
        assert phrase.lower() in text.lower(), phrase
