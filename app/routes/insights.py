"""Opportunity Insights — DEV-023 (ML Opportunity Insights Web Integration).

The ONLY module in the entire marketplace extension that imports from
`src/` (REF-010 Section 4; CLAUDE.md Section 25). This file is a thin
controller: it validates the mechanic's selection against real values
`RankingEngine` actually supports, calls `RankingEngine.rank()` unchanged,
and renders its output. No prediction, ranking, band, or SHAP logic is
implemented here — all of it remains in `src/recommendation` and
`src/explainability`, exactly as `dashboard/app.py` (DEV-013) already
consumes it. This route never writes to `data/`, `models/`, or `mlruns/`,
never retrains anything, and never persists a query as if it were demand
data (MARKETPLACE_EXTENSION.md Section 7.2).

`configs/recommendation_v2.yaml` chooses the engine (REF-009 ADR-043). In v2
mode this page shows the Vehicle-Fleet Service Opportunity view. It is still
only a thin controller over `src/`.
"""

import logging
import threading

from flask import Blueprint, render_template, request

from ..forms.insights import InsightsFilterForm
from ..models.user import ROLE_MECHANIC
from ..utils.decorators import role_required

logger = logging.getLogger(__name__)

insights_bp = Blueprint("insights", __name__, url_prefix="/insights")

# Lazy, process-wide singleton (DEV-023 FR6) — analogous to Streamlit's
# @st.cache_resource (dashboard/data_access.py::load_ranking_engine).
# Loaded once, reused by every request; never reloaded per operation.
# Guarded by a lock so two concurrent first-requests can't both trigger a
# duplicate, wasteful (and potentially non-reentrant-safe) load at once —
# DEV-023's own Edge Case about concurrent mechanics viewing this page.
_engine = None
_engine_load_error = None
_engine_lock = threading.Lock()


def _get_ranking_engine():
    global _engine, _engine_load_error
    if _engine is not None or _engine_load_error is not None:
        return _engine
    with _engine_lock:
        if _engine is not None or _engine_load_error is not None:
            return _engine
        try:
            from src.recommendation.active_engine import load_active_engine

            _engine = load_active_engine()
        except Exception as exc:  # noqa: BLE001 - any load failure must
            # degrade to a clear error state, never crash or silently fall
            # back to stale/fabricated data (DEV-023 Error Cases).
            logger.exception("Opportunity Insights: failed to load the ranking engine.")
            _engine_load_error = str(exc)
    return _engine


def _configured_for_v1():
    """Which wording an error page may use when no engine is loaded. It names
    the v1 model only when v1 is definitely the configured engine."""
    try:
        from src.recommendation import active_engine

        return active_engine.get_active_engine_name() == active_engine.ENGINE_V1
    except Exception:  # noqa: BLE001 - a broken setting must still reach the error page
        logger.exception("Opportunity Insights: could not read the engine setting.")
        return False


@insights_bp.route("/")
@role_required(ROLE_MECHANIC)
def dashboard():
    engine = _get_ranking_engine()
    if engine is None:
        return render_template(
            "insights/opportunity_insights.html", backend_unavailable=True, indicator_v2=not _configured_for_v1(),
        ), 503

    from src.models.xgboost_model import VEHICLE_CATEGORIES
    from src.recommendation.active_engine import is_fleet_engine
    from src.recommendation.ranking_engine import STATUS_OK

    indicator_v2 = is_fleet_engine(engine)
    available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
    available_periods = [y + 1 for y in available_years]

    form = InsightsFilterForm(formdata=request.args)
    form.vehicle_type.choices = [(vt, vt) for vt in VEHICLE_CATEGORIES]
    form.period.choices = [(str(p), str(p)) for p in available_periods]
    if indicator_v2:
        form.period.choices = [(str(p), engine.period_label(p)) for p in available_periods]
        form.period.label.text = "Data year"
    form.district.choices = [("", "All Districts")] + [(d, d) for d in engine.canonical_districts]

    # DEV-023 Validation: an unrecognized selection is silently treated as
    # unset (falls back to a real default), never passed through to
    # RankingEngine or allowed to raise an unhandled exception.
    vehicle_type = form.vehicle_type.data if form.vehicle_type.data in VEHICLE_CATEGORIES else VEHICLE_CATEGORIES[0]

    period_raw = form.period.data
    try:
        period = int(period_raw) if period_raw else available_periods[-1]
    except (TypeError, ValueError):
        period = available_periods[-1]
    if period not in available_periods:
        period = available_periods[-1]

    # Optional district filter — an unrecognized/tampered value is silently
    # treated as "All Districts", the same defensive pattern as above.
    district = form.district.data if form.district.data in engine.canonical_districts else None

    try:
        top_n = int(request.args.get("top_n", engine.config["top_n"]))
    except (TypeError, ValueError):
        top_n = engine.config["top_n"]
    top_n = max(1, min(top_n, len(engine.canonical_districts)))

    form.vehicle_type.data = vehicle_type
    form.period.data = str(period)
    form.district.data = district or ""
    form.top_n.data = top_n

    try:
        # Always request SHAP explanations for every eligible district, not
        # just the configured top-N — the same full-coverage pattern the
        # Streamlit dashboard already uses (REF-009 ADR-021) so a single
        # selected district can be shown with its real rank/band/SHAP
        # factors even when it falls outside the default top-N, without a
        # second, independently-computed prediction or SHAP call.
        result = engine.rank(vehicle_type, period, top_n=len(engine.canonical_districts))
    except Exception:  # noqa: BLE001 - same "never crash, never fabricate" rule as the load path above
        logger.exception("Opportunity Insights: RankingEngine.rank() raised unexpectedly.")
        return render_template(
            "insights/opportunity_insights.html", backend_unavailable=True, indicator_v2=indicator_v2,
        ), 503

    district_not_found = False
    if result["status"] != STATUS_OK:
        display_entries = []
    elif district:
        selected_entry = next((e for e in result["top_n"] if e["district"] == district), None)
        if selected_entry is not None:
            display_entries = [selected_entry]
        else:
            display_entries = []
            district_not_found = True
    else:
        display_entries = result["top_n"][:top_n]

    return render_template(
        "insights/opportunity_insights.html",
        form=form,
        result=result,
        display_entries=display_entries,
        selected_district=district,
        district_not_found=district_not_found,
        max_top_n=len(engine.canonical_districts),
        model_info=None if indicator_v2 else _model_info(engine),
        method_summary=engine.method_summary() if indicator_v2 else None,
        interface_label=engine.config["interface_label"] if indicator_v2 else None,
        indicator_v2=indicator_v2,
        backend_unavailable=False,
    )


def _model_info(engine):
    """Plain dict-shaping of already-computed metadata for display — not a
    computation of anything new (mirrors dashboard/views.py's
    format_model_version_summary, which does the same for Streamlit)."""
    test_metrics = engine.metadata.get("test_metrics", {})
    mae = test_metrics.get("mae")
    return {
        "production_model": "XGBoost (tuned)",
        "dataset_version": engine.metadata.get("dataset_version"),
        "model_trained": engine.metadata.get("generated_date"),
        "test_mae": f"{mae:.1f}" if mae is not None else "n/a",
    }
