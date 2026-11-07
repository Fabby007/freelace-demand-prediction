"""Opportunity Insights in v2 mode, through the real route and the real engine.

v2 is the committed default (REF-009 ADR-043). The switch is still patched
inside each test, so these tests do not depend on the config file, and the v1
page tests in test_insights_integration.py pin v1 the same way.
"""
import html as html_lib

import pytest

import app.routes.insights as insights_module
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC

from .conftest import create_user, login

DISCLAIMER_TEXT = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)
MEANING_FRAGMENT = "does not represent actual mechanic jobs or measured service demand"
PROJECT_TITLE = "Mechanic Service Demand Opportunity Prediction and Recommendation System"


@pytest.fixture
def v2_mode(monkeypatch):
    from src.recommendation import active_engine

    monkeypatch.setattr(active_engine, "get_active_engine_name", lambda *a, **k: "v2")
    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)


@pytest.fixture
def v2_engine(v2_mode):
    return insights_module._get_ranking_engine()


def _page(client, url="/insights/", email="fleetmech@example.com"):
    create_user(role=ROLE_MECHANIC, email=email, password="password123", name="Fleet Mechanic")
    login(client, email, "password123")
    response = client.get(url)
    return response, html_lib.unescape(response.get_data(as_text=True))


def test_page_shows_real_top_districts(client, app, v2_engine):
    response, text = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024&top_n=5")
    assert response.status_code == 200
    assert "Vehicle-Fleet Service Opportunity" in text
    expected = v2_engine.rank("Motorcycle", 2024, top_n=25)["top_n"]
    for entry in expected[:5]:
        assert entry["district"] in text
        assert f"{entry['licence_count']:,.0f}" in text
        assert entry["recommendation_sentence"] in text
    assert "394,975" in text
    assert text.count('class="insights-card-header"') == 5
    # Card headings only: the district dropdown lists every name earlier in the page.
    assert text.index("<h3>Kurunegala") < text.index("<h3>Gampaha") < text.index("<h3>Anuradhapura")


def test_each_vehicle_type_has_its_own_ranking(client, app, v2_mode):
    _, motorcycle = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024&top_n=1", email="a@example.com")
    assert "#1</span>\n        <h3>Kurunegala" in motorcycle
    car = html_lib.unescape(client.get("/insights/?vehicle_type=Car&period=2024&top_n=1").get_data(as_text=True))
    assert "#1</span>\n        <h3>Colombo" in car
    wheeler = html_lib.unescape(client.get("/insights/?vehicle_type=Three-wheeler&period=2024&top_n=1").get_data(as_text=True))
    assert "#1</span>\n        <h3>Gampaha" in wheeler


def test_table_lists_all_reporting_districts_with_band_share_and_change(client, app, v2_engine):
    _, text = _page(client, "/insights/?vehicle_type=Car&period=2024")
    assert "All reporting districts" in text
    for entry in v2_engine.rank("Car", 2024, top_n=25)["ranked_districts"]:
        assert f"<td>{entry['district']}</td>" in text
        assert f"<td>{entry['licence_count']:,.0f}</td>" in text
        assert f"<td>{entry['share_pct']:.1f}</td>" in text
    for band in ("Low", "Moderate", "High", "Very High"):
        assert f"<td>{band}</td>" in text
    assert "Share of Car (%)" in text and "Change from previous year (%)" in text


def test_required_disclaimer_and_meaning_note_are_shown_and_not_merged(client, app, v2_mode):
    _, text = _page(client)
    assert text.count(DISCLAIMER_TEXT) == 2
    assert MEANING_FRAGMENT in text
    assert DISCLAIMER_TEXT + " " + "This indicator" not in text
    assert "did not beat last year's value" in text


def test_no_model_wording_or_demand_claims(client, app, v2_mode):
    _, text = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024&top_n=25")
    assert "XGBoost" not in text and "SHAP" not in text and "Predicted value" not in text
    assert "Production model" not in text and "Positive factors" not in text

    # The Project row and the two fixed notes are the only places these words are allowed.
    allowed = text.replace(PROJECT_TITLE, "").replace(DISCLAIMER_TEXT, "").replace(MEANING_FRAGMENT, "")
    for word in ("demand", "customer numbers", "income", "best district"):
        assert word not in allowed.lower()


def test_official_project_title_is_preserved(client, app, v2_mode):
    _, text = _page(client)
    assert PROJECT_TITLE in text


def test_flagged_value_shows_warning_with_reason(client, app, v2_mode):
    _, text = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024&district=Kurunegala")
    assert "Uncertain value:" in text
    assert "only Table 9.3 citing the Department of Motor Traffic" in text
    assert "On the 2022 count it ranked 2nd." in text
    assert 'class="insights-warning"' in text
    assert text.count("Uncertain value:") == 1  # shown as the warning, not repeated in the list


def test_unflagged_value_shows_no_warning(client, app, v2_mode):
    _, text = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024&district=Gampaha")
    assert "Uncertain value" not in text
    assert 'class="insights-warning"' not in text


def test_table_marks_flagged_rows(client, app, v2_mode):
    _, text = _page(client, "/insights/?vehicle_type=Car&period=2024")
    assert text.count("Uncertain value</td>") == 3  # Kalutara, Kandy, Kilinochchi
    assert text.count("(caution)") >= 3


def test_district_filter_shows_one_real_card(client, app, v2_engine):
    _, text = _page(client, "/insights/?vehicle_type=Car&period=2024&district=Matara")
    entry = next(e for e in v2_engine.rank("Car", 2024, top_n=25)["top_n"] if e["district"] == "Matara")
    assert text.count('class="insights-card-header"') == 1
    assert entry["recommendation_sentence"] in text
    assert "All reporting districts" not in text


def test_missing_value_shows_clear_message_and_no_card(client, app, v2_mode):
    _, text = _page(client, "/insights/?vehicle_type=Car&period=2020&district=Ampara")
    assert "No usable 2019 car count for Ampara" in text
    assert "not treated as zero" in text
    assert "No opportunity data available for this district." in text
    assert 'class="insights-card-header"' not in text


def test_period_selector_uses_data_year_labels(client, app, v2_mode):
    _, text = _page(client)
    assert "Data year" in text
    assert "2023 data (2024 estimate)" in text
    assert "2019 data (history)" in text
    assert 'value="2024" selected' in text.replace('selected value="2024"', 'value="2024" selected')


def test_method_panel_replaces_model_panel(client, app, v2_mode):
    _, text = _page(client)
    assert "Method & data information" in text
    assert "Previous-year value (no machine-learning model)" in text
    assert "modelling_dataset_v2_04eaecafd7e1" in text
    assert "57-85%" in text and "2,729" in text


@pytest.mark.parametrize("url", [
    "/insights/?vehicle_type=Truck", "/insights/?period=not-a-year", "/insights/?period=2030",
    "/insights/?district=NotAPlace", "/insights/?top_n=999999", "/insights/?top_n=-5", "/insights/?top_n=abc",
])
def test_invalid_selections_fall_back_safely(client, app, v2_mode, url):
    response, text = _page(client, url)
    assert response.status_code == 200
    assert "Vehicle-Fleet Service Opportunity" in text


def test_access_rules_are_unchanged(client, app, v2_mode):
    assert client.get("/insights/", follow_redirects=False).status_code == 302

    create_user(role=ROLE_CUSTOMER, email="fleetcust@example.com", password="password123")
    login(client, "fleetcust@example.com", "password123")
    assert client.get("/insights/").status_code == 403


def test_admin_is_still_denied(client, app, v2_mode):
    create_user(role=ROLE_ADMIN, email="fleetadmin@example.com", password="password123")
    login(client, "fleetadmin@example.com", "password123")
    assert client.get("/insights/").status_code == 403


def test_data_check_failure_shows_error_page_and_no_numbers(client, app, v2_mode, monkeypatch):
    from src.recommendation import fleet_opportunity_v2 as module

    def _refuse(cls):
        raise module.FleetDataError("simulated hash mismatch")

    monkeypatch.setattr(module.FleetOpportunityEngine, "load", classmethod(_refuse))
    response, text = _page(client)
    assert response.status_code == 503
    assert "the licence data could not be loaded" in text
    assert "XGBoost" not in text and "Traceback" not in text and "simulated" not in text


def test_rank_failure_shows_error_page(client, app, v2_engine, monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("simulated")

    monkeypatch.setattr(v2_engine, "rank", _raise)
    response, text = _page(client)
    assert response.status_code == 503
    assert "the licence data could not be loaded" in text


def test_invalid_setting_shows_error_page_without_naming_a_model(client, app, monkeypatch):
    from src.recommendation import active_engine

    def _bad(*args, **kwargs):
        raise ValueError("bad setting")

    monkeypatch.setattr(active_engine, "get_active_engine_name", _bad)
    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)
    response, text = _page(client)
    assert response.status_code == 503
    assert "XGBoost" not in text and "bad setting" not in text


def test_marketplace_pages_still_work_in_v2_mode(client, app, v2_mode):
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200
    _, text = _page(client)
    assert "Opportunity Insights" in text  # the navigation link and page name are unchanged


def test_v1_mode_still_shows_the_v1_page(client, app, monkeypatch):
    """Rollback: the v1 text is rendered when the setting is v1."""
    from src.recommendation import active_engine

    monkeypatch.setattr(active_engine, "get_active_engine_name", lambda *a, **k: "v1")
    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)
    _, text = _page(client)
    assert "XGBoost (tuned)" in text and "Vehicle-Fleet Service Opportunity" not in text
    assert DISCLAIMER_TEXT in text


def test_committed_default_setting_shows_the_v2_page(client, app, monkeypatch):
    """No patch on the switch: the page follows configs/recommendation_v2.yaml."""
    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)
    response, text = _page(client, "/insights/?vehicle_type=Motorcycle&period=2024", email="default@example.com")
    assert response.status_code == 200
    assert "Vehicle-Fleet Service Opportunity" in text
    assert DISCLAIMER_TEXT in text
    assert "XGBoost" not in text
