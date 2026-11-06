"""SHAP Explainability Module (DEV-010).

Explains the saved DEV-008 XGBoost model's predictions - source doc Section
17: "Explains how individual variables influence XGBoost predictions." This
module computes; it never authors narrative text. Section 18's ranking
engine (DEV-012) is the one that turns raw SHAP numbers into a sentence like
"increased by strong recent registration growth" - DEV-010 only exposes the
faithful numeric contributions that make such a sentence checkable against
the model, never an invented explanation (Business Rule).

IMPORTANT - prediction explanation, not causal explanation: every SHAP value
this module produces describes how much a feature moved THIS MODEL's
prediction for THIS ROW, relative to the model's average prediction over the
data it explains. It is not evidence that the underlying real-world quantity
(e.g. recent registration growth) *causes* higher service demand - only that
the trained model's learned association responds to it. This distinction
(CLAUDE.md Section 19: "do not claim causal relationships when the model
only identifies predictive associations") is carried in every artifact this
module writes via the `EXPLANATION_TYPE_NOTE` string, and must be preserved
by every downstream consumer (DEV-012, DEV-013).

Method: `shap.TreeExplainer` against the saved XGBoost booster - the exact,
fast SHAP algorithm for tree ensembles (no approximation/sampling), so
"global explanations ... must come from the trained model, not be assumed in
advance" (17.1) is satisfied precisely, not approximately.

Feature schema fidelity (Section 26.2, "SHAP output aligns with the model
feature schema"): this module NEVER rebuilds or refits anything. It loads
the DEV-008 model, its already-fitted `OneHotEncoder`, and its exact
`feature_columns` list via `src.models.xgboost_model.load_model()`, and
reuses `build_feature_matrix()` verbatim to turn any row selection into the
identical matrix DEV-008 trained on - including the same all-null-feature
exclusions (REF-009 ADR-011) and the same one-hot `vehicle_type` columns, in
the same order. If the reloaded model's schema ever drifts from its own
metadata, `load_model()` itself already raises (DEV-008 Error Case) before
this module would compute anything against a mismatched schema.

One-hot `vehicle_type` aggregation (REF-009 ADR-014): SHAP naturally
attributes a separate value to each of the three `vehicle_type_*` dummy
columns. For a human-readable global ranking and local explanation, this
module ADDITIONALLY reports a single combined `vehicle_type` contribution
per row (the signed sum of its three dummy columns' SHAP values - the
standard way to collapse a one-hot group back to its original categorical
feature), alongside - never instead of - the raw per-column values, so
nothing is silently truncated (Edge Case).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import shap

from src.models.xgboost_model import (
    FROZEN_CSV,
    MODELS_DIR,
    TARGET_COLUMN,
    build_feature_matrix,
    load_model,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REPORTS_DIR = REPO_ROOT / "reports"

GLOBAL_SUMMARY_JSON = REPORTS_DIR / "shap_global_summary.json"
LOCAL_TEST_EXPLANATIONS_CSV = PROCESSED_DIR / "shap_local_explanations_test_v1.csv"

CATEGORICAL_PREFIX = "vehicle_type_"
CATEGORICAL_FEATURE_NAME = "vehicle_type"

IDENTIFIER_COLUMNS = ["district", "vehicle_type", "year", "target_year"]

EXPLANATION_TYPE_NOTE = (
    "SHAP values quantify how much each feature moved this model's prediction for "
    "this row, relative to the model's average prediction. They describe the "
    "trained model's learned predictive association, not a real-world causal "
    "effect - do not present them as proof that a feature causes higher/lower "
    "service demand (CLAUDE.md Section 19, REF-007 Section 4)."
)


def build_explainer(model) -> shap.TreeExplainer:
    return shap.TreeExplainer(model)


def compute_shap_values(explainer: shap.TreeExplainer, X: pd.DataFrame) -> np.ndarray:
    """Returns a (n_rows, n_features) array in the exact column order of X
    (which callers must have built via build_feature_matrix(), so it always
    matches the model's persisted feature_columns)."""
    return np.asarray(explainer.shap_values(X))


def _aggregate_categorical_contribution(row_shap: pd.Series, feature_columns: list[str]) -> float:
    """Sums the signed SHAP values of every vehicle_type_* dummy column for
    one row - the standard way to collapse a one-hot group's SHAP values
    back to a single contribution for the original categorical feature."""
    onehot_cols = [c for c in feature_columns if c.startswith(CATEGORICAL_PREFIX)]
    return float(row_shap[onehot_cols].sum())


def global_summary(
    shap_values: np.ndarray, feature_columns: list[str], dataset_version: str | None, n_rows: int,
) -> dict:
    """17.1: a global SHAP summary across the full test dataset, ranked by
    mean(|SHAP value|) - purely data-driven, no assumed/hardcoded ordering.
    Reports both the raw per-column ranking (including the 3 individual
    vehicle_type_* dummies) and an aggregated ranking (vehicle_type collapsed
    to one entry) - see REF-009 ADR-014."""
    shap_df = pd.DataFrame(shap_values, columns=feature_columns)

    raw_ranking = (
        shap_df.abs().mean().sort_values(ascending=False).rename("mean_abs_shap").reset_index()
        .rename(columns={"index": "feature"}).to_dict(orient="records")
    )

    numeric_cols = [c for c in feature_columns if not c.startswith(CATEGORICAL_PREFIX)]
    aggregated = shap_df[numeric_cols].copy()
    aggregated[CATEGORICAL_FEATURE_NAME] = shap_df.apply(
        lambda row: _aggregate_categorical_contribution(row, feature_columns), axis=1
    )
    aggregated_ranking = (
        aggregated.abs().mean().sort_values(ascending=False).rename("mean_abs_shap").reset_index()
        .rename(columns={"index": "feature"}).to_dict(orient="records")
    )

    return {
        "dataset_version": dataset_version,
        "generated_date": date.today().isoformat(),
        "n_rows_explained": n_rows,
        "note": EXPLANATION_TYPE_NOTE,
        "aggregated_feature_ranking": aggregated_ranking,
        "raw_feature_ranking": raw_ranking,
    }


def local_explanation(
    row_shap: pd.Series, feature_columns: list[str], feature_row: pd.Series,
    base_value: float, predicted_value: float, identifiers: dict,
) -> dict:
    """17.2: the largest positive and negative SHAP contributions for one
    row, as raw numeric values DEV-012 can turn into a sentence. Contains
    BOTH a `contributions` list with vehicle_type collapsed to one
    human-readable entry, AND a `raw_contributions` list with every
    individual model-input column (including the 3 vehicle_type_* dummies) -
    nothing is silently truncated (Edge Case)."""
    numeric_cols = [c for c in feature_columns if not c.startswith(CATEGORICAL_PREFIX)]
    active_category = next(
        (c[len(CATEGORICAL_PREFIX):] for c in feature_columns if c.startswith(CATEGORICAL_PREFIX) and feature_row[c] == 1),
        None,
    )

    contributions = [
        {"feature": col, "shap_value": float(row_shap[col]), "feature_value": _clean_value(feature_row[col])}
        for col in numeric_cols
    ]
    contributions.append({
        "feature": CATEGORICAL_FEATURE_NAME,
        "shap_value": _aggregate_categorical_contribution(row_shap, feature_columns),
        "feature_value": active_category,
    })
    contributions.sort(key=lambda c: c["shap_value"], reverse=True)

    raw_contributions = [
        {"feature": col, "shap_value": float(row_shap[col]), "feature_value": _clean_value(feature_row[col])}
        for col in feature_columns
    ]
    raw_contributions.sort(key=lambda c: c["shap_value"], reverse=True)

    return {
        **identifiers,
        "base_value": float(base_value),
        "predicted_value": float(predicted_value),
        "note": EXPLANATION_TYPE_NOTE,
        "contributions": contributions,
        "raw_contributions": raw_contributions,
    }


def _clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, (np.floating, np.integer)):
        return float(value)
    return value


def explain_rows(
    df_subset: pd.DataFrame, model, encoder, explainer: shap.TreeExplainer, active_numeric_features: list[str],
) -> list[dict]:
    """Computes local explanations for an arbitrary set of rows (any subset
    of the frozen-dataset schema - test-split rows, or an 'unlabeled' live-
    inference row a dashboard user selects). Always rebuilds X via
    build_feature_matrix() with the model's own persisted encoder/feature
    list - never a fresh fit, so this can never silently diverge from the
    DEV-008 training schema."""
    X = build_feature_matrix(df_subset, active_numeric_features, encoder)
    feature_columns = list(X.columns)
    shap_values = compute_shap_values(explainer, X)
    predictions = model.predict(X)
    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[0])

    df_subset = df_subset.reset_index(drop=True)
    results = []
    for i in range(len(df_subset)):
        identifiers = {col: _clean_value(df_subset.loc[i, col]) for col in IDENTIFIER_COLUMNS if col in df_subset.columns}
        results.append(local_explanation(
            row_shap=pd.Series(shap_values[i], index=feature_columns),
            feature_columns=feature_columns,
            feature_row=X.iloc[i],
            base_value=base_value,
            predicted_value=float(predictions[i]),
            identifiers=identifiers,
        ))
    return results


def explain_row(
    df: pd.DataFrame, district: str, vehicle_type: str, year: int, model, encoder,
    explainer: shap.TreeExplainer, active_numeric_features: list[str],
) -> dict:
    """Convenience wrapper for DEV-012: explain exactly one (district,
    vehicle_type, year) row from the frozen dataset (or an equivalent
    feature-schema dataframe)."""
    row = df[(df["district"] == district) & (df["vehicle_type"] == vehicle_type) & (df["year"] == year)]
    if len(row) != 1:
        raise ValueError(
            f"Expected exactly one row for ({district}, {vehicle_type}, {year}), found {len(row)}."
        )
    return explain_rows(row, model, encoder, explainer, active_numeric_features)[0]


def run(
    models_dir: Path = MODELS_DIR,
    frozen_csv: Path = FROZEN_CSV,
    global_summary_json: Path = GLOBAL_SUMMARY_JSON,
    local_explanations_csv: Path = LOCAL_TEST_EXPLANATIONS_CSV,
) -> dict:
    logging.basicConfig(level=logging.INFO)

    model, encoder, metadata = load_model(models_dir)
    df = pd.read_csv(frozen_csv)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    explainer = build_explainer(model)
    active_numeric_features = metadata["active_numeric_features"]

    X_test = build_feature_matrix(test_df, active_numeric_features, encoder)
    feature_columns = list(X_test.columns)
    if feature_columns != metadata["feature_columns"]:
        raise ValueError(
            "SHAP feature columns do not match the saved model's metadata.json feature_columns - "
            f"got {feature_columns}, expected {metadata['feature_columns']}."
        )

    shap_values = compute_shap_values(explainer, X_test)
    summary = global_summary(shap_values, feature_columns, metadata.get("dataset_version"), len(test_df))

    local_explanations = explain_rows(test_df, model, encoder, explainer, active_numeric_features)

    global_summary_json.parent.mkdir(parents=True, exist_ok=True)
    with open(global_summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    local_df = pd.DataFrame([
        {
            **{k: v for k, v in exp.items() if k in IDENTIFIER_COLUMNS},
            "base_value": exp["base_value"],
            "predicted_value": exp["predicted_value"],
            "target_value": test_df.loc[i, TARGET_COLUMN],
            **{f"shap_{c['feature']}": c["shap_value"] for c in exp["raw_contributions"]},
        }
        for i, exp in enumerate(local_explanations)
    ])
    local_explanations_csv.parent.mkdir(parents=True, exist_ok=True)
    local_df.to_csv(local_explanations_csv, index=False)

    logger.info(
        "SHAP: wrote global summary (%s) and %d local explanations (%s). Top feature: %s",
        global_summary_json, len(local_explanations), local_explanations_csv,
        summary["aggregated_feature_ranking"][0]["feature"],
    )
    return summary


if __name__ == "__main__":
    run()
