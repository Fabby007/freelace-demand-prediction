"""Chooses the recommendation engine from one setting (REF-009 ADR-043).

`configs/recommendation_v2.yaml` selects v1 (`RankingEngine`) or v2
(`FleetOpportunityEngine`). Each engine is imported only when selected, so v2
mode never loads the v1 model files. An unknown setting raises an error rather
than falling back to the other engine.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from src.recommendation.fleet_opportunity_v2 import INDICATOR_TYPE, RECOMMENDATION_CONFIG_YAML

ENGINE_V1 = "v1"
ENGINE_V2 = "v2"


def get_active_engine_name(config_path: Path = RECOMMENDATION_CONFIG_YAML) -> str:
    with open(config_path, encoding="utf-8") as f:
        name = yaml.safe_load(f).get("active_engine")
    if name not in (ENGINE_V1, ENGINE_V2):
        raise ValueError(f"active_engine must be '{ENGINE_V1}' or '{ENGINE_V2}', got {name!r}")
    return name


def load_active_engine():
    if get_active_engine_name() == ENGINE_V2:
        from src.recommendation.fleet_opportunity_v2 import FleetOpportunityEngine

        return FleetOpportunityEngine.load()

    from src.recommendation.ranking_engine import RankingEngine

    return RankingEngine.load()


def is_fleet_engine(engine) -> bool:
    return getattr(engine, "indicator_type", None) == INDICATOR_TYPE
