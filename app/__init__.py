"""Marketplace Flask application factory — DEV-018.

Entirely separate from the ML system's `src/`/`dashboard/` packages
(CLAUDE.md Section 25; REF-010). No module in this package is imported by
`src/` or `dashboard/`, and this package imports from `src/` only inside
`app/routes/insights.py` once DEV-023 is implemented.
"""

import os

from flask import Flask, render_template
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import config_by_name
from .extensions import csrf, db, login_manager


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite does not enforce FOREIGN KEY constraints unless explicitly
    told to, per connection (REF-011 Section 2)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_app(config_name=None):
    config_name = config_name or os.environ.get("MARKETPLACE_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
            app.instance_path, "marketplace.db"
        )

    if config_name == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "MARKETPLACE_SECRET_KEY must be set in the environment for a production deployment."
        )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    from . import models  # noqa: F401  registers models with SQLAlchemy before create_all()

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.customer import customer_bp
    from .routes.insights import insights_bp
    from .routes.marketplace import marketplace_bp
    from .routes.mechanic import mechanic_bp
    from .routes.reviews import reviews_bp

    app.register_blueprint(marketplace_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(mechanic_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(reviews_bp)

    _register_error_handlers(app)

    from .cli import register_cli

    register_cli(app)

    with app.app_context():
        # No migration framework is introduced for this academic-scale schema
        # (REF-004 Section 5 anti-over-engineering constraint) — create_all()
        # is idempotent and only creates tables that don't already exist yet.
        db.create_all()

        from .models.mechanic import seed_default_services

        seed_default_services()

    return app


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def payload_too_large(_error):
        # Raised by Werkzeug when a request body exceeds MAX_CONTENT_LENGTH
        # (e.g. an oversized profile-photo upload) before any form/view code
        # runs — REF-012 Section 5.
        return render_template("errors/413.html"), 413
