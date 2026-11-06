"""DEV-011 / DEV-015 tests for the SBERT natural-language query router.

Covers DEV-011's Testing Requirements: Section 26.3 ("unsupported SBERT
queries produce a safe fallback rather than a wrong category") and a
matching-accuracy spot-check against a small hand-written set of example
queries per category.
"""
import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pytest

from src.nlp.sbert_router import (
    STATUS_AMBIGUOUS,
    STATUS_CONFIDENT,
    STATUS_EMPTY,
    STATUS_UNSUPPORTED,
    SBERTRouter,
)

CANONICAL_CATEGORIES = {"Motorcycle", "Car", "Three-wheeler"}


@pytest.fixture(scope="module")
def router() -> SBERTRouter:
    return SBERTRouter.load()


# --- Category description embeddings defined once, reused per query --------

def test_category_embeddings_computed_once_and_reused(router):
    assert router.category_embeddings.shape[0] == len(router.category_names)
    assert set(router.category_names) == CANONICAL_CATEGORIES

    embeddings_before = router.category_embeddings.copy()
    router.route("I fix motorcycles")
    router.route("car mechanic here")
    # category_embeddings must be byte-identical after routing calls - never
    # recomputed per query (Functional Requirement).
    import numpy as np
    np.testing.assert_array_equal(embeddings_before, router.category_embeddings)


# --- Matching-accuracy spot-check (DEV-011 Testing Requirements) -----------

@pytest.mark.parametrize("query,expected_category", [
    ("bike repair", "Motorcycle"),
    ("I fix motorcycles", "Motorcycle"),
    ("car mechanic here", "Car"),
    ("trishaw repairs", "Three-wheeler"),
    ("tuk tuk mechanic", "Three-wheeler"),
])
def test_spot_check_confident_matches_correct_category(router, query, expected_category):
    result = router.route(query)
    assert result.status == STATUS_CONFIDENT
    assert result.matched_category == expected_category


def test_matched_category_is_always_a_canonical_category(router):
    for query in ["bike repair", "car mechanic here", "trishaw repairs"]:
        result = router.route(query)
        if result.matched_category is not None:
            assert result.matched_category in CANONICAL_CATEGORIES


# --- Safe fallback: unsupported queries never silently pick a category -----

@pytest.mark.parametrize("query", [
    "what is the weather today",
    "asdkfj alsdkfj qwe",
    "please recommend a good restaurant in Colombo",
])
def test_unsupported_queries_produce_safe_fallback_not_wrong_category(router, query):
    result = router.route(query)
    assert result.status == STATUS_UNSUPPORTED
    assert result.matched_category is None
    assert "manually" in result.message.lower() or "select" in result.message.lower()


def test_unsupported_query_still_exposes_similarity_scores_for_transparency(router):
    result = router.route("what is the weather today")
    assert set(result.similarity_scores.keys()) == CANONICAL_CATEGORIES


# --- Empty query is distinct from ambiguous/unsupported (Error Case) -------

@pytest.mark.parametrize("query", ["", "   ", None])
def test_empty_query_is_its_own_status_not_ambiguous_or_unsupported(router, query):
    result = router.route(query)
    assert result.status == STATUS_EMPTY
    assert result.matched_category is None
    assert result.similarity_scores == {}


# --- Ambiguous queries never silently default to a category (Business Rule) -

def test_close_call_query_is_flagged_ambiguous_not_silently_resolved(router):
    """'I service scooters and mopeds' plausibly matches Motorcycle and
    Three-wheeler nearly equally under this model/config (empirically
    verified during DEV-011 tuning - see REF-009 ADR-017) - must be
    ambiguous, never a silent pick of whichever scored marginally higher."""
    result = router.route("I service scooters and mopeds")
    assert result.status == STATUS_AMBIGUOUS
    assert result.matched_category is None


def test_ambiguous_status_never_defaults_to_motorcycle(router):
    """Business Rule: a failed/ambiguous match must never silently default
    to Motorcycle just because it's the primary scenario."""
    result = router.route("I service scooters and mopeds")
    assert result.matched_category is None  # NOT "Motorcycle", even though it's the top scorer


# --- Threshold/margin are documented config values, not hardcoded ----------

def test_threshold_and_margin_are_read_from_config(router):
    from src.nlp.sbert_router import SBERT_CATEGORIES_YAML
    import yaml
    with open(SBERT_CATEGORIES_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert router.similarity_threshold == pytest.approx(config["similarity_threshold"])
    assert router.ambiguous_margin == pytest.approx(config["ambiguous_margin"])


def test_below_threshold_query_is_unsupported_even_with_large_margin(router):
    """A query whose top score is below similarity_threshold must be
    'unsupported' regardless of how large its margin over the second-best
    category is - the threshold and margin checks are independent gates."""
    result = router.route("quantum physics homework help")
    assert result.top_score < router.similarity_threshold
    assert result.status == STATUS_UNSUPPORTED


# --- Custom router instances (constructor-level correctness) ---------------

def test_route_with_custom_thresholds_via_direct_construction(router):
    """A router built with a very low threshold/margin should reclassify a
    previously-ambiguous query as confident - proves the decision logic
    genuinely depends on the configured values, not hardcoded cutoffs."""
    import dataclasses
    permissive_router = dataclasses.replace(router, similarity_threshold=0.0, ambiguous_margin=0.0)
    result = permissive_router.route("I service scooters and mopeds")
    assert result.status == STATUS_CONFIDENT
    assert result.matched_category in CANONICAL_CATEGORIES
