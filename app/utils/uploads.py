"""Profile photo upload handling — REF-012 Section 5.

Kept as a small, reusable helper rather than mechanic-specific logic, in
case a later spec needs upload handling again. Global size enforcement
happens earlier, at the WSGI layer, via Flask's `MAX_CONTENT_LENGTH`
config (set from `configs/marketplace_config.yaml` in DEV-018) — a request
whose body exceeds that limit never reaches this module at all (see the
413 error handler in app/__init__.py).
"""

import os
import uuid

from flask import current_app

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

# Minimal "does this look like the image type it claims to be" check —
# a basic magic-byte sniff, not full content re-validation (REF-012 Section 5
# explicitly scopes deeper content validation, e.g. Pillow re-encoding, as
# optional DEV-024 hardening, not a DEV-019 requirement).
_MAGIC_BYTES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}


class UploadRejected(ValueError):
    """Raised with a user-facing message when an upload fails validation."""


def _extension(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _looks_like_declared_image_type(file_storage, extension):
    signatures = _MAGIC_BYTES.get(extension, ())
    if not signatures:
        return False
    header = file_storage.stream.read(max(len(sig) for sig in signatures))
    file_storage.stream.seek(0)
    return any(header.startswith(sig) for sig in signatures)


def save_mechanic_photo(file_storage):
    """Validate and save an uploaded mechanic profile photo.

    Returns the relative static path to store in
    MechanicProfile.profile_image_path, or None if no file was supplied.
    Raises UploadRejected (with a message safe to show the user) on any
    validation failure. Never trusts the client-supplied filename for the
    stored name — a random name prevents path traversal and filename
    collisions (REF-012 Section 5).
    """
    if not file_storage or not file_storage.filename:
        return None

    extension = _extension(file_storage.filename)
    allowed = set(
        current_app.config.get("MARKETPLACE_CONFIG", {})
        .get("uploads", {})
        .get("allowed_image_extensions", [f".{ext}" for ext in ALLOWED_EXTENSIONS])
    )
    allowed_extensions = {ext.lstrip(".").lower() for ext in allowed} or ALLOWED_EXTENSIONS

    if extension not in allowed_extensions:
        raise UploadRejected("Only PNG or JPG/JPEG images are allowed.")

    if not _looks_like_declared_image_type(file_storage, extension):
        raise UploadRejected("The uploaded file does not look like a valid image.")

    upload_dir = os.path.join(current_app.static_folder, "images", "mechanics")
    os.makedirs(upload_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}.{extension}"
    file_storage.save(os.path.join(upload_dir, stored_name))

    return f"images/mechanics/{stored_name}"
