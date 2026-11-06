"""Shared fixtures/helpers for the marketplace test suite.

CSRF protection is left ON in the testing config (see app/config.py) and is
never disabled here — `get_csrf_token()` fetches a real token from the
rendered form so tests exercise the actual Flask-WTF protection, per the
project rule against weakening security to make tests pass.
"""

import re

import pytest

from app import create_app
from app.extensions import db
from app.models.user import ROLE_CUSTOMER, User


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def get_csrf_token(client, get_url):
    response = client.get(get_url)
    html = response.get_data(as_text=True)
    tag_match = re.search(r'<input[^>]*name="csrf_token"[^>]*>', html)
    assert tag_match, f"Could not find a CSRF token field on {get_url}"
    value_match = re.search(r'value="([^"]+)"', tag_match.group(0))
    assert value_match, f"CSRF token field found but had no value on {get_url}"
    return value_match.group(1)


def create_user(role=ROLE_CUSTOMER, email="user@example.com", password="password123",
                 name="Test User", status="active"):
    user = User(name=name, email=email, role=role, status=status)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email, password, follow_redirects=True):
    token = get_csrf_token(client, "/login")
    return client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": token},
        follow_redirects=follow_redirects,
    )


def create_mechanic_profile(user, contact_number="0771234567", district="Colombo",
                             years_experience=5, description=None, vehicle_types=None,
                             service_names=None):
    """Create a MechanicProfile directly against the DB (bypassing the HTTP
    form), for tests that need an existing profile as setup rather than as
    the thing under test."""
    from app.models.mechanic import MechanicProfile, MechanicVehicleType, Service

    profile = MechanicProfile(
        user_id=user.id,
        contact_number=contact_number,
        district=district,
        years_experience=years_experience,
        description=description,
    )
    db.session.add(profile)
    db.session.flush()

    for vt in (vehicle_types or []):
        db.session.add(MechanicVehicleType(mechanic_id=profile.id, vehicle_type=vt))

    if service_names:
        profile.services = Service.query.filter(Service.name.in_(service_names)).all()

    db.session.commit()
    return profile
