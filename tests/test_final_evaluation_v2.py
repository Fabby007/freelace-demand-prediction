"""Tests for the frozen final evaluation.

These tests never run the real final evaluation. Logic is tested on small, clearly
artificial tables. Tests on real files read only availability, flags, or results
already saved by the single run.
"""
import json

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.evaluation.baseline_evaluation_v2 import DATASET_CSV, VEHICLES, load_dataset
from src.evaluation.baseline_evaluation_v2 import load_config as load_baseline_config
from src.evaluation.final_evaluation_v2 import (
    FREEZE_NAME,
    LOCK_NAME,
    OUTPUT_DIR,
    REPO_ROOT,
    _acquire_lock,
    blind_copy,
    build_forecasts,
    evaluate_final,
    file_hashes,
    fit_final_ridge,
    load_plan,
    preflight,
    run_final_test,
    verify_freeze,
    write_freeze_record,
)

MANIFEST = OUTPUT_DIR / "final_manifest.json"
REPORT = OUTPUT_DIR / "final_evaluation_report.md"
PLAN_TEXT = OUTPUT_DIR / "evaluation_plan.md"
needs_data = pytest.mark.skipif(not DATASET_CSV.exists(), reason="Dataset v2 not present locally")
after_run = pytest.mark.skipif(not MANIFEST.exists(), reason="final evaluation has not run")
RIDGE = "ridge_log_change_level"
MODELS = ["previous_year", "moving_average", RIDGE]


@pytest.fixture(scope="module")
def plan():
    return load_plan()


def synthetic_panel(districts=15, seed=3):
    """Artificial values with every column the evaluation needs."""
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
    df["target_licence_count"] = group.shift(-1)
    df["target_year"] = df["year"] + 1
    df["target_status"] = np.where(df["target_licence_count"].notna(), "available", "no_next_year")
    for column in ("licence_flagged", "target_flagged", "features_use_flagged_licence"):
        df[column] = False
    return df


# --- Plan ---------------------------------------------------------------------

def test_plan_selects_the_approved_models(plan):
    assert plan["models"] == MODELS
    assert plan["reference_model"] == "previous_year"
    assert plan["final_fold"] == {"name": "final_test", "origin_year": 2022, "target_year": 2023}


def test_frozen_ridge_matches_step_6(plan):
    """Same target, inputs and penalty as the selected experiment."""
    experiments = pd.read_csv(REPO_ROOT / "reports" / "ml_v2" / "experiments.csv")
    selected = experiments[experiments["experiment"] == plan["ridge"]["source_experiment"]]
    assert len(selected) == 2
    assert {json.loads(h)["alpha"] for h in selected["hyperparameters"]} == {plan["ridge"]["alpha"]}
    assert set(selected["target"]) == {plan["ridge"]["target"]}
    assert set(selected["inputs"]) == {"log_licence_count vehicle_type"}
    assert set(selected["training_rows"]) == {plan["ridge"]["training_rows_rule"]}


def test_plan_uses_the_baseline_evaluation_scenarios(plan):
    text = PLAN_TEXT.read_text(encoding="utf-8")
    for scenario in load_baseline_config()["scenarios"]:
        assert scenario["description"]
    for phrase in ["All rows", "No flagged target", "No flagged target or input", "Also no outlier candidates", "not truly unseen", "proxy", "Not tuned again"]:
        assert phrase in text, phrase


def test_every_frozen_file_exists(plan):
    assert all((REPO_ROOT / name).exists() for name in plan["frozen_files"])
    assert "src/evaluation/final_evaluation_v2.py" in plan["frozen_files"]


# --- Blind forecasts and leakage ----------------------------------------------

def test_blind_copy_removes_every_final_year_value(plan):
    df = synthetic_panel()
    blind = blind_copy(df, plan)
    assert blind.loc[blind["year"] == 2022, "target_licence_count"].isna().all()
    assert blind.loc[blind["year"] == 2023, "licence_count"].isna().all()
    assert blind.loc[blind["year"] == 2023, "licence_rolling_mean_3"].isna().all()
    pd.testing.assert_series_equal(blind.loc[blind["year"] < 2023, "licence_count"], df.loc[df["year"] < 2023, "licence_count"])
    assert df.loc[df["year"] == 2022, "target_licence_count"].notna().all()  # the original is untouched


def test_training_never_reaches_the_final_year(plan):
    result = fit_final_ridge(blind_copy(synthetic_panel(), plan), plan)
    assert result["train_target_years"] == [2020, 2021, 2022]
    assert result["train_rows"] == 15 * 3 * 3


def test_forecasts_do_not_depend_on_2023_values(plan):
    df = synthetic_panel()
    original, _ = build_forecasts(df, plan)
    changed = df.copy()
    changed.loc[changed["year"] == 2023, "licence_count"] *= 100
    changed.loc[changed["year"] == 2022, "target_licence_count"] *= 100
    other, _ = build_forecasts(changed, plan)
    row = df["year"] == 2022
    pd.testing.assert_frame_equal(original.loc[row, MODELS], other.loc[row, MODELS])


def test_ridge_uses_the_frozen_penalty_without_tuning(plan):
    df = synthetic_panel()
    high = {**plan, "ridge": {**plan["ridge"], "alpha": 100.0}}
    low = {**plan, "ridge": {**plan["ridge"], "alpha": 0.01}}
    blind = blind_copy(df, plan)
    assert not fit_final_ridge(blind, high)["predictions"].equals(fit_final_ridge(blind, low)["predictions"])


def test_scaling_uses_training_rows_only(plan):
    """An extreme value in one forecast row must not change other forecasts."""
    df = synthetic_panel()
    original = fit_final_ridge(blind_copy(df, plan), plan)["predictions"]
    changed = df.copy()
    position = changed.index[changed["year"] == 2022][0]
    changed.loc[position, "licence_count"] *= 1000
    other = fit_final_ridge(blind_copy(changed, plan), plan)["predictions"]
    pd.testing.assert_series_equal(original.drop(position), other.drop(position))


def test_baselines_are_this_years_values(plan):
    df = synthetic_panel()
    wide, _ = build_forecasts(df, plan)
    rows = wide[wide["year"] == 2022]
    assert (rows["previous_year"] == rows["licence_count"]).all()
    assert (rows["moving_average"] == rows["licence_rolling_mean_3"]).all()


# --- Evaluation on artificial data --------------------------------------------

@pytest.fixture(scope="module")
def synthetic_final(plan):
    baseline_config = load_baseline_config()
    wide, _ = build_forecasts(synthetic_panel(), plan)
    return evaluate_final(wide, plan, baseline_config)


def test_all_models_scored_on_identical_rows(synthetic_final):
    accuracy = synthetic_final["results"]["accuracy"]
    assert (accuracy.groupby(["scenario", "group"])["n"].nunique() == 1).all()
    assert set(accuracy["target_year"]) == {2023}


def test_results_cover_each_vehicle_type_and_scenario(synthetic_final):
    accuracy = synthetic_final["results"]["accuracy"]
    assert set(accuracy["group"]) == {"All", *VEHICLES}
    assert set(accuracy["scenario"]) == {"all_rows", "no_flagged_target", "no_flagged_target_or_input", "also_no_outlier_candidates"}
    assert set(accuracy["model"]) == set(MODELS)


def test_flagged_rows_leave_for_every_model_equally(plan):
    df = synthetic_panel()
    df.loc[df.index[df["year"] == 2022][:5], "target_flagged"] = True
    wide, _ = build_forecasts(df, plan)
    accuracy = evaluate_final(wide, plan, load_baseline_config())["results"]["accuracy"]
    part = accuracy[(accuracy["group"] == "All")].set_index(["scenario", "model"])["n"]
    assert {part[("all_rows", m)] for m in MODELS} == {45}
    assert {part[("no_flagged_target", m)] for m in MODELS} == {40}


def test_criteria_cover_the_two_non_reference_models(synthetic_final):
    assert set(synthetic_final["criteria"]["model"]) == {"moving_average", RIDGE}


# --- Freeze and one-shot run --------------------------------------------------

def test_verify_refuses_without_a_freeze_record(tmp_path, plan):
    with pytest.raises(RuntimeError, match="No freeze record"):
        verify_freeze(tmp_path, plan)


def test_verify_refuses_a_changed_file(tmp_path, plan):
    hashes = file_hashes(plan)
    hashes["configs/final_evaluation_v2.yaml"] = "0" * 64
    (tmp_path / FREEZE_NAME).write_text(json.dumps({"file_sha256": hashes}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Files changed"):
        verify_freeze(tmp_path, plan)


def test_verify_passes_when_nothing_changed(tmp_path, plan):
    (tmp_path / FREEZE_NAME).write_text(json.dumps({"file_sha256": file_hashes(plan)}), encoding="utf-8")
    assert verify_freeze(tmp_path, plan)


def test_lock_allows_one_start_only(tmp_path, plan):
    _acquire_lock(tmp_path, plan)
    with pytest.raises(RuntimeError, match="only run once"):
        _acquire_lock(tmp_path, plan)


def test_second_run_is_refused_before_any_data_is_read(tmp_path):
    (tmp_path / LOCK_NAME).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="only run once"):
        run_final_test(output_dir=tmp_path, dataset_csv=tmp_path / "does_not_exist.csv", mlruns_dir=tmp_path / "runs")


def test_run_without_a_freeze_is_refused_and_takes_no_lock(tmp_path):
    with pytest.raises(RuntimeError, match="No freeze record"):
        run_final_test(output_dir=tmp_path, dataset_csv=tmp_path / "does_not_exist.csv", mlruns_dir=tmp_path / "runs")
    assert not (tmp_path / LOCK_NAME).exists()


def test_freezing_is_refused_once_the_test_has_started(tmp_path):
    (tmp_path / LOCK_NAME).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already started"):
        write_freeze_record(output_dir=tmp_path)


# --- Real data, availability and flags only -----------------------------------

@needs_data
def test_preflight_matches_the_plan_without_reading_2023_values(plan):
    df = load_dataset(DATASET_CSV, plan["expected_dataset_sha256"])
    # Blank the real values: if pre-flight depended on them, it would now fail.
    df.loc[df["year"] == 2022, "target_licence_count"] = np.nan
    df.loc[df["year"] == 2023, "licence_count"] = np.nan
    report = preflight(df, plan)
    assert report == {"training_rows": 220, "training_target_years": [2020, 2021, 2022], "evaluation_rows": 75, "flagged_targets": 9}


@needs_data
def test_preflight_stops_when_an_expectation_fails(plan):
    wrong = {**plan, "expected": {**plan["expected"], "evaluation_rows": 74}}
    with pytest.raises(ValueError, match="do not match the plan"):
        preflight(load_dataset(DATASET_CSV, plan["expected_dataset_sha256"]), wrong)


# --- Saved results of the single run ------------------------------------------

@after_run
def test_files_are_still_as_frozen(plan):
    assert verify_freeze(OUTPUT_DIR, plan)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["file_sha256"] == json.loads((OUTPUT_DIR / FREEZE_NAME).read_text(encoding="utf-8"))["file_sha256"]
    assert manifest["dataset_sha256"] == plan["expected_dataset_sha256"]


@after_run
def test_the_freeze_came_before_the_run():
    freeze = json.loads((OUTPUT_DIR / FREEZE_NAME).read_text(encoding="utf-8"))["frozen_at"]
    lock = json.loads((OUTPUT_DIR / LOCK_NAME).read_text(encoding="utf-8"))["started_at"]
    assert freeze < lock


@after_run
def test_saved_predictions_cover_the_expected_rows():
    saved = pd.read_csv(OUTPUT_DIR / "predictions.csv")
    assert len(saved) == 75
    assert set(saved["target_year"]) == {2023} and set(saved["year"]) == {2022}
    assert saved[MODELS + ["target_licence_count"]].notna().all().all()
    assert saved["target_flagged"].sum() == 9


@after_run
def test_saved_ridge_forecasts_refit_independently_without_2023_values(plan):
    """Built directly with scikit-learn, not the project's helpers."""
    df = pd.read_csv(DATASET_CSV)
    train = df[(df["target_year"] <= 2022) & df["licence_count"].notna() & df["target_licence_count"].notna()]
    assert len(train) == 220
    frame = lambda d: pd.DataFrame({"x": np.log(d["licence_count"]), "vehicle_type": d["vehicle_type"]})
    prepare = ColumnTransformer([("n", StandardScaler(), ["x"]), ("v", OneHotEncoder(categories=[VEHICLES]), ["vehicle_type"])])
    model = Pipeline([("p", prepare), ("r", Ridge(alpha=100.0))]).fit(frame(train), np.log(train["target_licence_count"] / train["licence_count"]))
    test = df[(df["year"] == 2022)]
    forecast = test.assign(expected=test["licence_count"] * np.exp(model.predict(frame(test))))[["district", "vehicle_type", "expected"]]
    saved = pd.read_csv(OUTPUT_DIR / "predictions.csv").merge(forecast, on=["district", "vehicle_type"])
    assert (saved[RIDGE] - saved["expected"]).abs().max() < 1e-2


@after_run
def test_saved_metrics_recompute_from_saved_predictions():
    saved = pd.read_csv(OUTPUT_DIR / "predictions.csv")
    metrics = pd.read_csv(OUTPUT_DIR / "metrics_final.csv")
    part = metrics[(metrics["scenario"] == "all_rows") & (metrics["group"] == "All")].set_index("model")
    for model in MODELS:
        error = (saved[model] - saved["target_licence_count"]).abs()
        assert error.mean() == pytest.approx(part.loc[model, "mae"], abs=0.01)
        assert (error / saved["target_licence_count"]).mean() * 100 == pytest.approx(part.loc[model, "mape"], abs=0.01)
        assert part.loc[model, "n"] == 75


@after_run
def test_saved_ranking_recomputes_by_vehicle():
    saved = pd.read_csv(OUTPUT_DIR / "predictions.csv")
    ranking = pd.read_csv(OUTPUT_DIR / "ranking_final.csv")
    part = ranking[ranking["scenario"] == "all_rows"].set_index(["vehicle_type", "model"])
    for vehicle in VEHICLES:
        rows = saved[saved["vehicle_type"] == vehicle]
        for model in MODELS:
            assert stats.spearmanr(rows["target_licence_count"], rows[model]).statistic == pytest.approx(part.loc[(vehicle, model), "spearman_level"], abs=0.001)
            overlap = len(set(rows.nlargest(5, "target_licence_count")["district"]) & set(rows.nlargest(5, model)["district"])) / 5
            assert overlap == pytest.approx(part.loc[(vehicle, model), "top_5_overlap"])


@after_run
def test_mase_scale_is_recomputed_from_years_before_2023():
    df = pd.read_csv(DATASET_CSV)
    history = df[df["year"] <= 2022].sort_values(["district", "vehicle_type", "year"])
    scale = history.groupby(["district", "vehicle_type"])["licence_count"].diff().abs().mean()
    metrics = pd.read_csv(OUTPUT_DIR / "metrics_final.csv")
    stored = metrics[(metrics["scenario"] == "all_rows") & (metrics["group"] == "All")]["scale"].iloc[0]
    assert stored == pytest.approx(scale, abs=0.01)


@pytest.mark.skipif(not REPORT.exists(), reason="report not written")
def test_report_quotes_saved_results_and_states_limits():
    text = REPORT.read_text(encoding="utf-8")
    metrics = pd.read_csv(OUTPUT_DIR / "metrics_final.csv")
    part = metrics[metrics["group"] == "All"]
    for row in part[part["scenario"].isin(["all_rows", "no_flagged_target_or_input"])].itertuples():
        assert f"{row.mae:,.0f}" in text, (row.scenario, row.model)
        assert f"{row.mape:.2f}" in text, (row.scenario, row.model)
    bootstrap = pd.read_csv(OUTPUT_DIR / "bootstrap_against_previous_year.csv")
    for row in bootstrap[bootstrap["scenario"].isin(["all_rows", "no_flagged_target_or_input"])].itertuples():
        assert f"{row.mae_ratio:.2f} ({row.mae_ratio_low:.2f} to {row.mae_ratio_high:.2f})" in text, (row.scenario, row.model)
    lowered = text.lower()
    for phrase in ["proxy", "not actual mechanic-service demand", "not truly unseen", "one year", "exactly once"]:
        assert phrase in lowered, phrase
    for name in json.loads(MANIFEST.read_text(encoding="utf-8"))["tables"]:
        assert (OUTPUT_DIR / name).exists()
    for image in ("fig01_error_by_scenario.png", "fig02_error_by_vehicle.png", "fig03_mae_ratio_intervals.png", "fig04_ranking.png", "fig05_error_by_district.png"):
        assert f"figures/{image}" in text and (OUTPUT_DIR / "figures" / image).exists()


def test_plan_file_is_valid_yaml():
    assert yaml.safe_load((REPO_ROOT / "configs" / "final_evaluation_v2.yaml").read_text(encoding="utf-8"))["plan_version"]
