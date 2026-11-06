"""Customer-only routes.

`account` implements FR-M03 (view/edit own basic account info) — touches
only the `User` row already created by DEV-018, no new model needed.
`reviews` (DEV-021) lists the customer's own reviews, with a link to each
mechanic's profile (where the actual edit/delete form lives per DEV-021
FR2/FR4) and a direct delete action for convenience.
"""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..forms.auth import AccountEditForm
from ..models.mechanic import MechanicProfile
from ..models.review import Review
from ..models.user import ROLE_CUSTOMER
from ..utils.decorators import role_required

customer_bp = Blueprint("customer", __name__, url_prefix="/account")


@customer_bp.route("/", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def account():
    form = AccountEditForm(obj=current_user)
    if form.validate_on_submit():
        current_user.name = form.name.data.strip()
        current_user.email = form.email.data.strip().lower()
        db.session.commit()
        flash("Account details updated.", "success")
        return redirect(url_for("customer.account"))
    return render_template("customer/account.html", form=form)


@customer_bp.route("/reviews")
@role_required(ROLE_CUSTOMER)
def reviews():
    my_reviews = (
        Review.query.filter_by(customer_id=current_user.id)
        .options(joinedload(Review.mechanic).joinedload(MechanicProfile.user))
        .order_by(Review.created_at.desc())
        .all()
    )
    return render_template("customer/reviews.html", reviews=my_reviews)
