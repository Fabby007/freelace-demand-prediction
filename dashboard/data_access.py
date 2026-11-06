"""Cached resource/data loaders for the Streamlit dashboard (DEV-013).

Every function here is a thin wrapper around an existing `src.*` module -
this file contains no modelling, ranking, explanation, or routing logic of
its own (Backend Behavior: "dashboard code itself contains no
modelling/ranking logic"). `@st.cache_resource` is used for expensive,
stateful objects (the loaded model/encoder/SHAP explainer, the loaded SBERT
model) so they are constructed once per server process, not once per
widget interaction; `@st.cache_data` is used for cheap-to-copy data that
should still not be re-read from disk on every rerun.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy/xgboost/torch)

from src.data.fetch_district_geojson import load_geojson as _load_geojson, shape_name_to_canonical_district
from src.nlp.sbert_router import SBERTRouter
from src.recommendation.ranking_engine import RankingEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTER_CSV = REPO_ROOT / "data" / "source_register.csv"
SPLIT_CONFIG_YAML = REPO_ROOT / "configs" / "split_config.yaml"
MODEL_METADATA_JSON = REPO_ROOT / "models" / "xgboost_v1" / "metadata.json"
GEOJSON_PATH = REPO_ROOT / "data" / "raw" / "geo" / "sri_lanka_districts_adm2.geojson"


@st.cache_resource
def load_ranking_engine() -> RankingEngine:
    return RankingEngine.load()


@st.cache_resource
def load_sbert_router() -> SBERTRouter:
    return SBERTRouter.load()


@st.cache_resource
def load_geo_resources() -> dict:
    geojson = _load_geojson(GEOJSON_PATH)
    canonical_to_shape_name = {
        shape_name_to_canonical_district(f["properties"]["shapeName"]): f["properties"]["shapeName"]
        for f in geojson["features"]
    }
    return {"geojson": geojson, "canonical_to_shape_name": canonical_to_shape_name}


@st.cache_data
def load_source_register() -> pd.DataFrame:
    return pd.read_csv(SOURCE_REGISTER_CSV)


@st.cache_data
def load_model_metadata() -> dict:
    with open(MODEL_METADATA_JSON, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_dataset_version_info() -> dict:
    with open(SPLIT_CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@st.cache_data(show_spinner="Ranking districts...")
def cached_rank(_engine: RankingEngine, vehicle_type: str, period: int, top_n: int) -> dict:
    """Cached wrapper around RankingEngine.rank() - `_engine` is excluded
    from Streamlit's cache key (leading underscore) since the engine object
    itself never changes within a server process; (vehicle_type, period,
    top_n) are the real cache key, avoiding recomputing predictions + SHAP
    on every widget rerun for an unchanged selection."""
    return _engine.rank(vehicle_type, period, top_n=top_n)


@st.cache_data(show_spinner=False)
def cached_route_query(_router: SBERTRouter, query: str):
    return _router.route(query)


def get_district_history(_engine: RankingEngine, district: str, vehicle_type: str) -> pd.DataFrame:
    """Real historical new_registrations for one district/vehicle_type,
    read directly from the already-loaded frozen dataset - not a ranking
    computation, just a filter of existing real rows for display."""
    df = _engine.frozen_df
    history = df[(df["district"] == district) & (df["vehicle_type"] == vehicle_type)].sort_values("year")
    return history[["year", "new_registrations", "data_quality_flag"]].reset_index(drop=True)
