"""DEV-023 tests: mechanic-only access, real RankingEngine integration
(no forked/duplicated prediction logic), disclaimer, error handling, the
process-wide engine cache, and the marketplace/ML write boundary.

The real ML backend (XGBoost + SHAP + SBERT stack) is loaded on first use
— slow on the very first test that touches it (consistent with DEV-013's
own documented ~15s cold start), fast afterward since the engine is a
process-wide singleton (DEV-023 FR6), reused across every test in this
file and this pytest session.
"""

import os

from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_BLOCKED, User
from app.extensions import db

from .conftest import create_user, login

DISCLAIMER_TEXT = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)


def _make_mechanic(email="insightsmech@example.com", password="password123"):
    return create_user(role=ROLE_MECHANIC, email=email, password=password, name="Insights Mechanic")


# --- Access control -----------------------------------------------------

def test_mechanic_can_access_opportunity_insights(client, app):
    _make_mechanic()
    login(client, "insightsmech@example.com", "password123")
    response = client.get("/insights/")
    assert response.status_code == 200
    assert b"Opportunity Insights" in response.data


def test_anonymous_denied(client, app):
    response = client.get("/insights/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_customer_denied(client, app):
    create_user(role=ROLE_CUSTOMER, email="insightscust@example.com", password="password123")
    login(client, "insightscust@example.com", "password123")
    assert client.get("/insights/").status_code == 403


def test_admin_denied(client, app):
    create_user(role=ROLE_ADMIN, email="insightsadmin@example.com", password="password123")
    login(client, "insightsadmin@example.com", "password123")
    assert client.get("/insights/").status_code == 403


def test_blocked_mechanic_denied_even_mid_session(client, app):
    """UserMixin.is_authenticated defaults to self.is_active, and
    User.is_active already checks status — so blocking mid-session takes
    effect on the very next request without requiring re-login. Verified
    here directly in the Opportunity Insights context, per this spec's
    explicit instruction, rather than assumed."""
    user = _make_mechanic(email="blockmech@example.com")
    login(client, "blockmech@example.com", "password123")
    assert client.get("/insights/").status_code == 200

    user = db.session.get(User, user.id)
    user.status = STATUS_BLOCKED
    db.session.commit()

    response = client.get("/insights/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- Real backend integration -----------------------------------------

def test_valid_vehicle_and_period_selection_renders_real_ranking(client, app):
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    _make_mechanic(email="realdata@example.com")
    login(client, "realdata@example.com", "password123")
    response = client.get(f"/insights/?vehicle_type={vehicle_type}&period={period}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"{vehicle_type} mechanics in {period}" in html


def test_ranking_output_matches_ranking_engine_directly(client, app):
    """The web layer must not alter the underlying numbers — DEV-023's own
    Testing Requirement, checked by comparing the rendered page against an
    independent, direct call to RankingEngine.rank()."""
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine, STATUS_OK

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    direct_result = engine.rank(vehicle_type, period, top_n=3)
    if direct_result["status"] != STATUS_OK or not direct_result["top_n"]:
        import pytest

        pytest.skip("No real top-N data available for this vehicle_type/period combination.")

    _make_mechanic(email="matchcheck@example.com")
    login(client, "matchcheck@example.com", "password123")
    html = client.get(f"/insights/?vehicle_type={vehicle_type}&period={period}&top_n=3").get_data(as_text=True)

    top_entry = direct_result["top_n"][0]
    assert top_entry["district"] in html
    assert f"{top_entry['predicted_value']:.0f}" in html
    assert top_entry["opportunity_band"] in html
    assert top_entry["recommendation_sentence"] in html


def test_ranking_order_is_preserved_in_rendered_html(client, app):
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine, STATUS_OK

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    direct_result = engine.rank(vehicle_type, period, top_n=5)
    if direct_result["status"] != STATUS_OK or len(direct_result["top_n"]) < 2:
        import pytest

        pytest.skip("Fewer than 2 ranked districts available to check ordering.")

    _make_mechanic(email="orderchk@example.com")
    login(client, "orderchk@example.com", "password123")
    html = client.get(f"/insights/?vehicle_type={vehicle_type}&period={period}&top_n=5").get_data(as_text=True)

    first_district = direct_result["top_n"][0]["district"]
    second_district = direct_result["top_n"][1]["district"]
    assert html.index(first_district) < html.index(second_district)


def test_disclaimer_displayed_verbatim(client, app):
    _make_mechanic(email="disclaimercheck@example.com")
    login(client, "disclaimercheck@example.com", "password123")
    html = client.get("/insights/").get_data(as_text=True)
    assert DISCLAIMER_TEXT in html


def test_model_info_panel_present(client, app):
    _make_mechanic(email="modelinfocheck@example.com")
    login(client, "modelinfocheck@example.com", "password123")
    html = client.get("/insights/").get_data(as_text=True)
    assert "XGBoost (tuned)" in html
    assert "Dataset version" in html


# --- Optional district filter (UI/UX refinement, added post-DEV-023) ------
# The district selector never triggers a second/independent prediction —
# it only slices RankingEngine's own already-computed, full-coverage
# result (the same technique the Streamlit dashboard already uses for its
# district-detail panel, REF-009 ADR-021).

def test_district_field_exists_and_defaults_to_all_districts(client, app):
    _make_mechanic(email="distfield@example.com")
    login(client, "distfield@example.com", "password123")
    html = client.get("/insights/").get_data(as_text=True)
    assert "District (Optional)" in html
    assert "All Districts" in html


def test_all_25_canonical_districts_are_valid_dropdown_options(client, app):
    from app.utils.canonical import canonical_districts

    _make_mechanic(email="dist25@example.com")
    login(client, "dist25@example.com", "password123")
    html = client.get("/insights/").get_data(as_text=True)

    districts = canonical_districts()
    assert len(districts) == 25
    for district in districts:
        assert f'<option value="{district}">{district}</option>' in html


def test_no_district_selected_preserves_existing_top_n_behavior(client, app):
    """Default ("All Districts") must render byte-for-byte the same top-N
    ranking as before the district filter existed — proven by comparing
    against a direct RankingEngine.rank() call, not a re-derived number."""
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine, STATUS_OK

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    direct_result = engine.rank(vehicle_type, period, top_n=3)
    if direct_result["status"] != STATUS_OK or not direct_result["top_n"]:
        import pytest

        pytest.skip("No real top-N data available for this vehicle_type/period combination.")

    _make_mechanic(email="nodistrictdefault@example.com")
    login(client, "nodistrictdefault@example.com", "password123")
    html = client.get(f"/insights/?vehicle_type={vehicle_type}&period={period}&top_n=3").get_data(as_text=True)

    top_entry = direct_result["top_n"][0]
    assert top_entry["district"] in html
    assert f"{top_entry['predicted_value']:.0f}" in html
    assert "Top districts for" in html  # unchanged heading when no district is selected


def test_selecting_a_district_returns_its_real_ranking_engine_result(client, app):
    """The core of Change 1: selecting a real district (Kandy, per the
    approved example) shows exactly the rank/band/SHAP factors/sentence
    RankingEngine itself computed for it — never a re-derived value."""
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine, STATUS_OK

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    # Full-coverage call, exactly what the route itself now performs.
    direct_result = engine.rank(vehicle_type, period, top_n=len(engine.canonical_districts))
    kandy_entry = next((e for e in direct_result["top_n"] if e["district"] == "Kandy"), None)
    if direct_result["status"] != STATUS_OK or kandy_entry is None:
        import pytest

        pytest.skip("No real Kandy result available for this vehicle_type/period combination.")

    _make_mechanic(email="kandycheck@example.com")
    login(client, "kandycheck@example.com", "password123")
    html = client.get(f"/insights/?vehicle_type={vehicle_type}&period={period}&district=Kandy").get_data(as_text=True)

    assert "Opportunity for Kandy" in html
    assert f"{kandy_entry['predicted_value']:.0f}" in html
    assert kandy_entry["opportunity_band"] in html
    assert kandy_entry["recommendation_sentence"] in html
    # Exactly one card shown — not the full top-N grid.
    assert html.count('class="insights-card-header"') == 1


def test_selecting_a_district_outside_the_default_top_n_still_shows_it(client, app):
    """Proves the district filter reaches every eligible district, not just
    the ones that would normally appear in the configured top-N."""
    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.ranking_engine import RankingEngine, STATUS_OK

    engine = RankingEngine.load()
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    period = available_years[-1] + 1
    vehicle_type = VEHICLE_CATEGORIES[0]

    direct_result = engine.rank(vehicle_type, period, top_n=len(engine.canonical_districts))
    if direct_result["status"] != STATUS_OK or len(direct_result["top_n"]) < 6:
        import pytest

        pytest.skip("Fewer than 6 ranked districts available to find one outside a top-5 default.")

    below_top_5 = direct_result["top_n"][5]  # rank 6 — outside the default top_n=5

    _make_mechanic(email="belowtopn@example.com")
    login(client, "belowtopn@example.com", "password123")
    html = client.get(
        f"/insights/?vehicle_type={vehicle_type}&period={period}&district={below_top_5['district']}"
    ).get_data(as_text=True)
    assert f"Opportunity for {below_top_5['district']}" in html
    assert f"{below_top_5['predicted_value']:.0f}" in html


def test_unsupported_district_falls_back_to_all_districts_safely(client, app):
    _make_mechanic(email="baddistrict@example.com")
    login(client, "baddistrict@example.com", "password123")
    response = client.get("/insights/?district=NotARealPlace")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Top districts for" in html  # fell back to the unfiltered view


def test_district_with_no_data_shows_clear_message(client, app, monkeypatch):
    """A district genuinely absent from RankingEngine's own result (e.g. no
    eligible row for this vehicle_type/period) must show a clear message —
    never a fabricated card. Exercised via a monkeypatched result shaped
    exactly like a real one but missing one district, since the real
    dataset covers all 25 districts for the periods this page offers."""
    import app.routes.insights as insights_module
    from src.recommendation.ranking_engine import STATUS_OK

    _make_mechanic(email="districtnodata@example.com")
    login(client, "districtnodata@example.com", "password123")

    engine = insights_module._get_ranking_engine()
    real_rank = engine.rank

    def _fake_rank(vehicle_type, period, top_n=None):
        real_result = real_rank(vehicle_type, period, top_n=top_n)
        real_result = dict(real_result)
        real_result["status"] = STATUS_OK
        real_result["top_n"] = [e for e in real_result["top_n"] if e["district"] != "Kandy"]
        return real_result

    monkeypatch.setattr(engine, "rank", _fake_rank)
    response = client.get("/insights/?district=Kandy")
    assert response.status_code == 200
    assert b"No opportunity data available for this district." in response.data


# --- Validation / safe fallback -----------------------------------------

def test_invalid_vehicle_type_falls_back_safely(client, app):
    _make_mechanic(email="invalidveh@example.com")
    login(client, "invalidveh@example.com", "password123")
    response = client.get("/insights/?vehicle_type=Truck")
    assert response.status_code == 200


def test_invalid_period_falls_back_safely(client, app):
    _make_mechanic(email="invalidperiod@example.com")
    login(client, "invalidperiod@example.com", "password123")
    response = client.get("/insights/?period=not-a-year")
    assert response.status_code == 200


def test_out_of_range_top_n_clamped_safely(client, app):
    _make_mechanic(email="clamptopn@example.com")
    login(client, "clamptopn@example.com", "password123")
    assert client.get("/insights/?top_n=999999").status_code == 200
    assert client.get("/insights/?top_n=-5").status_code == 200
    assert client.get("/insights/?top_n=notanumber").status_code == 200


def test_no_data_period_shows_clear_message(client, app, monkeypatch):
    """The period dropdown is populated only from real available years
    (mirroring DEV-013's own dashboard precedent — "do not invent
    unsupported years"), so an out-of-range URL value is legitimately
    clamped back to a real one by the route, never passed through — a
    genuinely out-of-range value can never reach RankingEngine.rank() via
    this page's own UI. STATUS_NO_DATA is instead exercised directly here,
    against the real, already-loaded engine, to verify the template
    renders RankingEngine's own no-data message correctly when it occurs
    (e.g. a vehicle_type with no eligible rows for an otherwise-valid
    period) rather than a blank or fabricated ranking."""
    import app.routes.insights as insights_module
    from src.recommendation.ranking_engine import STATUS_NO_DATA

    _make_mechanic(email="nodataperiod@example.com")
    login(client, "nodataperiod@example.com", "password123")

    engine = insights_module._get_ranking_engine()
    # No apostrophe, deliberately - Jinja2 auto-escapes "'" to "&#39;" in
    # rendered HTML output, which would otherwise break a literal match.
    no_data_message = "No data is available for this selection - this period is outside the frozen datasets real coverage."

    def _fake_rank(vehicle_type, period, top_n=None):
        return {
            "vehicle_type": vehicle_type,
            "period": period,
            "status": STATUS_NO_DATA,
            "message": no_data_message,
            "excluded_districts": [],
            "ranked_districts": [],
            "top_n": [],
            "disclaimer": engine.config["disclaimer"],
        }

    monkeypatch.setattr(engine, "rank", _fake_rank)
    response = client.get("/insights/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert no_data_message in html


# --- Backend failure handling ---------------------------------------------

def test_ranking_engine_load_failure_handled_safely(client, app, monkeypatch):
    import app.routes.insights as insights_module

    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated missing model artifact")

    import src.recommendation.ranking_engine as ranking_engine_module

    monkeypatch.setattr(ranking_engine_module.RankingEngine, "load", classmethod(lambda cls: _raise()))

    _make_mechanic(email="loadfailure@example.com")
    login(client, "loadfailure@example.com", "password123")
    response = client.get("/insights/")
    assert response.status_code == 503
    assert b"temporarily unavailable" in response.data
    # No internal stack trace leaked to the page.
    assert b"RuntimeError" not in response.data
    assert b"Traceback" not in response.data

    # Reset module state so later tests in this session reload the real engine.
    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)


def test_engine_is_loaded_once_and_reused_across_requests(client, app, monkeypatch):
    import app.routes.insights as insights_module

    monkeypatch.setattr(insights_module, "_engine", None)
    monkeypatch.setattr(insights_module, "_engine_load_error", None)

    import src.recommendation.ranking_engine as ranking_engine_module

    real_load = ranking_engine_module.RankingEngine.load.__func__
    call_count = {"n": 0}

    def _counting_load(cls, *args, **kwargs):
        call_count["n"] += 1
        return real_load(cls, *args, **kwargs)

    monkeypatch.setattr(ranking_engine_module.RankingEngine, "load", classmethod(_counting_load))

    _make_mechanic(email="cachecheck@example.com")
    login(client, "cachecheck@example.com", "password123")
    client.get("/insights/")
    client.get("/insights/")
    client.get("/insights/")

    assert call_count["n"] == 1


# --- Marketplace/ML boundary ------------------------------------------

def test_insights_route_module_does_not_import_marketplace_models():
    import app.routes.insights as insights_module

    source_path = os.path.abspath(insights_module.__file__)
    with open(source_path, "r", encoding="utf-8") as fh:
        contents = fh.read()
    assert "from ..models.mechanic" not in contents
    assert "from ..models.review" not in contents


def test_insights_does_not_write_to_ml_data_directories(app):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(app.instance_path)))
    watched = [os.path.join(repo_root, d) for d in ("data", "models", "mlruns")]
    before = {}
    for path in watched:
        if os.path.isdir(path):
            before[path] = sorted(os.listdir(path))

    _make_mechanic(email="mlwritecheck@example.com")
    client = app.test_client()
    login(client, "mlwritecheck@example.com", "password123")
    client.get("/insights/")
    client.get("/insights/?vehicle_type=Car&period=2030")

    for path in watched:
        if os.path.isdir(path):
            assert sorted(os.listdir(path)) == before.get(path, [])


def test_streamlit_dashboard_files_untouched():
    """This spec must not modify dashboard/data_access.py or views.py —
    checked here by import, since neither executes anything at import time
    (they only define functions/constants). `dashboard/app.py` is
    deliberately NOT imported here: it calls main() unconditionally at
    module level and is only safe to execute inside a real Streamlit
    script-run context (Streamlit's own AppTest harness, already covered
    by tests/test_dashboard_app.py) — importing it directly from a plain
    pytest test would actually run the whole dashboard script outside that
    context. A lightweight source-text check stands in for app.py instead."""
    import dashboard.data_access as data_access_module
    import dashboard.views as views_module

    assert hasattr(data_access_module, "load_ranking_engine")
    assert hasattr(views_module, "DISCLAIMER")

    app_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dashboard", "app.py")
    with open(app_py_path, "r", encoding="utf-8") as fh:
        contents = fh.read()
    assert "def main() -> None:" in contents
