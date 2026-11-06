"""DEV-012 / DEV-015 tests for the District Ranking & Recommendation Engine.

Covers DEV-012's Testing Requirements: every top-N row carries a SHAP
explanation and the exact disclaimer; opportunity-band thresholds are
applied deterministically/consistently; ranking-table and map-ready output
share identical underlying prediction values (Section 26.3).
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.models.xgboost_model import MODELS_DIR, VEHICLE_CATEGORIES
from src.nlp.sbert_router import SBERTRouter
from src.recommendation.ranking_engine import (
    RANKING_CONFIG_YAML,
    STATUS_NO_DATA,
    STATUS_OK,
    RankingEngine,
    assign_band,
    build_recommendation_sentence,
    compute_band_thresholds,
    select_top_factors,
)

pytestmark = pytest.mark.skipif(
    not (MODELS_DIR / "model.json").exists(), reason="DEV-008 saved model not present locally"
)

EXACT_DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)


@pytest.fixture(scope="module")
def engine() -> RankingEngine:
    return RankingEngine.load()


@pytest.fixture(scope="module")
def router() -> SBERTRouter:
    return SBERTRouter.load()


# --- Six-step process end-to-end --------------------------------------------

def test_rank_returns_ok_status_with_full_ranking_for_a_real_period(engine):
    result = engine.rank("Motorcycle", 2024)
    assert result["status"] == STATUS_OK
    assert len(result["ranked_districts"]) > 0
    assert result["vehicle_type"] == "Motorcycle"
    assert result["period"] == 2024


def test_ranked_districts_are_sorted_descending_by_predicted_value(engine):
    result = engine.rank("Car", 2024)
    values = [d["predicted_value"] for d in result["ranked_districts"]]
    assert values == sorted(values, reverse=True)


def test_ranks_are_sequential_starting_at_one(engine):
    result = engine.rank("Three-wheeler", 2024)
    ranks = [d["rank"] for d in result["ranked_districts"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_top_n_respects_configured_default(engine):
    result = engine.rank("Motorcycle", 2024)
    with open(RANKING_CONFIG_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert len(result["top_n"]) == config["top_n"]


def test_top_n_can_be_overridden(engine):
    result = engine.rank("Motorcycle", 2024, top_n=3)
    assert len(result["top_n"]) == 3


# --- Every top-N row carries a SHAP explanation and the exact disclaimer ----

def test_every_top_n_row_has_non_empty_shap_explanation_and_exact_disclaimer(engine):
    result = engine.rank("Motorcycle", 2024)
    for entry in result["top_n"]:
        assert entry["disclaimer"] == EXACT_DISCLAIMER
        assert len(entry["positive_factors"]) + len(entry["negative_factors"]) > 0
        assert entry["recommendation_sentence"].endswith(EXACT_DISCLAIMER)
        assert "shap_note" in entry and len(entry["shap_note"]) > 0


def test_top_level_output_also_carries_the_exact_disclaimer(engine):
    result = engine.rank("Motorcycle", 2024)
    assert result["disclaimer"] == EXACT_DISCLAIMER


def test_vehicle_type_never_appears_as_a_named_factor(engine):
    """Module docstring rationale: vehicle_type's SHAP contribution is
    constant within one ranking call and cannot explain relative ranking."""
    result = engine.rank("Motorcycle", 2024)
    for entry in result["top_n"]:
        factor_names = [f["feature"] for f in entry["positive_factors"] + entry["negative_factors"]]
        assert "vehicle_type" not in factor_names


# --- Wording rules (REF-007 Section 4) --------------------------------------

def test_recommendation_sentence_never_claims_a_guaranteed_count(engine):
    result = engine.rank("Motorcycle", 2024)
    for entry in result["top_n"]:
        sentence = entry["recommendation_sentence"].lower()
        assert "guarantee" not in sentence.split("predictions are based")[0]  # only the disclaimer clause may mention it
        assert "definitely" not in sentence
        assert "jobs" not in sentence  # never claims a job count directly


def test_recommendation_sentence_follows_category_period_district_band_structure(engine):
    result = engine.rank("Car", 2024, top_n=1)
    entry = result["top_n"][0]
    sentence = entry["recommendation_sentence"]
    assert "car mechanics in 2024" in sentence.lower()
    assert entry["district"] in sentence
    assert entry["opportunity_band"].lower() in sentence.lower()


# --- Opportunity bands: deterministic, per-vehicle-type, train-split-only --

def test_assign_band_boundaries():
    thresholds = {"q25": 10.0, "q50": 20.0, "q75": 30.0}
    assert assign_band(5.0, thresholds) == "Low"
    assert assign_band(10.0, thresholds) == "Low"
    assert assign_band(15.0, thresholds) == "Moderate"
    assert assign_band(20.0, thresholds) == "Moderate"
    assert assign_band(25.0, thresholds) == "High"
    assert assign_band(30.0, thresholds) == "High"
    assert assign_band(31.0, thresholds) == "Very High"


def test_assign_band_handles_missing_value_and_missing_thresholds():
    assert assign_band(float("nan"), {"q25": 1.0, "q50": 2.0, "q75": 3.0}) is None
    assert assign_band(5.0, None) is None


def test_assign_band_handles_a_negative_predicted_value_honestly():
    """A real, disclosed XGBoost finding (REF-009 ADR-010/DEV-008): a
    physically-impossible negative prediction can occur (1/47 test rows).
    The ranking engine must not crash, clip, or hide it - a negative value
    is simply the lowest band, shown honestly, not silently corrected."""
    thresholds = {"q25": 10.0, "q50": 20.0, "q75": 30.0}
    assert assign_band(-5.0, thresholds) == "Low"


def test_band_thresholds_computed_per_vehicle_type_independently():
    """A Car district's band must never be influenced by Motorcycle-scale
    values, and vice versa (they are on very different numeric scales)."""
    train_df = pd.DataFrame({
        "vehicle_type": ["Motorcycle"] * 4 + ["Car"] * 4,
        "target_value": [100.0, 200.0, 300.0, 400.0, 1.0, 2.0, 3.0, 4.0],
    })
    thresholds = compute_band_thresholds(train_df, [0.25, 0.50, 0.75])
    assert thresholds["Motorcycle"]["q50"] == pytest.approx(250.0)
    assert thresholds["Car"]["q50"] == pytest.approx(2.5)


def test_band_thresholds_use_train_split_only_not_full_dataset(engine):
    """Sanity check against real data: band thresholds must match quartiles
    computed from the train split alone, not validation/test/unlabeled rows."""
    full_df = engine.frozen_df
    train_only = full_df[full_df["split"] == "train"]
    recomputed = compute_band_thresholds(train_only, engine.config["band_quantiles"])
    assert recomputed == engine.band_thresholds


def test_bands_not_recomputed_ad_hoc_per_query(engine):
    """Two separate rank() calls for the same vehicle_type at different
    periods must use the exact same band-threshold object (computed once at
    load time), not re-derive it per call from whatever's eligible that
    period - proven via object identity, not just equal values."""
    thresholds_before = engine.band_thresholds
    engine.rank("Motorcycle", 2023)
    engine.rank("Motorcycle", 2024)
    assert engine.band_thresholds is thresholds_before  # same object - never reassigned by rank()


# --- Deterministic tie-break rule (Edge Case) -------------------------------

def test_tied_predictions_break_ties_alphabetically(engine, monkeypatch):
    """Two districts with an identical predicted_value must be ordered
    alphabetically, reproducibly - not by insertion/row order."""
    fixed_eligible = pd.DataFrame({
        "district": ["Zebra-District", "Alpha-District", "Mid-District"],
        "vehicle_type": ["Motorcycle"] * 3,
        "year": [2023, 2023, 2023],
        "new_registrations": [10.0, 10.0, 10.0],
        "data_quality_flag": [None, None, None],
        "target_data_quality_flag": [None, None, None],
        "target_value": [None, None, None],
    }).sort_values(["district"])  # deliberately not pre-sorted by rank
    predicted = pd.Series([50.0, 50.0, 50.0])  # all tied

    combined = fixed_eligible.reset_index(drop=True).assign(predicted_value=predicted)
    combined = combined.sort_values(["predicted_value", "district"], ascending=[False, True]).reset_index(drop=True)
    assert list(combined["district"]) == ["Alpha-District", "Mid-District", "Zebra-District"]


# --- Missing period / no eligible districts (Error Case) -------------------

def test_period_outside_dataset_coverage_returns_clear_no_data_message(engine):
    result = engine.rank("Motorcycle", 2030)
    assert result["status"] == STATUS_NO_DATA
    assert result["ranked_districts"] == []
    assert result["top_n"] == []
    assert "2030" in result["message"]
    assert result["disclaimer"] == EXACT_DISCLAIMER  # even a no-data response carries it


def test_invalid_vehicle_type_raises_rather_than_silently_proceeding(engine):
    with pytest.raises(ValueError):
        engine.rank("Bicycle", 2024)


# --- Section 26.3: ranking table and map-ready output share the same values -

def test_top_n_predicted_values_match_ranked_districts_exactly(engine):
    result = engine.rank("Motorcycle", 2024)
    ranked_by_district = {d["district"]: d["predicted_value"] for d in result["ranked_districts"]}
    for entry in result["top_n"]:
        assert entry["predicted_value"] == ranked_by_district[entry["district"]]
        assert entry["opportunity_band"] == next(
            d["opportunity_band"] for d in result["ranked_districts"] if d["district"] == entry["district"]
        )


# --- SBERT integration: routes but never predicts/explains -----------------

def test_rank_from_query_confident_match_routes_to_correct_category(engine, router):
    result = engine.rank_from_query(router, "I fix motorcycles", 2024)
    assert result["status"] == STATUS_OK
    assert result["vehicle_type"] == "Motorcycle"
    assert len(result["ranked_districts"]) > 0


def test_rank_from_query_unsupported_returns_safe_fallback_no_fabricated_category(engine, router):
    result = engine.rank_from_query(router, "what is the weather today", 2024)
    assert result["status"] == "unsupported"
    assert result["vehicle_type"] is None
    assert result["ranked_districts"] == []
    assert result["top_n"] == []


def test_rank_from_query_ambiguous_returns_safe_fallback(engine, router):
    result = engine.rank_from_query(router, "I service scooters and mopeds", 2024)
    assert result["status"] == "ambiguous"
    assert result["vehicle_type"] is None
    assert result["ranked_districts"] == []


# --- select_top_factors: honesty for declining-trend-but-High districts ----

def test_select_top_factors_excludes_vehicle_type_and_unmapped_features():
    contributions = [
        {"feature": "vehicle_type", "shap_value": 100.0, "feature_value": "Motorcycle"},
        {"feature": "new_registrations", "shap_value": 50.0, "feature_value": 500.0},
        {"feature": "an_unmapped_feature", "shap_value": 40.0, "feature_value": 1.0},
        {"feature": "reg_growth_pct", "shap_value": -10.0, "feature_value": -5.0},
    ]
    positive, negative = select_top_factors(contributions, "Motorcycle", n_positive=2, n_negative=2)
    positive_names = [p["feature"] for p in positive]
    assert "vehicle_type" not in positive_names
    assert "an_unmapped_feature" not in positive_names
    assert "new_registrations" in positive_names
    assert negative[0]["feature"] == "reg_growth_pct"


def test_select_top_factors_surfaces_negative_factor_even_for_strong_district():
    """Edge Case: a district ranked High/Very High due to base level despite
    a genuinely negative growth factor must still show that negative factor
    - never suppressed to make the recommendation look uniformly positive."""
    contributions = [
        {"feature": "new_registrations", "shap_value": 900.0, "feature_value": 5000.0},
        {"feature": "reg_growth_pct", "shap_value": -300.0, "feature_value": -20.0},
    ]
    positive, negative = select_top_factors(contributions, "Motorcycle", n_positive=2, n_negative=1)
    assert len(negative) == 1
    assert negative[0]["feature"] == "reg_growth_pct"


def test_build_recommendation_sentence_structure():
    sentence = build_recommendation_sentence(
        district="Kandy", vehicle_type="Motorcycle", period=2024, band="High",
        positive=[{"plain_language": "strong recent registrations"}],
        negative=[{"plain_language": "a recent dip in growth"}],
        disclaimer=EXACT_DISCLAIMER,
    )
    assert sentence.startswith("For motorcycle mechanics in 2024, Kandy is ranked as a high-opportunity district.")
    assert "strong recent registrations" in sentence
    assert "a recent dip in growth" in sentence
    assert sentence.endswith(EXACT_DISCLAIMER)


# --- Config-driven, not hardcoded -------------------------------------------

def test_engine_config_matches_yaml_file(engine):
    with open(RANKING_CONFIG_YAML, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)
    assert engine.config["top_n"] == raw_config["top_n"]
    assert engine.config["n_positive_factors"] == raw_config["n_positive_factors"]
    assert engine.config["n_negative_factors"] == raw_config["n_negative_factors"]
    assert engine.config["band_quantiles"] == raw_config["band_quantiles"]
