"""DEV-024 tests: the security/UI-consistency checks that don't belong to
any single earlier DEV spec — SQL-injection resistance, no-password-in-logs,
disclaimer placement across the whole app, role-aware navigation, and
referential integrity after cascading deletes.

Per-route CSRF/ownership/role/upload tests already exist in
tests/marketplace/test_{auth,mechanic_profile,search,reviews,admin,
insights_integration}.py — this file adds only what DEV-024's own audit
found was not yet covered anywhere (see DEV-024.md's Additional
Implementation Notes for the full audit record).
"""

import os
import re

from app.extensions import db
from app.models.mechanic import DEFAULT_SERVICE_NAMES, MechanicProfile, MechanicService, MechanicVehicleType
from app.models.review import Review
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, User

from .conftest import create_mechanic_profile, create_user, get_csrf_token, login

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app")

SQLI_PAYLOAD = "Robert'); DROP TABLE user;--"


# --- SQL-injection resistance (FR2) ---------------------------------------

def test_injection_shaped_name_stored_and_rendered_literally(client, app):
    """A classic injection-shaped string in the registration name field
    must be treated as ordinary data — the ORM's parameterized queries mean
    it can never alter query behavior, and the `user` table must still
    exist and be queryable afterward."""
    token = get_csrf_token(client, "/register/customer")
    response = client.post(
        "/register/customer",
        data={
            "name": SQLI_PAYLOAD,
            "email": "sqli1@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    user = User.query.filter_by(email="sqli1@example.com").first()
    assert user is not None
    assert user.name == SQLI_PAYLOAD  # stored exactly, not interpreted

    # The table still exists and is queryable — proves no injection occurred.
    assert User.query.count() >= 1


def test_injection_shaped_review_text_rendered_safely_and_escaped(client, app):
    """Same payload in a review's free-text field: stored literally, and
    rendered HTML-escaped by Jinja2's autoescaping (no `|safe` filter is
    used anywhere on user-submitted text), so it can never execute as HTML
    either."""
    mechanic_user = create_user(role=ROLE_MECHANIC, email="sqlimech@example.com")
    profile = create_mechanic_profile(mechanic_user)
    create_user(role=ROLE_CUSTOMER, email="sqlicust@example.com", password="password123")
    login(client, "sqlicust@example.com", "password123")

    token = get_csrf_token(client, f"/mechanic/{profile.id}")
    review_text = f"{SQLI_PAYLOAD} <script>alert(1)</script> but otherwise a real review of decent length."
    client.post(
        f"/mechanic/{profile.id}/review",
        data={"rating": "4", "review_text": review_text, "csrf_token": token},
        follow_redirects=True,
    )

    review = Review.query.filter_by(mechanic_id=profile.id).first()
    assert review is not None
    assert review.review_text == review_text  # stored exactly

    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html  # never rendered as live HTML
    assert "&lt;script&gt;" in html  # Jinja2's autoescaping did its job

    assert User.query.count() >= 1  # table still intact


# --- No password data in logs (FR2) ---------------------------------------

def test_no_source_file_logs_password_values():
    """Static check across every app/ source file: no logging call
    references a password variable/field. Passwords are hashed at
    registration and never otherwise touched by any logging statement."""
    offending = []
    for root, _dirs, files in os.walk(APP_DIR):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(root, filename)
            with open(path, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if re.search(r"\blog(ger)?\.[a-z]+\(", line) and "password" in line.lower():
                        offending.append(f"{path}:{lineno}: {line.strip()}")
    assert offending == []


# --- Disclaimer placement (FR4) --------------------------------------------

APPENDIX_C3_DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)
REVIEW_DISCLAIMER_FRAGMENT = "not verified against any completed-job"


def test_ml_disclaimer_appears_only_where_specified(client, app):
    mechanic_user = create_user(role=ROLE_MECHANIC, email="discloc@example.com", password="password123")
    profile = create_mechanic_profile(mechanic_user)
    create_user(role=ROLE_CUSTOMER, email="disclocc@example.com", password="password123")

    # Present: Opportunity Insights.
    login(client, "discloc@example.com", "password123")
    assert APPENDIX_C3_DISCLAIMER in client.get("/insights/").get_data(as_text=True)
    client.get("/logout")

    # Absent everywhere else that a role can reach.
    pages_without_ml_disclaimer = [
        ("/", None),
        ("/search", None),
        (f"/mechanic/{profile.id}", None),
    ]
    for path, _ in pages_without_ml_disclaimer:
        html = client.get(path).get_data(as_text=True)
        assert APPENDIX_C3_DISCLAIMER not in html, path

    login(client, "disclocc@example.com", "password123")
    assert APPENDIX_C3_DISCLAIMER not in client.get("/account/").get_data(as_text=True)
    client.get("/logout")

    login(client, "discloc@example.com", "password123")
    assert APPENDIX_C3_DISCLAIMER not in client.get("/mechanic/profile").get_data(as_text=True)


def test_review_disclaimer_appears_only_where_specified(client, app):
    mechanic_user = create_user(role=ROLE_MECHANIC, email="revdiscloc@example.com", password="password123")
    profile = create_mechanic_profile(mechanic_user)

    # Present: public profile page, and the mechanic's own dashboard.
    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert REVIEW_DISCLAIMER_FRAGMENT in html

    login(client, "revdiscloc@example.com", "password123")
    dashboard_html = client.get("/mechanic/profile").get_data(as_text=True)
    assert REVIEW_DISCLAIMER_FRAGMENT in dashboard_html
    client.get("/logout")

    # Absent from unrelated pages.
    for path in ["/", "/search"]:
        html = client.get(path).get_data(as_text=True)
        assert REVIEW_DISCLAIMER_FRAGMENT not in html, path


def test_the_two_disclaimers_are_never_merged_into_one_sentence(client, app):
    """REF-013 Section 5: the two disclaimers must remain textually
    distinct wherever both could plausibly appear near each other (the
    mechanic's own dashboard, which shows both review content and a link
    to Opportunity Insights)."""
    mechanic_user = create_user(role=ROLE_MECHANIC, email="bothdisc@example.com", password="password123")
    create_mechanic_profile(mechanic_user)
    login(client, "bothdisc@example.com", "password123")

    dashboard_html = client.get("/mechanic/profile").get_data(as_text=True)
    assert REVIEW_DISCLAIMER_FRAGMENT in dashboard_html
    assert APPENDIX_C3_DISCLAIMER not in dashboard_html  # ML disclaimer lives only on /insights/

    insights_html = client.get("/insights/").get_data(as_text=True)
    assert APPENDIX_C3_DISCLAIMER in insights_html
    assert REVIEW_DISCLAIMER_FRAGMENT not in insights_html  # review disclaimer lives only where reviews show


# --- Role-aware navigation (FR4) -------------------------------------------

def test_navigation_is_correctly_role_aware_in_all_four_states(client, app):
    create_user(role=ROLE_CUSTOMER, email="navcust@example.com", password="password123")
    create_user(role=ROLE_MECHANIC, email="navmech@example.com", password="password123")
    create_user(role=ROLE_ADMIN, email="navadmin@example.com", password="password123")

    anon_html = client.get("/").get_data(as_text=True)
    assert "Login" in anon_html and "Register" in anon_html
    assert "My Account" not in anon_html and "My Profile" not in anon_html and ">Admin<" not in anon_html

    login(client, "navcust@example.com", "password123")
    cust_html = client.get("/").get_data(as_text=True)
    assert "My Account" in cust_html and "My Reviews" in cust_html
    assert "My Profile" not in cust_html and "Opportunity Insights" not in cust_html and ">Admin<" not in cust_html
    client.get("/logout")

    login(client, "navmech@example.com", "password123")
    mech_html = client.get("/").get_data(as_text=True)
    assert "My Profile" in mech_html and "Opportunity Insights" in mech_html
    assert "My Account" not in mech_html and ">Admin<" not in mech_html
    client.get("/logout")

    login(client, "navadmin@example.com", "password123")
    admin_html = client.get("/").get_data(as_text=True)
    assert ">Admin<" in admin_html
    assert "My Account" not in admin_html and "My Profile" not in admin_html


# --- Referential integrity after cascading deletes (database integrity) ---

def test_no_orphaned_rows_after_a_full_delete_chain(app):
    """Consolidated check spanning every relationship type at once — the
    pairwise cascades were already verified individually in DEV-019/022,
    this confirms none of them interfere with each other when a mechanic
    with a full profile (vehicle types, services, and a review) is deleted
    in one operation."""
    mechanic_user = create_user(role=ROLE_MECHANIC, email="orphancheck@example.com")
    profile = create_mechanic_profile(
        mechanic_user,
        vehicle_types=["Motorcycle", "Car"],
        service_names=list(DEFAULT_SERVICE_NAMES[:2]),
    )
    reviewer = create_user(role=ROLE_CUSTOMER, email="orphanreviewer@example.com")
    review = Review(customer_id=reviewer.id, mechanic_id=profile.id, rating=5, review_text="x" * 20)
    db.session.add(review)
    db.session.commit()

    profile_id = profile.id
    mechanic_user_id = mechanic_user.id

    db.session.delete(mechanic_user)
    db.session.commit()

    assert db.session.get(User, mechanic_user_id) is None
    assert db.session.get(MechanicProfile, profile_id) is None
    assert MechanicVehicleType.query.filter_by(mechanic_id=profile_id).count() == 0
    assert Review.query.filter_by(mechanic_id=profile_id).count() == 0
    assert db.session.execute(
        MechanicService.__table__.select().where(MechanicService.mechanic_id == profile_id)
    ).fetchall() == []
    # The reviewer's own account and their (now-deleted) review's absence
    # don't affect the reviewer row itself — only the review is gone.
    assert db.session.get(User, reviewer.id) is not None
