"""Role-based route protection — REF-012 Section 4.

`role_required` is the single decorator every role-gated marketplace route
uses. It composes with, rather than replaces, Flask-Login's own
`login_required`, so the two failure modes stay distinct:
  - anonymous visitor -> redirected to the login page (Flask-Login's
    standard behaviour, including a `next=` back-link);
  - logged-in user of the wrong role -> a plain HTTP 403, never a silent
    redirect that could be mistaken for success.
"""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator
