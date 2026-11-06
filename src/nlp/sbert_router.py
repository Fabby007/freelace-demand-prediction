"""SBERT Natural-Language Query Module (DEV-011).

Source doc Section 16: "Converts a user's natural-language question into an
embedding and matches it to the correct mechanic/vehicle category. SBERT is
NOT the model that predicts district demand, and it is NOT used as a
free-form explanation generator." This module only routes a free-text query
to one of the REF-002 canonical vehicle categories (or a safe-fallback
status) - it never predicts, ranks, or explains anything itself (Business
Rule). DEV-012 is the only consumer that should call `SBERTRouter.route()`,
using its `matched_category` to select which existing XGBoost/SHAP pipeline
to run.

Section 16.1's 5-step example interaction, steps 1-3, are this module's
scope; steps 4-5 (ranking, SHAP) belong to DEV-012/DEV-010 and are not
implemented here.

Model choice (not specified in the source documentation - REF-009 ADR-016):
`sentence-transformers/all-MiniLM-L6-v2`, the library's own standard
general-purpose semantic-similarity default (small, fast on CPU, already
present in this environment's local Hugging Face cache).

Category description embeddings (Functional Requirement: "not recomputed
per query") are computed once when `SBERTRouter.load()` is called and reused
for every subsequent `route()` call.

Safe-fallback design (Business Rule: never silently default to a category):
`route()` returns one of four statuses, never silently substituting a
guess for a missing one:
- "empty": the query string was empty/whitespace-only (Error Case - treated
  as "no query submitted", distinct from an ambiguous match).
- "unsupported": the best similarity score is below `similarity_threshold`
  - the query likely isn't about vehicle-repair categories at all (covers
  irrelevant queries and, per the Error Case, queries in a script/language
  the model wasn't trained to embed meaningfully - both naturally produce a
  low top score with no special-casing needed).
- "ambiguous": the best score clears the threshold, but the top two
  categories' scores differ by less than `ambiguous_margin` (Edge Case -
  e.g. "I fix three-wheelers and small cars" plausibly matching two
  categories almost equally).
- "confident": a single category clearly wins both checks.

`matched_category` is populated ONLY for "confident" - every other status
returns `None`, so a caller can never mistake a fallback for a real match.
Every status still returns the full `similarity_scores` for all categories,
so the category is always surfaced for display/override even on a confident
match (Functional Requirement), and so a dashboard can show *why* a fallback
happened rather than just that it happened.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
SBERT_CATEGORIES_YAML = CONFIGS_DIR / "sbert_categories.yaml"

# REF-009 ADR-016.
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"

STATUS_CONFIDENT = "confident"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNSUPPORTED = "unsupported"
STATUS_EMPTY = "empty"


@dataclass
class RouteResult:
    query: str
    status: str
    matched_category: str | None
    similarity_scores: dict[str, float]
    top_score: float | None
    margin: float | None
    message: str


@dataclass
class SBERTRouter:
    model: SentenceTransformer
    category_names: list[str]
    category_embeddings: np.ndarray  # (n_categories, embedding_dim), computed once
    similarity_threshold: float
    ambiguous_margin: float

    @classmethod
    def load(
        cls, config_path: Path = SBERT_CATEGORIES_YAML, model_name: str = DEFAULT_MODEL_NAME,
    ) -> "SBERTRouter":
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        category_names = [c["canonical_name"] for c in config["categories"]]
        category_texts = [c["description"].strip() for c in config["categories"]]

        logger.info("Loading SBERT model '%s' and encoding %d category descriptions.", model_name, len(category_names))
        model = SentenceTransformer(model_name)
        category_embeddings = model.encode(category_texts)

        return cls(
            model=model,
            category_names=category_names,
            category_embeddings=category_embeddings,
            similarity_threshold=float(config["similarity_threshold"]),
            ambiguous_margin=float(config["ambiguous_margin"]),
        )

    def route(self, query: str) -> RouteResult:
        """Section 16.1 steps 1-3: embed the query, compare against the
        precomputed category embeddings, and either select the highest
        match or fail safe. Never fabricates a category label - a returned
        `matched_category` is always one of `self.category_names`, and is
        `None` for every non-"confident" status."""
        if query is None or not query.strip():
            return RouteResult(
                query=query or "", status=STATUS_EMPTY, matched_category=None,
                similarity_scores={}, top_score=None, margin=None,
                message="No query was submitted.",
            )

        query_embedding = self.model.encode([query])
        scores = cosine_similarity(query_embedding, self.category_embeddings)[0]
        similarity_scores = {name: float(score) for name, score in zip(self.category_names, scores)}

        ranked = sorted(similarity_scores.items(), key=lambda item: item[1], reverse=True)
        top_name, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else float("-inf")
        margin = top_score - second_score

        if top_score < self.similarity_threshold:
            return RouteResult(
                query=query, status=STATUS_UNSUPPORTED, matched_category=None,
                similarity_scores=similarity_scores, top_score=top_score, margin=margin,
                message=(
                    "Your query could not be confidently matched to a supported vehicle category. "
                    "Please select a category manually."
                ),
            )

        if margin < self.ambiguous_margin:
            return RouteResult(
                query=query, status=STATUS_AMBIGUOUS, matched_category=None,
                similarity_scores=similarity_scores, top_score=top_score, margin=margin,
                message=(
                    "Your query could plausibly match more than one vehicle category. "
                    "Please select a category manually."
                ),
            )

        return RouteResult(
            query=query, status=STATUS_CONFIDENT, matched_category=top_name,
            similarity_scores=similarity_scores, top_score=top_score, margin=margin,
            message=f"Matched to the '{top_name}' mechanic category. You can override this selection.",
        )


def run(query: str) -> RouteResult:
    logging.basicConfig(level=logging.INFO)
    router = SBERTRouter.load()
    result = router.route(query)
    logger.info("Query %r -> status=%s matched_category=%s", query, result.status, result.matched_category)
    return result


if __name__ == "__main__":
    import sys
    run(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else "")
