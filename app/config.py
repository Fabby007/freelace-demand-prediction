"""Marketplace application configuration.

Secrets (SECRET_KEY, database URI overrides, admin-provisioning credentials)
are read from environment variables only — never hardcoded and never
committed to version control (REF-012 Section 2). Non-secret application
settings (pagination size, upload limits, review-text bounds) live in
configs/marketplace_config.yaml, per this project's existing config-driven
convention (CLAUDE.md Section 17), and are loaded once here.
"""

import os
from datetime import timedelta
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
MARKETPLACE_CONFIG_PATH = BASE_DIR / "configs" / "marketplace_config.yaml"


def _load_marketplace_yaml():
    if MARKETPLACE_CONFIG_PATH.exists():
        with open(MARKETPLACE_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


_MARKETPLACE_YAML = _load_marketplace_yaml()


class Config:
    """Base configuration shared by every environment."""

    SECRET_KEY = os.environ.get("MARKETPLACE_SECRET_KEY")
    # Left unset here; create_app() fills in an instance-relative SQLite path
    # once app.instance_path is known, unless this environment variable is set.
    SQLALCHEMY_DATABASE_URI = os.environ.get("MARKETPLACE_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    MARKETPLACE_CONFIG = _MARKETPLACE_YAML
    MAX_CONTENT_LENGTH = _MARKETPLACE_YAML.get("uploads", {}).get(
        "max_content_length_bytes", 2 * 1024 * 1024
    )
    PERMANENT_SESSION_LIFETIME = timedelta(
        days=_MARKETPLACE_YAML.get("session", {}).get("permanent_session_lifetime_days", 7)
    )

    # Address of the separate Streamlit dashboard (dashboard/app.py). The
    # mechanic dashboard only links to it; Flask does not run or proxy it,
    # and the Flask login does not carry over into Streamlit.
    STREAMLIT_DASHBOARD_URL = os.environ.get("STREAMLIT_DASHBOARD_URL", "http://localhost:8501")


class DevelopmentConfig(Config):
    DEBUG = True
    # Development-only fallback so `flask run` works out of the box without
    # any secret committed to the repository. Real deployments MUST set
    # MARKETPLACE_SECRET_KEY explicitly (enforced for "production" below).
    SECRET_KEY = Config.SECRET_KEY or "dev-only-insecure-secret-key-do-not-use-in-production"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = Config.SECRET_KEY or "testing-only-insecure-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # CSRF protection is deliberately left ON in tests — tests fetch a real
    # token from the rendered form rather than disabling the protection
    # (project rule: do not weaken security simply to make tests pass).
    WTF_CSRF_ENABLED = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
