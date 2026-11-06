"""DEV-022 tests: admin dashboard, user/mechanic management, review
moderation, and the full authorization matrix for every /admin/* route.

CSRF stays ON throughout — no test disables it, per project security policy.
"""

from app.extensions import db
from app.models.mechanic import MechanicProfile, MechanicVehicleType
from app.models.review import STATUS_REMOVED_BY_ADMIN, STATUS_VISIBLE, Review
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_ACTIVE, STATUS_BLOCKED, User

from .conftest import create_mechanic_profile, create_user, get_csrf_token, login

ADMIN_ROUTES_GET = [
    "/admin/",
    "/admin/users",
    "/admin/mechanics",
    "/admin/reviews",
]


def _make_admin(email="admin@example.com", password="adminpass1"):
    return create_user(role=ROLE_ADMIN, email=email, password=password, name="Site Admin")


def _make_mechanic(email="mech@example.com", name="Test Mechanic", status=STATUS_ACTIVE):
    user = create_user(role=ROLE_MECHANIC, email=email, name=name, status=status)
    profile = create_mechanic_profile(user)
    return user, profile


def _make_customer(email="cust@example.com", name="Test Customer"):
    return create_user(role=ROLE_CUSTOMER, email=email, name=name)


def _create_review(customer, mechanic_id, rating=5, text="Solid, dependable mechanic."):
    review = Review(customer_id=customer.id, mechanic_id=mechanic_id, rating=rating, review_text=text)
    db.session.add(review)
    db.session.commit()
    return review


# --- Authorization matrix: every /admin/* route -----------------------

def test_anonymous_denied_every_admin_get_route(client, app):
    for path in ADMIN_ROUTES_GET:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_customer_denied_every_admin_get_route(client, app):
    _make_customer()
    login(client, "cust@example.com", "password123")
    for path in ADMIN_ROUTES_GET:
        assert client.get(path).status_code == 403, path


def test_mechanic_denied_every_admin_get_route(client, app):
    _make_mechanic()
    login(client, "mech@example.com", "password123")
    for path in ADMIN_ROUTES_GET:
        assert client.get(path).status_code == 403, path


def test_admin_can_reach_every_admin_get_route(client, app):
    _make_admin()
    login(client, "admin@example.com", "adminpass1")
    for path in ADMIN_ROUTES_GET:
        assert client.get(path).status_code == 200, path


def test_customer_denied_admin_post_actions(client, app):
    _make_customer()
    user, profile = _make_mechanic()
    login(client, "cust@example.com", "password123")
    token = get_csrf_token(client, "/account/")
    assert client.post(f"/admin/users/{user.id}/block", data={"csrf_token": token}).status_code == 403
    assert client.post(f"/admin/users/{user.id}/delete", data={"csrf_token": token}).status_code == 403


def test_mechanic_denied_admin_post_actions(client, app):
    _make_mechanic()
    other_user, _ = _make_mechanic(email="other@example.com")
    login(client, "mech@example.com", "password123")
    # mechanic_dashboard.html (the "/mechanic/profile" view) has no form at
    # all — /mechanic/profile/edit always renders one, regardless of state.
    token = get_csrf_token(client, "/mechanic/profile/edit")
    assert client.post(f"/admin/users/{other_user.id}/block", data={"csrf_token": token}).status_code == 403


# --- Dashboard ----------------------------------------------------------

def test_dashboard_shows_accurate_counts(client, app):
    _make_admin()
    _make_customer(email="c1@example.com")
    _make_customer(email="c2@example.com")
    _, profile = _make_mechanic()
    create_user(role=ROLE_MECHANIC, email="blk@example.com", status=STATUS_BLOCKED)
    reviewer = _make_customer(email="reviewer@example.com")
    _create_review(reviewer, profile.id)

    # 3 customers (c1, c2, reviewer); 2 mechanics (1 active with a profile,
    # 1 blocked with no profile); 1 mechanic profile; 1 blocked account;
    # 1 review, 0 removed.
    login(client, "admin@example.com", "adminpass1")
    response = client.get("/admin/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for expected_value in ("3", "2", "1", "1", "1", "0"):
        assert f'<span class="stat-value">{expected_value}</span>' in html


def test_dashboard_reflects_removed_review_count(client, app):
    _make_admin()
    _, profile = _make_mechanic()
    reviewer = _make_customer()
    review = _create_review(reviewer, profile.id)
    login(client, "admin@example.com", "adminpass1")

    before = client.get("/admin/").get_data(as_text=True)
    review.status = STATUS_REMOVED_BY_ADMIN
    db.session.commit()
    after = client.get("/admin/").get_data(as_text=True)
    assert before != after


# --- User management ------------------------------------------------------

def test_admin_user_list_shows_customers_and_mechanics(client, app):
    _make_admin()
    _make_customer(email="listedcust@example.com", name="Listed Customer")
    _make_mechanic(email="listedmech@example.com", name="Listed Mechanic")
    login(client, "admin@example.com", "adminpass1")
    html = client.get("/admin/users").get_data(as_text=True)
    assert "Listed Customer" in html
    assert "Listed Mechanic" in html


def test_admin_user_list_excludes_admin_rows(client, app):
    _make_admin()
    login(client, "admin@example.com", "adminpass1")
    html = client.get("/admin/users").get_data(as_text=True)
    assert "Site Admin" not in html


def test_admin_user_list_filter_by_role(client, app):
    _make_admin()
    _make_customer(email="fc@example.com", name="Filter Customer")
    _make_mechanic(email="fm@example.com", name="Filter Mechanic")
    login(client, "admin@example.com", "adminpass1")

    html = client.get("/admin/users?role=customer").get_data(as_text=True)
    assert "Filter Customer" in html
    assert "Filter Mechanic" not in html


def test_admin_user_list_filter_by_status(client, app):
    _make_admin()
    create_user(role=ROLE_CUSTOMER, email="activeone@example.com", name="Active One", status=STATUS_ACTIVE)
    create_user(role=ROLE_CUSTOMER, email="blockedone@example.com", name="Blocked One", status=STATUS_BLOCKED)
    login(client, "admin@example.com", "adminpass1")

    html = client.get("/admin/users?status=blocked").get_data(as_text=True)
    assert "Blocked One" in html
    assert "Active One" not in html


def test_admin_can_block_and_unblock_customer(client, app):
    _make_admin()
    customer = _make_customer()
    login(client, "admin@example.com", "adminpass1")

    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{customer.id}/block", data={"csrf_token": token}, follow_redirects=True)
    assert db.session.get(User, customer.id).status == STATUS_BLOCKED

    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{customer.id}/unblock", data={"csrf_token": token}, follow_redirects=True)
    assert db.session.get(User, customer.id).status == STATUS_ACTIVE


def test_blocking_mechanic_removes_them_from_search_and_login(client, app):
    _make_admin()
    user, profile = _make_mechanic(name="Soon Blocked")
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{user.id}/block", data={"csrf_token": token}, follow_redirects=True)

    # Log the admin out of this same client so the rest of this check
    # reflects an ordinary, unauthenticated visitor (DEV-020 search
    # behavior, DEV-018 login behavior).
    client.get("/logout")

    search_html = client.get("/search").get_data(as_text=True)
    assert "Soon Blocked" not in search_html

    login_response = client.post(
        "/login",
        data={
            "email": "mech@example.com",
            "password": "password123",
            "csrf_token": get_csrf_token(client, "/login"),
        },
    )
    assert b"deactivated" in login_response.data


def test_blocked_account_can_log_in_again_after_unblock(client, app):
    _make_admin()
    user, _ = _make_mechanic()
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{user.id}/block", data={"csrf_token": token}, follow_redirects=True)
    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{user.id}/unblock", data={"csrf_token": token}, follow_redirects=True)

    client.get("/logout")
    response = client.post(
        "/login",
        data={
            "email": "mech@example.com",
            "password": "password123",
            "csrf_token": get_csrf_token(client, "/login"),
        },
        follow_redirects=True,
    )
    assert b"Welcome back" in response.data


def test_admin_cannot_block_or_delete_self(client, app):
    admin = _make_admin()
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/users")

    response = client.post(f"/admin/users/{admin.id}/block", data={"csrf_token": token})
    assert response.status_code == 404
    assert db.session.get(User, admin.id).status == STATUS_ACTIVE

    response = client.post(f"/admin/users/{admin.id}/delete", data={"csrf_token": token})
    assert response.status_code == 404
    assert db.session.get(User, admin.id) is not None


def test_admin_cannot_manage_another_admin(client, app):
    _make_admin()
    other_admin = _make_admin(email="other-admin@example.com")
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/users")
    response = client.post(f"/admin/users/{other_admin.id}/block", data={"csrf_token": token})
    assert response.status_code == 404


def test_block_nonexistent_user_returns_404(client, app):
    _make_admin()
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/users")
    response = client.post("/admin/users/999999/block", data={"csrf_token": token})
    assert response.status_code == 404


def test_admin_delete_customer_cascades_to_their_reviews(client, app):
    _make_admin()
    customer = _make_customer()
    _, profile = _make_mechanic()
    _create_review(customer, profile.id)
    login(client, "admin@example.com", "adminpass1")

    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{customer.id}/delete", data={"csrf_token": token}, follow_redirects=True)

    assert db.session.get(User, customer.id) is None
    assert Review.query.filter_by(customer_id=customer.id).count() == 0


def test_admin_delete_mechanic_cascades_to_profile_and_reviews(client, app):
    _make_admin()
    user, profile = _make_mechanic()
    reviewer = _make_customer()
    _create_review(reviewer, profile.id)
    mechanic_id, profile_id, user_id = user.id, profile.id, user.id
    login(client, "admin@example.com", "adminpass1")

    token = get_csrf_token(client, "/admin/users")
    client.post(f"/admin/users/{user_id}/delete", data={"csrf_token": token}, follow_redirects=True)

    assert db.session.get(User, user_id) is None
    assert db.session.get(MechanicProfile, profile_id) is None
    assert Review.query.filter_by(mechanic_id=profile_id).count() == 0
    assert MechanicVehicleType.query.filter_by(mechanic_id=profile_id).count() == 0


def test_delete_requires_csrf_token(client, app):
    _make_admin()
    customer = _make_customer()
    login(client, "admin@example.com", "adminpass1")
    response = client.post(f"/admin/users/{customer.id}/delete")
    assert response.status_code == 400
    assert db.session.get(User, customer.id) is not None


def test_block_requires_csrf_token(client, app):
    _make_admin()
    customer = _make_customer()
    login(client, "admin@example.com", "adminpass1")
    response = client.post(f"/admin/users/{customer.id}/block")
    assert response.status_code == 400
    assert db.session.get(User, customer.id).status == STATUS_ACTIVE


def test_unblock_requires_csrf_token(client, app):
    _make_admin()
    customer = create_user(role=ROLE_CUSTOMER, email="unblockcsrf@example.com", status=STATUS_BLOCKED)
    login(client, "admin@example.com", "adminpass1")
    response = client.post(f"/admin/users/{customer.id}/unblock")
    assert response.status_code == 400
    assert db.session.get(User, customer.id).status == STATUS_BLOCKED


def test_remove_review_requires_csrf_token(client, app):
    _make_admin()
    _, profile = _make_mechanic()
    reviewer = _make_customer()
    review = _create_review(reviewer, profile.id)
    login(client, "admin@example.com", "adminpass1")
    response = client.post(f"/admin/reviews/{review.id}/remove")
    assert response.status_code == 400
    assert db.session.get(Review, review.id).status == STATUS_VISIBLE


def test_restore_review_requires_csrf_token(client, app):
    _make_admin()
    _, profile = _make_mechanic()
    reviewer = _make_customer()
    review = _create_review(reviewer, profile.id)
    review.status = STATUS_REMOVED_BY_ADMIN
    db.session.commit()
    login(client, "admin@example.com", "adminpass1")
    response = client.post(f"/admin/reviews/{review.id}/restore")
    assert response.status_code == 400
    assert db.session.get(Review, review.id).status == STATUS_REMOVED_BY_ADMIN


def test_admin_can_browse_search_like_any_role(client, app):
    """REF-012 Section 3: search/browse is Yes for every role, including
    admin — the allowed-case cell DEV-024's audit checks for completeness."""
    _make_admin()
    login(client, "admin@example.com", "adminpass1")
    assert client.get("/search").status_code == 200


def test_no_password_hash_ever_exposed_in_admin_pages(client, app):
    _make_admin()
    customer = _make_customer()
    login(client, "admin@example.com", "adminpass1")
    html = client.get("/admin/users").get_data(as_text=True)
    assert customer.password_hash not in html
    assert "pbkdf2" not in html.lower()


# --- Mechanic management ---------------------------------------------------

def test_admin_mechanics_list_shows_profile_and_view_link(client, app):
    _make_admin()
    _, profile = _make_mechanic(name="Listed For Admin")
    login(client, "admin@example.com", "adminpass1")
    html = client.get("/admin/mechanics").get_data(as_text=True)
    assert "Listed For Admin" in html
    assert f"/mechanic/{profile.id}" in html


def test_admin_can_view_blocked_mechanics_full_profile(client, app):
    _make_admin()
    user, profile = _make_mechanic(name="Blocked But Viewable", status=STATUS_BLOCKED)
    login(client, "admin@example.com", "adminpass1")

    response = client.get(f"/mechanic/{profile.id}")
    assert response.status_code == 200
    assert b"Blocked But Viewable" in response.data
    assert b"blocked and hidden" in response.data


def test_non_admin_still_gets_404_for_blocked_mechanic_profile(client, app):
    _make_customer()
    user, profile = _make_mechanic(status=STATUS_BLOCKED)
    login(client, "cust@example.com", "password123")
    response = client.get(f"/mechanic/{profile.id}")
    assert response.status_code == 404


# --- Review moderation ------------------------------------------------

def test_admin_review_list_shows_mechanic_and_customer(client, app):
    _make_admin()
    _, profile = _make_mechanic(name="Reviewed Mechanic")
    reviewer = _make_customer(name="The Reviewer")
    _create_review(reviewer, profile.id, text="This mechanic did a fantastic job overall.")
    login(client, "admin@example.com", "adminpass1")

    html = client.get("/admin/reviews").get_data(as_text=True)
    assert "Reviewed Mechanic" in html
    assert "The Reviewer" in html
    assert "This mechanic did a fantastic job overall." in html


def test_admin_review_filter_by_status(client, app):
    _make_admin()
    _, profile = _make_mechanic()
    reviewer = _make_customer()
    review = _create_review(reviewer, profile.id, text="A review that will be removed shortly.")
    review.status = STATUS_REMOVED_BY_ADMIN
    db.session.commit()
    login(client, "admin@example.com", "adminpass1")

    visible_html = client.get("/admin/reviews?status=visible").get_data(as_text=True)
    assert "A review that will be removed shortly." not in visible_html

    removed_html = client.get("/admin/reviews?status=removed_by_admin").get_data(as_text=True)
    assert "A review that will be removed shortly." in removed_html


def test_admin_can_remove_and_restore_review(client, app):
    _make_admin()
    _, profile = _make_mechanic()
    reviewer = _make_customer()
    review = _create_review(reviewer, profile.id, rating=5)
    login(client, "admin@example.com", "adminpass1")

    token = get_csrf_token(client, "/admin/reviews")
    client.post(f"/admin/reviews/{review.id}/remove", data={"csrf_token": token}, follow_redirects=True)
    assert db.session.get(Review, review.id).status == STATUS_REMOVED_BY_ADMIN

    # Effect verified against DEV-021's average-rating computation.
    from app.models.review import compute_rating_stats

    average, count = compute_rating_stats(profile.id)
    assert average is None
    assert count == 0

    token = get_csrf_token(client, "/admin/reviews")
    client.post(f"/admin/reviews/{review.id}/restore", data={"csrf_token": token}, follow_redirects=True)
    assert db.session.get(Review, review.id).status == STATUS_VISIBLE
    average, count = compute_rating_stats(profile.id)
    assert average == 5.0
    assert count == 1


def test_remove_nonexistent_review_returns_safe_response(client, app):
    _make_admin()
    login(client, "admin@example.com", "adminpass1")
    token = get_csrf_token(client, "/admin/reviews")
    response = client.post("/admin/reviews/999999/remove", data={"csrf_token": token}, follow_redirects=True)
    assert response.status_code == 200
    assert b"not found" in response.data.lower()


# --- Admin account provisioning (regression) -----------------------------

def test_admin_account_not_reachable_via_public_registration(client, app):
    token = get_csrf_token(client, "/register/customer")
    client.post(
        "/register/customer",
        data={
            "name": "Sneaky",
            "email": "sneaky@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "role": "admin",
            "csrf_token": token,
        },
    )
    user = User.query.filter_by(email="sneaky@example.com").first()
    assert user.role != ROLE_ADMIN


# --- Regression: DEV-018/019/020/021 rules unaffected ---------------------

def test_mechanic_ownership_rules_still_protected(client, app):
    _make_customer()
    login(client, "cust@example.com", "password123")
    assert client.get("/mechanic/profile/edit").status_code == 403


def test_review_ownership_rules_still_protected(client, app):
    _, profile = _make_mechanic()
    other_customer = _make_customer(email="other2@example.com")
    owner = _make_customer(email="owner2@example.com")
    _create_review(owner, profile.id)

    login(client, "other2@example.com", "password123")
    token = get_csrf_token(client, f"/mechanic/{profile.id}")
    response = client.post(f"/mechanic/{profile.id}/review/delete", data={"csrf_token": token})
    assert response.status_code == 404
    assert Review.query.filter_by(customer_id=owner.id).count() == 1
