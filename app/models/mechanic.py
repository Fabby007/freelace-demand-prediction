"""MechanicProfile, Service, MechanicService, MechanicVehicleType — REF-011
Sections 3.2-3.5.
"""

from datetime import datetime, timezone

from ..extensions import db

VEHICLE_TYPE_MOTORCYCLE = "Motorcycle"
VEHICLE_TYPE_CAR = "Car"
VEHICLE_TYPE_THREE_WHEELER = "Three-wheeler"
VEHICLE_TYPES = (VEHICLE_TYPE_MOTORCYCLE, VEHICLE_TYPE_CAR, VEHICLE_TYPE_THREE_WHEELER)

# REF-011 Section 3.3 — starter seed list, editable only by an admin
# thereafter (DEV-022). Clearly labelled reference/seed data, not
# fabricated user records (MARKETPLACE_EXTENSION.md Section 5).
DEFAULT_SERVICE_NAMES = (
    "General Repair & Servicing",
    "Engine Diagnostics & Repair",
    "Electrical Work",
    "Tyre & Battery Service",
    "Body Work & Painting",
    "Scheduled Maintenance",
)


class MechanicProfile(db.Model):
    __tablename__ = "mechanic_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True
    )
    contact_number = db.Column(db.String(30), nullable=False)
    district = db.Column(db.String(50), nullable=False, index=True)
    years_experience = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    profile_image_path = db.Column(db.String(255), nullable=True)
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
        db.CheckConstraint(
            "years_experience >= 0", name="ck_mechanic_profile_years_experience_non_negative"
        ),
    )

    # cascade="all, delete-orphan" — DEV-022 FR5 (admin account deletion)
    # relies on deleting a mechanic's User row alone cascading correctly to
    # this profile (and, via vehicle_type_rows/services/reviews below, to
    # everything that in turn depends on the profile).
    user = db.relationship(
        "User", backref=db.backref("mechanic_profile", uselist=False, cascade="all, delete-orphan")
    )
    services = db.relationship("Service", secondary="mechanic_service", backref="mechanics")
    vehicle_type_rows = db.relationship(
        "MechanicVehicleType",
        backref="mechanic_profile",
        cascade="all, delete-orphan",
    )

    @property
    def vehicle_types(self):
        return sorted(row.vehicle_type for row in self.vehicle_type_rows)

    def __repr__(self):
        return f"<MechanicProfile id={self.id} user_id={self.user_id} district={self.district!r}>"


class Service(db.Model):
    __tablename__ = "service"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)

    def __repr__(self):
        return f"<Service id={self.id} name={self.name!r}>"


class MechanicService(db.Model):
    """Join table, REF-011 Section 3.4. Mapped explicitly (not just an
    implicit secondary table) so it is directly queryable/testable, matching
    REF-011's entity listing; also used as MechanicProfile.services'
    `secondary=` table since it carries no extra payload columns."""

    __tablename__ = "mechanic_service"

    mechanic_id = db.Column(
        db.Integer, db.ForeignKey("mechanic_profile.id"), primary_key=True
    )
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), primary_key=True)


class MechanicVehicleType(db.Model):
    """Attribute table, REF-011 Section 3.5 — not a full lookup entity; the
    vehicle_type column is constrained to REF-002's fixed 3-value canonical
    list via CHECK constraint, not a separate VehicleType table."""

    __tablename__ = "mechanic_vehicle_type"

    mechanic_id = db.Column(
        db.Integer, db.ForeignKey("mechanic_profile.id"), primary_key=True
    )
    vehicle_type = db.Column(db.String(20), primary_key=True)

    __table_args__ = (
        db.CheckConstraint(
            "vehicle_type IN ('Motorcycle', 'Car', 'Three-wheeler')",
            name="ck_mechanic_vehicle_type_valid",
        ),
    )


def seed_default_services():
    """Seed the starter Service list (REF-011 Section 3.3 / DEV-019 FR2) if
    the table is currently empty. Idempotent — a no-op once any Service row
    exists, so it never overwrites admin-managed edits made later (DEV-022).
    """
    if Service.query.first() is not None:
        return
    for name in DEFAULT_SERVICE_NAMES:
        db.session.add(Service(name=name))
    db.session.commit()
