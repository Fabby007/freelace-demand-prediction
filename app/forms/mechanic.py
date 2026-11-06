"""Mechanic profile create/edit form — DEV-019 FR4.

Vehicle types and services render as checkbox lists (not a native
multi-select box), per DEV-019 FR4's explicit "checkboxes" wording.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import IntegerField, SelectField, SelectMultipleField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp
from wtforms.widgets import CheckboxInput, ListWidget

from ..models.mechanic import VEHICLE_TYPES

PHONE_REGEXP = r"^[0-9+\-\s()]{7,20}$"
PHONE_MESSAGE = "Enter a valid contact number (digits, spaces, +, -, ( ) only)."


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class MechanicProfileForm(FlaskForm):
    contact_number = StringField(
        "Contact / mobile number",
        validators=[DataRequired(), Length(max=30), Regexp(PHONE_REGEXP, message=PHONE_MESSAGE)],
    )
    district = SelectField("District", validators=[DataRequired()])
    years_experience = IntegerField(
        "Years of experience",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=80, message="Enter a realistic number of years (0-80)."),
        ],
    )
    description = TextAreaField(
        "About / description", validators=[Optional(), Length(max=2000)]
    )
    vehicle_types = MultiCheckboxField(
        "Vehicle types you service", choices=[(vt, vt) for vt in VEHICLE_TYPES], validators=[Optional()]
    )
    services = MultiCheckboxField("Services you offer", coerce=int, validators=[Optional()])
    photo = FileField(
        "Profile photo (optional)",
        validators=[
            Optional(),
            FileAllowed(["png", "jpg", "jpeg"], "Only PNG or JPG images are allowed."),
            FileSize(max_size=2 * 1024 * 1024, message="Photo must be smaller than 2MB."),
        ],
    )
    submit = SubmitField("Save profile")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from ..models.mechanic import Service
        from ..utils.canonical import canonical_districts

        self.district.choices = [(d, d) for d in canonical_districts()]
        self.services.choices = [(s.id, s.name) for s in Service.query.order_by(Service.name).all()]
