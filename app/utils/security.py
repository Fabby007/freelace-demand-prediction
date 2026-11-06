"""Small, focused security helpers used across marketplace routes."""

from urllib.parse import urljoin, urlparse

from flask import request


def is_safe_redirect_target(target):
    """Reject absolute/external redirect targets.

    The login route accepts a `next` query parameter so a user is returned
    to the page they originally requested. Without this check, `next` would
    be a classic open-redirect vector (e.g. `/login?next=https://evil.example`).
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc
