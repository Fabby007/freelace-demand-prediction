"""DEV-024 FR3: the cross-role end-to-end integration scenario.

register mechanic -> complete profile -> register customer -> search and
find that mechanic -> submit a review -> mechanic views the review on
their dashboard -> admin removes the review -> review no longer
appears/counts.

Every step reuses the real routes exactly as a human would use them (no
direct DB manipulation except to provision the admin account, which has no
public registration path by design). This is deliberately one continuous
test, not a collection of independent per-step assertions, so it proves
the whole chain actually works together end to end.
"""

from app.extensions import db
from app.models.mechanic import DEFAULT_SERVICE_NAMES, Service
from app.models.review import Review
from app.models.user import ROLE_ADMIN, User

from .conftest import create_user, get_csrf_token, login


def test_full_customer_mechanic_admin_review_lifecycle(client, app):
    # --- Register mechanic ---
    token = get_csrf_token(client, "/register/mechanic")
    client.post(
        "/register/mechanic",
        data={
            "name": "Lifecycle Mechanic",
            "email": "lifecycle-mech@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    # --- Log in (redirects straight to profile completion, DEV-019 FR3) ---
    login_response = login(client, "lifecycle-mech@example.com", "password123", follow_redirects=False)
    assert login_response.headers["Location"] == "/mechanic/profile/edit"

    # --- Complete profile ---
    service_id = Service.query.filter_by(name=DEFAULT_SERVICE_NAMES[0]).first().id
    token = get_csrf_token(client, "/mechanic/profile/edit")
    client.post(
        "/mechanic/profile/edit",
        data={
            "contact_number": "0771112222",
            "district": "Kandy",
            "years_experience": "6",
            "description": "Experienced with motorcycles and light repairs.",
            "vehicle_types": ["Motorcycle"],
            "services": [str(service_id)],
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    dashboard_html = client.get("/mechanic/profile").get_data(as_text=True)
    assert "Lifecycle Mechanic" in dashboard_html
    assert "Kandy" in dashboard_html
    client.get("/logout")

    # --- Register customer ---
    token = get_csrf_token(client, "/register/customer")
    client.post(
        "/register/customer",
        data={
            "name": "Lifecycle Customer",
            "email": "lifecycle-cust@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    login(client, "lifecycle-cust@example.com", "password123")

    # --- Search and find the mechanic ---
    search_html = client.get("/search?district=Kandy&vehicle_type=Motorcycle").get_data(as_text=True)
    assert "Lifecycle Mechanic" in search_html

    mechanic_user = User.query.filter_by(email="lifecycle-mech@example.com").first()
    profile_id = mechanic_user.mechanic_profile.id

    # --- View the mechanic's public profile, confirm contact number shown ---
    profile_html = client.get(f"/mechanic/{profile_id}").get_data(as_text=True)
    assert "0771112222" in profile_html

    # --- Submit a review ---
    token = get_csrf_token(client, f"/mechanic/{profile_id}")
    client.post(
        f"/mechanic/{profile_id}/review",
        data={
            "rating": "5",
            "review_text": "Fixed my bike quickly, fair price, would recommend to anyone nearby.",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    review = Review.query.filter_by(mechanic_id=profile_id).first()
    assert review is not None
    assert review.rating == 5

    # Reflected immediately on the search card and the profile average.
    search_html = client.get("/search?district=Kandy").get_data(as_text=True)
    assert "5.0 / 5" in search_html
    client.get("/logout")

    # --- Mechanic views the review on their own dashboard ---
    login(client, "lifecycle-mech@example.com", "password123")
    dashboard_html = client.get("/mechanic/profile").get_data(as_text=True)
    assert "Lifecycle Customer" in dashboard_html
    assert "Fixed my bike quickly" in dashboard_html
    assert "5.0 / 5" in dashboard_html
    client.get("/logout")

    # --- Admin removes the review ---
    admin_password = "adminpass1"
    create_user(role=ROLE_ADMIN, email="lifecycle-admin@example.com", password=admin_password, name="Lifecycle Admin")
    login(client, "lifecycle-admin@example.com", admin_password)

    admin_reviews_html = client.get("/admin/reviews").get_data(as_text=True)
    assert "Lifecycle Mechanic" in admin_reviews_html
    assert "Lifecycle Customer" in admin_reviews_html

    token = get_csrf_token(client, "/admin/reviews")
    client.post(f"/admin/reviews/{review.id}/remove", data={"csrf_token": token}, follow_redirects=True)
    assert db.session.get(Review, review.id).status == "removed_by_admin"
    client.get("/logout")

    # --- Review no longer appears/counts anywhere it's publicly shown ---
    profile_html = client.get(f"/mechanic/{profile_id}").get_data(as_text=True)
    assert "Fixed my bike quickly" not in profile_html
    assert "No ratings yet" in profile_html

    search_html = client.get("/search?district=Kandy").get_data(as_text=True)
    assert "No ratings yet" in search_html
    assert "5.0 / 5" not in search_html

    from app.models.review import compute_rating_stats

    average, count = compute_rating_stats(profile_id)
    assert average is None
    assert count == 0
