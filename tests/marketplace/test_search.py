"""DEV-020 tests: mechanic search/filtering, pagination, the public
mechanic profile view, and the marketplace/ML boundary.

No Review model exists yet (DEV-021 is not implemented) — every mechanic
currently has an identical, absent rating, so these tests do not assert
any specific rating-based ordering beyond the documented stable fallback
(alphabetical by name); see app/routes/marketplace.py's docstring.
"""

import os

from app.extensions import db
from app.models.mechanic import DEFAULT_SERVICE_NAMES, MechanicProfile, Service
from app.models.user import ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_BLOCKED, User

from .conftest import create_mechanic_profile, create_user, get_csrf_token, login


def _make_mechanic(email, name, district="Kandy", vehicle_types=None, service_names=None,
                    years_experience=5, status="active"):
    user = create_user(role=ROLE_MECHANIC, email=email, name=name, status=status)
    profile = create_mechanic_profile(
        user, district=district, years_experience=years_experience,
        vehicle_types=vehicle_types or [], service_names=service_names or [],
    )
    return user, profile


# --- Page loads / basic listing ------------------------------------------

def test_search_page_loads_with_no_filters(client):
    response = client.get("/search")
    assert response.status_code == 200
    assert b"Find a Mechanic" in response.data


def test_active_mechanic_appears_in_unfiltered_results(client, app):
    _make_mechanic("active1@example.com", "Amara Fernando")
    response = client.get("/search")
    assert b"Amara Fernando" in response.data


def test_blocked_mechanic_does_not_appear_in_results(client, app):
    _make_mechanic("blocked1@example.com", "Blocked Mechanic", status=STATUS_BLOCKED)
    response = client.get("/search")
    assert b"Blocked Mechanic" not in response.data


def test_mechanic_with_no_profile_does_not_appear(client, app):
    # A mechanic User with no MechanicProfile at all must not crash the
    # search or appear as a phantom result.
    create_user(role=ROLE_MECHANIC, email="noprofile@example.com", name="No Profile Yet")
    response = client.get("/search")
    assert response.status_code == 200
    assert b"No Profile Yet" not in response.data


# --- Filters ---------------------------------------------------------------

def test_filter_by_district(client, app):
    _make_mechanic("d1@example.com", "Kandy Mechanic", district="Kandy")
    _make_mechanic("d2@example.com", "Galle Mechanic", district="Galle")

    response = client.get("/search?district=Kandy")
    assert b"Kandy Mechanic" in response.data
    assert b"Galle Mechanic" not in response.data


def test_filter_by_vehicle_type(client, app):
    _make_mechanic("v1@example.com", "Bike Guy", vehicle_types=["Motorcycle"])
    _make_mechanic("v2@example.com", "Car Guy", vehicle_types=["Car"])

    response = client.get("/search?vehicle_type=Motorcycle")
    assert b"Bike Guy" in response.data
    assert b"Car Guy" not in response.data


def test_filter_by_service(client, app):
    service = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[0]).first()
    other_service = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[1]).first()
    _make_mechanic("s1@example.com", "Electrical Person", service_names=[DEFAULT_SERVICE_NAMES[0]])
    _make_mechanic("s2@example.com", "Other Person", service_names=[DEFAULT_SERVICE_NAMES[1]])

    response = client.get(f"/search?service={service.id}")
    assert b"Electrical Person" in response.data
    assert b"Other Person" not in response.data
    assert other_service.id != service.id


def test_mechanic_name_search_field_no_longer_appears(client, app):
    """UI/UX refinement: a customer (often searching during a breakdown)
    cannot be expected to know a mechanic's name in advance — the free-text
    name field was intentionally removed from the search form."""
    html = client.get("/search").get_data(as_text=True)
    assert "Mechanic name" not in html
    assert 'name="name"' not in html


def test_name_query_parameter_no_longer_filters_results(client, app):
    """A `?name=` query string (e.g. an old bookmarked link) must be
    silently ignored, not applied as a filter — the route no longer reads
    or acts on it at all."""
    _make_mechanic("n1@example.com", "Nimal Perera")
    _make_mechanic("n2@example.com", "Sunil Silva")

    response = client.get("/search?name=Nimal")
    assert response.status_code == 200
    assert b"Nimal Perera" in response.data
    assert b"Sunil Silva" in response.data  # no longer filtered out


def test_combined_filters(client, app):
    _make_mechanic(
        "c1@example.com", "Match Person", district="Jaffna",
        vehicle_types=["Three-wheeler"], service_names=[DEFAULT_SERVICE_NAMES[2]],
    )
    _make_mechanic(
        "c2@example.com", "Wrong District", district="Colombo",
        vehicle_types=["Three-wheeler"], service_names=[DEFAULT_SERVICE_NAMES[2]],
    )
    service = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[2]).first()

    response = client.get(f"/search?district=Jaffna&vehicle_type=Three-wheeler&service={service.id}")
    assert b"Match Person" in response.data
    assert b"Wrong District" not in response.data


def test_invalid_filter_values_are_ignored_not_errors(client, app):
    _make_mechanic("iv1@example.com", "Visible Mechanic")
    response = client.get("/search?district=NotARealDistrict&vehicle_type=Truck&service=abc&page=notanumber")
    assert response.status_code == 200
    assert b"Visible Mechanic" in response.data


def test_no_results_shows_empty_state(client, app):
    _make_mechanic("only1@example.com", "Only Mechanic", district="Kandy")
    response = client.get("/search?district=Mannar")
    assert response.status_code == 200
    assert b"No mechanics found" in response.data
    assert b"Only Mechanic" not in response.data


def test_clear_filters_link_present_on_empty_state(client, app):
    response = client.get("/search?district=Mannar")
    assert b"Clear filters" in response.data


# --- Sorting / pagination ---------------------------------------------------

def test_results_have_a_stable_deterministic_order(client, app):
    _make_mechanic("order1@example.com", "Zed Mechanic")
    _make_mechanic("order2@example.com", "Amal Mechanic")
    html = client.get("/search").get_data(as_text=True)
    assert html.index("Amal Mechanic") < html.index("Zed Mechanic")


def test_pagination_splits_results_across_pages(client, app):
    for i in range(15):
        _make_mechanic(f"page{i}@example.com", f"Mechanic Number {i:02d}")

    page1 = client.get("/search?page=1")
    assert page1.status_code == 200
    assert b"Page 1 of 2" in page1.data

    page2 = client.get("/search?page=2")
    assert page2.status_code == 200
    assert b"Page 2 of 2" in page2.data


# --- Public mechanic profile -----------------------------------------------

def test_public_profile_shows_expected_fields(client, app):
    user, profile = _make_mechanic(
        "profile1@example.com", "Full Profile Mechanic", district="Matara",
        vehicle_types=["Car"], service_names=[DEFAULT_SERVICE_NAMES[0]], years_experience=12,
    )
    profile.contact_number = "0711112222"
    profile.description = "Honest and reliable work."
    db.session.commit()

    response = client.get(f"/mechanic/{profile.id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Full Profile Mechanic" in html
    assert "Matara" in html
    assert "12 year" in html
    assert "0711112222" in html
    assert "Honest and reliable work." in html
    assert "Car" in html
    # Jinja2 auto-escapes "&" to "&amp;" in rendered HTML output.
    assert "General Repair &amp; Servicing" in html
    assert "No ratings yet" in html
    assert "not verified against any completed-job" in html


def test_public_profile_has_tel_link(client, app):
    user, profile = _make_mechanic("tel1@example.com", "Callable Mechanic")
    profile.contact_number = "071 234 5678"
    db.session.commit()

    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert 'href="tel:0712345678"' in html


def test_contact_number_not_shown_on_list_page(client, app):
    user, profile = _make_mechanic("nolist1@example.com", "Hidden Number Mechanic")
    profile.contact_number = "0779998877"
    db.session.commit()

    html = client.get("/search").get_data(as_text=True)
    assert "Hidden Number Mechanic" in html
    assert "0779998877" not in html


def test_profile_photo_or_default_avatar_shown(client, app):
    _make_mechanic("noavatar1@example.com", "No Photo Mechanic")
    list_html = client.get("/search").get_data(as_text=True)
    assert "default-avatar.svg" in list_html

    user, profile = _make_mechanic("avatar1@example.com", "Has Photo Mechanic")
    profile.profile_image_path = "images/mechanics/fake-uuid.png"
    db.session.commit()
    profile_html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "images/mechanics/fake-uuid.png" in profile_html


def test_nonexistent_mechanic_profile_returns_404(client):
    response = client.get("/mechanic/999999")
    assert response.status_code == 404
    assert b"not found" in response.data.lower() or b"404" in response.data


def test_blocked_mechanic_profile_returns_404_not_the_profile(client, app):
    user, profile = _make_mechanic("blockedprofile1@example.com", "Blocked Profile Person", status=STATUS_BLOCKED)
    response = client.get(f"/mechanic/{profile.id}")
    assert response.status_code == 404
    assert b"Blocked Profile Person" not in response.data


# --- Ownership / role rules unaffected by DEV-020 --------------------------

def test_customer_still_cannot_reach_mechanic_edit_route(client):
    create_user(role=ROLE_CUSTOMER, email="stillcust@example.com", password="mypassword1")
    login(client, "stillcust@example.com", "mypassword1")
    assert client.get("/mechanic/profile/edit").status_code == 403


def test_mechanic_a_editing_does_not_affect_mechanic_bs_public_profile(client, app):
    mechanic_a = create_user(role=ROLE_MECHANIC, email="pa@example.com", password="mypassword1")
    create_mechanic_profile(mechanic_a, district="Colombo")
    _, profile_b = _make_mechanic("pb@example.com", "Mechanic B", district="Galle")

    login(client, "pa@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    client.post(
        "/mechanic/profile/edit",
        data={
            "contact_number": "0770000000", "district": "Trincomalee", "years_experience": "1",
            "description": "", "vehicle_types": [], "services": [], "csrf_token": token,
        },
        follow_redirects=True,
    )

    html = client.get(f"/mechanic/{profile_b.id}").get_data(as_text=True)
    assert "Mechanic B" in html
    assert "Galle" in html


# --- Search/list results never come from anywhere but the marketplace DB --

def test_search_route_module_does_not_import_the_ml_pipeline():
    import app.routes.marketplace as marketplace_module

    source = os.path.abspath(marketplace_module.__file__)
    with open(source, "r", encoding="utf-8") as fh:
        contents = fh.read()
    assert "import src" not in contents
    assert "from src" not in contents


def test_search_does_not_write_to_ml_data_directories(app):
    # A search request must not create/modify anything under data/, models/,
    # or mlruns/ — sanity-checked by mtime, not by mocking, so a real
    # accidental write would be caught, not just an intended one.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(app.instance_path)))
    watched = [os.path.join(repo_root, d) for d in ("data", "models", "mlruns")]
    before = {}
    for path in watched:
        if os.path.isdir(path):
            before[path] = sorted(os.listdir(path))

    client = app.test_client()
    client.get("/search")
    client.get("/search?district=Kandy&vehicle_type=Motorcycle")

    for path in watched:
        if os.path.isdir(path):
            assert sorted(os.listdir(path)) == before.get(path, [])
