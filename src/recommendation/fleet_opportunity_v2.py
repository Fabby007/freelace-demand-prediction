"""Vehicle-Fleet Service Opportunity engine for Dataset v2 (REF-009 ADR-042, ADR-043).

Read-only. It loads no model and writes nothing. The estimate for a year equals
the previous year's revenue-licence count, the method selected by the final
evaluation. Districts are ranked within one vehicle type by that count, with
quartile bands for the same vehicle type and year.

`rank()` returns the same keys as `RankingEngine.rank()`, plus fleet-specific
ones, so both engines can feed the same panels. `period` also has the same
meaning: the estimate year, read from data for `period - 1`.

The output describes relative licensed-vehicle fleet size. It does not measure
mechanic jobs or service demand, so it contains no demand score or job figure.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOMMENDATION_CONFIG_YAML = REPO_ROOT / "configs" / "recommendation_v2.yaml"
RANKING_CONFIG_YAML = REPO_ROOT / "configs" / "ranking_config.yaml"
DISTRICT_LOOKUP_CSV = REPO_ROOT / "configs" / "district_lookup.csv"

INDICATOR_TYPE = "fleet_opportunity_v2"
STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"
RELIABILITY_REPORTED = "Reported"
RELIABILITY_UNCERTAIN = "Uncertain value"

BAND_DESCRIPTIONS = {
    "Low": "the lowest quarter",
    "Moderate": "the second-lowest quarter",
    "High": "the second-highest quarter",
    "Very High": "the highest quarter",
}


class FleetDataError(RuntimeError):
    """The dataset or flag register failed a check, so no results may be shown."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalise_text(config: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        config[key] = " ".join(config[key].split())


def ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def split_flag_ids(value) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def compute_band_thresholds(counts: pd.Series, quantiles: list[float]) -> list[float]:
    """Quartiles of one vehicle type's counts in one data year (ADR-043)."""
    return [float(counts.quantile(q)) for q in quantiles]


def assign_band(count: float, thresholds: list[float], labels: list[str]) -> str:
    for threshold, label in zip(thresholds, labels):
        if count <= threshold:
            return label
    return labels[-1]


def rank_districts(rows: pd.DataFrame) -> pd.DataFrame:
    """Highest count first. Ties resolve by district name, A to Z."""
    ordered = rows.sort_values(["licence_count", "district"], ascending=[False, True]).reset_index(drop=True)
    return ordered.assign(rank=ordered.index + 1)


@dataclass
class FleetOpportunityEngine:
    frozen_df: pd.DataFrame
    config: dict
    metadata: dict
    canonical_districts: list[str]
    flag_reasons: dict[str, str]

    indicator_type: ClassVar[str] = INDICATOR_TYPE

    @classmethod
    def load(
        cls,
        config_path: Path = RECOMMENDATION_CONFIG_YAML,
        ranking_config_path: Path = RANKING_CONFIG_YAML,
        district_lookup_path: Path = DISTRICT_LOOKUP_CSV,
        repo_root: Path = REPO_ROOT,
    ) -> "FleetOpportunityEngine":
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        with open(ranking_config_path, encoding="utf-8") as f:
            ranking = yaml.safe_load(f)
        # One source for shared rules, including the verbatim Appendix C.3 disclaimer.
        for key in ("disclaimer", "band_quantiles", "band_labels", "top_n"):
            config[key] = ranking[key]
        _normalise_text(config, ("disclaimer", "meaning_note", "evidence_note", "position_note", "explanation_note"))

        dataset_path = repo_root / config["dataset_path"]
        if not dataset_path.exists():
            raise FleetDataError(f"Dataset v2 not found: {config['dataset_path']}")
        if _sha256(dataset_path) != config["dataset_sha256"]:
            raise FleetDataError("Dataset v2 does not match the approved version, so it will not be used.")

        frozen_df = pd.read_csv(dataset_path)
        register = pd.read_csv(repo_root / config["anomaly_register"]).set_index("anomaly_id")
        used_ids = {i for value in frozen_df["licence_flag_ids"].dropna() for i in split_flag_ids(value)}
        unknown = sorted(used_ids - set(register.index))
        if unknown:
            raise FleetDataError(f"Flags have no reason in the anomaly register: {unknown}")
        flag_reasons = {i: str(register.loc[i, "finding"]) for i in used_ids}

        canonical_districts = sorted(pd.read_csv(district_lookup_path)["canonical_name"].unique())
        unknown_districts = sorted(set(frozen_df["district"]) - set(canonical_districts))
        if unknown_districts:
            raise FleetDataError(f"Unknown districts in Dataset v2: {unknown_districts}")

        latest_year = int(frozen_df.dropna(subset=["licence_count"])["year"].max())
        metadata = {
            "dataset_version": config["dataset_version"],
            "method": config["method_label"],
            "data_cutoff_year": latest_year,
            "interface_label": config["interface_label"],
        }
        return cls(frozen_df, config, metadata, canonical_districts, flag_reasons)

    @property
    def latest_year(self) -> int:
        return self.metadata["data_cutoff_year"]

    def available_periods(self) -> list[int]:
        return [int(y) + 1 for y in sorted(self.frozen_df["year"].unique())]

    def period_label(self, period: int) -> str:
        """Selector text. Only the latest data year gives an unobserved estimate."""
        if period == self.latest_year + 1:
            return f"{period - 1} data ({period} estimate)"
        return f"{period - 1} data (history)"

    def method_summary(self) -> list[tuple[str, str]]:
        """Plain-language method and evidence rows, shared by both interfaces."""
        evaluation = self.config["final_evaluation"]
        return [
            ("Project", self.config["official_project_title"]),
            ("Method", self.config["method_label"]),
            ("Dataset version", self.config["dataset_version"]),
            ("Data cut-off", str(self.latest_year)),
            (
                f"Final evaluation, target year {evaluation['target_year']}",
                f"Average error {evaluation['mae']:,} vehicles (MAE), {evaluation['mape_pct']:.2f}% (MAPE), "
                f"median {evaluation['median_ape_pct']:.2f}%",
            ),
            ("Licence coverage", self.config["coverage_note"]),
        ]

    def history(self, district: str, vehicle_type: str) -> pd.DataFrame:
        """Published licence counts for one series. Missing years stay missing."""
        df = self.frozen_df
        rows = df[(df["district"] == district) & (df["vehicle_type"] == vehicle_type)].sort_values("year")
        return rows[["year", "licence_count", "licence_flagged", "licence_flag_ids"]].reset_index(drop=True)

    def _uncertainty_note(self, vehicle_type: str) -> str:
        change = self.config["typical_change"][vehicle_type]
        return (
            f"{vehicle_type} counts typically change about {change['median_pct']:.0f}% a year, "
            f"but 1 in 10 changed by more than {change['p90_pct']:.0f}%."
        )

    def _no_data(self, vehicle_type: str, period: int) -> dict:
        return {
            "indicator_type": INDICATOR_TYPE, "vehicle_type": vehicle_type, "period": period,
            "reference_year": period - 1, "status": STATUS_NO_DATA,
            "message": f"No {vehicle_type} licence counts are available for {period - 1}.",
            "excluded_districts": self.canonical_districts, "missing_message": None,
            "ranked_districts": [], "top_n": [], "disclaimer": self.config["disclaimer"],
        }

    def _flag_warning(self, row: pd.Series, reference_year: int, prior_ranks: dict, reasons: list[str]) -> str | None:
        if not reasons:
            return None
        warning = "Uncertain value: " + " ".join(reasons)
        prior = prior_ranks.get(row["district"])
        if prior is not None:
            warning += f" On the {reference_year - 1} count it ranked {ordinal(prior)}."
        return warning

    def _change_fact(self, row: pd.Series, change_pct: float | None, reference_year: int) -> str:
        if change_pct is None:
            return f"No {reference_year - 1} count is available to compare."
        if row["licence_count"] == row["licence_lag_1"]:
            fact = f"Unchanged from {reference_year - 1}."
        else:
            fact = f"{'Up' if change_pct > 0 else 'Down'} {abs(change_pct):.1f}% from {reference_year - 1}."
        fact += " This is history and is not used in the rank."
        if bool(row["features_use_flagged_licence"]):
            fact += " Recent counts include a flagged value, so treat this change with caution."
        return fact

    def _entry(self, row: pd.Series, vehicle_type: str, period: int, n_ranked: int, total: float, prior_ranks: dict, band: str) -> dict:
        reference_year = period - 1
        plural = self.config["vehicle_categories"][vehicle_type]
        count = float(row["licence_count"])
        share_pct = count / total * 100
        lag = row["licence_lag_1"]
        change_pct = None if pd.isna(lag) else (count / float(lag) - 1) * 100
        flag_ids = split_flag_ids(row["licence_flag_ids"])
        reasons = [self.flag_reasons[i] for i in flag_ids]
        flagged = bool(row["licence_flagged"])
        rank = int(row["rank"])
        actual = None if pd.isna(row["target_licence_count"]) else float(row["target_licence_count"])

        facts = [
            f"{count:,.0f} licensed {plural} in {reference_year}, ranking {ordinal(rank)} of {n_ranked} reporting districts.",
            f"{share_pct:.1f}% of licensed {plural} across reporting districts.",
            f"{band} band: {BAND_DESCRIPTIONS[band]} of reporting districts for {plural} in {reference_year}.",
            self._change_fact(row, change_pct, reference_year),
        ]
        if reference_year == self.latest_year:
            facts.append(f"The {period} estimate equals this count, using the previous-year method.")
        elif actual is not None:
            facts.append(f"The previous-year estimate for {period} was this count. The reported {period} count was {actual:,.0f}.")
        warning = self._flag_warning(row, reference_year, prior_ranks, reasons)
        if warning:
            facts.append(warning)

        sentence = (
            f"For {vehicle_type.lower()} mechanics, {row['district']} had {count:,.0f} licensed {plural} in "
            f"{reference_year}, ranking {ordinal(rank)} of {n_ranked} districts and in the {band} band. "
            "This describes fleet size, not mechanic work."
        )
        if flagged:
            sentence += " This count is flagged as uncertain."

        return {
            "rank": rank,
            "district": row["district"],
            "vehicle_type": vehicle_type,
            "period": period,
            "reference_year": reference_year,
            "predicted_value": count,  # the previous-year estimate: the same number as licence_count
            "licence_count": count,
            "share_pct": share_pct,
            "opportunity_band": band,
            "previous_count": None if pd.isna(lag) else float(lag),
            "change_pct": change_pct,
            "change_caution": bool(row["features_use_flagged_licence"]),
            "reliability": RELIABILITY_UNCERTAIN if flagged else RELIABILITY_REPORTED,
            "flag_ids": flag_ids,
            "flag_reasons": reasons,
            "flag_warning": warning,
            "data_quality_flag": " ".join(reasons) if reasons else None,
            "target_data_quality_flag": None,
            "actual_target_value": actual,
            "positive_factors": [],
            "negative_factors": [],
            "explanation_facts": facts,
            "recommendation_sentence": sentence,
            "explanation_note": self.config["explanation_note"],
            "shap_note": None,
            "disclaimer": self.config["disclaimer"],
        }

    def rank(self, vehicle_type: str, period: int, top_n: int | None = None) -> dict:
        if vehicle_type not in self.config["vehicle_categories"]:
            raise ValueError(f"vehicle_type must be one of {list(self.config['vehicle_categories'])}, got {vehicle_type!r}")
        top_n = top_n or self.config["top_n"]
        reference_year = period - 1

        series = self.frozen_df[self.frozen_df["vehicle_type"] == vehicle_type]
        reported = series[(series["year"] == reference_year) & series["licence_count"].notna()]
        if reported.empty:
            return self._no_data(vehicle_type, period)

        ranked = rank_districts(reported)
        thresholds = compute_band_thresholds(ranked["licence_count"], self.config["band_quantiles"])
        total = float(ranked["licence_count"].sum())
        prior = series[(series["year"] == reference_year - 1) & series["licence_count"].notna()]
        prior_ranked = rank_districts(prior)
        prior_ranks = dict(zip(prior_ranked["district"], prior_ranked["rank"].astype(int)))

        entries = [
            self._entry(
                row, vehicle_type, period, len(ranked), total, prior_ranks,
                assign_band(row["licence_count"], thresholds, self.config["band_labels"]),
            )
            for _, row in ranked.iterrows()
        ]

        excluded = sorted(set(self.canonical_districts) - set(ranked["district"]))
        missing_message = None
        if excluded:
            missing_message = (
                f"No usable {reference_year} {vehicle_type.lower()} count for {', '.join(excluded)}. "
                "Not ranked, and not treated as zero."
            )

        return {
            "indicator_type": INDICATOR_TYPE,
            "vehicle_type": vehicle_type,
            "period": period,
            "reference_year": reference_year,
            "is_latest_estimate": reference_year == self.latest_year,
            "status": STATUS_OK,
            "message": None,
            "excluded_districts": excluded,
            "missing_message": missing_message,
            "n_ranked": len(ranked),
            "ranked_districts": entries,  # map, table and detail panels all read this one list
            "top_n": entries[:top_n],
            "disclaimer": self.config["disclaimer"],
            "meaning_note": self.config["meaning_note"],
            "evidence_note": self.config["evidence_note"],
            "position_note": self.config["position_note"],
            "uncertainty_note": self._uncertainty_note(vehicle_type),
        }

    def rank_from_query(self, sbert_router, query: str, period: int, top_n: int | None = None) -> dict:
        """SBERT only selects the vehicle type, exactly as in `RankingEngine`."""
        from src.nlp.sbert_router import STATUS_CONFIDENT

        route_result = sbert_router.route(query)
        if route_result.status != STATUS_CONFIDENT:
            return {
                "indicator_type": INDICATOR_TYPE, "vehicle_type": None, "period": period,
                "status": route_result.status, "message": route_result.message,
                "sbert_similarity_scores": route_result.similarity_scores,
                "excluded_districts": [], "ranked_districts": [], "top_n": [],
                "disclaimer": self.config["disclaimer"],
            }
        result = self.rank(route_result.matched_category, period, top_n)
        result["matched_via_query"] = query
        result["sbert_similarity_scores"] = route_result.similarity_scores
        return result
