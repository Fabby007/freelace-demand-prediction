"""Registration, login, and account-edit forms.

All validation here is authoritative and server-side (REF-012 Section 5) —
any client-side HTML5 attributes rendered from these fields are a UX
convenience only, never the actual security/validation boundary.
"""

from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from ..models.user import User


def _normalized_email(raw_email):
    return (raw_email or "").strip().lower()


class _BaseRegistrationForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )

    def validate_email(self, field):
        if User.query.filter_by(email=_normalized_email(field.data)).first() is not None:
            raise ValidationError("An account with this email already exists.")


class CustomerRegistrationForm(_BaseRegistrationForm):
    submit = SubmitField("Create customer account")


class MechanicRegistrationForm(_BaseRegistrationForm):
    # User-facing label says "freelancer" (the account-role framing customers
    # and freelancers see at sign-up); the underlying role stored in the
    # database remains "mechanic" throughout — unchanged, per REF-012 and to
    # avoid touching authorization/DB constraints for a presentational change.
    submit = SubmitField("Create freelancer account")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class AccountEditForm(FlaskForm):
    """FR-M03 — customer view/edit of own basic account information
    (DEV-018 FR "customer account" scope; see DEV-018.md Related Requirements)."""

    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Save changes")

    def validate_email(self, field):
        normalized = _normalized_email(field.data)
        existing = User.query.filter_by(email=normalized).first()
        if existing is not None and existing.id != current_user.id:
            raise ValidationError("An account with this email already exists.")
