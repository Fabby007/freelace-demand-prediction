"""Admin account provisioning — the *only* way an admin account is created.

No public route accepts a role selection or otherwise creates a
`role='admin'` User row (REF-012 Section 2). This custom `flask create-admin`
command is the sole provisioning path, intended for one-time development/demo
setup, not for repeated use.
"""

import os

import click
from email_validator import EmailNotValidError, validate_email

from .extensions import db
from .models.user import ROLE_ADMIN, User


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--name", default=None, help="Admin display name.")
    @click.option("--email", default=None, help="Admin login email.")
    @click.option(
        "--password",
        default=None,
        help=(
            "Admin password. Prefer the MARKETPLACE_ADMIN_PASSWORD environment "
            "variable over passing this on a shared shell history."
        ),
    )
    def create_admin(name, email, password):
        """Provision the single marketplace admin account."""
        name = (name or os.environ.get("MARKETPLACE_ADMIN_NAME") or "").strip()
        email = (email or os.environ.get("MARKETPLACE_ADMIN_EMAIL") or "").strip().lower()
        password = password or os.environ.get("MARKETPLACE_ADMIN_PASSWORD")

        if not name or not email or not password:
            raise click.UsageError(
                "Provide --name/--email/--password, or set MARKETPLACE_ADMIN_NAME / "
                "MARKETPLACE_ADMIN_EMAIL / MARKETPLACE_ADMIN_PASSWORD environment variables."
            )
        # Same check as the login form's Email() validator, so the CLI cannot
        # create an admin whose email the login form would then refuse
        # (for example an address ending in ".local").
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as exc:
            raise click.UsageError(
                f"'{email}' is not an email address the login form accepts: {exc}"
            ) from exc
        if len(password) < 8:
            raise click.UsageError("Admin password must be at least 8 characters.")
        if User.query.filter_by(email=email).first() is not None:
            raise click.ClickException(f"A user with email '{email}' already exists.")

        admin = User(name=name, email=email, role=ROLE_ADMIN)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Admin account created: {email}")
