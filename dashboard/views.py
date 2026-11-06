"""Pure presentation-building functions for the dashboard (DEV-013).

Deliberately free of Streamlit widget calls (`st.*`) so every function here
is directly unit-testable without spinning up a Streamlit session, and so
`app.py` stays a thin layout/widget layer that only calls into these
functions plus `src.*` (Backend Behavior).
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)


def build_choropleth_figure(
    ranked_districts: list[dict], geojson: dict, canonical_to_shape_name: dict, vehicle_type: str,
) -> go.Figure:
    """Section 19.2: Sri Lanka choropleth map, coloured by the SAME
    `predicted_value` the ranking table shows (Section 26.3) - never a
    separately-derived number."""
    df = pd.DataFrame(ranked_districts)
    df["shape_name"] = df["district"].map(canonical_to_shape_name)

    fig = px.choropleth(
        df, geojson=geojson, locations="shape_name", featureidkey="properties.shapeName",
        color="predicted_value", color_continuous_scale="Blues",
        hover_name="district",
        hover_data={"shape_name": False, "predicted_value": ":.0f", "opportunity_band": True, "rank": True},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar_title=f"Predicted {vehicle_type.lower()} opportunity",
    )
    return fig


RANKING_TABLE_COLUMNS = ["Rank", "District", "Predicted value", "Opportunity band", "Data quality note"]


def build_ranking_table(ranked_or_top_entries: list[dict]) -> pd.DataFrame:
    """Section 19.2: ranking table. `data_quality_flag`/`target_data_quality_flag`
    (REF-006/REF-009) are surfaced as a visible column, never dropped."""
    if not ranked_or_top_entries:
        # Edge Case: a top-N slice can legitimately be empty (e.g. no
        # eligible districts) - return the correct empty shape, not a
        # column-less DataFrame that breaks downstream column selection.
        return pd.DataFrame(columns=RANKING_TABLE_COLUMNS)

    df = pd.DataFrame(ranked_or_top_entries)
    df["Data quality note"] = df.apply(
        lambda r: r.get("target_data_quality_flag") or r.get("data_quality_flag") or "", axis=1
    )
    df = df.rename(columns={
        "rank": "Rank", "district": "District", "predicted_value": "Predicted value",
        "opportunity_band": "Opportunity band",
    })
    return df[RANKING_TABLE_COLUMNS]


def build_trend_figure(history_df: pd.DataFrame, district: str, vehicle_type: str) -> go.Figure:
    """Section 19.2: historical registration trend. Real observed values
    only - gaps (missing years, REF-009 ADR-005) are left as gaps in the
    line, never interpolated or zero-filled."""
    fig = px.line(
        history_df, x="year", y="new_registrations", markers=True,
        title=f"Historical {vehicle_type.lower()} registrations - {district}",
    )
    fig.update_layout(xaxis_title="Year", yaxis_title="New registrations")
    return fig


def format_source_register(source_register_df: pd.DataFrame) -> pd.DataFrame:
    """Section 19.2: data-source information panel."""
    return source_register_df[
        ["source_name", "publication_title", "url", "licence", "download_date", "status"]
    ].rename(columns={
        "source_name": "Source", "publication_title": "Publication", "url": "URL",
        "licence": "Licence", "download_date": "Retrieved", "status": "Status",
    })


def format_model_version_summary(model_metadata: dict, dataset_version_info: dict) -> pd.DataFrame:
    """Section 19.2: model-version information panel - plain-language
    summary, no ML jargon required to read it (Usability NFR). Returned as a
    two-column, all-string DataFrame so Streamlit's Arrow serialization
    never has to guess a mixed-type column's dtype."""
    test_metrics = model_metadata.get("test_metrics", {})
    mae = test_metrics.get("mae")
    rows = {
        "Production model": "XGBoost (tuned)",
        "Dataset version": dataset_version_info.get("dataset_version"),
        "Model trained": model_metadata.get("generated_date"),
        "Test-period average error (MAE)": f"{mae:.1f}" if mae is not None else "n/a",
        "Test-period rows evaluated": f"{test_metrics.get('n_scored')} / {test_metrics.get('n_total')}",
    }
    return pd.DataFrame({"Field": list(rows.keys()), "Value": [str(v) for v in rows.values()]})
