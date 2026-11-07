"""Tests for the Dataset v2 recommendation engine and the engine switch.

Expected values are recalculated separately from the dataset CSV and the saved
evaluation outputs, not taken from the engine. Nothing here retrains a model or
reruns the final evaluation: those outputs are only read.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy)

import numpy as np
import pandas as pd
import pytest
import yaml

from src.recommendation import active_engine
from src.recommendation.fleet_opportunity_v2 import (
    RECOMMENDATION_CONFIG_YAML,
    REPO_ROOT,
    FleetDataError,
    FleetOpportunityEngine,
    assign_band,
    compute_band_thresholds,
    ordinal,
    rank_districts,
)

DATASET = REPO_ROOT / "data" / "processed" / "v2" / "modelling_dataset_v2.csv"
REGISTER = REPO_ROOT / "data" / "corrections" / "source_anomalies_v2.csv"
BASELINE_PREDICTIONS = REPO_ROOT / "reports" / "baseline_v2" / "predictions.csv"
FINAL_PREDICTIONS = REPO_ROOT / "reports" / "final_evaluation_v2" / "predictions.csv"
FINAL_METRICS = REPO_ROOT / "reports" / "final_evaluation_v2" / "metrics_final.csv"
DATASET_REPORT = REPO_ROOT / "reports" / "dataset_v2" / "dataset_v2_report.md"

VEHICLE_TYPES = ["Motorcycle", "Car", "Three-wheeler"]
PERIODS = [2020, 2021, 2022, 2023, 2024]
BANDS = ["Low", "Moderate", "High", "Very High"]
DISCLAIMER = (
    "Predictions are based on available historical and proxy data. They indicate relative "
    "service opportunity and do not guarantee customer numbers, employment or income."
)

pytestmark = pytest.mark.skipif(not DATASET.exists(), reason="Dataset v2 not present locally")


@pytest.fixture(scope="module")
def engine():
    return FleetOpportunityEngine.load()


@pytest.fixture(scope="module")
def data():
    return pd.read_csv(DATASET)


def _by_district(result):
    return {e["district"]: e for e in result["ranked_districts"]}


def _reported(data, vehicle_type, year):
    rows = data[(data.vehicle_type == vehicle_type) & (data.year == year) & data.licence_count.notna()]
    return rows.set_index("district")


# --- Ranking accuracy ---------------------------------------------------------

@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
@pytest.mark.parametrize("period", PERIODS)
def test_ranks_counts_and_shares_match_the_dataset(engine, data, vehicle_type, period):
    rows = _reported(data, vehicle_type, period - 1)
    expected_rank = rows.sort_index().licence_count.rank(ascending=False, method="first").astype(int)
    expected_share = rows.licence_count / rows.licence_count.sum() * 100

    result = engine.rank(vehicle_type, period, top_n=25)
    assert result["status"] == "ok"
    assert len(result["ranked_districts"]) == len(rows)
    for entry in result["ranked_districts"]:
        assert entry["rank"] == expected_rank[entry["district"]]
        assert entry["licence_count"] == rows.licence_count[entry["district"]]
        assert entry["share_pct"] == pytest.approx(expected_share[entry["district"]])
    assert sum(e["share_pct"] for e in result["ranked_districts"]) == pytest.approx(100)


def test_vehicle_types_are_ranked_separately(engine):
    top = {vt: engine.rank(vt, 2024)["top_n"][0]["district"] for vt in VEHICLE_TYPES}
    assert top == {"Motorcycle": "Kurunegala", "Car": "Colombo", "Three-wheeler": "Gampaha"}


def test_known_2023_values(engine):
    motorcycles = _by_district(engine.rank("Motorcycle", 2024, top_n=25))
    assert motorcycles["Kurunegala"]["rank"] == 1 and motorcycles["Kurunegala"]["licence_count"] == 394975
    assert motorcycles["Gampaha"]["rank"] == 2 and motorcycles["Gampaha"]["licence_count"] == 366685
    assert motorcycles["Anuradhapura"]["rank"] == 5 and motorcycles["Anuradhapura"]["licence_count"] == 186540
    assert _by_district(engine.rank("Car", 2024, top_n=25))["Colombo"]["licence_count"] == 145098


def test_ties_resolve_by_district_name():
    # Made-up test input for the tie rule only, never shown as real data.
    rows = pd.DataFrame({"district": ["B", "A", "C"], "licence_count": [5.0, 5.0, 9.0]})
    assert rank_districts(rows)["district"].tolist() == ["C", "A", "B"]
    assert rank_districts(rows)["rank"].tolist() == [1, 2, 3]


def test_top_n_slices_the_same_entries(engine):
    result = engine.rank("Car", 2024, top_n=3)
    assert result["top_n"] == result["ranked_districts"][:3]
    assert len(engine.rank("Car", 2024)["top_n"]) == 5


@pytest.mark.parametrize("n, expected", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (23, "23rd"), (25, "25th")])
def test_ordinals(n, expected):
    assert ordinal(n) == expected


# --- Opportunity bands --------------------------------------------------------

@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
@pytest.mark.parametrize("period", PERIODS)
def test_bands_are_quartiles_of_that_vehicle_type_and_year(engine, data, vehicle_type, period):
    counts = _reported(data, vehicle_type, period - 1).licence_count
    q25, q50, q75 = np.percentile(counts.to_numpy(), [25, 50, 75])

    for district, entry in _by_district(engine.rank(vehicle_type, period, top_n=25)).items():
        count = counts[district]
        expected = "Low" if count <= q25 else "Moderate" if count <= q50 else "High" if count <= q75 else "Very High"
        assert entry["opportunity_band"] == expected


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_2023_band_sizes(engine, vehicle_type):
    bands = [e["opportunity_band"] for e in engine.rank(vehicle_type, 2024, top_n=25)["ranked_districts"]]
    assert {b: bands.count(b) for b in BANDS} == {"Low": 7, "Moderate": 6, "High": 6, "Very High": 6}


def test_band_boundaries_are_inclusive():
    thresholds = compute_band_thresholds(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), [0.25, 0.5, 0.75])
    assert thresholds == [2.0, 3.0, 4.0]
    assert [assign_band(v, thresholds, BANDS) for v in (2.0, 2.5, 3.0, 4.0, 4.1)] == ["Low", "Moderate", "Moderate", "High", "Very High"]


def test_bands_never_decrease_with_rank(engine):
    order = [BANDS.index(e["opportunity_band"]) for e in engine.rank("Motorcycle", 2024, top_n=25)["ranked_districts"]]
    assert order == sorted(order, reverse=True)


# --- Agreement with the approved previous-year baseline -----------------------

def test_estimates_equal_every_saved_previous_year_forecast(engine):
    """Compared with the forecasts saved by the baseline and final evaluations."""
    saved = pd.concat([pd.read_csv(BASELINE_PREDICTIONS), pd.read_csv(FINAL_PREDICTIONS)], ignore_index=True)
    assert len(saved) == 220
    results = {}
    for row in saved.itertuples():
        key = (row.vehicle_type, int(row.target_year))
        if key not in results:
            results[key] = _by_district(engine.rank(key[0], key[1], top_n=25))
        assert results[key][row.district]["predicted_value"] == row.previous_year


def test_2024_estimate_equals_the_2023_count(engine, data):
    for vehicle_type in VEHICLE_TYPES:
        counts = _reported(data, vehicle_type, 2023).licence_count
        result = engine.rank(vehicle_type, 2024, top_n=25)
        assert result["is_latest_estimate"] is True
        for entry in result["ranked_districts"]:
            assert entry["predicted_value"] == entry["licence_count"] == counts[entry["district"]]


def test_period_reads_only_the_previous_year(engine, data):
    """No value from the estimate year may feed the estimate."""
    changed = data.copy()
    changed.loc[changed.year == 2023, "licence_count"] = 1.0
    other = FleetOpportunityEngine(changed, engine.config, engine.metadata, engine.canonical_districts, engine.flag_reasons)
    assert other.rank("Car", 2023, top_n=25)["ranked_districts"][0]["licence_count"] == engine.rank("Car", 2023, top_n=25)["ranked_districts"][0]["licence_count"]


def test_past_actual_is_reported_as_history_only(engine, data):
    entry = _by_district(engine.rank("Car", 2023, top_n=25))["Colombo"]
    actual = _reported(data, "Car", 2023).licence_count["Colombo"]
    assert entry["actual_target_value"] == actual
    assert f"{actual:,.0f}" in " ".join(entry["explanation_facts"])
    assert _by_district(engine.rank("Car", 2024, top_n=25))["Colombo"]["actual_target_value"] is None


def test_saved_error_summary_matches_the_config():
    config = yaml.safe_load(RECOMMENDATION_CONFIG_YAML.read_text(encoding="utf-8"))
    saved = pd.concat([pd.read_csv(BASELINE_PREDICTIONS), pd.read_csv(FINAL_PREDICTIONS)], ignore_index=True)
    ape = (saved.previous_year - saved.target_licence_count).abs() / saved.target_licence_count * 100
    for vehicle_type, expected in config["typical_change"].items():
        values = ape[saved.vehicle_type == vehicle_type]
        assert round(values.median(), 1) == expected["median_pct"]
        assert round(values.quantile(0.9), 1) == expected["p90_pct"]

    metrics = pd.read_csv(FINAL_METRICS)
    row = metrics[(metrics.scenario == "all_rows") & (metrics.group == "All") & (metrics.model == "previous_year")].iloc[0]
    assert round(row.mae) == config["final_evaluation"]["mae"]
    assert round(row.mape, 2) == config["final_evaluation"]["mape_pct"]
    assert round(row.median_ape, 2) == config["final_evaluation"]["median_ape_pct"]
    assert "57-85%" in DATASET_REPORT.read_text(encoding="utf-8") and "57-85%" in config["coverage_note"]


# --- Historical change --------------------------------------------------------

def test_change_is_calculated_from_consecutive_years(engine, data):
    now = _reported(data, "Motorcycle", 2023).licence_count
    before = _reported(data, "Motorcycle", 2022).licence_count
    for district, entry in _by_district(engine.rank("Motorcycle", 2024, top_n=25)).items():
        assert entry["previous_count"] == before[district]
        assert entry["change_pct"] == pytest.approx((now[district] / before[district] - 1) * 100)


def test_change_is_empty_when_the_previous_count_is_missing(engine):
    entry = _by_district(engine.rank("Motorcycle", 2023, top_n=25))["Jaffna"]  # 2021 count is missing
    assert entry["previous_count"] is None and entry["change_pct"] is None
    assert any("No 2021 count is available" in fact for fact in entry["explanation_facts"])


def test_unchanged_count_is_described_as_unchanged(engine):
    entry = _by_district(engine.rank("Car", 2024, top_n=25))["Kandy"]
    assert entry["change_pct"] == 0
    assert any(fact.startswith("Unchanged from 2022.") for fact in entry["explanation_facts"])


# --- Missing values -----------------------------------------------------------

@pytest.mark.parametrize("vehicle_type, period, district", [
    ("Car", 2020, "Ampara"), ("Motorcycle", 2020, "Ampara"), ("Three-wheeler", 2020, "Ampara"), ("Motorcycle", 2022, "Jaffna"),
])
def test_missing_value_gets_no_rank_and_is_never_zero(engine, vehicle_type, period, district):
    result = engine.rank(vehicle_type, period, top_n=25)
    assert district not in _by_district(result)
    assert result["excluded_districts"] == [district]
    assert district in result["missing_message"] and "not treated as zero" in result["missing_message"]
    assert result["n_ranked"] == 24
    assert all(e["licence_count"] > 0 for e in result["ranked_districts"])


def test_complete_year_has_no_missing_message(engine):
    result = engine.rank("Motorcycle", 2024)
    assert result["excluded_districts"] == [] and result["missing_message"] is None


@pytest.mark.parametrize("period", [2019, 2025, 2030])
def test_period_outside_coverage_returns_no_data(engine, period):
    result = engine.rank("Motorcycle", period)
    assert result["status"] == "no_data"
    assert result["ranked_districts"] == [] and result["top_n"] == []
    assert result["message"] and result["disclaimer"] == DISCLAIMER


def test_unknown_vehicle_type_is_refused(engine):
    with pytest.raises(ValueError):
        engine.rank("Truck", 2024)


# --- Flags and warnings -------------------------------------------------------

EXPECTED_2023_FLAGS = {
    ("Kalutara", "Car"): "L09", ("Kandy", "Car"): "L03", ("Kilinochchi", "Car"): "L08",
    ("Kalutara", "Motorcycle"): "L09", ("Kandy", "Motorcycle"): "L03", ("Kurunegala", "Motorcycle"): "L11",
    ("Kalutara", "Three-wheeler"): "L09", ("Kandy", "Three-wheeler"): "L03", ("Mannar", "Three-wheeler"): "L16",
}


def test_exactly_the_nine_flagged_2023_values_warn(engine):
    found = {}
    for vehicle_type in VEHICLE_TYPES:
        for entry in engine.rank(vehicle_type, 2024, top_n=25)["ranked_districts"]:
            if entry["reliability"] == "Uncertain value":
                found[(entry["district"], vehicle_type)] = ";".join(entry["flag_ids"])
    assert found == EXPECTED_2023_FLAGS


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
@pytest.mark.parametrize("period", PERIODS)
def test_warning_matches_the_dataset_flag_and_register_reason(engine, data, vehicle_type, period):
    rows = _reported(data, vehicle_type, period - 1)
    register = pd.read_csv(REGISTER).set_index("anomaly_id")["finding"]

    for district, entry in _by_district(engine.rank(vehicle_type, period, top_n=25)).items():
        flagged = bool(rows.licence_flagged[district])
        assert (entry["reliability"] == "Uncertain value") == flagged
        assert bool(entry["flag_warning"]) == flagged
        if flagged:
            assert entry["flag_warning"].startswith("Uncertain value: ")
            assert entry["flag_warning"] in entry["explanation_facts"]
            assert "flagged as uncertain" in entry["recommendation_sentence"]
            assert entry["flag_ids"]
            for flag_id in entry["flag_ids"]:
                assert register[flag_id] in entry["flag_warning"]
        else:
            assert entry["flag_ids"] == [] and entry["data_quality_flag"] is None
            assert "flagged as uncertain" not in entry["recommendation_sentence"]


def test_kurunegala_warning_states_its_2022_rank(engine):
    entry = _by_district(engine.rank("Motorcycle", 2024, top_n=25))["Kurunegala"]
    assert entry["rank"] == 1
    assert "On the 2022 count it ranked 2nd." in entry["flag_warning"]


def test_change_caution_follows_the_dataset_flag(engine, data):
    rows = _reported(data, "Car", 2023)
    for district, entry in _by_district(engine.rank("Car", 2024, top_n=25)).items():
        caution = bool(rows.features_use_flagged_licence[district])
        assert entry["change_caution"] == caution
        assert any("treat this change with caution" in fact for fact in entry["explanation_facts"]) == caution


# --- Explanations and wording -------------------------------------------------

def test_rule_based_sentence_uses_real_values(engine):
    entry = _by_district(engine.rank("Motorcycle", 2024, top_n=25))["Anuradhapura"]
    assert entry["recommendation_sentence"] == (
        "For motorcycle mechanics, Anuradhapura had 186,540 licensed motorcycles in 2023, ranking 5th of 25 "
        "districts and in the Very High band. This describes fleet size, not mechanic work."
    )


def test_every_ranked_district_has_explanation_and_disclaimer(engine):
    for vehicle_type in VEHICLE_TYPES:
        for entry in engine.rank(vehicle_type, 2024, top_n=25)["top_n"]:
            assert len(entry["explanation_facts"]) >= 4
            assert entry["recommendation_sentence"] and entry["explanation_note"]
            assert entry["disclaimer"] == DISCLAIMER
            assert entry["positive_factors"] == [] and entry["negative_factors"] == [] and entry["shap_note"] is None


def test_disclaimer_is_exact_and_notes_state_the_limits(engine):
    result = engine.rank("Motorcycle", 2024)
    assert result["disclaimer"] == DISCLAIMER
    assert "relative licensed-vehicle fleet size" in result["meaning_note"]
    assert "does not represent actual mechanic jobs or measured service demand" in result["meaning_note"]
    assert "did not beat last year's value" in result["evidence_note"]


def test_output_contains_no_invented_scores_or_unsupported_claims(engine):
    """The only allowed mentions are the fixed notes and the source flag reasons."""
    for vehicle_type in VEHICLE_TYPES:
        result = engine.rank(vehicle_type, 2024, top_n=25)
        assert not {k for k in result["ranked_districts"][0] if any(w in k for w in ("demand", "score", "job", "customer", "income"))}
        for entry in result["ranked_districts"]:
            text = " ".join(entry["explanation_facts"] + [entry["recommendation_sentence"]]).lower()
            for word in ("demand", "customers", "income", "guarantee", "best district", "xgboost", "shap"):
                assert word not in text


def test_uncertainty_note_uses_the_configured_change(engine):
    assert engine.rank("Motorcycle", 2024)["uncertainty_note"] == (
        "Motorcycle counts typically change about 3% a year, but 1 in 10 changed by more than 13%."
    )


def test_period_labels(engine):
    assert engine.available_periods() == PERIODS
    assert engine.period_label(2024) == "2023 data (2024 estimate)"
    assert engine.period_label(2021) == "2020 data (history)"


def test_method_summary_keeps_project_title_and_evaluation(engine):
    summary = dict(engine.method_summary())
    assert summary["Project"] == "Mechanic Service Demand Opportunity Prediction and Recommendation System"
    assert summary["Method"] == "Previous-year value (no machine-learning model)"
    assert summary["Data cut-off"] == "2023"
    assert "2,729" in summary["Final evaluation, target year 2023"]


def test_history_keeps_gaps_and_flags(engine):
    jaffna = engine.history("Jaffna", "Motorcycle").set_index("year")
    assert list(jaffna.index) == [2019, 2020, 2021, 2022, 2023]
    assert pd.isna(jaffna.licence_count[2021])
    assert bool(engine.history("Kurunegala", "Motorcycle").set_index("year").licence_flagged[2023])


def test_output_keeps_every_v1_key():
    """The panels written for RankingEngine read these keys."""
    entry_keys = {
        "rank", "district", "predicted_value", "opportunity_band", "data_quality_flag", "target_data_quality_flag",
        "actual_target_value", "vehicle_type", "period", "positive_factors", "negative_factors",
        "recommendation_sentence", "shap_note", "disclaimer",
    }
    result_keys = {"vehicle_type", "period", "status", "message", "excluded_districts", "ranked_districts", "top_n", "disclaimer"}
    result = FleetOpportunityEngine.load().rank("Car", 2024)
    assert result_keys <= set(result)
    assert entry_keys <= set(result["top_n"][0])
    assert result_keys <= set(FleetOpportunityEngine.load().rank("Car", 2030))


class _Route:
    def __init__(self, status, category=None):
        self.status, self.matched_category, self.message, self.similarity_scores = status, category, "fallback", {}


class _Router:
    def __init__(self, route):
        self._route = route

    def route(self, query):
        return self._route


def test_query_routing_only_selects_the_category(engine):
    from src.nlp.sbert_router import STATUS_CONFIDENT

    result = engine.rank_from_query(_Router(_Route(STATUS_CONFIDENT, "Car")), "I fix cars", 2024)
    direct = engine.rank("Car", 2024)
    assert result["vehicle_type"] == "Car" and result["top_n"] == direct["top_n"]


def test_unconfident_query_returns_no_ranking(engine):
    result = engine.rank_from_query(_Router(_Route("unsupported")), "what is the weather", 2024)
    assert result["vehicle_type"] is None and result["ranked_districts"] == []
    assert result["message"] == "fallback" and result["disclaimer"] == DISCLAIMER


# --- Safe loading -------------------------------------------------------------

def _temp_config(tmp_path, **changes):
    config = yaml.safe_load(RECOMMENDATION_CONFIG_YAML.read_text(encoding="utf-8"))
    config.update(changes)
    path = tmp_path / "recommendation_v2.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_dataset_hash_mismatch_is_refused(tmp_path):
    with pytest.raises(FleetDataError, match="does not match"):
        FleetOpportunityEngine.load(config_path=_temp_config(tmp_path, dataset_sha256="0" * 64))


def test_missing_dataset_is_refused(tmp_path):
    with pytest.raises(FleetDataError, match="not found"):
        FleetOpportunityEngine.load(config_path=_temp_config(tmp_path, dataset_path="data/absent.csv"))


def test_flag_without_a_register_reason_is_refused(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy(DATASET, tmp_path / "data" / "d.csv")
    register = pd.read_csv(REGISTER)
    register[register.anomaly_id != "L11"].to_csv(tmp_path / "data" / "r.csv", index=False)
    path = _temp_config(tmp_path, dataset_path="data/d.csv", anomaly_register="data/r.csv")
    with pytest.raises(FleetDataError, match="L11"):
        FleetOpportunityEngine.load(config_path=path, repo_root=tmp_path)


def test_engine_changes_nothing(engine):
    before_file = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    before_df = engine.frozen_df.copy()
    for vehicle_type in VEHICLE_TYPES:
        for period in PERIODS:
            engine.rank(vehicle_type, period, top_n=25)
    pd.testing.assert_frame_equal(engine.frozen_df, before_df)
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == before_file


# --- Engine switch ------------------------------------------------------------

def test_v1_is_the_committed_default():
    """Change this only when the project author approves making v2 the default."""
    assert active_engine.get_active_engine_name() == "v1"


@pytest.mark.parametrize("value", ["v3", "", None, "V2"])
def test_unknown_switch_value_is_refused(tmp_path, value):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"active_engine": value}), encoding="utf-8")
    with pytest.raises(ValueError):
        active_engine.get_active_engine_name(path)


@pytest.mark.parametrize("value", ["v1", "v2"])
def test_switch_reads_valid_values(tmp_path, value):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"active_engine": value}), encoding="utf-8")
    assert active_engine.get_active_engine_name(path) == value


def test_switch_selects_the_v1_engine(monkeypatch):
    from src.recommendation import ranking_engine

    monkeypatch.setattr(active_engine, "get_active_engine_name", lambda *a, **k: "v1")
    monkeypatch.setattr(ranking_engine.RankingEngine, "load", classmethod(lambda cls: "v1 engine"))
    assert active_engine.load_active_engine() == "v1 engine"


def test_v2_mode_loads_no_model_or_v1_engine():
    """A separate process shows exactly what v2 mode imports."""
    code = (
        "import sys\n"
        "from unittest.mock import patch\n"
        "from src.recommendation import active_engine as a\n"
        "with patch.object(a, 'get_active_engine_name', return_value='v2'):\n"
        "    engine = a.load_active_engine()\n"
        "assert a.is_fleet_engine(engine)\n"
        "engine.rank('Motorcycle', 2024, top_n=25)\n"
        "banned = ['xgboost', 'shap', 'tensorflow', 'src.recommendation.ranking_engine', 'src.models.xgboost_model']\n"
        "assert not [m for m in banned if m in sys.modules], [m for m in banned if m in sys.modules]\n"
        "assert not hasattr(engine, 'model')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-800:]


def test_import_boundaries_hold():
    """`src/` and `dashboard/` never import `app/`, and only insights.py imports `src/`."""
    for folder in ("src", "dashboard"):
        for path in (REPO_ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "from app" not in text and "import app." not in text, path

    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path.name != "insights.py" or path.parent.name != "routes":
            text = path.read_text(encoding="utf-8")
            assert "from src" not in text and "import src" not in text, path
