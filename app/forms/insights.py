"""Opportunity Insights selector form — DEV-023 FR2.

Read-only GET form (like DEV-020's SearchFilterForm) — CSRF is intentionally
disabled (see REF-012 Section 2's scope: CSRF protects state-changing
requests; this page performs no writes at all). Choices are populated in
the route from the already-loaded RankingEngine, since the real supported
vehicle types/periods are data-driven, not hardcoded (DEV-023 Validation).
"""

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField
from wtforms.validators import Optional


class InsightsFilterForm(FlaskForm):
    class Meta:
        csrf = False

    vehicle_type = SelectField("Vehicle type", choices=[], validators=[Optional()])
    period = SelectField("Prediction year", choices=[], validators=[Optional()])
    # Optional — defaults to "All Districts" (empty value). Filters which of
    # RankingEngine's own already-computed results are displayed; it never
    # triggers a second/independent prediction (see app/routes/insights.py).
    district = SelectField("District (Optional)", choices=[], validators=[Optional()])
    top_n = IntegerField("Number of districts to show", validators=[Optional()])
