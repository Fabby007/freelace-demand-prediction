"""DEV-013 / DEV-015 tests for dashboard/views.py's pure presentation
functions - deliberately free of Streamlit, so these run fast and test the
actual data transformation logic directly.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest

from dashboard.views import (
    DISCLAIMER,
    build_choropleth_figure,
    build_ranking_table,
    build_trend_figure,
    format_model_version_summary,
    format_source_register,
)

EXACT_DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)


def test_disclaimer_constant_matches_appendix_c3_verbatim():
    assert DISCLAIMER == EXACT_DISCLAIMER


# --- Choropleth map ---------------------------------------------------------

def test_choropleth_uses_same_predicted_values_as_input():
    ranked = [
        {"rank": 1, "district": "Kandy", "predicted_value": 500.0, "opportunity_band": "High"},
        {"rank": 2, "district": "Galle", "predicted_value": 200.0, "opportunity_band": "Moderate"},
    ]
    geojson = {"features": [
        {"properties": {"shapeName": "Kandy District"}}, {"properties": {"shapeName": "Galle District"}},
    ]}
    canonical_to_shape_name = {"Kandy": "Kandy District", "Galle": "Galle District"}

    fig = build_choropleth_figure(ranked, geojson, canonical_to_shape_name, "Motorcycle")
    values = list(fig.data[0].z)
    assert sorted(values) == sorted([500.0, 200.0])


def test_choropleth_maps_canonical_district_to_correct_shape_name():
    ranked = [{"rank": 1, "district": "Kandy", "predicted_value": 500.0, "opportunity_band": "High"}]
    geojson = {"features": [{"properties": {"shapeName": "Kandy District"}}]}
    canonical_to_shape_name = {"Kandy": "Kandy District"}
    fig = build_choropleth_figure(ranked, geojson, canonical_to_shape_name, "Motorcycle")
    assert list(fig.data[0].locations) == ["Kandy District"]


# --- Ranking table -----------------------------------------------------------

def test_ranking_table_preserves_data_quality_flags():
    entries = [
        {"rank": 1, "district": "Colombo", "predicted_value": 100.0, "opportunity_band": "High",
         "data_quality_flag": None, "target_data_quality_flag": "district_sum_exceeds_dmt_national_total_for_new_registrations"},
        {"rank": 2, "district": "Galle", "predicted_value": 50.0, "opportunity_band": "Moderate",
         "data_quality_flag": None, "target_data_quality_flag": None},
    ]
    df = build_ranking_table(entries)
    assert df.loc[df["District"] == "Colombo", "Data quality note"].iloc[0] == "district_sum_exceeds_dmt_national_total_for_new_registrations"
    assert df.loc[df["District"] == "Galle", "Data quality note"].iloc[0] == ""


def test_ranking_table_column_order_and_names():
    entries = [{"rank": 1, "district": "Kandy", "predicted_value": 10.0, "opportunity_band": "Low",
                "data_quality_flag": None, "target_data_quality_flag": None}]
    df = build_ranking_table(entries)
    assert list(df.columns) == ["Rank", "District", "Predicted value", "Opportunity band", "Data quality note"]


def test_ranking_table_handles_empty_top_n_gracefully():
    """Edge Case: a top-N selection larger than the number of valid entries
    must not error - build_ranking_table is called with an already-sliced
    (possibly empty) list."""
    df = build_ranking_table([])
    assert len(df) == 0
    assert list(df.columns) == ["Rank", "District", "Predicted value", "Opportunity band", "Data quality note"]


# --- Historical trend --------------------------------------------------------

def test_trend_figure_does_not_fabricate_missing_years():
    """Real gaps (missing years) must appear as gaps in the plotted series,
    never interpolated or zero-filled (REF-009 ADR-005)."""
    history_df = pd.DataFrame({
        "year": [2019, 2020, 2021, 2022, 2023],
        "new_registrations": [755.0, 492.0, 214.0, None, 813.0],
        "data_quality_flag": [None] * 5,
    })
    fig = build_trend_figure(history_df, "Kandy", "Motorcycle")
    y_values = list(fig.data[0].y)
    assert y_values[3] is None or (isinstance(y_values[3], float) and pd.isna(y_values[3]))


# --- Data-source panel -------------------------------------------------------

def test_format_source_register_selects_expected_columns():
    df = pd.DataFrame({
        "source_id": ["X"], "source_name": ["DCS"], "publication_title": ["Handbook"],
        "url": ["https://example.com"], "expected_variables": ["foo"], "geography": ["All"],
        "time_range": ["2019-2023"], "file_type": ["PDF"], "licence": ["Public"],
        "download_date": ["2026-08-15"], "status": ["confirmed"], "notes": ["n/a"],
    })
    formatted = format_source_register(df)
    assert list(formatted.columns) == ["Source", "Publication", "URL", "Licence", "Retrieved", "Status"]


def test_format_model_version_summary_is_all_string_dataframe():
    """Avoids the Arrow mixed-type-column serialization warning - every
    displayed value must already be a string."""
    model_metadata = {
        "generated_date": "2026-08-15",
        "test_metrics": {"mae": 312.8663456186335, "n_scored": 47, "n_total": 47},
    }
    dataset_version_info = {"dataset_version": "modelling_dataset_v1_1310eaead622"}
    df = format_model_version_summary(model_metadata, dataset_version_info)
    assert list(df.columns) == ["Field", "Value"]
    assert all(isinstance(v, str) for v in df["Value"])
    assert "312.9" in df.loc[df["Field"] == "Test-period average error (MAE)", "Value"].iloc[0]


def test_format_model_version_summary_handles_missing_metrics_gracefully():
    df = format_model_version_summary({"test_metrics": {}}, {"dataset_version": None})
    assert df.loc[df["Field"] == "Test-period average error (MAE)", "Value"].iloc[0] == "n/a"
