"""District Ranking & Recommendation Engine (DEV-012).

Source doc Section 18's six-step process, deterministically turning DEV-008's
per-district predictions into a sorted, banded, SHAP-explained,
disclaimer-carrying recommendation output - "the direct answer to the
project's core user question." This module never predicts anything itself
(DEV-008's saved XGBoost model does that, unchanged) and never invents an
explanation not backed by DEV-010's actual SHAP values (Section 18: "must
not invent narrative explanations unsupported by features/SHAP values").

Six-step process (Section 18), and where each step lives here:
1. Receive vehicle category + period - `RankingEngine.rank()`'s arguments,
   either supplied directly (DEV-013's dropdown controls) or resolved from a
   free-text query via `RankingEngine.rank_from_query()`, which calls
   DEV-011's `SBERTRouter.route()` and does nothing else with it - SBERT
   only ever selects which category to rank, never predicts or explains.
2. Generate the model prediction for each eligible district - reuses
   DEV-008's own `build_feature_matrix()` (same encoder, same feature order,
   same all-null-feature exclusions) and the saved model's `.predict()`.
3. Sort districts highest to lowest, with a deterministic tie-break
   (predicted_value descending, district name ascending - Edge Case).
4. Convert predictions to opportunity bands via `compute_band_thresholds()` -
   REF-009 ADR-018 for the exact rule (per-vehicle-type train-split
   quartiles).
5. Use DEV-010's `explain_rows()` to extract SHAP factors for the top-N
   districts only (not every eligible district - SHAP is comparatively
   expensive and Section 18's business rule only requires it for "top-ranked"
   recommendations).
6. Return top-N with trend context, the SHAP-derived plain-language factors,
   and the disclaimer.

Wording note (structure vs. mandatory text): Section 18.1's example sentence
ends with a paraphrased limitation statement ("This is a model-based
opportunity estimate and does not represent a guaranteed number of jobs.").
This module follows 18.1's STRUCTURE (category + period -> district -> band
-> plain-language SHAP factors -> limitation statement) but uses the exact,
verbatim Appendix C.3 disclaimer text as the limitation-statement slot, since
CLAUDE.md Section 15 / MASTER_PROMPT.md Section 0 require that specific text
verbatim on every recommendation-bearing surface, non-negotiably - the two
requirements are reconciled, not in conflict: 18.1 supplies the sentence
shape, Appendix C.3 supplies its final clause.

Why `vehicle_type`'s SHAP contribution never appears as a "factor": one
`rank()` call always ranks districts within a single vehicle_type, so that
factor's SHAP value is (near-)constant across every row being compared - it
cannot explain why one district outranks another in the same call, so
listing it as a "reason" would be misleading rather than merely redundant.
It remains fully available via DEV-010's raw output for anyone inspecting a
single district's full explanation outside a ranking context.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.explainability.shap_explainer import EXPLANATION_TYPE_NOTE, build_explainer, explain_rows
from src.models.xgboost_model import FROZEN_CSV, MODELS_DIR, TARGET_COLUMN, VEHICLE_CATEGORIES, build_feature_matrix, load_model
from src.nlp.sbert_router import STATUS_CONFIDENT, SBERTRouter

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
REPORTS_DIR = REPO_ROOT / "reports"

RANKING_CONFIG_YAML = CONFIGS_DIR / "ranking_config.yaml"
DISTRICT_LOOKUP_CSV = CONFIGS_DIR / "district_lookup.csv"
BAND_THRESHOLDS_JSON = REPORTS_DIR / "opportunity_band_thresholds.json"

GROUP_KEYS = ["district", "vehicle_type"]
BAND_ORDER = ["Low", "Moderate", "High", "Very High"]

STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"

# Section 18 step 4 excludes vehicle_type - see module docstring.
PLAIN_LANGUAGE_TEMPLATES = {
    "new_registrations": "the current level of {vt} registrations",
    "reg_lag_1": "the {vt} registration level in the previous period",
    "reg_lag_2": "the {vt} registration level two periods ago",
    "reg_growth_pct": "recent {vt} registration growth",
    "change_from_lag_2": "the change in {vt} registrations over the past two periods",
    "rolling_mean_3": "the recent average {vt} registration trend",
    "rolling_std_3": "the volatility of recent {vt} registrations",
    "vehicle_population": "the existing {vt} vehicle stock in the district",
}


def _clean(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.floating, np.integer)):
        return float(value)
    return value


def load_canonical_districts(path: Path = DISTRICT_LOOKUP_CSV) -> list[str]:
    return sorted(pd.read_csv(path)["canonical_name"].unique())


def compute_band_thresholds(train_df: pd.DataFrame, quantiles: list[float]) -> dict[str, dict[str, float] | None]:
    """REF-009 ADR-018: per-vehicle-type quartiles of the TRAIN-split
    target_value distribution, computed once (never on validation/test, and
    never recomputed per query)."""
    thresholds: dict[str, dict[str, float] | None] = {}
    for vehicle_type in VEHICLE_CATEGORIES:
        values = train_df.loc[train_df["vehicle_type"] == vehicle_type, TARGET_COLUMN].dropna()
        if values.empty:
            thresholds[vehicle_type] = None
            continue
        thresholds[vehicle_type] = {f"q{int(q * 100)}": float(values.quantile(q)) for q in quantiles}
    return thresholds


def assign_band(value: float, thresholds: dict[str, float] | None) -> str | None:
    if thresholds is None or value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if value <= thresholds["q25"]:
        return "Low"
    if value <= thresholds["q50"]:
        return "Moderate"
    if value <= thresholds["q75"]:
        return "High"
    return "Very High"


def _plain_language_phrase(feature: str, vehicle_type: str) -> str | None:
    template = PLAIN_LANGUAGE_TEMPLATES.get(feature)
    if template is None:
        return None
    return template.format(vt=vehicle_type.lower())


def select_top_factors(
    contributions: list[dict], vehicle_type: str, n_positive: int, n_negative: int,
) -> tuple[list[dict], list[dict]]:
    """Filters DEV-010's aggregated `contributions` (already collapsed
    one-hot vehicle_type, sorted descending) down to plain-language-mappable,
    non-constant factors, then splits into the strongest positive and
    strongest negative - never inventing a factor not present in the real
    SHAP output (Business Rule)."""
    named = []
    for c in contributions:
        if c["feature"] == "vehicle_type":
            continue  # constant within one ranking call - see module docstring
        phrase = _plain_language_phrase(c["feature"], vehicle_type)
        if phrase is None:
            continue
        named.append({**c, "plain_language": phrase})

    positive = [c for c in named if c["shap_value"] > 0][:n_positive]
    negative = sorted((c for c in named if c["shap_value"] < 0), key=lambda c: c["shap_value"])[:n_negative]
    return positive, negative


def _join_phrases(phrases: list[str]) -> str:
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def build_recommendation_sentence(
    district: str, vehicle_type: str, period: int, band: str,
    positive: list[dict], negative: list[dict], disclaimer: str,
) -> str:
    """Section 18.1 template structure: category + period -> district ->
    band -> plain-language SHAP factors -> limitation statement (the exact
    Appendix C.3 disclaimer - see module docstring)."""
    sentence = (
        f"For {vehicle_type.lower()} mechanics in {period}, {district} is ranked as a "
        f"{band.lower()}-opportunity district."
    )
    if positive:
        sentence += f" The main positive factors are {_join_phrases([p['plain_language'] for p in positive])}."
    if negative:
        sentence += f" This is partly offset by {_join_phrases([n['plain_language'] for n in negative])}."
    return sentence + " " + disclaimer


@dataclass
class RankingEngine:
    model: object
    encoder: object
    metadata: dict
    explainer: object
    frozen_df: pd.DataFrame
    band_thresholds: dict
    config: dict
    canonical_districts: list[str]

    @classmethod
    def load(
        cls,
        models_dir: Path = MODELS_DIR,
        frozen_csv: Path = FROZEN_CSV,
        ranking_config_path: Path = RANKING_CONFIG_YAML,
        district_lookup_path: Path = DISTRICT_LOOKUP_CSV,
    ) -> "RankingEngine":
        model, encoder, metadata = load_model(models_dir)
        frozen_df = pd.read_csv(frozen_csv)
        explainer = build_explainer(model)

        with open(ranking_config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        config["disclaimer"] = " ".join(config["disclaimer"].split())  # normalize YAML folded-scalar whitespace

        train_df = frozen_df[frozen_df["split"] == "train"]
        band_thresholds = compute_band_thresholds(train_df, config["band_quantiles"])
        canonical_districts = load_canonical_districts(district_lookup_path)

        return cls(model, encoder, metadata, explainer, frozen_df, band_thresholds, config, canonical_districts)

    def rank(self, vehicle_type: str, period: int, top_n: int | None = None) -> dict:
        """Steps 1 (category/period already resolved) through 6."""
        if vehicle_type not in VEHICLE_CATEGORIES:
            raise ValueError(f"vehicle_type must be one of {VEHICLE_CATEGORIES}, got {vehicle_type!r}")
        top_n = top_n or self.config["top_n"]
        disclaimer = self.config["disclaimer"]

        feature_year = period - 1
        eligible = self.frozen_df[
            (self.frozen_df["vehicle_type"] == vehicle_type) & (self.frozen_df["year"] == feature_year)
        ].reset_index(drop=True)

        if eligible.empty:
            return {
                "vehicle_type": vehicle_type, "period": period, "status": STATUS_NO_DATA,
                "message": (
                    f"No {vehicle_type} data is available to predict {period} - this period is "
                    "outside the frozen dataset's real coverage."
                ),
                "excluded_districts": self.canonical_districts,
                "ranked_districts": [], "top_n": [], "disclaimer": disclaimer,
            }

        excluded_districts = sorted(set(self.canonical_districts) - set(eligible["district"]))

        # Step 2: generate the model prediction for each eligible district.
        X = build_feature_matrix(eligible, self.metadata["active_numeric_features"], self.encoder)
        eligible = eligible.assign(predicted_value=self.model.predict(X))

        # Step 4: opportunity bands (before sorting - band doesn't depend on rank).
        thresholds = self.band_thresholds.get(vehicle_type)
        eligible["opportunity_band"] = eligible["predicted_value"].apply(lambda v: assign_band(v, thresholds))

        # Step 3: sort descending, deterministic alphabetical tie-break (Edge Case).
        eligible = eligible.sort_values(["predicted_value", "district"], ascending=[False, True]).reset_index(drop=True)
        eligible["rank"] = eligible.index + 1

        ranked_districts = [
            {
                "rank": int(row["rank"]),
                "district": row["district"],
                "predicted_value": float(row["predicted_value"]),
                "opportunity_band": row["opportunity_band"],
                "data_quality_flag": _clean(row.get("data_quality_flag")),
                "target_data_quality_flag": _clean(row.get("target_data_quality_flag")),
                "actual_target_value": _clean(row.get(TARGET_COLUMN)),
            }
            for _, row in eligible.iterrows()
        ]

        # Step 5 + 6: SHAP-explained recommendations for the top-N only.
        top_rows = eligible.head(top_n).reset_index(drop=True)
        explanations = explain_rows(top_rows, self.model, self.encoder, self.explainer, self.metadata["active_numeric_features"])
        top_n_output = [
            self._build_recommendation(top_rows.loc[i], explanations[i], vehicle_type, period, disclaimer)
            for i in range(len(top_rows))
        ]

        return {
            "vehicle_type": vehicle_type,
            "period": period,
            "status": STATUS_OK,
            "message": None,
            "excluded_districts": excluded_districts,
            # Section 26.3 / Validation: ranking table AND map source from this
            # one list - never recomputed separately per panel.
            "ranked_districts": ranked_districts,
            "top_n": top_n_output,
            "disclaimer": disclaimer,
        }

    def _build_recommendation(self, row: pd.Series, explanation: dict, vehicle_type: str, period: int, disclaimer: str) -> dict:
        positive, negative = select_top_factors(
            explanation["contributions"], vehicle_type,
            self.config["n_positive_factors"], self.config["n_negative_factors"],
        )
        sentence = build_recommendation_sentence(
            row["district"], vehicle_type, period, row["opportunity_band"], positive, negative, disclaimer,
        )
        return {
            "rank": int(row["rank"]),
            "district": row["district"],
            "vehicle_type": vehicle_type,
            "period": period,
            "predicted_value": float(row["predicted_value"]),
            "opportunity_band": row["opportunity_band"],
            "positive_factors": positive,
            "negative_factors": negative,
            "recommendation_sentence": sentence,
            "shap_note": EXPLANATION_TYPE_NOTE,
            "disclaimer": disclaimer,
            "data_quality_flag": _clean(row.get("data_quality_flag")),
            "target_data_quality_flag": _clean(row.get("target_data_quality_flag")),
        }

    def rank_from_query(self, sbert_router: SBERTRouter, query: str, period: int, top_n: int | None = None) -> dict:
        """Section 16.1 steps 3-4 hand-off: SBERT only ever selects which
        category to rank - it never predicts or explains anything itself
        (Business Rule)."""
        route_result = sbert_router.route(query)
        if route_result.status != STATUS_CONFIDENT:
            return {
                "vehicle_type": None, "period": period, "status": route_result.status,
                "message": route_result.message,
                "sbert_similarity_scores": route_result.similarity_scores,
                "excluded_districts": [], "ranked_districts": [], "top_n": [],
                "disclaimer": self.config["disclaimer"],
            }

        result = self.rank(route_result.matched_category, period, top_n)
        result["matched_via_query"] = query
        result["sbert_similarity_scores"] = route_result.similarity_scores
        return result


def run(models_dir: Path = MODELS_DIR, frozen_csv: Path = FROZEN_CSV) -> dict:
    logging.basicConfig(level=logging.INFO)

    engine = RankingEngine.load(models_dir=models_dir, frozen_csv=frozen_csv)

    output = {"generated_date": date.today().isoformat(), "dataset_version": engine.metadata.get("dataset_version"), "band_thresholds": engine.band_thresholds}
    BAND_THRESHOLDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(BAND_THRESHOLDS_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    logger.info("Opportunity band thresholds (per vehicle_type, train-split quartiles): %s", engine.band_thresholds)
    return output


if __name__ == "__main__":
    run()
