"""Mechanic search/filter form — DEV-020 FR1.

Used only to render the filter dropdowns/choices consistently with
MechanicProfileForm's pattern; the actual filter parsing/validation
(DEV-020's Validation rule: an unrecognized value is silently ignored, not
a 400/500) is done in app/routes/marketplace.py, not via form.validate().
"""

from flask_wtf import FlaskForm
from wtforms import SelectField
from wtforms.validators import Optional

from ..models.mechanic import VEHICLE_TYPES, Service
from ..utils.canonical import canonical_districts


class SearchFilterForm(FlaskForm):
    # This is a read-only GET search form. CSRF protection defends
    # state-changing POST/PUT/PATCH/DELETE requests (REF-012 Section 2);
    # an idempotent GET search has nothing for CSRF to protect, and
    # Flask-WTF's CSRFProtect does not check GET requests in any case —
    # this Meta override just makes that intent explicit for this form.
    class Meta:
        csrf = False

    # District, vehicle type, and service only — a customer (often searching
    # during a breakdown) is not expected to know a mechanic's name in
    # advance; free-text name search was intentionally removed (a UI/UX
    # refinement approved after DEV-020's original build).
    district = SelectField("District", choices=[], validators=[Optional()])
    vehicle_type = SelectField("Vehicle type", choices=[], validators=[Optional()])
    service = SelectField("Service", choices=[], validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.district.choices = [("", "All districts")] + [
            (d, d) for d in canonical_districts()
        ]
        self.vehicle_type.choices = [("", "All vehicle types")] + [
            (vt, vt) for vt in VEHICLE_TYPES
        ]
        self.service.choices = [("", "All services")] + [
            (str(s.id), s.name) for s in Service.query.order_by(Service.name).all()
        ]
