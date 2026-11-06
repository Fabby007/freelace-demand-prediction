"""Shared Flask extension instances, initialized against the app in create_app().

Kept in their own module (rather than instantiated in app/__init__.py) so
that app/models/*.py and app/routes/*.py can import `db`/`login_manager`
without triggering a circular import with the app factory itself.
"""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
