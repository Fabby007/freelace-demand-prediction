"""Mechanic-only routes — DEV-019 (Mechanic Profile Management).

`profile` is the "My Profile" nav destination: it shows the mechanic's own
dashboard/summary once a profile exists, or routes a profile-less mechanic
to `edit_profile` (DEV-019 FR3). Public, customer-facing profile viewing is
explicitly DEV-020's scope (DEV-019.md's own User Roles section) — no such
route is added here.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..forms.mechanic import MechanicProfileForm
from ..models.mechanic import MechanicProfile, MechanicVehicleType, Service
from ..models.review import Review, STATUS_VISIBLE, compute_rating_stats
from ..models.user import ROLE_MECHANIC
from ..utils.decorators import role_required
from ..utils.uploads import UploadRejected, save_mechanic_photo

mechanic_bp = Blueprint("mechanic", __name__, url_prefix="/mechanic")


@mechanic_bp.route("/profile")
@role_required(ROLE_MECHANIC)
def profile():
    profile_row = current_user.mechanic_profile
    if profile_row is None:
        return redirect(url_for("mechanic.edit_profile"))

    # Same aggregate helper the public profile (DEV-020) and search cards
    # use (DEV-021 FR5) — a mechanic viewing their own dashboard sees
    # exactly the same numbers a customer would (FR-M11).
    profile_row.average_rating, profile_row.review_count = compute_rating_stats(profile_row.id)
    reviews = (
        Review.query.filter_by(mechanic_id=profile_row.id, status=STATUS_VISIBLE)
        .options(joinedload(Review.customer))
        .order_by(Review.created_at.desc())
        .all()
    )
    return render_template("mechanic/mechanic_dashboard.html", profile=profile_row, reviews=reviews)


@mechanic_bp.route("/profile/edit", methods=["GET", "POST"])
@role_required(ROLE_MECHANIC)
def edit_profile():
    existing = current_user.mechanic_profile
    form = MechanicProfileForm(obj=existing)

    if existing is not None and request.method == "GET":
        # Pre-fill the multi-checkbox fields — WTForms' obj= population
        # only covers simple scalar columns, not these derived collections.
        form.vehicle_types.data = existing.vehicle_types
        form.services.data = [s.id for s in existing.services]

    if form.validate_on_submit():
        if form.photo.data and getattr(form.photo.data, "filename", ""):
            try:
                saved_path = save_mechanic_photo(form.photo.data)
            except UploadRejected as exc:
                # Whole submission fails atomically (DEV-019 Error Cases) —
                # nothing below has touched the session yet, so returning
                # here leaves the database exactly as it was.
                flash(str(exc), "error")
                return render_template(
                    "mechanic/mechanic_edit_profile.html", form=form, is_new=existing is None
                )
        else:
            saved_path = None

        profile_row = existing or MechanicProfile(user_id=current_user.id)
        profile_row.contact_number = form.contact_number.data.strip()
        profile_row.district = form.district.data
        profile_row.years_experience = form.years_experience.data
        profile_row.description = (form.description.data or "").strip() or None
        if saved_path is not None:
            profile_row.profile_image_path = saved_path

        profile_row.vehicle_type_rows = [
            MechanicVehicleType(vehicle_type=vt) for vt in form.vehicle_types.data
        ]
        selected_service_ids = set(form.services.data or [])
        profile_row.services = (
            Service.query.filter(Service.id.in_(selected_service_ids)).all()
            if selected_service_ids
            else []
        )

        if existing is None:
            db.session.add(profile_row)
        db.session.commit()

        if not profile_row.vehicle_type_rows or not profile_row.services:
            flash(
                "Profile saved. Add at least one vehicle type and service so customers can find you.",
                "info",
            )
        else:
            flash("Profile saved.", "success")
        return redirect(url_for("mechanic.profile"))

    return render_template(
        "mechanic/mechanic_edit_profile.html", form=form, is_new=existing is None
    )
