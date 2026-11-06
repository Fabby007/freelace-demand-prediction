"""Registration, login, and logout — REF-012 Section 2; DEV-018 FR4-FR6."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms.auth import CustomerRegistrationForm, LoginForm, MechanicRegistrationForm
from ..models.user import ROLE_CUSTOMER, ROLE_MECHANIC, STATUS_BLOCKED, User
from ..utils.security import is_safe_redirect_target

auth_bp = Blueprint("auth", __name__)

# Purely cosmetic display hint for the login form's heading (e.g. "Freelancer
# Login" vs "Customer Login") — never compared against a user's real role and
# never used for any authorization decision. The actual login route below
# still authenticates by email/password alone and loads whichever account
# that email/password pair belongs to, exactly as before this change.
_LOGIN_AS_LABELS = {"customer": "Customer Login", "mechanic": "Freelancer Login"}


def _create_user(form, role):
    user = User(
        name=form.name.data.strip(),
        email=form.email.data.strip().lower(),
        role=role,
    )
    user.set_password(form.password.data)
    db.session.add(user)
    db.session.commit()
    return user


@auth_bp.route("/register/choose")
def register_choice():
    if current_user.is_authenticated:
        return redirect(url_for("marketplace.home"))
    return render_template("auth/register_choice.html")


@auth_bp.route("/register/customer", methods=["GET", "POST"])
def register_customer():
    if current_user.is_authenticated:
        return redirect(url_for("marketplace.home"))
    form = CustomerRegistrationForm()
    if form.validate_on_submit():
        _create_user(form, ROLE_CUSTOMER)
        flash("Account created. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register_customer.html", form=form)


@auth_bp.route("/register/mechanic", methods=["GET", "POST"])
def register_mechanic():
    if current_user.is_authenticated:
        return redirect(url_for("marketplace.home"))
    form = MechanicRegistrationForm()
    if form.validate_on_submit():
        _create_user(form, ROLE_MECHANIC)
        flash("Account created. Please log in to complete your mechanic profile.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register_mechanic.html", form=form)


@auth_bp.route("/login/choose")
def login_choice():
    if current_user.is_authenticated:
        return redirect(url_for("marketplace.home"))
    return render_template("auth/login_choice.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("marketplace.home"))
    form = LoginForm()
    # request.values covers both the initial GET's `?as=...` query string and
    # a hidden field of the same name carried through the POST, so the
    # heading stays correct even after a failed/re-rendered submission.
    login_as = request.values.get("as")
    if login_as not in _LOGIN_AS_LABELS:
        login_as = None
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        # A single generic message for "unknown email" and "wrong password" —
        # does not reveal whether the email exists (DEV-018 Error Cases).
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "error")
        elif user.status == STATUS_BLOCKED:
            flash("This account has been deactivated. Contact an administrator.", "error")
        else:
            login_user(user)
            flash(f"Welcome back, {user.name}.", "success")
            # DEV-019 FR3: a mechanic with no MechanicProfile yet is routed
            # straight to profile completion, ahead of any `next=` target —
            # there is little else useful they can do first.
            if user.is_mechanic and user.mechanic_profile is None:
                flash("Complete your mechanic profile so customers can find you.", "info")
                return redirect(url_for("mechanic.edit_profile"))
            next_target = request.args.get("next")
            if is_safe_redirect_target(next_target):
                return redirect(next_target)
            return redirect(url_for("marketplace.home"))
    return render_template(
        "auth/login.html", form=form, login_as=login_as, login_heading=_LOGIN_AS_LABELS.get(login_as, "Log in")
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("marketplace.home"))
