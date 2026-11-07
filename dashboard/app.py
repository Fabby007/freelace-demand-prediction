"""Streamlit + Plotly Dashboard (DEV-013).

Thin presentation layer only (Backend Behavior): every prediction, SHAP
explanation, and SBERT routing decision is computed by `src.recommendation`,
`src.explainability`, and `src.nlp` (DEV-012/DEV-010/DEV-011), unchanged.
This script lays out controls and panels and renders their output - it never
recomputes a prediction, a SHAP value, or a category match itself.

Every panel for a given (vehicle_type, period) selection is built from ONE
`RankingEngine.rank()` call's output (`cached_rank`, DEV-012's ranking
engine) - the map, the table, and the district-detail panel all read the
same `predicted_value`/`opportunity_band` per district (Section 26.3), never
a separately re-derived number.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run dashboard/app.py` puts this file's own directory on
# sys.path, not the repo root - add the repo root so `import src` (and
# therefore ADR-003's torch-first import order) resolves correctly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src  # noqa: E402,F401  (ADR-003 import order - must precede pandas/numpy/xgboost/torch)

import streamlit as st  # noqa: E402

from dashboard.data_access import (  # noqa: E402
    cached_rank,
    cached_route_query,
    get_district_history,
    load_dataset_version_info,
    load_geo_resources,
    load_model_metadata,
    load_ranking_engine,
    load_sbert_router,
    load_source_register,
)
from dashboard.views import (  # noqa: E402
    DISCLAIMER,
    build_band_choropleth_figure,
    build_choropleth_figure,
    build_fleet_ranking_table,
    build_fleet_trend_figure,
    build_ranking_table,
    build_trend_figure,
    format_fleet_method_summary,
    format_model_version_summary,
    format_source_register,
)
from src.models.xgboost_model import VEHICLE_CATEGORIES  # noqa: E402
from src.nlp.sbert_router import STATUS_CONFIDENT  # noqa: E402
from src.recommendation.active_engine import ENGINE_V2, get_active_engine_name, is_fleet_engine  # noqa: E402
from src.recommendation.fleet_opportunity_v2 import FleetDataError  # noqa: E402
from src.recommendation.ranking_engine import STATUS_OK  # noqa: E402

FLEET_PAGE_TITLE = "Vehicle-Fleet Service Opportunity - Sri Lanka"

st.set_page_config(
    page_title=FLEET_PAGE_TITLE if get_active_engine_name() == ENGINE_V2 else "Mechanic Service Demand Opportunity - Sri Lanka",
    layout="wide",
)


def render_disclaimer() -> None:
    """Appendix C.3, verbatim - persistent, not confined to one panel
    (Business Rule)."""
    st.info(DISCLAIMER)


def render_sidebar_controls(engine, router) -> tuple[str, int, int, str]:
    """Section 19.1 controls. Returns (vehicle_type, period, top_n, selected_district)."""
    with st.sidebar:
        st.header("Find your best districts")

        vehicle_types = VEHICLE_CATEGORIES
        if "vehicle_type" not in st.session_state:
            st.session_state.vehicle_type = vehicle_types[0]

        with st.form("nl_query_form", clear_on_submit=False):
            query = st.text_input(
                "Describe your work (optional)",
                placeholder='e.g. "I repair motorcycles, where should I focus next month?"',
            )
            submitted = st.form_submit_button("Match my category")
        if submitted and query.strip():
            route_result = cached_route_query(router, query)
            if route_result.status == STATUS_CONFIDENT:
                st.session_state.vehicle_type = route_result.matched_category
                st.success(f"Matched to the '{route_result.matched_category}' mechanic category below. You can change it.")
            else:
                st.warning(route_result.message)
        elif submitted:
            st.warning("No query was submitted.")

        vehicle_type = st.selectbox(
            "Vehicle category", vehicle_types,
            index=vehicle_types.index(st.session_state.vehicle_type),
        )
        st.session_state.vehicle_type = vehicle_type

        available_years = sorted(int(y) for y in engine.frozen_df["year"].unique())
        available_periods = [y + 1 for y in available_years]
        period = st.selectbox("Prediction year", available_periods, index=len(available_periods) - 1)

        top_n = st.slider(
            "Number of districts to recommend",
            min_value=1, max_value=len(engine.canonical_districts), value=engine.config["top_n"],
        )

        selected_district = st.selectbox("District for detailed view", engine.canonical_districts)

        st.divider()
        st.caption(DISCLAIMER)

    return vehicle_type, period, top_n, selected_district


def render_no_data_state(message: str) -> None:
    st.warning(message)


def render_map_and_table(result: dict, geo: dict, vehicle_type: str, top_n: int) -> None:
    col_map, col_table = st.columns([3, 2])
    with col_map:
        st.subheader("Predicted opportunity by district")
        fig = build_choropleth_figure(
            result["ranked_districts"], geo["geojson"], geo["canonical_to_shape_name"], vehicle_type,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader(f"Top {top_n} districts")
        table_df = build_ranking_table(result["top_n"][:top_n])
        st.dataframe(table_df, hide_index=True, use_container_width=True)
        # FR-12 (best-effort, optional per source doc "if time permits").
        st.download_button(
            "Download this ranking as CSV",
            data=table_df.to_csv(index=False),
            file_name=f"{vehicle_type.lower()}_ranking_{result['period']}.csv",
            mime="text/csv",
        )


def render_district_detail(engine, result: dict, selected_district: str, vehicle_type: str, period: int) -> None:
    st.divider()
    st.subheader(f"Detail: {selected_district}")

    detail_entry = next((e for e in result["top_n"] if e["district"] == selected_district), None)
    ranked_entry = next((d for d in result["ranked_districts"] if d["district"] == selected_district), None)

    col_forecast, col_trend = st.columns([1, 2])
    with col_forecast:
        st.markdown("**Forecast for the selected period**")
        if ranked_entry is not None:
            st.metric(
                f"Predicted {vehicle_type.lower()} opportunity ({period})",
                f"{ranked_entry['predicted_value']:.0f}",
            )
            st.write(f"Opportunity band: **{ranked_entry['opportunity_band']}**")
            if ranked_entry.get("data_quality_flag") or ranked_entry.get("target_data_quality_flag"):
                st.warning(
                    "This district's underlying data carries a data-quality note: "
                    f"{ranked_entry.get('target_data_quality_flag') or ranked_entry.get('data_quality_flag')}"
                )
        else:
            st.info("No prediction is available for this district in the selected period.")

    with col_trend:
        st.markdown("**Historical registration trend**")
        history_df = get_district_history(engine, selected_district, vehicle_type)
        if history_df.empty or history_df["new_registrations"].notna().sum() == 0:
            st.info("No historical registration data is available for this district/vehicle type.")
        else:
            st.plotly_chart(build_trend_figure(history_df, selected_district, vehicle_type), use_container_width=True)

    st.markdown("**Why this prediction? (SHAP explanation)**")
    if detail_entry is not None:
        st.write(detail_entry["recommendation_sentence"])
        st.caption(detail_entry["shap_note"])
    else:
        st.info(
            "This district is outside the currently-computed detail range. "
            "Increase 'Number of districts to recommend' to include it."
        )


def render_data_source_panel() -> None:
    st.divider()
    st.subheader("Data sources and model version")

    summary_df = format_model_version_summary(load_model_metadata(), load_dataset_version_info())
    st.dataframe(summary_df, hide_index=True, use_container_width=True)

    st.markdown("**Registered data sources**")
    st.dataframe(format_source_register(load_source_register()), hide_index=True, use_container_width=True)


def render_fleet_sidebar_controls(engine, router) -> tuple[str, int, int, str]:
    """The same controls as v1. Years are labelled by data year, and only the
    latest year gives an unobserved estimate."""
    with st.sidebar:
        st.header("Compare districts")

        vehicle_types = VEHICLE_CATEGORIES
        if "vehicle_type" not in st.session_state:
            st.session_state.vehicle_type = vehicle_types[0]

        with st.form("nl_query_form", clear_on_submit=False):
            query = st.text_input("Describe your work (optional)", placeholder='e.g. "I repair motorcycles"')
            submitted = st.form_submit_button("Match my category")
        if submitted and query.strip():
            route_result = cached_route_query(router, query)
            if route_result.status == STATUS_CONFIDENT:
                st.session_state.vehicle_type = route_result.matched_category
                st.success(f"Matched to the '{route_result.matched_category}' mechanic category below. You can change it.")
            else:
                st.warning(route_result.message)
        elif submitted:
            st.warning("No query was submitted.")

        # Bound by key, so a changing `index` cannot reset the widget and drop a selection.
        vehicle_type = st.selectbox("Vehicle category", vehicle_types, key="vehicle_type")

        periods = engine.available_periods()
        period = st.selectbox("Data year", periods, index=len(periods) - 1, format_func=engine.period_label)

        top_n = st.slider(
            "Number of districts to show",
            min_value=1, max_value=len(engine.canonical_districts), value=engine.config["top_n"],
        )
        selected_district = st.selectbox("District for detailed view", engine.canonical_districts)

        st.divider()
        st.caption(DISCLAIMER)

    return vehicle_type, period, top_n, selected_district


def render_fleet_map_and_table(result: dict, geo: dict, vehicle_type: str, top_n: int) -> None:
    year = result["reference_year"]
    st.subheader("Relative vehicle-fleet opportunity by district")
    fig = build_band_choropleth_figure(
        result["ranked_districts"], geo["geojson"], geo["canonical_to_shape_name"], vehicle_type,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Full width, so the band, reliability and flag columns stay visible.
    st.subheader(f"Top {top_n} districts by licensed vehicles ({year})")
    entries = result["ranked_districts"][:top_n]
    table_df = build_fleet_ranking_table(entries)
    st.dataframe(table_df, hide_index=True, use_container_width=True)
    st.download_button(
        "Download this ranking as CSV",
        data=table_df.assign(Disclaimer=DISCLAIMER).to_csv(index=False),
        file_name=f"{vehicle_type.lower()}_fleet_opportunity_{year}.csv",
        mime="text/csv",
    )
    st.caption(f"{result['uncertainty_note']} {result['position_note']}")

    for entry in entries:
        if entry["flag_warning"]:
            st.warning(f"{entry['district']} (rank {entry['rank']}). {entry['flag_warning']}")


def render_fleet_district_detail(engine, result: dict, selected_district: str, vehicle_type: str) -> None:
    year = result["reference_year"]
    st.divider()
    st.subheader(f"Detail: {selected_district}")
    entry = next((d for d in result["ranked_districts"] if d["district"] == selected_district), None)

    col_value, col_trend = st.columns([1, 2])
    with col_value:
        if entry is None:
            st.info(f"No usable {year} count is available for this district and vehicle type.")
        else:
            st.metric(f"Licensed vehicles, {vehicle_type.lower()} ({year})", f"{entry['licence_count']:,.0f}")
            st.write(f"Opportunity band: **{entry['opportunity_band']}**")
            st.write(f"Rank: **{entry['rank']} of {result['n_ranked']}**")
            st.write(f"Share of {vehicle_type.lower()} licences: **{entry['share_pct']:.1f}%**")
            st.write(f"Reliability: **{entry['reliability']}**")
            if entry["flag_warning"]:
                st.warning(entry["flag_warning"])

    with col_trend:
        st.markdown("**Licensed vehicles over time**")
        history_df = get_district_history(engine, selected_district, vehicle_type)
        if history_df.empty or history_df["licence_count"].notna().sum() == 0:
            st.info("No licence counts are available for this district and vehicle type.")
        else:
            st.plotly_chart(build_fleet_trend_figure(history_df, selected_district, vehicle_type), use_container_width=True)

    st.markdown("**Why this district ranks here**")
    if entry is not None:
        st.write(entry["recommendation_sentence"])
        for fact in entry["explanation_facts"]:
            if fact != entry["flag_warning"]:
                st.markdown(f"- {fact}")
        st.caption(entry["explanation_note"])


def render_fleet_data_panel(engine) -> None:
    st.divider()
    st.subheader("Data sources and method")
    st.dataframe(format_fleet_method_summary(engine.method_summary()), hide_index=True, use_container_width=True)
    st.markdown("**Registered data sources**")
    st.dataframe(format_source_register(load_source_register()), hide_index=True, use_container_width=True)


def main_fleet(engine, router, geo) -> None:
    """Vehicle-Fleet Service Opportunity view (REF-009 ADR-042, ADR-043). Every
    panel reads one `rank()` result, as in the v1 view."""
    vehicle_type, period, top_n, selected_district = render_fleet_sidebar_controls(engine, router)
    render_disclaimer()
    st.info(engine.config["meaning_note"])
    st.caption(engine.config["evidence_note"])

    result = cached_rank(engine, vehicle_type, period, len(engine.canonical_districts), engine_key=ENGINE_V2)
    if result["status"] != STATUS_OK:
        render_no_data_state(result["message"])
        render_fleet_data_panel(engine)
        return

    if result["missing_message"]:
        st.warning(result["missing_message"])
    render_fleet_map_and_table(result, geo, vehicle_type, top_n)
    render_fleet_district_detail(engine, result, selected_district, vehicle_type)
    render_fleet_data_panel(engine)
    render_disclaimer()


def main() -> None:
    is_v2 = get_active_engine_name() == ENGINE_V2
    if is_v2:
        st.title(FLEET_PAGE_TITLE)
        st.caption("Part of the project: Mechanic Service Demand Opportunity Prediction and Recommendation System.")
    else:
        st.title("Mechanic Service Demand Opportunity - Sri Lanka")
        st.caption("A decision-support tool for freelance mechanics. It does not guarantee jobs, customers, or income.")

    try:
        engine = load_ranking_engine()
    except FleetDataError as exc:
        st.error(f"Results are not shown because the licence data failed a check. {exc}")
        return
    router = load_sbert_router()
    geo = load_geo_resources()

    if is_fleet_engine(engine):
        main_fleet(engine, router, geo)
        return

    vehicle_type, period, top_n, selected_district = render_sidebar_controls(engine, router)

    render_disclaimer()

    result = cached_rank(engine, vehicle_type, period, len(engine.canonical_districts))

    if result["status"] != STATUS_OK:
        render_no_data_state(result["message"])
        render_data_source_panel()
        return

    render_map_and_table(result, geo, vehicle_type, top_n)
    render_district_detail(engine, result, selected_district, vehicle_type, period)
    render_data_source_panel()
    render_disclaimer()


main()
