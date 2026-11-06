"""Admin dashboard & management routes — DEV-022.

Protected twice, per REF-012 Section 4's "defense in depth" instruction:
once at the blueprint level (`before_request`) and once again on every
individual view via the same `role_required` decorator every other
role-gated route uses.

Every management action reuses existing state/logic rather than
duplicating it: blocking sets the same `User.status` DEV-018/DEV-020
already check; review moderation calls DEV-021's `remove_review`/
`restore_review` directly; "view profile" links to DEV-020's own public
profile route (extended in that module to let an admin view a blocked
profile too, rather than rebuilding profile rendering here).
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models.mechanic import MechanicProfile
from ..models.review import (
    STATUS_REMOVED_BY_ADMIN,
    STATUS_VISIBLE,
    Review,
    compute_rating_stats_bulk,
    remove_review,
    restore_review,
)
from ..models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_ACTIVE, STATUS_BLOCKED, User
from ..utils.decorators import role_required
from ..utils.security import is_safe_redirect_target

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

USERS_PER_PAGE = 20


@admin_bp.before_request
@role_required(ROLE_ADMIN)
def _require_admin():
    return None


def _redirect_back(default_endpoint):
    """Return to whichever admin list page the action was submitted from
    (users or mechanics can both trigger the same block/unblock/delete
    routes), falling back to `default_endpoint` — validated the same way
    the DEV-018 login route validates `next=`, since a raw Referer header
    is not a trusted redirect target on its own."""
    target = request.referrer
    if target and is_safe_redirect_target(target):
        return redirect(target)
    return redirect(url_for(default_endpoint))


@admin_bp.route("/")
@role_required(ROLE_ADMIN)
def dashboard():
    counts = {
        "customers": User.query.filter_by(role=ROLE_CUSTOMER).count(),
        "mechanics": User.query.filter_by(role=ROLE_MECHANIC).count(),
        "mechanic_profiles": MechanicProfile.query.count(),
        "blocked_accounts": User.query.filter(
            User.role.in_([ROLE_CUSTOMER, ROLE_MECHANIC]), User.status == STATUS_BLOCKED
        ).count(),
        "total_reviews": Review.query.count(),
        "removed_reviews": Review.query.filter_by(status=STATUS_REMOVED_BY_ADMIN).count(),
    }
    return render_template("admin/dashboard.html", counts=counts)


def _get_manageable_user_or_404(user_id):
    """Admin account-management routes only ever act on customer/mechanic
    accounts — REF-012's authorization matrix has no "admin manages admin"
    row, so an admin-role target (including the acting admin's own
    account) is treated as not found, not as a permission error that might
    hint at its existence."""
    user = db.session.get(User, user_id)
    if user is None or user.role == ROLE_ADMIN:
        abort(404)
    return user


@admin_bp.route("/users")
@role_required(ROLE_ADMIN)
def users():
    role_filter = request.args.get("role", "")
    status_filter = request.args.get("status", "")

    query = User.query.filter(User.role.in_([ROLE_CUSTOMER, ROLE_MECHANIC]))
    if role_filter in (ROLE_CUSTOMER, ROLE_MECHANIC):
        query = query.filter(User.role == role_filter)
    if status_filter in (STATUS_ACTIVE, STATUS_BLOCKED):
        query = query.filter(User.status == status_filter)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=USERS_PER_PAGE, error_out=False
    )
    return render_template(
        "admin/users.html",
        pagination=pagination,
        users=pagination.items,
        role_filter=role_filter,
        status_filter=status_filter,
    )


@admin_bp.route("/users/<int:user_id>/block", methods=["POST"])
@role_required(ROLE_ADMIN)
def block_user(user_id):
    user = _get_manageable_user_or_404(user_id)
    # Structurally unreachable (an admin's own row never has role
    # 'customer'/'mechanic', so it never passes the check above) — kept as
    # an explicit, documented safety net matching the Business Rule's
    # literal "explicitly rejected with a clear message" requirement.
    if user.id == current_user.id:
        flash("You cannot block your own account.", "error")
        return _redirect_back("admin.users")
    user.status = STATUS_BLOCKED
    db.session.commit()
    flash(f"{user.name} has been blocked.", "success")
    return _redirect_back("admin.users")


@admin_bp.route("/users/<int:user_id>/unblock", methods=["POST"])
@role_required(ROLE_ADMIN)
def unblock_user(user_id):
    user = _get_manageable_user_or_404(user_id)
    user.status = STATUS_ACTIVE
    db.session.commit()
    flash(f"{user.name} has been unblocked.", "success")
    return _redirect_back("admin.users")


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user = _get_manageable_user_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users"))
    name = user.name
    # A single delete cascades correctly in both directions (verified
    # during implementation): a mechanic's User -> MechanicProfile ->
    # MechanicVehicleType/services/reviews; a customer's User -> their own
    # written reviews. See app/models/mechanic.py and app/models/review.py.
    db.session.delete(user)
    db.session.commit()
    flash(f"{name}'s account has been permanently deleted.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/mechanics")
@role_required(ROLE_ADMIN)
def mechanics():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    pagination = (
        MechanicProfile.query.join(MechanicProfile.user)
        .order_by(User.name.asc())
        .paginate(page=page, per_page=USERS_PER_PAGE, error_out=False)
    )
    stats = compute_rating_stats_bulk([m.id for m in pagination.items])
    for mechanic in pagination.items:
        mechanic.average_rating, mechanic.review_count = stats[mechanic.id]

    return render_template("admin/mechanics.html", pagination=pagination, mechanics=pagination.items)


@admin_bp.route("/reviews")
@role_required(ROLE_ADMIN)
def reviews():
    status_filter = request.args.get("status", "")
    query = Review.query
    if status_filter in (STATUS_VISIBLE, STATUS_REMOVED_BY_ADMIN):
        query = query.filter(Review.status == status_filter)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    pagination = query.order_by(Review.created_at.desc()).paginate(
        page=page, per_page=USERS_PER_PAGE, error_out=False
    )
    return render_template(
        "admin/reviews.html", pagination=pagination, reviews=pagination.items, status_filter=status_filter
    )


@admin_bp.route("/reviews/<int:review_id>/remove", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_remove_review(review_id):
    review = remove_review(review_id)
    if review is None:
        flash("Review not found.", "error")
    else:
        flash("Review removed.", "success")
    return _redirect_back("admin.reviews")


@admin_bp.route("/reviews/<int:review_id>/restore", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_restore_review(review_id):
    review = restore_review(review_id)
    if review is None:
        flash("Review not found.", "error")
    else:
        flash("Review restored.", "success")
    return _redirect_back("admin.reviews")
