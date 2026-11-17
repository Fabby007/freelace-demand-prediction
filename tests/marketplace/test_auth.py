"""DEV-018 tests: registration, login/logout, role-based route protection,
CSRF, and password hashing.

Maps to DEV-018.md's Testing Requirements: "registration success (both
roles), duplicate-email rejection, login success/failure, logout clears
session, blocked-account login rejection, role_required denies a wrong-role
user with 403, admin account is not reachable via any public registration
route."
"""

from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_BLOCKED, User

from .conftest import create_user, get_csrf_token, login


# --- Registration -----------------------------------------------------

def test_customer_registration_creates_hashed_password(client):
    token = get_csrf_token(client, "/register/customer")
    response = client.post(
        "/register/customer",
        data={
            "name": "Amara Perera",
            "email": "amara@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    user = User.query.filter_by(email="amara@example.com").first()
    assert user is not None
    assert user.role == ROLE_CUSTOMER
    assert user.password_hash != "supersecret1"
    assert "supersecret1" not in user.password_hash
    assert user.check_password("supersecret1")


def test_mechanic_registration_creates_mechanic_role(client):
    token = get_csrf_token(client, "/register/mechanic")
    client.post(
        "/register/mechanic",
        data={
            "name": "Nimal Silva",
            "email": "nimal@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    user = User.query.filter_by(email="nimal@example.com").first()
    assert user is not None
    assert user.role == ROLE_MECHANIC


def test_duplicate_email_registration_rejected(client):
    create_user(email="dup@example.com")
    token = get_csrf_token(client, "/register/customer")
    response = client.post(
        "/register/customer",
        data={
            "name": "Someone Else",
            "email": "dup@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "csrf_token": token,
        },
    )
    assert response.status_code == 200  # re-rendered form, not a redirect
    assert User.query.filter_by(email="dup@example.com").count() == 1
    assert b"already exists" in response.data


def test_password_confirmation_mismatch_rejected(client):
    token = get_csrf_token(client, "/register/customer")
    response = client.post(
        "/register/customer",
        data={
            "name": "Mismatch Case",
            "email": "mismatch@example.com",
            "password": "supersecret1",
            "confirm_password": "differentpassword",
            "csrf_token": token,
        },
    )
    assert User.query.filter_by(email="mismatch@example.com").first() is None
    assert b"must match" in response.data


def test_no_public_route_can_create_an_admin_account(client):
    token = get_csrf_token(client, "/register/customer")
    client.post(
        "/register/customer",
        data={
            "name": "Attempted Admin",
            "email": "notadmin@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "role": "admin",  # not a real form field — smuggling attempt must have no effect
            "csrf_token": token,
        },
    )
    user = User.query.filter_by(email="notadmin@example.com").first()
    assert user is not None
    assert user.role == ROLE_CUSTOMER
    assert user.role != ROLE_ADMIN


# --- Login / logout -----------------------------------------------------

def test_login_success(client):
    create_user(email="login@example.com", password="mypassword1")
    response = login(client, "login@example.com", "mypassword1")
    assert response.status_code == 200
    assert b"Welcome back" in response.data


def test_login_wrong_password_rejected(client):
    create_user(email="wrongpw@example.com", password="correctpassword")
    response = login(client, "wrongpw@example.com", "incorrectpassword")
    assert b"Invalid email or password" in response.data


def test_login_unknown_email_rejected(client):
    response = login(client, "doesnotexist@example.com", "whatever123")
    assert b"Invalid email or password" in response.data


def test_blocked_account_login_rejected_with_distinct_message(client):
    create_user(email="blocked@example.com", password="mypassword1", status=STATUS_BLOCKED)
    response = login(client, "blocked@example.com", "mypassword1")
    assert b"deactivated" in response.data
    assert b"Welcome back" not in response.data


def test_logout_clears_session(client):
    create_user(email="logout@example.com", password="mypassword1")
    login(client, "logout@example.com", "mypassword1")
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    protected = client.get("/account/", follow_redirects=False)
    assert protected.status_code == 302
    assert "/login" in protected.headers["Location"]


def test_login_required_route_redirects_anonymous_to_login(client):
    response = client.get("/account/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- Role-based route protection ----------------------------------------

def test_role_required_denies_wrong_role_with_403(client):
    create_user(role=ROLE_MECHANIC, email="mech@example.com", password="mypassword1")
    login(client, "mech@example.com", "mypassword1")
    response = client.get("/account/")  # customer-only route
    assert response.status_code == 403


def test_admin_route_rejects_customer(client):
    create_user(role=ROLE_CUSTOMER, email="cust@example.com", password="mypassword1")
    login(client, "cust@example.com", "mypassword1")
    response = client.get("/admin/")
    assert response.status_code == 403


def test_admin_route_rejects_mechanic(client):
    create_user(role=ROLE_MECHANIC, email="mechadmin@example.com", password="mypassword1")
    login(client, "mechadmin@example.com", "mypassword1")
    response = client.get("/admin/")
    assert response.status_code == 403


def test_admin_route_rejects_anonymous(client):
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_route_accessible_to_admin_only(client):
    create_user(role=ROLE_ADMIN, email="admin@example.com", password="mypassword1")
    login(client, "admin@example.com", "mypassword1")
    response = client.get("/admin/")
    assert response.status_code == 200


def test_mechanic_cannot_reach_customer_account_route(client):
    create_user(role=ROLE_MECHANIC, email="mechonly@example.com", password="mypassword1")
    login(client, "mechonly@example.com", "mypassword1")
    response = client.get("/account/")
    assert response.status_code == 403


def test_customer_cannot_reach_mechanic_or_insights_routes(client):
    create_user(role=ROLE_CUSTOMER, email="custonly@example.com", password="mypassword1")
    login(client, "custonly@example.com", "mypassword1")
    assert client.get("/mechanic/profile").status_code == 403
    assert client.get("/insights/").status_code == 403


def test_stub_role_protected_pages_reachable_by_correct_role(client):
    create_user(role=ROLE_MECHANIC, email="stubmech@example.com", password="mypassword1")
    login(client, "stubmech@example.com", "mypassword1")
    # /mechanic/profile is real as of DEV-019: a profile-less mechanic is
    # redirected to the edit-profile form (DEV-019 FR3), not a bare 200.
    assert client.get("/mechanic/profile").status_code == 302
    assert client.get("/mechanic/profile", follow_redirects=True).status_code == 200
    # /insights/ remains a DEV-023 stub (unaffected by DEV-019).
    assert client.get("/insights/").status_code == 200


# --- CSRF -----------------------------------------------------------------

def test_csrf_protection_rejects_post_without_token(client):
    response = client.post(
        "/register/customer",
        data={
            "name": "No Token",
            "email": "notoken@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
        },
    )
    assert response.status_code == 400
    assert User.query.filter_by(email="notoken@example.com").first() is None


def test_csrf_protection_rejects_login_post_without_token(client):
    create_user(email="csrflogin@example.com", password="mypassword1")
    response = client.post(
        "/login",
        data={"email": "csrflogin@example.com", "password": "mypassword1"},
    )
    assert response.status_code == 400


# --- Admin CLI provisioning ------------------------------------------------

def test_admin_cli_provisioning_creates_admin_account(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "create-admin",
            "--name", "Site Admin",
            "--email", "siteadmin@example.com",
            "--password", "adminpassword1",
        ],
    )
    assert result.exit_code == 0
    admin = User.query.filter_by(email="siteadmin@example.com").first()
    assert admin is not None
    assert admin.role == ROLE_ADMIN
    assert admin.check_password("adminpassword1")


def test_admin_cli_rejects_duplicate_email(app):
    create_user(role=ROLE_ADMIN, email="dupadmin@example.com", password="adminpassword1")
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "create-admin",
            "--name", "Duplicate",
            "--email", "dupadmin@example.com",
            "--password", "adminpassword1",
        ],
    )
    assert result.exit_code != 0
    assert User.query.filter_by(role=ROLE_ADMIN).count() == 1


def test_admin_cli_rejects_short_password(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "create-admin",
            "--name", "Weak Password",
            "--email", "weak@example.com",
            "--password", "short",
        ],
    )
    assert result.exit_code != 0
    assert User.query.filter_by(email="weak@example.com").first() is None


def test_admin_cli_rejects_email_the_login_form_would_refuse(app, client):
    # Regression (pre-demo audit, 2026-11-17): the CLI used to accept
    # "admin@school.local", which the login form's Email() validator rejects,
    # leaving an admin account that could never log in.
    runner = app.test_cli_runner()
    for bad_email in ("admin@school.local", "not-an-email"):
        result = runner.invoke(
            args=["create-admin", "--name", "Bad Email", "--email", bad_email, "--password", "adminpassword1"],
        )
        assert result.exit_code != 0
        assert User.query.filter_by(email=bad_email).first() is None


def test_admin_created_by_cli_can_log_in(app, client):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin", "--name", "Site Admin", "--email", "loginadmin@example.com", "--password", "adminpassword1"],
    )
    assert result.exit_code == 0
    response = login(client, "loginadmin@example.com", "adminpassword1")
    assert b"Welcome back" in response.data


# --- Customer account edit (FR-M03) ---------------------------------------

def test_customer_account_view_and_edit(client):
    create_user(role=ROLE_CUSTOMER, email="editme@example.com", password="mypassword1", name="Old Name")
    login(client, "editme@example.com", "mypassword1")
    token = get_csrf_token(client, "/account/")
    response = client.post(
        "/account/",
        data={"name": "New Name", "email": "editme@example.com", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    updated = User.query.filter_by(email="editme@example.com").first()
    assert updated.name == "New Name"


def test_customer_account_edit_rejects_email_already_used_by_another_account(client):
    create_user(role=ROLE_CUSTOMER, email="taken@example.com", password="mypassword1")
    create_user(role=ROLE_CUSTOMER, email="editor@example.com", password="mypassword1")
    login(client, "editor@example.com", "mypassword1")
    token = get_csrf_token(client, "/account/")
    response = client.post(
        "/account/",
        data={"name": "Editor", "email": "taken@example.com", "csrf_token": token},
    )
    assert b"already exists" in response.data
    assert User.query.filter_by(email="editor@example.com").first() is not None


# --- Login/register choice pages and "Freelancer" terminology -------------
# (UI/UX refinement: user-facing labels only — the underlying `mechanic`
# role, routes, and authentication logic are unchanged; see app/routes/auth.py)

def test_login_choice_page_offers_customer_and_freelancer_options(client):
    html = client.get("/login/choose").get_data(as_text=True)
    assert "Login as Customer" in html
    assert "Login as Freelancer" in html
    assert 'href="/login?as=customer"' in html
    assert 'href="/login?as=mechanic"' in html


def test_register_choice_page_offers_customer_and_freelancer_options(client):
    html = client.get("/register/choose").get_data(as_text=True)
    assert "Register as Customer" in html
    assert "Register as Freelancer" in html


def test_register_choice_customer_link_reaches_customer_registration_route(client):
    html = client.get("/register/choose").get_data(as_text=True)
    assert "/register/customer" in html
    # Following the link itself reaches the real, unchanged registration form.
    response = client.get("/register/customer")
    assert response.status_code == 200
    assert b"Register as a Customer" in response.data


def test_register_choice_freelancer_link_reaches_existing_mechanic_registration_route(client):
    html = client.get("/register/choose").get_data(as_text=True)
    assert "/register/mechanic" in html
    # The route itself is unchanged — still /register/mechanic, still creates
    # a role='mechanic' account — only its user-facing heading changed.
    response = client.get("/register/mechanic")
    assert response.status_code == 200
    assert b"Register as a Freelancer" in response.data


def test_login_as_customer_hint_shows_customer_heading_but_authenticates_normally(client):
    create_user(role=ROLE_CUSTOMER, email="hintcust@example.com", password="mypassword1")
    html = client.get("/login?as=customer").get_data(as_text=True)
    assert "Customer Login" in html

    token = get_csrf_token(client, "/login?as=customer")
    response = client.post(
        "/login?as=customer",
        data={"email": "hintcust@example.com", "password": "mypassword1", "csrf_token": token},
        follow_redirects=True,
    )
    assert b"Welcome back" in response.data


def test_login_as_freelancer_hint_shows_freelancer_heading_but_authenticates_normally(client):
    create_user(role=ROLE_MECHANIC, email="hintmech@example.com", password="mypassword1")
    html = client.get("/login?as=mechanic").get_data(as_text=True)
    assert "Freelancer Login" in html

    token = get_csrf_token(client, "/login?as=mechanic")
    response = client.post(
        "/login?as=mechanic",
        data={"email": "hintmech@example.com", "password": "mypassword1", "csrf_token": token},
        follow_redirects=False,
    )
    # Same real routing as before this change (DEV-019 FR3): a mechanic with
    # no profile yet is sent to profile completion regardless of the hint.
    assert response.status_code == 302
    assert response.headers["Location"] == "/mechanic/profile/edit"


def test_login_without_a_role_hint_still_shows_generic_heading(client):
    html = client.get("/login").get_data(as_text=True)
    assert "<h1>Log in</h1>" in html


def test_an_invalid_role_hint_is_ignored_not_trusted(client):
    """The `as` hint is cosmetic only — an unrecognized or tampered value
    must never be reflected as-is or cause an error, and must never affect
    which account actually gets logged in."""
    response = client.get("/login?as=admin")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h1>Log in</h1>" in html  # falls back to the generic heading


def test_home_page_top_right_nav_shows_login_and_register_for_anonymous_visitor(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/login/choose"' in html
    assert 'href="/register/choose"' in html
    assert ">Login<" in html
    assert ">Register<" in html


def test_freelancer_wording_used_for_authentication_choices(client):
    """Account/role framing says 'Freelancer'; the underlying route paths
    and the database role value are untouched (verified separately)."""
    login_choice_html = client.get("/login/choose").get_data(as_text=True)
    register_choice_html = client.get("/register/choose").get_data(as_text=True)
    assert "Login as Mechanic" not in login_choice_html
    assert "Register as Mechanic" not in register_choice_html


def test_post_login_mechanic_terminology_is_unaffected(client):
    """Per the explicit instruction: after login, "Mechanic Profile",
    "Find a Mechanic", and similar mechanic-domain terms may remain,
    since customers are still searching for *mechanics*."""
    create_user(role=ROLE_MECHANIC, email="postlogin@example.com", password="mypassword1")
    login(client, "postlogin@example.com", "mypassword1")
    html = client.get("/mechanic/profile/edit").get_data(as_text=True)
    assert "mechanic profile" in html.lower()


def test_freelancer_registration_still_creates_a_mechanic_role_account(client):
    """The internal database role remains 'mechanic' — only labels changed."""
    token = get_csrf_token(client, "/register/mechanic")
    client.post(
        "/register/mechanic",
        data={
            "name": "Role Check Freelancer",
            "email": "rolecheck@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    user = User.query.filter_by(email="rolecheck@example.com").first()
    assert user is not None
    assert user.role == ROLE_MECHANIC
