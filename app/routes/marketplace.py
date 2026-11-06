"""Public home page, mechanic search/discovery, and the public mechanic
profile view — DEV-020 (Mechanic Search & Discovery).

This is ordinary database search over marketplace records only. It never
calls into `src/` or the ML prediction pipeline — the mechanic-facing
"Opportunity Insights" page (DEV-023) is the sole, separate integration
point for that (MARKETPLACE_EXTENSION.md Section 7).
"""

import re

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from ..extensions import db
from ..forms.review import ReviewForm
from ..forms.search import SearchFilterForm
from ..models.mechanic import VEHICLE_TYPES, MechanicProfile, MechanicVehicleType, Service
from ..models.review import Review, STATUS_VISIBLE, compute_rating_stats, compute_rating_stats_bulk
from ..models.user import ROLE_CUSTOMER, STATUS_ACTIVE, User
from ..utils.canonical import canonical_districts

marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("/")
def home():
    # UI refresh: the homepage hero includes a compact quick-search bar
    # that GETs straight to marketplace.search. It reuses the exact same
    # SearchFilterForm (and therefore the exact same canonical choices and
    # field names) the search page already uses, rather than a second,
    # hand-duplicated list of districts/services — no new form/validation
    # logic, just passing an existing form into a second template.
    form = SearchFilterForm()
    return render_template("home.html", form=form)


def _mechanic_query(include_blocked=False):
    """Base MechanicProfile query with `user`/vehicle-type/service
    collections eager-loaded in a small constant number of queries
    (contains_eager reuses the join already needed for the status filter;
    selectinload adds two more) rather than one extra query per mechanic
    per collection (DEV-020 FR2's "avoid N+1" instruction).

    `include_blocked=True` is used only by the single-profile lookup below,
    only for an admin viewer (DEV-022's "link to view the full profile"
    working even for a blocked mechanic, so an admin can inspect one before
    deciding whether to unblock) — never for search/listing, so a blocked
    mechanic still never appears in results (DEV-020's rule, unchanged)."""
    query = MechanicProfile.query.join(MechanicProfile.user)
    if not include_blocked:
        query = query.filter(User.status == STATUS_ACTIVE)
    return query.options(
        contains_eager(MechanicProfile.user),
        selectinload(MechanicProfile.vehicle_type_rows),
        selectinload(MechanicProfile.services),
    )


def _base_active_mechanics_query():
    return _mechanic_query(include_blocked=False)


def _parse_filters(form):
    """Validate submitted filter values against their canonical sources
    (REF-002 districts, REF-011's 3 vehicle types, live `Service` rows).
    An unrecognized value is treated as unset, never a 400/500 (DEV-020
    Validation rule)."""
    district = form.district.data if form.district.data in canonical_districts() else None
    vehicle_type = form.vehicle_type.data if form.vehicle_type.data in VEHICLE_TYPES else None

    service_id = None
    if form.service.data and form.service.data.isdigit():
        candidate = int(form.service.data)
        if db.session.get(Service, candidate) is not None:
            service_id = candidate

    return district, vehicle_type, service_id


def _search_mechanics(district, vehicle_type, service_id):
    """DEV-020 FR2 — combinable AND filters over marketplace records only.
    `.any()` translates to an EXISTS subquery per filter, matching REF-011
    Section 6's filtering semantics without the row-duplication a literal
    LEFT JOIN + GROUP BY would otherwise require."""
    query = _base_active_mechanics_query()

    if district:
        query = query.filter(MechanicProfile.district == district)
    if vehicle_type:
        query = query.filter(
            MechanicProfile.vehicle_type_rows.any(MechanicVehicleType.vehicle_type == vehicle_type)
        )
    if service_id:
        query = query.filter(MechanicProfile.services.any(Service.id == service_id))

    # DEV-020 FR4 / DEV-021: average rating descending, unrated mechanics
    # shown after rated ones, alphabetical-by-name as a stable tie-break.
    # A correlated scalar subquery keeps this independent of the `.any()`
    # filters above — no JOIN/GROUP BY is needed just to sort.
    avg_rating_subquery = (
        select(func.avg(Review.rating))
        .where(Review.mechanic_id == MechanicProfile.id, Review.status == STATUS_VISIBLE)
        .correlate(MechanicProfile)
        .scalar_subquery()
    )
    return query.order_by(avg_rating_subquery.desc().nullslast(), User.name.asc())


@marketplace_bp.route("/search")
def search():
    form = SearchFilterForm(formdata=request.args)
    district, vehicle_type, service_id = _parse_filters(form)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    results_per_page = (
        current_app.config.get("MARKETPLACE_CONFIG", {}).get("search", {}).get("results_per_page", 12)
    )

    pagination = _search_mechanics(district, vehicle_type, service_id).paginate(
        page=page, per_page=results_per_page, error_out=False
    )

    # One aggregate query for the whole page of results (DEV-021 FR5's
    # "not N+1" rule) — attached as plain transient attributes for
    # convenient template access, never persisted (they aren't mapped
    # Columns, so nothing is written back to the database).
    stats = compute_rating_stats_bulk([m.id for m in pagination.items])
    for mechanic in pagination.items:
        mechanic.average_rating, mechanic.review_count = stats[mechanic.id]

    # Re-bind the form's fields to exactly what was actually applied (not
    # whatever raw, possibly-invalid string was submitted), so the
    # rendered dropdowns reflect the real filter state.
    form.district.data = district or ""
    form.vehicle_type.data = vehicle_type or ""
    form.service.data = str(service_id) if service_id else ""

    return render_template(
        "marketplace/mechanic_list.html",
        form=form,
        pagination=pagination,
        mechanics=pagination.items,
        has_filters=any([district, vehicle_type, service_id]),
    )


def _tel_uri(contact_number):
    digits = re.sub(r"[^0-9+]", "", contact_number or "")
    return f"tel:{digits}"


@marketplace_bp.route("/mechanic/<int:mechanic_id>")
def mechanic_profile(mechanic_id):
    # DEV-022: an admin viewer may inspect a blocked mechanic's profile
    # (e.g. before deciding whether to unblock) via the same page/template
    # DEV-020 already built — every other viewer keeps the exact original
    # behavior (blocked == not found, no moderation-state leak).
    viewer_is_admin = current_user.is_authenticated and current_user.is_admin
    profile = (
        _mechanic_query(include_blocked=viewer_is_admin)
        .filter(MechanicProfile.id == mechanic_id)
        .first()
    )
    if profile is None:
        # Covers both "no such id" and "id belongs to a blocked account"
        # (for a non-admin viewer) with an identical response, so neither
        # case leaks moderation state (DEV-020 UI States / REF-012).
        abort(404)

    profile.average_rating, profile.review_count = compute_rating_stats(profile.id)
    reviews = (
        Review.query.filter_by(mechanic_id=profile.id, status=STATUS_VISIBLE)
        .options(joinedload(Review.customer))
        .order_by(Review.created_at.desc())
        .all()
    )

    my_review = None
    review_form = None
    if current_user.is_authenticated and current_user.role == ROLE_CUSTOMER:
        my_review = Review.query.filter_by(
            customer_id=current_user.id, mechanic_id=profile.id
        ).first()
        review_form = ReviewForm(obj=my_review)

    return render_template(
        "marketplace/mechanic_profile.html",
        profile=profile,
        tel_href=_tel_uri(profile.contact_number),
        reviews=reviews,
        my_review=my_review,
        review_form=review_form,
    )
