"""Streamlit dashboard in v2 mode, using Streamlit's AppTest with the real engine.

The switch is patched only inside each test, and the cached engine is cleared
around it, so the v1 dashboard tests keep using the committed v1 default.
"""
import json
from pathlib import Path
from unittest.mock import patch

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard import data_access
from dashboard.views import (
    BAND_COLOURS,
    FLEET_TABLE_COLUMNS,
    build_band_choropleth_figure,
    build_fleet_ranking_table,
    build_fleet_trend_figure,
    clockwise_geojson,
    format_fleet_method_summary,
)
from src.recommendation.fleet_opportunity_v2 import REPO_ROOT, FleetDataError, FleetOpportunityEngine

APP_PATH = str(REPO_ROOT / "dashboard" / "app.py")
EXACT_DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)
MEANING_FRAGMENT = "does not represent actual mechanic jobs or measured service demand"

pytestmark = pytest.mark.skipif(
    not Path(REPO_ROOT / "data" / "processed" / "v2" / "modelling_dataset_v2.csv").exists(),
    reason="Dataset v2 not present locally",
)


def _clear():
    data_access.load_ranking_engine.clear()
    st.cache_data.clear()


@pytest.fixture
def v2_mode():
    _clear()
    with patch("src.recommendation.active_engine.get_active_engine_name", return_value="v2"):
        yield
    _clear()


@pytest.fixture(scope="module")
def engine():
    return FleetOpportunityEngine.load()


def _run() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    return at


def _selectbox(at, label):
    return next(sb for sb in at.sidebar.selectbox if sb.label == label)


def _all_text(at) -> str:
    parts = []
    for group in (at.title, at.header, at.subheader, at.markdown, at.caption, at.info, at.warning, at.metric):
        parts.extend(getattr(item, "label", "") + " " + str(item.value) for item in group)
    for group in (at.sidebar.selectbox, at.sidebar.slider):
        parts.extend(item.label for item in group)
    parts.extend(item.value for item in at.sidebar.header)
    return " ".join(parts)


def test_app_runs_with_interface_label_and_project_title(v2_mode):
    at = _run()
    assert at.title[0].value == "Vehicle-Fleet Service Opportunity - Sri Lanka"
    assert any("Mechanic Service Demand Opportunity Prediction and Recommendation System" in c.value for c in at.caption)


def test_disclaimer_and_meaning_note_are_visible_and_separate(v2_mode):
    at = _run()
    assert any(i.value == EXACT_DISCLAIMER for i in at.info)
    assert any(c.value == EXACT_DISCLAIMER for c in at.sidebar.caption)
    assert any(MEANING_FRAGMENT in i.value and EXACT_DISCLAIMER not in i.value for i in at.info)
    assert any("did not beat last year's value" in c.value for c in at.caption)


def test_no_model_wording_or_demand_claims(v2_mode):
    at = _run()
    text = _all_text(at)
    for word in ("XGBoost", "SHAP", "Predicted", "Prediction year", "best districts"):
        assert word not in text
    allowed = (
        text.replace("Mechanic Service Demand Opportunity Prediction and Recommendation System", "")
        .replace(EXACT_DISCLAIMER, "").replace(MEANING_FRAGMENT, "")
    )
    assert "demand" not in allowed.lower()


def test_table_shows_required_columns_and_real_values(v2_mode, engine):
    at = _run()
    table = at.dataframe[0].value
    assert list(table.columns) == FLEET_TABLE_COLUMNS
    expected = engine.rank("Motorcycle", 2024, top_n=25)["ranked_districts"][:5]
    assert table["District"].tolist() == [e["district"] for e in expected]
    assert table["Licensed vehicles"].tolist() == [int(e["licence_count"]) for e in expected]
    assert table["Licensed vehicles"].iloc[0] == 394975


def test_table_and_map_use_the_same_bands(v2_mode):
    at = _run()
    at.sidebar.slider[0].set_value(25).run()
    table = at.dataframe[0].value.set_index("District")
    spec = json.loads(at.get("plotly_chart")[0].proto.figure.spec)

    map_bands = {}
    for trace in spec["data"]:
        for location in trace["locations"]:
            map_bands[location] = trace["name"]
    geo = data_access.load_geo_resources()["canonical_to_shape_name"]
    assert len(map_bands) == 25
    for district, row in table.iterrows():
        assert map_bands[geo[district]] == row["Opportunity band"]


def test_vehicle_type_updates_panels(v2_mode, engine):
    at = _run()
    _selectbox(at, "District for detailed view").select("Kandy").run()
    _selectbox(at, "Vehicle category").select("Car").run()
    assert not at.exception
    assert at.metric[0].value == "52,858"
    assert at.dataframe[0].value["District"].iloc[0] == "Colombo"

    _selectbox(at, "Vehicle category").select("Three-wheeler").run()
    assert at.metric[0].value == "78,853"
    assert at.dataframe[0].value["District"].iloc[0] == "Gampaha"


def test_top_n_changes_row_count(v2_mode):
    at = _run()
    at.sidebar.slider[0].set_value(2).run()
    assert len(at.dataframe[0].value) == 2


def test_data_year_selector_changes_year_and_labels_history(v2_mode):
    at = _run()
    box = _selectbox(at, "Data year")
    assert "2023 data (2024 estimate)" in box.options and "2019 data (history)" in box.options
    assert box.value == 2024
    box.select(2023).run()
    assert not at.exception
    assert any("(2022)" in s.value for s in at.subheader)


def test_flagged_top_district_shows_warning(v2_mode):
    at = _run()
    warnings = [w.value for w in at.warning]
    assert any(w.startswith("Kurunegala (rank 1).") and "On the 2022 count it ranked 2nd." in w for w in warnings)
    table = at.dataframe[0].value.set_index("District")
    assert table.loc["Kurunegala", "Reliability"] == "Uncertain value"
    assert table.loc["Kurunegala", "Data quality note"]
    assert table.loc["Gampaha", "Reliability"] == "Reported"
    assert table.loc["Gampaha", "Data quality note"] == ""


def test_unflagged_detail_has_no_warning(v2_mode):
    at = _run()
    at.sidebar.slider[0].set_value(1).run()
    _selectbox(at, "Vehicle category").select("Car").run()
    _selectbox(at, "District for detailed view").select("Colombo").run()
    assert not at.warning


def test_rule_based_explanation_panel(v2_mode):
    at = _run()
    _selectbox(at, "District for detailed view").select("Anuradhapura").run()
    text = " ".join(m.value for m in at.markdown)
    assert "**Why this district ranks here**" in text
    assert "Anuradhapura had 186,540 licensed motorcycles in 2023, ranking 5th of 25 districts" in text
    assert any("No model is involved" in c.value for c in at.caption)
    assert not any("SHAP" in c.value for c in at.caption)


def test_trend_panel_is_drawn(v2_mode):
    at = _run()
    assert len(at.get("plotly_chart")) == 2


def test_missing_value_shows_message_not_zero(v2_mode):
    at = _run()
    _selectbox(at, "Vehicle category").select("Car").run()
    _selectbox(at, "Data year").select(2020).run()
    _selectbox(at, "District for detailed view").select("Ampara").run()
    assert not at.exception
    assert any("No usable 2019 car count for Ampara" in w.value for w in at.warning)
    assert any("No usable 2019 count is available" in i.value for i in at.info)
    assert "Ampara" not in at.dataframe[0].value["District"].tolist()


def test_no_data_state_shows_message_and_no_charts(v2_mode):
    with patch.object(FleetOpportunityEngine, "rank") as mock_rank:
        mock_rank.return_value = {
            "status": "no_data", "message": "No Motorcycle licence counts are available for 2029.",
            "excluded_districts": [], "ranked_districts": [], "top_n": [], "disclaimer": EXACT_DISCLAIMER,
        }
        at = _run()
    assert any("available for 2029" in w.value for w in at.warning)
    assert len(at.get("plotly_chart")) == 0


def test_data_check_failure_shows_error_and_no_results(v2_mode):
    with patch.object(FleetOpportunityEngine, "load", side_effect=FleetDataError("simulated mismatch")):
        at = _run()
    assert any("failed a check" in e.value for e in at.error)
    assert len(at.dataframe) == 0 and len(at.get("plotly_chart")) == 0


def test_method_panel_present(v2_mode):
    at = _run()
    assert any(s.value == "Data sources and method" for s in at.subheader)
    summary = next(d.value for d in at.dataframe if list(d.value.columns) == ["Field", "Value"])
    assert "Previous-year value (no machine-learning model)" in summary["Value"].tolist()
    assert len(at.dataframe) >= 3


def test_unsupported_query_keeps_safe_fallback(v2_mode):
    at = _run()
    before = _selectbox(at, "Vehicle category").value
    at.sidebar.text_input[0].set_value("what is the weather today")
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any("could not be confidently matched" in w.value for w in at.warning)
    assert _selectbox(at, "Vehicle category").value == before


def test_confident_query_only_selects_category(v2_mode):
    at = _run()
    at.sidebar.text_input[0].set_value("I fix cars")
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert _selectbox(at, "Vehicle category").value == "Car"
    assert at.dataframe[0].value["District"].iloc[0] == "Colombo"


def test_v1_setting_shows_v1_dashboard():
    """Rollback: the v1 view returns when the setting is v1."""
    _clear()
    try:
        with patch("src.recommendation.active_engine.get_active_engine_name", return_value="v1"):
            at = _run()
        assert at.title[0].value == "Mechanic Service Demand Opportunity - Sri Lanka"
        assert "Predicted value" in at.dataframe[0].value.columns
        assert any("Data sources and model version" in s.value for s in at.subheader)
    finally:
        _clear()


# --- Presentation functions ---------------------------------------------------

def test_ranking_table_handles_empty_and_missing_change():
    assert list(build_fleet_ranking_table([]).columns) == FLEET_TABLE_COLUMNS
    entry = {
        "rank": 1, "district": "Jaffna", "opportunity_band": "High", "licence_count": 1000.0, "share_pct": 12.34,
        "change_pct": None, "reliability": "Reported", "data_quality_flag": None,
    }
    row = build_fleet_ranking_table([entry]).iloc[0]
    assert pd.isna(row["Change from previous year (%)"])
    assert row["Share of vehicle type (%)"] == 12.3 and row["Data quality note"] == ""


def test_band_map_has_one_trace_per_band_in_order(engine):
    geojson = data_access.load_geo_resources()
    fig = build_band_choropleth_figure(
        engine.rank("Car", 2024, top_n=25)["ranked_districts"], geojson["geojson"], geojson["canonical_to_shape_name"], "Car",
    )
    assert [t.name for t in fig.data] == ["Low", "Moderate", "High", "Very High"]
    assert list(BAND_COLOURS) == ["Low", "Moderate", "High", "Very High"]


def test_map_rings_are_clockwise_and_source_object_is_unchanged():
    """Counter-clockwise rings made every district fill the area outside itself."""
    source = data_access.load_geo_resources()["geojson"]
    before = json.dumps(source)
    fixed = clockwise_geojson(source)
    assert json.dumps(source) == before

    def outer_rings(geojson):
        for feature in geojson["features"]:
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            yield from (polygon[0] for polygon in polygons)

    def signed_area(ring):
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])) / 2

    assert all(signed_area(ring) < 0 for ring in outer_rings(fixed))
    assert [abs(signed_area(r)) for r in outer_rings(fixed)] == pytest.approx([abs(signed_area(r)) for r in outer_rings(source)])
    assert [f["properties"] for f in fixed["features"]] == [f["properties"] for f in source["features"]]


def test_clockwise_geojson_handles_polygon_and_keeps_holes_opposite():
    # Made-up squares, used only to test ring direction.
    outer = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]  # counter-clockwise
    hole = [[0.5, 0.5], [0.5, 1], [1, 1], [1, 0.5], [0.5, 0.5]]  # clockwise
    geojson = {"features": [{"properties": {}, "geometry": {"type": "Polygon", "coordinates": [outer, hole]}}]}
    rings = clockwise_geojson(geojson)["features"][0]["geometry"]["coordinates"]
    assert rings[0] == outer[::-1]
    assert rings[1] == hole[::-1]


def test_trend_keeps_gap_and_marks_flagged_years(engine):
    fig = build_fleet_trend_figure(engine.history("Jaffna", "Motorcycle"), "Jaffna", "Motorcycle")
    years = list(fig.data[0].x)
    assert pd.isna(fig.data[0].y[years.index(2021)])  # a gap, never zero
    assert fig.data[0].connectgaps in (None, False)

    flagged = build_fleet_trend_figure(engine.history("Kurunegala", "Motorcycle"), "Kurunegala", "Motorcycle")
    assert flagged.data[1].name == "Flagged as uncertain"
    assert list(flagged.data[1].x) == [2023]
    assert flagged.data[1].marker.symbol == "x"


def test_method_summary_is_a_two_column_table(engine):
    df = format_fleet_method_summary(engine.method_summary())
    assert list(df.columns) == ["Field", "Value"]
