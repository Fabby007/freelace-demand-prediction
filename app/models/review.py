"""Review model — REF-011 Section 3.6.

Also hosts the average-rating/review-count aggregate helpers (DEV-021 FR5)
and the admin moderation actions (DEV-021 FR8 — the *functions* only; the
admin UI that calls them is DEV-022's scope).
"""

from datetime import datetime, timezone

from sqlalchemy import func

from ..extensions import db

STATUS_VISIBLE = "visible"
STATUS_REMOVED_BY_ADMIN = "removed_by_admin"
STATUSES = (STATUS_VISIBLE, STATUS_REMOVED_BY_ADMIN)

MIN_REVIEW_TEXT_LENGTH = 10
MAX_REVIEW_TEXT_LENGTH = 1000


class Review(db.Model):
    __tablename__ = "review"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    mechanic_id = db.Column(
        db.Integer, db.ForeignKey("mechanic_profile.id"), nullable=False, index=True
    )
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_VISIBLE)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        db.CheckConstraint(
            "status IN ('visible', 'removed_by_admin')", name="ck_review_status_valid"
        ),
        # A plain, unconditional constraint (not scoped to status='visible')
        # — see REF-009 ADR-032 for why this is the deliberate, simpler
        # choice: an admin-removed review permanently occupies its
        # (customer, mechanic) slot rather than freeing it for a fresh one.
        db.UniqueConstraint("customer_id", "mechanic_id", name="uq_review_customer_mechanic"),
    )

    # Both sides cascade — DEV-022 FR5 (admin account deletion) relies on
    # deleting a User alone correctly removing every review that mentions
    # them, whichever side of the relationship they were on: a deleted
    # customer's own written reviews, or a deleted mechanic's received ones.
    customer = db.relationship(
        "User", backref=db.backref("reviews_written", lazy="dynamic", cascade="all, delete-orphan")
    )
    mechanic = db.relationship(
        "MechanicProfile",
        backref=db.backref("reviews", lazy="dynamic", cascade="all, delete-orphan"),
    )

    def __repr__(self):
        return (
            f"<Review id={self.id} customer_id={self.customer_id} "
            f"mechanic_id={self.mechanic_id} rating={self.rating}>"
        )


def compute_rating_stats_bulk(mechanic_ids):
    """(average_rating, review_count) for many mechanics in a single
    aggregate query — the search-results page's route into this data
    (DEV-020/DEV-021 FR5's "not N+1" requirement). Every requested id is
    present in the result, defaulting to (None, 0) when it has no visible
    reviews at all (never a fabricated 0.0 average)."""
    mechanic_ids = list(mechanic_ids)
    stats = {mechanic_id: (None, 0) for mechanic_id in mechanic_ids}
    if not mechanic_ids:
        return stats

    rows = (
        db.session.query(Review.mechanic_id, func.avg(Review.rating), func.count(Review.id))
        .filter(Review.mechanic_id.in_(mechanic_ids), Review.status == STATUS_VISIBLE)
        .group_by(Review.mechanic_id)
        .all()
    )
    for mechanic_id, average, count in rows:
        stats[mechanic_id] = (round(average, 1) if average is not None else None, count)
    return stats


def compute_rating_stats(mechanic_id):
    """(average_rating, review_count) for a single mechanic — implemented
    as a thin wrapper over compute_rating_stats_bulk() so the single- and
    many-mechanic code paths are provably the same computation, not two
    independently-maintained ones (DEV-021's Definition of Done)."""
    return compute_rating_stats_bulk([mechanic_id])[mechanic_id]


def remove_review(review_id):
    """Admin moderation: soft-hide a review (reversible). DEV-022 exposes
    this via the admin UI; this spec defines only the underlying action."""
    review = db.session.get(Review, review_id)
    if review is None:
        return None
    review.status = STATUS_REMOVED_BY_ADMIN
    db.session.commit()
    return review


def restore_review(review_id):
    """Admin moderation: reverse a prior removal."""
    review = db.session.get(Review, review_id)
    if review is None:
        return None
    review.status = STATUS_VISIBLE
    db.session.commit()
    return review
