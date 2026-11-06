"""Review submit/edit form — DEV-021 FR2/FR4.

Rendered as a plain dropdown, not a JS star-widget — DEV-021's Frontend
Behavior allows either ("a 1-5 star-selector... the underlying <select>...
is what's actually submitted"); a dropdown needs no JavaScript at all,
consistent with this project's "minimal JS" preference.
"""

from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length

from ..models.review import MAX_REVIEW_TEXT_LENGTH, MIN_REVIEW_TEXT_LENGTH

RATING_CHOICES = [("", "Select a rating")] + [
    (str(i), f"{i} star{'s' if i != 1 else ''}") for i in range(1, 6)
]


def _coerce_rating(value):
    if value in (None, ""):
        return None
    return int(value)


class ReviewForm(FlaskForm):
    rating = SelectField(
        "Rating",
        choices=RATING_CHOICES,
        coerce=_coerce_rating,
        validators=[DataRequired(message="Please select a rating.")],
    )
    review_text = TextAreaField(
        "Your review",
        validators=[
            DataRequired(),
            Length(
                min=MIN_REVIEW_TEXT_LENGTH,
                max=MAX_REVIEW_TEXT_LENGTH,
                message=(
                    f"Review must be between {MIN_REVIEW_TEXT_LENGTH} and "
                    f"{MAX_REVIEW_TEXT_LENGTH} characters."
                ),
            ),
        ],
    )
    submit = SubmitField("Submit review")
