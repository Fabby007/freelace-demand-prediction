"""User model — REF-011 Section 3.1.

Base account for all three marketplace roles (customer, mechanic, admin),
distinguished by the `role` column rather than separate tables, so
registration/login/session logic stays uniform (REF-011 Section 3.1's
design rationale). Mechanic-specific fields belong to MechanicProfile
(REF-011 Section 3.2), introduced in DEV-019 — not here.
"""

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, login_manager

ROLE_CUSTOMER = "customer"
ROLE_MECHANIC = "mechanic"
ROLE_ADMIN = "admin"
ROLES = (ROLE_CUSTOMER, ROLE_MECHANIC, ROLE_ADMIN)

STATUS_ACTIVE = "active"
STATUS_BLOCKED = "blocked"
STATUSES = (STATUS_ACTIVE, STATUS_BLOCKED)


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_ACTIVE)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.CheckConstraint("role IN ('customer', 'mechanic', 'admin')", name="ck_user_role_valid"),
        db.CheckConstraint("status IN ('active', 'blocked')", name="ck_user_status_valid"),
    )

    def set_password(self, raw_password):
        """Hash and store a password. The plaintext value is never persisted
        anywhere (REF-012 Section 2)."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self):
        # Overrides UserMixin.is_active (which defaults to True). Flask-Login's
        # login_user() checks this and refuses to log in a blocked account
        # even if a caller forgets the explicit status check in the route —
        # defense in depth alongside the route-level check in auth.login().
        return self.status == STATUS_ACTIVE

    @property
    def is_customer(self):
        return self.role == ROLE_CUSTOMER

    @property
    def is_mechanic(self):
        return self.role == ROLE_MECHANIC

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def __repr__(self):
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
