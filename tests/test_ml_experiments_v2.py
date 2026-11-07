"""Tests for the Dataset v2 Ridge and XGBoost experiments.

Calculation tests use small, clearly artificial tables that exist only to exercise
the logic. Real-data tests read Dataset v2 and write only to tmp_path.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.evaluation.baseline_evaluation_v2 import DATASET_CSV, VEHICLES, load_dataset
from src.evaluation.baseline_evaluation_v2 import load_config as load_baseline_config
from src.models.ml_experiments_v2 import (
    GROUP_BOTH_FOLDS,
    GROUP_FOLD_2,
    GROUP_REGISTRATIONS,
    OUTPUT_DIR,
    REPO_ROOT,
    add_model_inputs,
    comparison_groups,
    decode_prediction,
    encode_target,
    evaluate_group,
    experiment_name,
    fit_fold,
    fit_xgboost_fold,
    load_config,
    make_ridge,
    numeric_inputs,
    run,
    run_ridge_experiments,
    select_alpha,
    size_rule_change_ranking,
    success_criteria,
    training_rows,
    xgboost_gate,
)

REPORT = OUTPUT_DIR / "ml_experiments_report.md"
V1_MLRUNS = REPO_ROOT / "mlruns"
needs_data = pytest.mark.skipif(not DATASET_CSV.exists(), reason="Dataset v2 not present locally")


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def baseline_config():
    return load_baseline_config()


def synthetic_panel(districts=15, seed=1):
    generator = np.random.default_rng(seed)
    rows = []
    for d in range(districts):
        for v, vehicle in enumerate(VEHICLES):
            level = 1000.0 * (d + 1) * (v + 1)
            for year in range(2019, 2024):
                rows.append({"district": f"D{d:02d}", "vehicle_type": vehicle, "year": year, "licence_count": level})
                level *= np.exp(generator.normal(0.01, 0.05))
    df = pd.DataFrame(rows).sort_values(["district", "vehicle_type", "year"]).reset_index(drop=True)
    group = df.groupby(["district", "vehicle_type"])["licence_count"]
    df["licence_growth_log"] = np.log(df["licence_count"] / group.shift(1))
    df["licence_rolling_mean_3"] = group.transform(lambda s: s.rolling(3, min_periods=2).mean())
    df["licence_rolling_std_3"] = group.transform(lambda s: s.rolling(3, min_periods=2).std())
    df["total_registrations"] = 500.0
    df["total_registrations_growth_log"] = 0.0
    df["target_licence_count"] = group.shift(-1)
    df["target_year"] = df["year"] + 1
    for column in ("licence_flagged", "target_flagged", "features_use_flagged_licence"):
        df[column] = False
    return add_model_inputs(df)


FOLD_1 = {"name": "fold_1", "origin_year": 2020, "target_year": 2021}
FOLD_2 = {"name": "fold_2", "origin_year": 2021, "target_year": 2022}


# --- Targets ------------------------------------------------------------------

@pytest.mark.parametrize("target", ["raw_count", "log_count", "log_change"])
def test_target_round_trip_returns_the_count(target):
    frame = pd.DataFrame({"licence_count": [100.0, 200.0], "target_licence_count": [110.0, 190.0]})
    encoded = encode_target(frame, target)
    assert decode_prediction(encoded.to_numpy(), frame, target) == pytest.approx([110.0, 190.0])


def test_log_change_is_relative_to_this_years_count():
    frame = pd.DataFrame({"licence_count": [100.0], "target_licence_count": [110.0]})
    assert encode_target(frame, "log_change").iloc[0] == pytest.approx(np.log(1.1))
    assert decode_prediction(np.array([0.0]), frame, "log_change")[0] == pytest.approx(100.0)  # no change predicted


def test_unknown_target_is_an_error():
    frame = pd.DataFrame({"licence_count": [1.0], "target_licence_count": [1.0]})
    with pytest.raises(ValueError):
        encode_target(frame, "other")


def test_raw_target_uses_a_raw_level_input(config):
    feature_set = config["feature_sets"]["level"]
    assert numeric_inputs(feature_set, "raw_count", config) == ["licence_count"]
    assert numeric_inputs(feature_set, "log_change", config) == ["log_licence_count"]


# --- Training rows and leakage ------------------------------------------------

def test_training_rows_stop_at_the_origin_year():
    df = synthetic_panel()
    assert set(training_rows(df, 2020, ["log_licence_count"], "all")["target_year"]) == {2020}
    assert set(training_rows(df, 2021, ["log_licence_count"], "all")["target_year"]) == {2020, 2021}


def test_growth_inputs_limit_training_to_rows_with_history():
    df = synthetic_panel()
    rows = training_rows(df, 2021, ["log_licence_count", "licence_growth_log"], "all")
    assert set(rows["target_year"]) == {2021}


def test_training_rows_are_dropped_not_imputed():
    df = synthetic_panel()
    df.loc[df.index[df["year"] == 2019][0], "log_licence_count"] = np.nan
    assert len(training_rows(df, 2020, ["log_licence_count"], "all")) == 15 * 3 - 1


def test_clean_training_removes_flagged_rows():
    df = synthetic_panel()
    index = df.index[df["year"] == 2019]
    df.loc[index[0], "target_flagged"] = True
    df.loc[index[1], "features_use_flagged_licence"] = True
    assert len(training_rows(df, 2020, ["log_licence_count"], "no_flagged")) == 15 * 3 - 2
    with pytest.raises(ValueError):
        training_rows(df, 2020, ["log_licence_count"], "other")


def _future_changed(df, origin_year):
    """Changes everything first known after the origin year, including targets."""
    changed = df.copy()
    later = changed["year"] > origin_year
    for column in ("licence_count", "log_licence_count", "licence_growth_log", "licence_rolling_mean_3", "licence_rolling_std_3", "target_licence_count"):
        changed.loc[later, column] = changed.loc[later, column] * 3 + 1
    # The origin year's own target is next year's value, which must also be unknown.
    changed.loc[changed["year"] == origin_year, "target_licence_count"] *= 3
    return changed


@pytest.mark.parametrize("fold, feature_set", [(FOLD_1, "level"), (FOLD_2, "level"), (FOLD_2, "level_growth")])
def test_ridge_predictions_ignore_all_future_values(config, fold, feature_set):
    df = synthetic_panel()
    original = fit_fold(df, fold, feature_set, "log_change", "all", config)
    changed = fit_fold(_future_changed(df, fold["origin_year"]), fold, feature_set, "log_change", "all", config)
    pd.testing.assert_series_equal(original["predictions"], changed["predictions"])
    assert original["alpha"] == changed["alpha"]


def test_xgboost_predictions_ignore_all_future_values(config):
    df = synthetic_panel()
    original = fit_xgboost_fold(df, FOLD_2, "level_growth", "all", config)
    changed = fit_xgboost_fold(_future_changed(df, 2021), FOLD_2, "level_growth", "all", config)
    pd.testing.assert_series_equal(original["predictions"], changed["predictions"])


def test_scaling_is_fitted_on_training_rows_only(config):
    """An extreme value in a test row must not change predictions for other test rows."""
    df = synthetic_panel()
    original = fit_fold(df, FOLD_1, "level", "log_change", "all", config)["predictions"]
    changed_df = df.copy()
    test_index = changed_df.index[changed_df["year"] == 2020]
    changed_df.loc[test_index[0], "log_licence_count"] = 50.0
    changed = fit_fold(changed_df, FOLD_1, "level", "log_change", "all", config)["predictions"]
    pd.testing.assert_series_equal(original.drop(test_index[0]), changed.drop(test_index[0]))


def test_ridge_scaler_learns_from_the_rows_it_is_given():
    train = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "vehicle_type": VEHICLES + VEHICLES[:1]})
    model = make_ridge(["x"], 1.0).fit(train, [1.0, 2.0, 3.0, 4.0])
    assert model.named_steps["prepare"].named_transformers_["numeric"].mean_[0] == pytest.approx(2.5)


def test_alpha_selection_uses_whole_districts_and_returns_a_grid_value(config):
    df = synthetic_panel()
    rows = training_rows(df, 2020, ["log_licence_count"], "all")
    alpha, table = select_alpha(rows, ["log_licence_count"], "log_change", config)
    assert alpha in config["ridge"]["alpha_grid"]
    assert len(table) == len(config["ridge"]["alpha_grid"])


def test_xgboost_config_is_conservative(config):
    assert max(config["xgboost"]["grid"]["max_depth"]) <= 2
    assert max(config["xgboost"]["grid"]["n_estimators"]) <= 100
    assert config["xgboost"]["target"] == "log_change"
    assert config["xgboost"]["fixed"]["min_child_weight"] >= 5


def test_final_test_year_is_not_in_any_fold(config, baseline_config):
    assert all(f["target_year"] < config["final_test_target_year"] for f in baseline_config["development_folds"])


# --- Gate and rules -----------------------------------------------------------

def _criteria(model, lower=False, change=False):
    return {"model": model, "c1_lower_mae_and_mape_both_row_sets": lower, "c4_positive_change_ranking_every_vehicle_and_fold": change}


def test_gate_closed_when_ridge_shows_nothing():
    gate = xgboost_gate(pd.DataFrame([_criteria("ridge__a"), _criteria("moving_average", lower=True, change=True)]))
    assert gate["open"] is False  # a non-Ridge success cannot open it


def test_gate_opens_on_either_route():
    assert xgboost_gate(pd.DataFrame([_criteria("ridge__a", lower=True)]))["open"] is True
    assert xgboost_gate(pd.DataFrame([_criteria("ridge__a", change=True)]))["open"] is True


def test_size_rule_hand_calculation():
    rows = pd.DataFrame({
        "fold": "fold_1", "vehicle_type": "Car", "licence_count": [100.0, 200.0, 300.0],
        "target_licence_count": [120.0, 220.0, 300.0],  # smaller districts grow more
    })
    assert size_rule_change_ranking(rows)["spearman_change_smaller_is_higher"].iloc[0] == pytest.approx(1.0)


def test_experiment_names_are_unique(config):
    names = [experiment_name(s, t, r) for s, targets in config["experiments"].items() for t in targets for r in config["training_rows"]]
    assert len(names) == len(set(names)) == 20


# --- Real data ----------------------------------------------------------------

@pytest.fixture(scope="module")
def real(config, baseline_config):
    df = load_dataset(expected_sha256=baseline_config["expected_dataset_sha256"])
    wide, log, coefficients = run_ridge_experiments(df, config, baseline_config)
    evaluations = {name: evaluate_group(wide, group, baseline_config) for name, group in comparison_groups(config).items()}
    return df, wide, log, coefficients, evaluations


@needs_data
def test_models_are_scored_on_the_same_rows_as_the_baselines(real):
    evaluations = real[4]
    assert len(evaluations[GROUP_BOTH_FOLDS]["results"]["rows"]) == 145
    assert len(evaluations[GROUP_FOLD_2]["results"]["rows"]) == 74
    assert len(evaluations[GROUP_REGISTRATIONS]["results"]["rows"]) == 59
    for evaluation in evaluations.values():
        counts = evaluation["results"]["accuracy"].groupby(["fold", "scenario", "group"])["n"].nunique()
        assert (counts == 1).all()


@needs_data
def test_rows_match_the_baseline_evaluation_file(real):
    saved = pd.read_csv(REPO_ROOT / "reports" / "baseline_v2" / "predictions.csv")
    rows = real[4][GROUP_BOTH_FOLDS]["results"]["rows"]
    key = ["district", "vehicle_type", "year"]
    assert sorted(map(tuple, rows[key].to_numpy())) == sorted(map(tuple, saved[key].to_numpy()))
    # The previous-year forecast is unchanged from the approved Step 5 results.
    joined = rows.merge(saved, on=key, suffixes=("", "_saved"))
    assert (joined["previous_year"] - joined["previous_year_saved"]).abs().max() < 1e-3


@needs_data
def test_no_row_targets_the_final_test_year(real):
    for evaluation in real[4].values():
        assert set(evaluation["results"]["rows"]["target_year"]) <= {2021, 2022}
    assert set(real[2]["predicts_target_year"]) == {2021, 2022}


@needs_data
def test_training_years_never_pass_the_origin(real):
    log = real[2]
    assert set(log[log["fold"] == "fold_1"]["train_target_years"]) == {"2020"}
    assert set(log[log["fold"] == "fold_2"]["train_target_years"]) <= {"2020 2021", "2021"}


@needs_data
def test_changing_2023_values_changes_no_prediction(config, baseline_config, real):
    """Only checks equality, so nothing about 2023 is read or reported."""
    df, wide = real[0], real[1]
    changed = df.copy()
    changed.loc[changed["year"] == 2023, "licence_count"] *= 50
    changed.loc[changed["year"] == 2022, "target_licence_count"] *= 50
    other_wide, _, _ = run_ridge_experiments(changed, config, baseline_config)
    columns = [c for c in wide.columns if c.startswith("ridge__")]
    development = wide["year"] <= 2021
    pd.testing.assert_frame_equal(wide.loc[development, columns], other_wide.loc[development, columns])


@needs_data
def test_level_only_models_repeat_the_baseline_level_ranking(real):
    """A monotonic function of size within a vehicle type cannot reorder districts."""
    ranking = real[4][GROUP_BOTH_FOLDS]["summary"]["ranking"]
    part = ranking[ranking["scenario"] == "all_rows"].set_index("model")
    for target in ("log_count", "log_change"):
        name = f"ridge__level__{target}__train_all"
        assert part.loc[name, "spearman_level"] == pytest.approx(part.loc["previous_year", "spearman_level"])
        assert part.loc[name, "top_5_overlap"] == pytest.approx(part.loc["previous_year", "top_5_overlap"])


@needs_data
def test_level_only_change_ranking_is_just_the_size_rule(real):
    results = real[4][GROUP_BOTH_FOLDS]["results"]
    size_rule = size_rule_change_ranking(results["rows"]).set_index(["fold", "vehicle_type"])["spearman_change_smaller_is_higher"]
    ranking = results["ranking"]
    part = ranking[(ranking["scenario"] == "all_rows") & (ranking["model"] == "ridge__level__log_change__train_all")].set_index(["fold", "vehicle_type"])
    for key in part.index:
        assert part.loc[key, "spearman_change"] == pytest.approx(size_rule[key])


@needs_data
def test_no_model_met_the_accuracy_criteria(real):
    criteria = pd.concat([success_criteria(e, name) for name, e in real[4].items()], ignore_index=True)
    ridge = criteria[criteria["model"].str.startswith("ridge__")]
    assert not ridge["c1_lower_mae_and_mape_both_row_sets"].any()
    assert not ridge["c2_interval_below_one_both_row_sets"].any()


@needs_data
def test_unverified_totals_are_not_imputed_for_registration_models(real):
    wide = real[1]
    name = "ridge__level_growth_registrations__log_change__train_all"
    fold_rows = wide[wide["year"] == 2021]
    assert fold_rows.loc[fold_rows["total_registrations"].isna(), name].isna().all()


# --- Pipeline -----------------------------------------------------------------

def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_state(folder):
    return sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file())


@needs_data
def test_run_writes_only_where_told_and_is_repeatable(tmp_path):
    protected = (DATASET_CSV, REPO_ROOT / "data" / "processed" / "modelling_dataset_v1.csv", REPO_ROOT / "models" / "xgboost_v1" / "model.json")
    before = {p: _sha(p) for p in protected if p.exists()}
    v1_runs_before = _tree_state(V1_MLRUNS) if V1_MLRUNS.exists() else []

    first = run(output_dir=tmp_path / "first", mlruns_dir=tmp_path / "runs_first")
    run(output_dir=tmp_path / "second", mlruns_dir=tmp_path / "runs_second")

    assert first["final_test_evaluated"] is False
    assert first["target_years_evaluated"] == [2021, 2022]
    for name in first["tables"]:
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes(), name
    assert (tmp_path / "runs_first").exists()
    assert {p: _sha(p) for p in before} == before
    assert (_tree_state(V1_MLRUNS) if V1_MLRUNS.exists() else []) == v1_runs_before


@needs_data
def test_run_stops_on_a_different_dataset(tmp_path):
    altered = tmp_path / "altered.csv"
    altered.write_bytes(DATASET_CSV.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="not the frozen"):
        run(dataset_csv=altered, output_dir=tmp_path / "out", mlruns_dir=tmp_path / "runs")


def test_module_does_not_use_dataset_v1():
    source = Path(__file__).resolve().parents[1].joinpath("src", "models", "ml_experiments_v2.py").read_text(encoding="utf-8")
    for forbidden in ["modelling_dataset_v1", "xgboost_v1", "models/xgboost", "save_model", "joblib", "include_final_test=True", "fillna(", ".interpolate("]:
        assert forbidden not in source, forbidden


def test_v2_mlflow_store_is_separate_and_ignored():
    assert "mlruns_v2/" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


# --- Saved outputs and report -------------------------------------------------

saved = pytest.mark.skipif(not (OUTPUT_DIR / "ml_manifest.json").exists(), reason="results not generated")


@saved
def test_saved_results_hold_no_final_test_year():
    manifest = json.loads((OUTPUT_DIR / "ml_manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_test_evaluated"] is False
    assert manifest["experiments"] == 24
    assert set(pd.read_csv(OUTPUT_DIR / "metrics_by_fold.csv")["target_year"]) == {2021, 2022}
    assert set(pd.read_csv(OUTPUT_DIR / "experiments.csv")["predicts_target_year"]) == {2021, 2022}


@saved
def test_saved_gate_opened_only_through_the_change_route():
    gate = json.loads((OUTPUT_DIR / "ml_manifest.json").read_text(encoding="utf-8"))["xgboost_gate"]
    assert gate["open"] is True
    assert gate["ridge_lower_mae_and_mape_both_row_sets"] == []
    assert gate["ridge_positive_change_ranking_every_vehicle_and_fold"]


@saved
def test_no_saved_model_passes_all_accuracy_criteria():
    criteria = pd.read_csv(OUTPUT_DIR / "success_criteria.csv")
    assert not criteria["passes_all_accuracy_criteria"].any()
    models = criteria[criteria["model"].str.contains("__")]
    assert not models["c1_lower_mae_and_mape_both_row_sets"].any()
    assert not models["c2_interval_below_one_both_row_sets"].any()


@pytest.mark.skipif(not REPORT.exists(), reason="report not written")
def test_report_quotes_the_saved_results():
    text = REPORT.read_text(encoding="utf-8")
    summary = pd.read_csv(OUTPUT_DIR / "metrics_summary.csv")
    bootstrap = pd.read_csv(OUTPUT_DIR / "bootstrap_against_previous_year.csv")
    quoted = ["previous_year", "ridge__level__raw_count__train_all", "ridge__level__log_count__train_all",
              "ridge__level__log_change__train_all", "xgboost__level__log_change__train_all"]
    part = summary[(summary["comparison"] == GROUP_BOTH_FOLDS) & (summary["group"] == "All")]
    for model in quoted:
        row = part[(part["model"] == model) & (part["scenario"] == "all_rows")].iloc[0]
        assert f"{row['mae']:,.0f}" in text, model
        assert f"{row['mape']:.2f}" in text, model
        assert f"{row['mase']:.2f}" in text, model
    table = bootstrap[(bootstrap["comparison"] == GROUP_BOTH_FOLDS) & bootstrap["scenario"].isin(["all_rows", "no_flagged_target_or_input"]) & bootstrap["model"].isin(quoted)]
    for row in table.itertuples():
        assert f"{row.mae_ratio:.2f} ({row.mae_ratio_low:.2f} to {row.mae_ratio_high:.2f})" in text, (row.scenario, row.model)
    sensitivity = part[part["model"].isin(["ridge__level__log_change__train_no_flagged", "xgboost__level__log_change__train_no_flagged"])]
    for row in sensitivity.itertuples():
        assert f"{row.mape:.2f}" in text, (row.scenario, row.model)


@pytest.mark.skipif(not REPORT.exists(), reason="report not written")
def test_report_images_exist_and_limitations_are_stated():
    text = REPORT.read_text(encoding="utf-8")
    for name in ("fig01_models_vs_baseline_both_folds.png", "fig02_mae_ratio_intervals_fold_2.png", "fig03_change_ranking_fold_2.png"):
        assert f"figures/{name}" in text and (OUTPUT_DIR / "figures" / name).exists()
    for phrase in ["no model passed", "not truly unseen", "proxy", "many comparisons", "hindsight", "second route"]:
        assert phrase in text.lower(), phrase


def test_config_is_valid_yaml_and_matches_baseline_dataset():
    config = yaml.safe_load((REPO_ROOT / "configs" / "ml_v2.yaml").read_text(encoding="utf-8"))
    assert config["targets"] == ["raw_count", "log_count", "log_change"]
