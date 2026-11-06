"""Review submit/delete routes — DEV-021 FR2-FR4.

Kept separate from app/routes/marketplace.py (which stays read-only, per
its own DEV-020 design) and from app/routes/customer.py (account
settings). Routes nest under /mechanic/<id>/review to sit naturally
alongside the public profile page (DEV-020) they attach to.

Neither route takes a `review_id` in the URL — both resolve "the current
customer's review of this mechanic" via (customer_id, mechanic_id), the
same pattern DEV-019 established for mechanic-profile editing. This makes
"edit/delete another customer's review by guessing an ID" structurally
impossible rather than merely checked-and-rejected (REF-012 Section 3).
"""

from flask import Blueprint, abort, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..forms.review import ReviewForm
from ..models.mechanic import MechanicProfile
from ..models.review import Review
from ..models.user import ROLE_CUSTOMER, STATUS_ACTIVE, User
from ..utils.decorators import role_required

reviews_bp = Blueprint("reviews", __name__)


def _get_active_mechanic_or_404(mechanic_id):
    profile = (
        MechanicProfile.query.join(MechanicProfile.user)
        .filter(MechanicProfile.id == mechanic_id, User.status == STATUS_ACTIVE)
        .first()
    )
    if profile is None:
        abort(404)
    return profile


@reviews_bp.route("/mechanic/<int:mechanic_id>/review", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def submit_review(mechanic_id):
    profile = _get_active_mechanic_or_404(mechanic_id)
    form = ReviewForm()

    if form.validate_on_submit():
        existing = Review.query.filter_by(
            customer_id=current_user.id, mechanic_id=profile.id
        ).first()
        if existing is not None:
            existing.rating = form.rating.data
            existing.review_text = form.review_text.data.strip()
            db.session.commit()
            flash("Your review has been updated.", "success")
        else:
            review = Review(
                customer_id=current_user.id,
                mechanic_id=profile.id,
                rating=form.rating.data,
                review_text=form.review_text.data.strip(),
            )
            db.session.add(review)
            try:
                db.session.commit()
                flash("Thanks for your review.", "success")
            except IntegrityError:
                # A second, near-simultaneous submission from the same
                # customer/mechanic pair (race condition) — the DB unique
                # constraint is the final backstop; surfaced as a clear
                # message, never a raw database error (DEV-021 Error Cases).
                db.session.rollback()
                flash(
                    "You've already reviewed this mechanic — edit your existing review instead.",
                    "error",
                )
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "error")

    return redirect(f"{url_for('marketplace.mechanic_profile', mechanic_id=mechanic_id)}#reviews")


@reviews_bp.route("/mechanic/<int:mechanic_id>/review/delete", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def delete_review(mechanic_id):
    review = Review.query.filter_by(customer_id=current_user.id, mechanic_id=mechanic_id).first()
    if review is None:
        # No review of *this customer's own* exists for this mechanic —
        # 404 rather than 403 so the response never confirms or denies
        # whether some other customer's review exists here (no leak).
        abort(404)
    db.session.delete(review)
    db.session.commit()
    flash("Your review has been deleted.", "info")
    return redirect(url_for("marketplace.mechanic_profile", mechanic_id=mechanic_id))
