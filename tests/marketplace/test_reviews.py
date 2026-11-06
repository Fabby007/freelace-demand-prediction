"""DEV-021 tests: review submit/edit/delete, ownership, average-rating
computation, admin moderation functions, and the disclaimer.

CSRF stays ON throughout — no test disables it, per project security policy.
"""

from app.extensions import db
from app.models.mechanic import DEFAULT_SERVICE_NAMES
from app.models.review import (
    STATUS_REMOVED_BY_ADMIN,
    STATUS_VISIBLE,
    Review,
    compute_rating_stats,
    compute_rating_stats_bulk,
    remove_review,
    restore_review,
)
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_BLOCKED

from .conftest import create_mechanic_profile, create_user, get_csrf_token, login


def _make_mechanic(email="mech@example.com", name="Test Mechanic"):
    user = create_user(role=ROLE_MECHANIC, email=email, name=name)
    profile = create_mechanic_profile(user)
    return user, profile


def _submit_review(client, mechanic_id, rating="5", text="Great work, very professional and fast."):
    token = get_csrf_token(client, f"/mechanic/{mechanic_id}")
    return client.post(
        f"/mechanic/{mechanic_id}/review",
        data={"rating": rating, "review_text": text, "csrf_token": token},
        follow_redirects=True,
    )


def _create_review(customer, mechanic_profile_id, rating=5, text="Solid, dependable mechanic."):
    review = Review(customer_id=customer.id, mechanic_id=mechanic_profile_id, rating=rating, review_text=text)
    db.session.add(review)
    db.session.commit()
    return review


# --- Submit -----------------------------------------------------------

def test_customer_can_submit_valid_review(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust1@example.com", password="mypassword1")
    login(client, "cust1@example.com", "mypassword1")

    response = _submit_review(client, profile.id, rating="5", text="Fixed my bike quickly and fairly priced.")
    assert response.status_code == 200
    review = Review.query.filter_by(mechanic_id=profile.id).first()
    assert review is not None
    assert review.rating == 5
    assert review.review_text == "Fixed my bike quickly and fairly priced."
    assert review.status == STATUS_VISIBLE


def test_anonymous_user_cannot_submit_review(client, app):
    _, profile = _make_mechanic()
    # The review form is only rendered on the profile page for a logged-in
    # customer (DEV-021 FR3) — an anonymous visitor sees no such form to
    # scrape a token from, so grab a valid (session-tied) token from the
    # public login page instead, which is unaffected by CSRF token source.
    token = get_csrf_token(client, "/login")
    response = client.post(
        f"/mechanic/{profile.id}/review",
        data={"rating": "5", "review_text": "Should not be allowed.", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert Review.query.count() == 0


def test_mechanic_cannot_submit_customer_review(client, app):
    _, profile = _make_mechanic(email="target@example.com")
    create_user(role=ROLE_MECHANIC, email="reviewer_mech@example.com", password="mypassword1")
    # Fetch a token while still anonymous (the mechanic viewing the profile
    # page afterward gets no review form either, per FR3 — mechanics/admins
    # see nothing there). The CSRF token is session-bound, not page-bound,
    # so it remains valid across the login() call that follows.
    token = get_csrf_token(client, "/login")
    login(client, "reviewer_mech@example.com", "mypassword1")

    response = client.post(
        f"/mechanic/{profile.id}/review",
        data={"rating": "5", "review_text": "Mechanics should not review.", "csrf_token": token},
    )
    assert response.status_code == 403
    assert Review.query.count() == 0


def test_admin_cannot_submit_customer_review(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_ADMIN, email="admin1@example.com", password="mypassword1")
    token = get_csrf_token(client, "/login")
    login(client, "admin1@example.com", "mypassword1")

    response = client.post(
        f"/mechanic/{profile.id}/review",
        data={"rating": "5", "review_text": "Admins should not review either.", "csrf_token": token},
    )
    assert response.status_code == 403
    assert Review.query.count() == 0


def test_cannot_review_a_blocked_mechanic(client, app):
    user = create_user(role=ROLE_MECHANIC, email="blockedmech@example.com", status=STATUS_BLOCKED)
    profile = create_mechanic_profile(user)
    create_user(role=ROLE_CUSTOMER, email="cust2@example.com", password="mypassword1")
    login(client, "cust2@example.com", "mypassword1")

    # The blocked mechanic's own profile page 404s too (no form to scrape a
    # token from there) — /account/ always renders a real CSRF form for a
    # logged-in customer regardless of which mechanic is being tested.
    token = get_csrf_token(client, "/account/")
    response = client.post(
        f"/mechanic/{profile.id}/review",
        data={"rating": "5", "review_text": "x" * 20, "csrf_token": token},
    )
    assert response.status_code == 404
    assert Review.query.count() == 0


# --- Validation ------------------------------------------------------------

def test_rating_zero_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust3@example.com", password="mypassword1")
    login(client, "cust3@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="0", text="Rating of zero should fail.")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_rating_above_five_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust4@example.com", password="mypassword1")
    login(client, "cust4@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="6", text="Rating above five should fail.")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_negative_rating_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust5@example.com", password="mypassword1")
    login(client, "cust5@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="-1", text="Negative rating should fail.")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_missing_rating_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust6@example.com", password="mypassword1")
    login(client, "cust6@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="", text="No rating selected at all.")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_review_text_too_short_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust7@example.com", password="mypassword1")
    login(client, "cust7@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="4", text="short")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_review_text_too_long_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust8@example.com", password="mypassword1")
    login(client, "cust8@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="4", text="x" * 1001)
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_missing_review_text_rejected(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="cust9@example.com", password="mypassword1")
    login(client, "cust9@example.com", "mypassword1")
    response = _submit_review(client, profile.id, rating="4", text="")
    assert Review.query.count() == 0
    assert response.status_code == 200


def test_csrf_required_for_review_submission(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="csrfcust@example.com", password="mypassword1")
    login(client, "csrfcust@example.com", "mypassword1")
    response = client.post(
        f"/mechanic/{profile.id}/review", data={"rating": "5", "review_text": "No token supplied here."}
    )
    assert response.status_code == 400
    assert Review.query.count() == 0


# --- Edit / duplicate --------------------------------------------------

def test_second_submission_edits_existing_review_not_duplicate(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="editor1@example.com", password="mypassword1")
    login(client, "editor1@example.com", "mypassword1")

    _submit_review(client, profile.id, rating="3", text="Initial review text here, okay job.")
    _submit_review(client, profile.id, rating="5", text="Updated my mind, actually excellent work.")

    assert Review.query.filter_by(mechanic_id=profile.id).count() == 1
    review = Review.query.filter_by(mechanic_id=profile.id).first()
    assert review.rating == 5
    assert "Updated my mind" in review.review_text


def test_duplicate_review_race_condition_handled_by_db_constraint(client, app):
    _, profile = _make_mechanic()
    customer = create_user(role=ROLE_CUSTOMER, email="race1@example.com", password="mypassword1")
    _create_review(customer, profile.id)  # bypass the app-level "edit instead" path

    login(client, "race1@example.com", "mypassword1")
    # The route's own "edit existing" logic would normally handle this, but
    # confirm the DB-level UniqueConstraint independently as defense in depth.
    duplicate = Review(customer_id=customer.id, mechanic_id=profile.id, rating=2, review_text="Second row attempt.")
    db.session.add(duplicate)
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# --- Ownership -----------------------------------------------------------

def test_customer_can_edit_own_review(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="ownedit@example.com", password="mypassword1")
    login(client, "ownedit@example.com", "mypassword1")
    _submit_review(client, profile.id, rating="2", text="First impression was mediocre honestly.")

    _submit_review(client, profile.id, rating="4", text="After a follow-up, much better than I thought.")
    review = Review.query.filter_by(mechanic_id=profile.id).first()
    assert review.rating == 4


def test_customer_cannot_edit_another_customers_review(client, app):
    _, profile = _make_mechanic()
    owner = create_user(role=ROLE_CUSTOMER, email="realowner@example.com", password="mypassword1")
    _create_review(owner, profile.id, rating=5, text="Original owner's honest review text.")
    create_user(role=ROLE_CUSTOMER, email="intruder@example.com", password="mypassword1")

    login(client, "intruder@example.com", "mypassword1")
    _submit_review(client, profile.id, rating="1", text="Trying to sneak in my own separate review.")

    # The intruder gets their OWN new row — the owner's review is untouched.
    owner_review = Review.query.filter_by(customer_id=owner.id, mechanic_id=profile.id).first()
    assert owner_review.rating == 5
    assert "Original owner" in owner_review.review_text
    assert Review.query.filter_by(mechanic_id=profile.id).count() == 2


def test_customer_can_delete_own_review(client, app):
    _, profile = _make_mechanic()
    create_user(role=ROLE_CUSTOMER, email="deleter@example.com", password="mypassword1")
    login(client, "deleter@example.com", "mypassword1")
    _submit_review(client, profile.id, rating="3", text="Will delete this one shortly after.")

    token = get_csrf_token(client, f"/mechanic/{profile.id}")
    response = client.post(
        f"/mechanic/{profile.id}/review/delete", data={"csrf_token": token}, follow_redirects=True
    )
    assert response.status_code == 200
    assert Review.query.filter_by(mechanic_id=profile.id).count() == 0


def test_customer_cannot_delete_another_customers_review(client, app):
    _, profile = _make_mechanic()
    owner = create_user(role=ROLE_CUSTOMER, email="ownerdel@example.com", password="mypassword1")
    _create_review(owner, profile.id)
    create_user(role=ROLE_CUSTOMER, email="notowner@example.com", password="mypassword1")
    login(client, "notowner@example.com", "mypassword1")

    token = get_csrf_token(client, f"/mechanic/{profile.id}")
    response = client.post(f"/mechanic/{profile.id}/review/delete", data={"csrf_token": token})
    assert response.status_code == 404
    assert Review.query.filter_by(customer_id=owner.id, mechanic_id=profile.id).count() == 1


def test_anonymous_cannot_delete_review(client, app):
    _, profile = _make_mechanic()
    response = client.post(f"/mechanic/{profile.id}/review/delete", follow_redirects=False)
    assert response.status_code in (302, 400)


# --- Database constraints ---------------------------------------------

def test_db_rejects_rating_outside_range(app):
    from sqlalchemy.exc import IntegrityError
    import pytest

    _, profile = _make_mechanic()
    customer = create_user(role=ROLE_CUSTOMER, email="dbcheck1@example.com")
    bad = Review(customer_id=customer.id, mechanic_id=profile.id, rating=0, review_text="x" * 20)
    db.session.add(bad)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejects_duplicate_customer_mechanic_pair(app):
    from sqlalchemy.exc import IntegrityError
    import pytest

    _, profile = _make_mechanic()
    customer = create_user(role=ROLE_CUSTOMER, email="dbcheck2@example.com")
    _create_review(customer, profile.id)
    dup = Review(customer_id=customer.id, mechanic_id=profile.id, rating=1, review_text="y" * 20)
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# --- Average rating / review count --------------------------------------

def test_average_rating_computation(app):
    _, profile = _make_mechanic()
    c1 = create_user(role=ROLE_CUSTOMER, email="avg1@example.com")
    c2 = create_user(role=ROLE_CUSTOMER, email="avg2@example.com")
    _create_review(c1, profile.id, rating=5)
    _create_review(c2, profile.id, rating=3)

    average, count = compute_rating_stats(profile.id)
    assert average == 4.0
    assert count == 2


def test_average_rating_none_when_no_reviews(app):
    _, profile = _make_mechanic()
    average, count = compute_rating_stats(profile.id)
    assert average is None
    assert count == 0


def test_admin_removed_review_excluded_from_average(app):
    _, profile = _make_mechanic()
    c1 = create_user(role=ROLE_CUSTOMER, email="rm1@example.com")
    c2 = create_user(role=ROLE_CUSTOMER, email="rm2@example.com")
    r1 = _create_review(c1, profile.id, rating=5)
    _create_review(c2, profile.id, rating=1)

    remove_review(r1.id)
    average, count = compute_rating_stats(profile.id)
    assert average == 1.0
    assert count == 1

    restore_review(r1.id)
    average, count = compute_rating_stats(profile.id)
    assert average == 3.0
    assert count == 2


def test_bulk_rating_stats_matches_single_computation(app):
    _, profile_a = _make_mechanic(email="bulk1@example.com", name="Bulk A")
    _, profile_b = _make_mechanic(email="bulk2@example.com", name="Bulk B")
    c1 = create_user(role=ROLE_CUSTOMER, email="bulkc1@example.com")
    _create_review(c1, profile_a.id, rating=4)

    bulk = compute_rating_stats_bulk([profile_a.id, profile_b.id])
    assert bulk[profile_a.id] == compute_rating_stats(profile_a.id)
    assert bulk[profile_b.id] == compute_rating_stats(profile_b.id) == (None, 0)


# --- Display: profile page, search cards, mechanic dashboard -----------

def test_profile_page_shows_no_ratings_yet_when_empty(client, app):
    _, profile = _make_mechanic()
    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "No ratings yet" in html


def test_profile_page_shows_real_average_and_review_list(client, app):
    _, profile = _make_mechanic()
    c1 = create_user(role=ROLE_CUSTOMER, email="disp1@example.com", name="Reviewer One")
    _create_review(c1, profile.id, rating=5, text="Absolutely fantastic service every time.")

    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "5.0 / 5" in html
    assert "Based on 1 review" in html
    assert "Reviewer One" in html
    assert "Absolutely fantastic service every time." in html


def test_review_disclaimer_present_on_profile_and_mechanic_dashboard(client, app):
    user, profile = _make_mechanic(email="discmech@example.com")
    profile_html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "not verified against any completed-job" in profile_html

    login(client, "discmech@example.com", "password123")
    dashboard_html = client.get("/mechanic/profile").get_data(as_text=True)
    assert "not verified against any completed-job" in dashboard_html


def test_search_cards_show_real_average_rating(client, app):
    _, profile = _make_mechanic(email="cardrate@example.com", name="Card Rated Mechanic")
    c1 = create_user(role=ROLE_CUSTOMER, email="cardc1@example.com")
    _create_review(c1, profile.id, rating=5)

    html = client.get("/search").get_data(as_text=True)
    assert "Card Rated Mechanic" in html
    assert "5.0 / 5" in html


def test_search_sorts_higher_rated_mechanics_first(client, app):
    _, low = _make_mechanic(email="lowrated@example.com", name="Low Rated Mechanic")
    _, high = _make_mechanic(email="highrated@example.com", name="High Rated Mechanic")
    c1 = create_user(role=ROLE_CUSTOMER, email="sortc1@example.com")
    c2 = create_user(role=ROLE_CUSTOMER, email="sortc2@example.com")
    _create_review(c1, low.id, rating=1)
    _create_review(c2, high.id, rating=5)

    html = client.get("/search").get_data(as_text=True)
    assert html.index("High Rated Mechanic") < html.index("Low Rated Mechanic")


def test_search_places_unrated_mechanics_after_rated_ones(client, app):
    _, rated = _make_mechanic(email="israted@example.com", name="Is Rated Mechanic")
    _, unrated = _make_mechanic(email="isunrated@example.com", name="Is Unrated Mechanic")
    c1 = create_user(role=ROLE_CUSTOMER, email="unratedc1@example.com")
    _create_review(c1, rated.id, rating=1)  # even a low real rating outranks "no rating"

    html = client.get("/search").get_data(as_text=True)
    assert html.index("Is Rated Mechanic") < html.index("Is Unrated Mechanic")


def test_mechanic_dashboard_shows_own_reviews(client, app):
    user, profile = _make_mechanic(email="ownerdash@example.com")
    c1 = create_user(role=ROLE_CUSTOMER, email="dashc1@example.com", name="Dash Reviewer")
    _create_review(c1, profile.id, rating=4, text="Reliable and on time as promised.")

    login(client, "ownerdash@example.com", "password123")
    html = client.get("/mechanic/profile").get_data(as_text=True)
    assert "4.0 / 5" in html
    assert "Dash Reviewer" in html
    assert "Reliable and on time as promised." in html


# --- My Reviews (customer) ------------------------------------------------

def test_customer_my_reviews_page_lists_own_reviews(client, app):
    _, profile = _make_mechanic(email="listmech@example.com", name="Listed Mechanic")
    create_user(role=ROLE_CUSTOMER, email="listcust@example.com", password="mypassword1")
    login(client, "listcust@example.com", "mypassword1")
    _submit_review(client, profile.id, rating="4", text="Good experience overall with this shop.")

    html = client.get("/account/reviews").get_data(as_text=True)
    assert "Listed Mechanic" in html
    assert "Good experience overall with this shop." in html


def test_customer_my_reviews_page_empty_state(client, app):
    create_user(role=ROLE_CUSTOMER, email="noreviews@example.com", password="mypassword1")
    login(client, "noreviews@example.com", "mypassword1")
    html = client.get("/account/reviews").get_data(as_text=True)
    assert "haven't written any reviews" in html


# --- Admin moderation functions (no UI yet — DEV-022) --------------------

def test_remove_and_restore_review_functions(app):
    _, profile = _make_mechanic()
    customer = create_user(role=ROLE_CUSTOMER, email="modfunc@example.com")
    review = _create_review(customer, profile.id)

    removed = remove_review(review.id)
    assert removed.status == STATUS_REMOVED_BY_ADMIN

    restored = restore_review(review.id)
    assert restored.status == STATUS_VISIBLE


def test_remove_review_hides_it_from_profile_list(client, app):
    _, profile = _make_mechanic()
    customer = create_user(role=ROLE_CUSTOMER, email="hiddenrev@example.com")
    review = _create_review(customer, profile.id, text="This review will be removed by an admin.")

    remove_review(review.id)
    html = client.get(f"/mechanic/{profile.id}").get_data(as_text=True)
    assert "This review will be removed by an admin." not in html
    assert "No ratings yet" in html


def test_remove_review_returns_none_for_nonexistent_id(app):
    assert remove_review(999999) is None
    assert restore_review(999999) is None


# --- Regression: DEV-018/019/020 unaffected -------------------------------

def test_mechanic_ownership_rules_still_protected(client):
    create_user(role=ROLE_CUSTOMER, email="stillcust2@example.com", password="mypassword1")
    login(client, "stillcust2@example.com", "mypassword1")
    assert client.get("/mechanic/profile/edit").status_code == 403


def test_blocked_mechanic_search_exclusion_still_works(client, app):
    user = create_user(role=ROLE_MECHANIC, email="stillblocked@example.com", name="Still Blocked", status=STATUS_BLOCKED)
    create_mechanic_profile(user)
    html = client.get("/search").get_data(as_text=True)
    assert "Still Blocked" not in html
