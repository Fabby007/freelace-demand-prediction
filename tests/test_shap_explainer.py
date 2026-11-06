"""DEV-010 / DEV-015 tests for the SHAP explainability module.

Covers DEV-010's Testing Requirements: SHAP output aligns with the model's
exact feature schema (Section 26.2), and the standard SHAP additivity sanity
check (sum of local contributions + base_value approximates the raw
prediction). Also verifies the one-hot vehicle_type aggregation (REF-009
ADR-014) and that global rankings are genuinely data-driven, not hardcoded.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest

from src.models.xgboost_model import MODELS_DIR, build_feature_matrix, load_model
from src.explainability.shap_explainer import (
    EXPLANATION_TYPE_NOTE,
    _aggregate_categorical_contribution,
    build_explainer,
    compute_shap_values,
    explain_row,
    explain_rows,
    global_summary,
    local_explanation,
    run,
)

pytestmark = pytest.mark.skipif(
    not (MODELS_DIR / "model.json").exists(), reason="DEV-008 saved model not present locally"
)


@pytest.fixture(scope="module")
def model_bundle():
    model, encoder, metadata = load_model()
    return model, encoder, metadata


@pytest.fixture(scope="module")
def frozen_df() -> pd.DataFrame:
    from src.models.xgboost_model import FROZEN_CSV
    return pd.read_csv(FROZEN_CSV)


@pytest.fixture(scope="module")
def test_df(frozen_df) -> pd.DataFrame:
    return frozen_df[frozen_df["split"] == "test"].reset_index(drop=True)


@pytest.fixture(scope="module")
def explainer(model_bundle):
    model, _, _ = model_bundle
    return build_explainer(model)


# --- Feature schema alignment (Section 26.2) --------------------------------

def test_shap_values_shape_matches_feature_schema(model_bundle, test_df, explainer):
    model, encoder, metadata = model_bundle
    X = build_feature_matrix(test_df, metadata["active_numeric_features"], encoder)
    shap_values = compute_shap_values(explainer, X)
    assert shap_values.shape == (len(test_df), len(metadata["feature_columns"]))
    assert list(X.columns) == metadata["feature_columns"]


def test_run_raises_if_rebuilt_features_diverge_from_metadata(tmp_path):
    """Structural guard specific to shap_explainer.run() (distinct from
    DEV-008's own load_model() schema check): if metadata's
    active_numeric_features ever falls out of sync with feature_columns (so
    rebuilding X here yields a different column set than the model expects),
    run() must raise rather than silently compute SHAP against a mismatched
    matrix. Simulated by copying the real saved model and corrupting only
    active_numeric_features (feature_columns/model.json untouched, so
    load_model() itself still succeeds and this module's own check is what
    catches it)."""
    import json
    import shutil

    corrupted_dir = tmp_path / "xgboost_v1"
    shutil.copytree(MODELS_DIR, corrupted_dir)
    metadata_path = corrupted_dir / "metadata.json"
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    metadata["active_numeric_features"] = metadata["active_numeric_features"][:-1]  # drop one
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    # Outputs redirected so that a regression in this guard fails the test
    # without overwriting the real SHAP report and explanations CSV.
    with pytest.raises(ValueError):
        run(
            models_dir=corrupted_dir,
            global_summary_json=tmp_path / "shap_global_summary.json",
            local_explanations_csv=tmp_path / "shap_local_explanations_test_v1.csv",
        )


# --- SHAP additivity sanity check -------------------------------------------

def test_local_explanations_satisfy_additivity(model_bundle, test_df, explainer):
    """Standard SHAP consistency check: sum(local contributions) + base_value
    approximates the model's raw prediction for that row."""
    model, encoder, metadata = model_bundle
    explanations = explain_rows(test_df, model, encoder, explainer, metadata["active_numeric_features"])
    for exp in explanations:
        reconstructed = exp["base_value"] + sum(c["shap_value"] for c in exp["raw_contributions"])
        assert reconstructed == pytest.approx(exp["predicted_value"], abs=1e-2)


def test_run_produces_additivity_consistent_csv(tmp_path):
    # Redirect outputs to tmp_path - run() must never overwrite the real
    # reports/shap_global_summary.json or data/processed/shap_local_explanations_test_v1.csv
    # as a side effect of running this test.
    global_summary_json = tmp_path / "shap_global_summary.json"
    local_explanations_csv = tmp_path / "shap_local_explanations_test_v1.csv"

    summary = run(global_summary_json=global_summary_json, local_explanations_csv=local_explanations_csv)
    assert local_explanations_csv.exists()
    assert global_summary_json.exists()

    local_df = pd.read_csv(local_explanations_csv)
    shap_cols = [c for c in local_df.columns if c.startswith("shap_")]
    reconstructed = local_df["base_value"] + local_df[shap_cols].sum(axis=1)
    diff = (reconstructed - local_df["predicted_value"]).abs()
    assert diff.max() < 1e-2
    assert summary["note"] == EXPLANATION_TYPE_NOTE


# --- One-hot vehicle_type aggregation (REF-009 ADR-014) ---------------------

def test_aggregate_categorical_contribution_sums_dummy_columns():
    feature_columns = ["a", "vehicle_type_Motorcycle", "vehicle_type_Car", "vehicle_type_Three-wheeler"]
    row = pd.Series({"a": 100.0, "vehicle_type_Motorcycle": 5.0, "vehicle_type_Car": -2.0, "vehicle_type_Three-wheeler": 0.0})
    assert _aggregate_categorical_contribution(row, feature_columns) == pytest.approx(3.0)


def test_local_explanation_includes_aggregated_and_raw_contributions():
    feature_columns = ["feat_a", "vehicle_type_Motorcycle", "vehicle_type_Car", "vehicle_type_Three-wheeler"]
    row_shap = pd.Series({"feat_a": 10.0, "vehicle_type_Motorcycle": 3.0, "vehicle_type_Car": 0.0, "vehicle_type_Three-wheeler": 0.0})
    feature_row = pd.Series({"feat_a": 42.0, "vehicle_type_Motorcycle": 1.0, "vehicle_type_Car": 0.0, "vehicle_type_Three-wheeler": 0.0})

    result = local_explanation(row_shap, feature_columns, feature_row, base_value=1.0, predicted_value=14.0, identifiers={"district": "X"})

    contribution_features = [c["feature"] for c in result["contributions"]]
    assert "vehicle_type" in contribution_features
    assert "vehicle_type_Motorcycle" not in contribution_features  # collapsed, not duplicated

    raw_features = [c["feature"] for c in result["raw_contributions"]]
    assert set(raw_features) == set(feature_columns)  # nothing silently truncated

    vt_entry = next(c for c in result["contributions"] if c["feature"] == "vehicle_type")
    assert vt_entry["shap_value"] == pytest.approx(3.0)
    assert vt_entry["feature_value"] == "Motorcycle"
    assert result["note"] == EXPLANATION_TYPE_NOTE


def test_contributions_sorted_descending_by_shap_value():
    feature_columns = ["a", "b", "vehicle_type_Motorcycle", "vehicle_type_Car", "vehicle_type_Three-wheeler"]
    row_shap = pd.Series({"a": -5.0, "b": 10.0, "vehicle_type_Motorcycle": 1.0, "vehicle_type_Car": 0.0, "vehicle_type_Three-wheeler": 0.0})
    feature_row = pd.Series({"a": 1.0, "b": 2.0, "vehicle_type_Motorcycle": 1.0, "vehicle_type_Car": 0.0, "vehicle_type_Three-wheeler": 0.0})
    result = local_explanation(row_shap, feature_columns, feature_row, base_value=0.0, predicted_value=6.0, identifiers={})
    values = [c["shap_value"] for c in result["contributions"]]
    assert values == sorted(values, reverse=True)


# --- Global summary is data-driven, not hardcoded ---------------------------

def test_global_summary_ranking_is_sorted_and_data_driven(model_bundle, test_df, explainer):
    model, encoder, metadata = model_bundle
    X = build_feature_matrix(test_df, metadata["active_numeric_features"], encoder)
    shap_values = compute_shap_values(explainer, X)
    summary = global_summary(shap_values, list(X.columns), metadata.get("dataset_version"), len(test_df))

    agg_scores = [f["mean_abs_shap"] for f in summary["aggregated_feature_ranking"]]
    assert agg_scores == sorted(agg_scores, reverse=True)

    agg_features = {f["feature"] for f in summary["aggregated_feature_ranking"]}
    assert agg_features == set(metadata["active_numeric_features"]) | {"vehicle_type"}

    raw_features = {f["feature"] for f in summary["raw_feature_ranking"]}
    assert raw_features == set(metadata["feature_columns"])  # nothing truncated at the raw level
    assert summary["n_rows_explained"] == len(test_df)


# --- explain_row convenience wrapper ----------------------------------------

def test_explain_row_raises_when_row_not_found(model_bundle, frozen_df, explainer):
    model, encoder, metadata = model_bundle
    with pytest.raises(ValueError):
        explain_row(frozen_df, "Nonexistent District", "Motorcycle", 2022, model, encoder, explainer, metadata["active_numeric_features"])


def test_explain_row_works_for_a_single_real_row(model_bundle, frozen_df, explainer):
    model, encoder, metadata = model_bundle
    sample = frozen_df[frozen_df["split"] == "test"].iloc[0]
    result = explain_row(
        frozen_df, sample["district"], sample["vehicle_type"], int(sample["year"]),
        model, encoder, explainer, metadata["active_numeric_features"],
    )
    assert result["district"] == sample["district"]
    reconstructed = result["base_value"] + sum(c["shap_value"] for c in result["raw_contributions"])
    assert reconstructed == pytest.approx(result["predicted_value"], abs=1e-2)


# --- Reuses the persisted encoder/model, never refits -----------------------

def test_explain_rows_reuses_the_loaded_encoder_without_refitting(model_bundle, test_df, explainer):
    model, encoder, metadata = model_bundle
    categories_before = [c.copy() for c in encoder.categories_]
    explain_rows(test_df, model, encoder, explainer, metadata["active_numeric_features"])
    for before, after in zip(categories_before, encoder.categories_):
        np.testing.assert_array_equal(before, after)
