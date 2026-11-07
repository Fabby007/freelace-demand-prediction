"""DEV-013 / DEV-015 tests for dashboard/app.py - Section 26.3 dashboard
tests, run via Streamlit's official `AppTest` harness (real script
execution, real widgets, no browser needed): filters correctly update all
panels; unsupported SBERT queries produce a safe fallback; missing-period
data displays a clear message; ranking table and map use the same
prediction values; model limitation text is visible.
"""
from pathlib import Path
from unittest.mock import patch

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pytest
from streamlit.testing.v1 import AppTest

from src.models.xgboost_model import MODELS_DIR

pytestmark = pytest.mark.skipif(
    not (MODELS_DIR / "model.json").exists(), reason="DEV-008 saved model not present locally"
)

APP_PATH = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")

EXACT_DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)


@pytest.fixture(scope="module", autouse=True)
def v1_mode():
    """These tests cover the v1 dashboard, which stays available for rollback.
    v2 is the committed default (REF-009 ADR-043); its view is tested in
    test_dashboard_v2.py."""
    import streamlit as st

    from dashboard import data_access

    def _clear():
        data_access.load_ranking_engine.clear()
        st.cache_data.clear()

    _clear()
    with patch("src.recommendation.active_engine.get_active_engine_name", return_value="v1"):
        yield
    _clear()


def _run() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    return at


def _selectbox(at, label):
    return next(sb for sb in at.sidebar.selectbox if sb.label == label)


# --- App loads cleanly, no exceptions ---------------------------------------

def test_app_runs_without_exceptions():
    _run()


def test_all_19_1_controls_present():
    at = _run()
    labels = {sb.label for sb in at.sidebar.selectbox}
    assert "Vehicle category" in labels
    assert "Prediction year" in labels
    assert "District for detailed view" in labels
    assert any(s.label == "Number of districts to recommend" for s in at.sidebar.slider)
    assert len(at.sidebar.text_input) == 1  # NL query box


# --- Section 26.3: filters correctly update all panels ----------------------

def test_changing_vehicle_type_updates_forecast_metric():
    at = _run()
    _selectbox(at, "District for detailed view").select("Kandy").run()
    _selectbox(at, "Vehicle category").select("Motorcycle").run()
    moto_metric = at.metric[0].value

    _selectbox(at, "Vehicle category").select("Car").run()
    assert not at.exception
    car_metric = at.metric[0].value
    assert car_metric != moto_metric  # a real, different prediction was computed


def test_changing_district_updates_detail_panel():
    at = _run()
    _selectbox(at, "District for detailed view").select("Kandy").run()
    kandy_sentence = next(m.value for m in at.markdown if "Kandy" in m.value)

    _selectbox(at, "District for detailed view").select("Colombo").run()
    assert not at.exception
    assert any("Colombo" in m.value for m in at.markdown)
    assert not any(m.value == kandy_sentence for m in at.markdown)


def test_changing_top_n_changes_table_row_count():
    at = _run()
    at.sidebar.slider[0].set_value(2).run()
    table_2 = at.dataframe[0].value
    assert len(table_2) == 2

    at.sidebar.slider[0].set_value(7).run()
    table_7 = at.dataframe[0].value
    assert len(table_7) == 7


# --- Section 26.3: unsupported SBERT queries -> safe fallback ---------------

def test_unsupported_query_shows_fallback_and_does_not_change_vehicle_type():
    at = _run()
    vt_before = _selectbox(at, "Vehicle category").value

    at.sidebar.text_input[0].set_value("what is the weather today")
    at.sidebar.button[0].click().run()

    assert not at.exception
    assert any("could not be confidently matched" in w.value for w in at.warning)
    assert _selectbox(at, "Vehicle category").value == vt_before  # never silently changed


def test_confident_query_updates_vehicle_type_with_visible_match_and_override_available():
    at = _run()
    at.sidebar.text_input[0].set_value("I fix motorcycles")
    at.sidebar.button[0].click().run()

    assert not at.exception
    assert any("Matched to the 'Motorcycle'" in s.value for s in at.success)
    assert _selectbox(at, "Vehicle category").value == "Motorcycle"
    # override still available: the selectbox is a normal, still-editable control
    _selectbox(at, "Vehicle category").select("Car").run()
    assert not at.exception
    assert _selectbox(at, "Vehicle category").value == "Car"


def test_ambiguous_query_also_produces_safe_fallback():
    at = _run()
    at.sidebar.text_input[0].set_value("I service scooters and mopeds")
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any(
        "plausibly match more than one" in w.value or "could not be confidently matched" in w.value
        for w in at.warning
    )


# --- Section 26.3: missing-period data displays a clear message ------------

def test_missing_period_shows_clear_message_not_blank_charts():
    import streamlit as st
    st.cache_data.clear()  # cached_rank() is keyed on (vehicle_type, period, top_n) -
    # earlier tests may have already cached this exact combination with real
    # data, which would bypass the mock below entirely.

    try:
        with patch("src.recommendation.ranking_engine.RankingEngine.rank") as mock_rank:
            mock_rank.return_value = {
                "vehicle_type": "Motorcycle", "period": 2030, "status": "no_data",
                "message": "No Motorcycle data is available to predict 2030 - this period is outside the frozen dataset's real coverage.",
                "excluded_districts": [], "ranked_districts": [], "top_n": [],
                "disclaimer": EXACT_DISCLAIMER,
            }
            at = AppTest.from_file(APP_PATH, default_timeout=60)
            at.run()

        assert not at.exception
        assert any("outside the frozen dataset's real coverage" in w.value for w in at.warning)
        assert len(at.get("plotly_chart")) == 0  # no misleading blank/broken chart rendered
    finally:
        # The mock above returns the same no_data dict regardless of the
        # real (vehicle_type, period, top_n) the app actually requested,
        # which would otherwise poison cached_rank's cache for that key and
        # break every later test expecting real data - clear it again.
        st.cache_data.clear()


# --- Section 26.3: ranking table and map use the same prediction values ----

def test_table_and_map_share_identical_predicted_values():
    at = _run()
    table_df = at.dataframe[0].value  # top-N table (first dataframe rendered)
    map_fig = at.get("plotly_chart")[0].proto

    table_values = sorted(round(v, 3) for v in table_df["Predicted value"])
    # The map's colour array (z) is the predicted_value for every eligible
    # district, a superset of the table's top-N rows - every table value
    # must appear in the map's underlying data.
    import json
    map_json = json.loads(map_fig.figure.spec)
    map_z = sorted(round(v, 3) for v in map_json["data"][0]["z"])
    for v in table_values:
        assert v in map_z


# --- Section 26.3: model limitation text is visible -------------------------

def test_disclaimer_is_visible():
    at = _run()
    assert any(i.value == EXACT_DISCLAIMER for i in at.info)


def test_disclaimer_visible_in_sidebar_too():
    """Business Rule: persistent, not buried in a separate panel."""
    at = _run()
    assert any(c.value == EXACT_DISCLAIMER for c in at.sidebar.caption)


def test_data_source_and_model_version_panel_present():
    at = _run()
    assert any("Data sources and model version" in s.value for s in at.subheader)
    # at least one dataframe is the source register, one is the version summary
    assert len(at.dataframe) >= 2
