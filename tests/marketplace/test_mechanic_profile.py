"""DEV-019 tests: mechanic profile create/edit, ownership, vehicle-type/
service mappings, photo upload security, and the profile-completion
redirect.

CSRF stays ON throughout (see conftest.get_csrf_token) — no test disables
it to make a POST easier, per project security policy.
"""

import io

from app.extensions import db
from app.models.mechanic import (
    DEFAULT_SERVICE_NAMES,
    MechanicProfile,
    MechanicVehicleType,
    Service,
)
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC
from app.utils.canonical import canonical_districts

from .conftest import create_mechanic_profile, create_user, get_csrf_token, login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 64
NOT_AN_IMAGE_BYTES = b"just some plain text pretending to be a photo" * 4


def _edit_form_data(csrf_token, **overrides):
    data = {
        "contact_number": "0771234567",
        "district": "Kandy",
        "years_experience": "3",
        "description": "Experienced motorcycle mechanic.",
        "vehicle_types": ["Motorcycle"],
        "services": [],
        "csrf_token": csrf_token,
    }
    data.update(overrides)
    return data


# --- Seed data --------------------------------------------------------

def test_default_services_are_seeded(app):
    names = {s.name for s in Service.query.all()}
    assert names == set(DEFAULT_SERVICE_NAMES)


def test_service_seeding_is_idempotent(app):
    from app.models.mechanic import seed_default_services

    seed_default_services()
    seed_default_services()
    assert Service.query.count() == len(DEFAULT_SERVICE_NAMES)


def test_canonical_districts_returns_25_names(app):
    districts = canonical_districts()
    assert len(districts) == 25
    assert "Kandy" in districts
    assert "Colombo" in districts


# --- Profile-completion redirect (FR3) ---------------------------------

def test_mechanic_with_no_profile_redirected_to_edit_after_login(client):
    create_user(role=ROLE_MECHANIC, email="newmech@example.com", password="mypassword1")
    response = login(client, "newmech@example.com", "mypassword1", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] == "/mechanic/profile/edit"


def test_mechanic_with_existing_profile_not_redirected_to_edit(client, app):
    user = create_user(role=ROLE_MECHANIC, email="existingmech@example.com", password="mypassword1")
    create_mechanic_profile(user)
    response = login(client, "existingmech@example.com", "mypassword1", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] != "/mechanic/profile/edit"


def test_profile_route_redirects_profile_less_mechanic_to_edit(client):
    create_user(role=ROLE_MECHANIC, email="noprofile@example.com", password="mypassword1")
    login(client, "noprofile@example.com", "mypassword1")
    response = client.get("/mechanic/profile", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] == "/mechanic/profile/edit"


# --- Create / edit round-trip -------------------------------------------

def test_mechanic_can_create_profile(client, app):
    user = create_user(role=ROLE_MECHANIC, email="create@example.com", password="mypassword1")
    login(client, "create@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    service_id = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[0]).first().id
    response = client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, services=[str(service_id)]),
        follow_redirects=True,
    )
    assert response.status_code == 200

    profile = MechanicProfile.query.filter_by(user_id=user.id).first()
    assert profile is not None
    assert profile.contact_number == "0771234567"
    assert profile.district == "Kandy"
    assert profile.years_experience == 3
    assert profile.vehicle_types == ["Motorcycle"]
    assert [s.id for s in profile.services] == [service_id]


def test_mechanic_can_edit_existing_profile_without_creating_a_second_row(client, app):
    user = create_user(role=ROLE_MECHANIC, email="edit@example.com", password="mypassword1")
    create_mechanic_profile(user, district="Galle", years_experience=2, vehicle_types=["Car"])
    login(client, "edit@example.com", "mypassword1")

    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, district="Matara", years_experience="7", vehicle_types=["Car", "Three-wheeler"]),
        follow_redirects=True,
    )
    assert response.status_code == 200

    assert MechanicProfile.query.filter_by(user_id=user.id).count() == 1
    profile = MechanicProfile.query.filter_by(user_id=user.id).first()
    assert profile.district == "Matara"
    assert profile.years_experience == 7
    assert profile.vehicle_types == ["Car", "Three-wheeler"]


def test_editing_profile_replaces_vehicle_type_selection_not_appends(client, app):
    user = create_user(role=ROLE_MECHANIC, email="replace@example.com", password="mypassword1")
    create_mechanic_profile(user, vehicle_types=["Motorcycle", "Car", "Three-wheeler"])
    login(client, "replace@example.com", "mypassword1")

    token = get_csrf_token(client, "/mechanic/profile/edit")
    client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, vehicle_types=["Motorcycle"]),
        follow_redirects=True,
    )

    profile = MechanicProfile.query.filter_by(user_id=user.id).first()
    assert profile.vehicle_types == ["Motorcycle"]
    assert MechanicVehicleType.query.filter_by(mechanic_id=profile.id).count() == 1


def test_profile_view_shows_saved_fields(client, app):
    user = create_user(role=ROLE_MECHANIC, email="view@example.com", password="mypassword1")
    create_mechanic_profile(
        user, contact_number="0719998888", district="Jaffna", years_experience=9,
        description="Reliable and fast.", vehicle_types=["Motorcycle"],
        service_names=[DEFAULT_SERVICE_NAMES[0]],
    )
    login(client, "view@example.com", "mypassword1")
    response = client.get("/mechanic/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "0719998888" in html
    assert "Jaffna" in html
    assert "9 year" in html
    assert "Reliable and fast." in html
    assert "Motorcycle" in html
    # Jinja2 auto-escapes "&" to "&amp;" in rendered HTML output.
    assert "General Repair &amp; Servicing" in html


# --- Ownership -----------------------------------------------------------

def test_editing_own_profile_never_affects_another_mechanics_profile(client, app):
    mechanic_a = create_user(role=ROLE_MECHANIC, email="mecha@example.com", password="mypassword1")
    mechanic_b = create_user(role=ROLE_MECHANIC, email="mechb@example.com", password="mypassword1")
    create_mechanic_profile(mechanic_a, district="Colombo", years_experience=1)
    profile_b = create_mechanic_profile(mechanic_b, district="Galle", years_experience=10)

    login(client, "mecha@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, district="Trincomalee", years_experience="20"),
        follow_redirects=True,
    )

    # Mechanic B's row must be completely untouched by A's edit.
    reloaded_b = db.session.get(MechanicProfile, profile_b.id)
    assert reloaded_b.district == "Galle"
    assert reloaded_b.years_experience == 10

    # Mechanic A's own edit route has no ID parameter to manipulate — it is
    # always scoped to current_user.mechanic_profile, so there is no URL a
    # mechanic can construct that even names another mechanic's profile.
    assert MechanicProfile.query.count() == 2


def test_customer_cannot_reach_mechanic_profile_edit_route(client):
    create_user(role=ROLE_CUSTOMER, email="custedit@example.com", password="mypassword1")
    login(client, "custedit@example.com", "mypassword1")
    assert client.get("/mechanic/profile/edit").status_code == 403


def test_admin_cannot_reach_mechanic_profile_edit_route(client):
    create_user(role=ROLE_ADMIN, email="adminedit@example.com", password="mypassword1")
    login(client, "adminedit@example.com", "mypassword1")
    assert client.get("/mechanic/profile/edit").status_code == 403


def test_anonymous_redirected_to_login_for_edit_route(client):
    response = client.get("/mechanic/profile/edit", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- Validation ------------------------------------------------------------

def test_negative_years_experience_rejected(client):
    create_user(role=ROLE_MECHANIC, email="negyears@example.com", password="mypassword1")
    login(client, "negyears@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit", data=_edit_form_data(token, years_experience="-1")
    )
    assert MechanicProfile.query.count() == 0
    assert response.status_code == 200
    assert b"realistic number" in response.data


def test_invalid_phone_number_rejected(client):
    create_user(role=ROLE_MECHANIC, email="badphone@example.com", password="mypassword1")
    login(client, "badphone@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit", data=_edit_form_data(token, contact_number="call-me-maybe")
    )
    assert MechanicProfile.query.count() == 0
    assert response.status_code == 200
    assert b"valid contact number" in response.data


def test_missing_required_fields_rejected(client):
    create_user(role=ROLE_MECHANIC, email="missing@example.com", password="mypassword1")
    login(client, "missing@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit",
        data={"contact_number": "", "district": "", "years_experience": "", "csrf_token": token},
    )
    assert MechanicProfile.query.count() == 0
    assert response.status_code == 200


def test_tampered_vehicle_type_value_rejected(client):
    create_user(role=ROLE_MECHANIC, email="tamper@example.com", password="mypassword1")
    login(client, "tamper@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, vehicle_types=["Truck"]),  # not a canonical value
    )
    assert MechanicProfile.query.count() == 0
    assert response.status_code == 200
    assert b"is not a valid choice" in response.data


def test_profile_with_no_vehicle_types_or_services_is_saveable_with_a_nudge(client, app):
    create_user(role=ROLE_MECHANIC, email="empty@example.com", password="mypassword1")
    login(client, "empty@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    response = client.post(
        "/mechanic/profile/edit",
        data=_edit_form_data(token, vehicle_types=[], services=[]),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert MechanicProfile.query.count() == 1
    assert b"Add at least one vehicle type and service" in response.data


# --- Photo upload security ------------------------------------------------

def test_valid_png_upload_is_accepted_and_stored_with_random_filename(client, app):
    create_user(role=ROLE_MECHANIC, email="photo@example.com", password="mypassword1")
    login(client, "photo@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(PNG_BYTES), "my-photo.png")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200

    profile = MechanicProfile.query.first()
    assert profile.profile_image_path is not None
    assert profile.profile_image_path.startswith("images/mechanics/")
    assert profile.profile_image_path.endswith(".png")
    assert "my-photo" not in profile.profile_image_path  # never the client-supplied filename

    import os

    saved_path = os.path.join(app.static_folder, profile.profile_image_path.replace("/", os.sep))
    assert os.path.isfile(saved_path)
    os.remove(saved_path)


def test_disallowed_file_extension_rejected(client, app):
    create_user(role=ROLE_MECHANIC, email="badext@example.com", password="mypassword1")
    login(client, "badext@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(b"whatever"), "malware.exe")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 200
    assert MechanicProfile.query.count() == 0
    assert b"Only PNG or JPG" in response.data


def test_file_with_mismatched_content_rejected_despite_valid_extension(client, app):
    create_user(role=ROLE_MECHANIC, email="mismatch@example.com", password="mypassword1")
    login(client, "mismatch@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(NOT_AN_IMAGE_BYTES), "fake.png")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 200
    assert MechanicProfile.query.count() == 0
    assert b"does not look like a valid image" in response.data


def test_oversized_upload_rejected_with_413(client, app):
    create_user(role=ROLE_MECHANIC, email="huge@example.com", password="mypassword1")
    login(client, "huge@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    oversized = PNG_BYTES + (b"\x00" * (3 * 1024 * 1024))  # 3MB, over the 2MB cap
    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(oversized), "huge.png")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 413
    assert MechanicProfile.query.count() == 0


def test_valid_jpeg_upload_accepted(client, app):
    create_user(role=ROLE_MECHANIC, email="jpegphoto@example.com", password="mypassword1")
    login(client, "jpegphoto@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(JPEG_BYTES), "photo.jpg")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200

    profile = MechanicProfile.query.first()
    assert profile.profile_image_path.endswith(".jpg")

    import os

    saved_path = os.path.join(app.static_folder, profile.profile_image_path.replace("/", os.sep))
    assert os.path.isfile(saved_path)
    os.remove(saved_path)


def test_malicious_filename_cannot_escape_the_upload_directory(client, app):
    """DEV-024 upload-security re-check: a filename containing path-traversal
    segments must never influence where the file is written — the stored
    name is always a fresh UUID, never derived from client input at all."""
    create_user(role=ROLE_MECHANIC, email="traversal@example.com", password="mypassword1")
    login(client, "traversal@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")

    data = _edit_form_data(token)
    data["photo"] = (io.BytesIO(PNG_BYTES), "../../../../etc/evil.png")
    response = client.post(
        "/mechanic/profile/edit", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200

    profile = MechanicProfile.query.first()
    assert profile.profile_image_path is not None
    assert ".." not in profile.profile_image_path
    assert profile.profile_image_path.startswith("images/mechanics/")

    import os

    saved_path = os.path.join(app.static_folder, profile.profile_image_path.replace("/", os.sep))
    # Resolves to strictly inside the intended upload directory, not above it.
    upload_dir = os.path.join(app.static_folder, "images", "mechanics")
    assert os.path.commonpath([os.path.abspath(saved_path), os.path.abspath(upload_dir)]) == os.path.abspath(upload_dir)
    assert os.path.isfile(saved_path)
    os.remove(saved_path)


def test_no_photo_uploaded_leaves_profile_image_path_null(client, app):
    create_user(role=ROLE_MECHANIC, email="nophoto@example.com", password="mypassword1")
    login(client, "nophoto@example.com", "mypassword1")
    token = get_csrf_token(client, "/mechanic/profile/edit")
    client.post("/mechanic/profile/edit", data=_edit_form_data(token), follow_redirects=True)

    profile = MechanicProfile.query.first()
    assert profile.profile_image_path is None


# --- Database relationships ------------------------------------------------

def test_mechanic_profile_is_one_to_one_with_user(app):
    user = create_user(role=ROLE_MECHANIC, email="onetoone@example.com", password="mypassword1")
    profile = create_mechanic_profile(user)
    assert user.mechanic_profile.id == profile.id
    assert profile.user.id == user.id


def test_mechanic_service_join_table_reflects_many_to_many(app):
    user = create_user(role=ROLE_MECHANIC, email="m2m@example.com", password="mypassword1")
    profile = create_mechanic_profile(user, service_names=list(DEFAULT_SERVICE_NAMES[:2]))
    assert {s.name for s in profile.services} == set(DEFAULT_SERVICE_NAMES[:2])
    service = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[0]).first()
    assert profile in service.mechanics


def test_mechanic_vehicle_type_rows_deleted_when_profile_deleted(app):
    user = create_user(role=ROLE_MECHANIC, email="cascade@example.com", password="mypassword1")
    profile = create_mechanic_profile(user, vehicle_types=["Motorcycle", "Car"])
    profile_id = profile.id
    assert MechanicVehicleType.query.filter_by(mechanic_id=profile_id).count() == 2

    db.session.delete(profile)
    db.session.commit()

    assert MechanicVehicleType.query.filter_by(mechanic_id=profile_id).count() == 0
