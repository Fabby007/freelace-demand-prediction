"""Tests for Dataset v2: target, features, approved corrections and integrity.

Calculation tests use small artificial series that exist only to exercise the
formulas; they are not project data. Real-data tests read the v2 extraction and
write only to tmp_path.
"""
import hashlib
import json

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import numpy as np
import pandas as pd
import pytest

from src.data.extract_dcs_tables_v2 import RAW_DIR, REPO_ROOT, V2_CELLS_CSV
from src.data.extract_dcs_tables_v2 import load_config as load_extraction_config
from src.features.build_dataset_v2 import (
    ACTION_KEPT_FLAGGED,
    ACTION_SET_MISSING,
    ACTION_TOTAL_MASKED,
    STATUS_SET_MISSING,
    STATUS_VALUE,
    TARGET_AVAILABLE,
    TARGET_NO_NEXT_YEAR,
    TARGET_SET_MISSING,
    _parse_cell_list,
    add_features,
    add_target,
    build,
    build_corrections_log,
    data_dictionary_markdown,
    load_cells,
    load_config,
    load_corrections,
    run,
    verify_dataset,
)

YEARS = [2019, 2020, 2021, 2022, 2023]
V1_DATASET = REPO_ROOT / "data" / "processed" / "modelling_dataset_v1.csv"
V1_HASH_PREFIX = "1310eaead622"

needs_extraction = pytest.mark.skipif(not V2_CELLS_CSV.exists(), reason="v2 extraction output not present locally")
ENGINEERED_NOT_TARGET = [
    "licence_lag_1", "licence_lag_2", "licence_growth_log", "licence_rolling_mean_3", "licence_rolling_std_3",
    "licence_window_observations", "total_registrations_lag_1", "total_registrations_growth_log",
    "features_use_flagged_licence",
]


def _series(values, registrations=None, district="A", vehicle="Car", flags=None, statuses=None):
    registrations = registrations if registrations is not None else [100.0] * 5
    return pd.DataFrame({
        "district": district, "vehicle_type": vehicle, "year": YEARS,
        "licence_count": values,
        "licence_value_status": statuses or [STATUS_VALUE] * 5,
        "licence_flag_ids": flags or [""] * 5,
        "licence_flagged": [bool(f) for f in (flags or [""] * 5)],
        "total_registrations": registrations,
    })


@pytest.fixture(scope="module")
def config():
    return load_config()


def _engineered(frame, config):
    return add_target(add_features(frame, config), config).set_index("year")


# --- Target -------------------------------------------------------------------

def test_target_is_next_years_licences_for_the_same_series(config):
    df = _engineered(_series([10.0, 20.0, 30.0, 40.0, 50.0]), config)
    assert df.loc[2019, "target_licence_count"] == 20
    assert df.loc[2022, "target_licence_count"] == 50
    assert df.loc[2022, "target_year"] == 2023
    assert df.loc[2019, "target_status"] == TARGET_AVAILABLE


def test_latest_year_is_kept_with_no_target(config):
    df = _engineered(_series([10.0, 20.0, 30.0, 40.0, 50.0]), config)
    assert np.isnan(df.loc[2023, "target_licence_count"])
    assert df.loc[2023, "target_status"] == TARGET_NO_NEXT_YEAR
    assert df.loc[2023, "target_year"] == 2024
    assert not df.loc[2023, "has_target"]


def test_rejected_next_year_gives_a_missing_target_never_a_filled_one(config):
    statuses = [STATUS_VALUE, STATUS_VALUE, STATUS_SET_MISSING, STATUS_VALUE, STATUS_VALUE]
    df = _engineered(_series([10.0, 20.0, np.nan, 40.0, 50.0], statuses=statuses), config)
    assert np.isnan(df.loc[2020, "target_licence_count"])
    assert df.loc[2020, "target_status"] == TARGET_SET_MISSING
    assert not df.loc[2020, "has_target"]


def test_target_flag_comes_from_next_years_value(config):
    df = _engineered(_series([10.0, 20.0, 30.0, 40.0, 50.0], flags=["", "", "L99", "", ""]), config)
    assert df.loc[2020, "target_flagged"]
    assert df.loc[2020, "target_flag_ids"] == "L99"
    assert not df.loc[2021, "target_flagged"]


def test_has_target_and_level_needs_both(config):
    statuses = [STATUS_SET_MISSING] + [STATUS_VALUE] * 4
    df = _engineered(_series([np.nan, 20.0, 30.0, 40.0, 50.0], statuses=statuses), config)
    assert df.loc[2019, "has_target"]
    assert not df.loc[2019, "has_target_and_level"]
    assert df.loc[2020, "has_target_and_level"]


# --- Features: hand-computed values -------------------------------------------

def test_lags_and_log_growth(config):
    df = _engineered(_series([100.0, 110.0, 121.0, 133.0, 146.0]), config)
    assert df.loc[2021, "licence_lag_1"] == 110
    assert df.loc[2021, "licence_lag_2"] == 100
    assert df.loc[2020, "licence_growth_log"] == pytest.approx(np.log(110 / 100))
    assert np.isnan(df.loc[2019, "licence_lag_1"])
    assert np.isnan(df.loc[2020, "licence_lag_2"])
    assert np.isnan(df.loc[2019, "licence_growth_log"])


def test_rolling_statistics_include_the_latest_year(config):
    df = _engineered(_series([10.0, 20.0, 60.0, 40.0, 50.0]), config)
    assert df.loc[2021, "licence_rolling_mean_3"] == pytest.approx((10 + 20 + 60) / 3)
    assert df.loc[2021, "licence_rolling_std_3"] == pytest.approx(np.std([10, 20, 60], ddof=1))
    assert df.loc[2021, "licence_window_observations"] == 3
    assert df.loc[2020, "licence_rolling_mean_3"] == pytest.approx(15)
    assert df.loc[2020, "licence_window_observations"] == 2
    assert np.isnan(df.loc[2019, "licence_rolling_mean_3"])  # one value is below the minimum of 2


def test_missing_value_is_skipped_by_rolling_and_never_bridged_by_growth(config):
    statuses = [STATUS_VALUE, STATUS_VALUE, STATUS_SET_MISSING, STATUS_VALUE, STATUS_VALUE]
    df = _engineered(_series([100.0, 110.0, np.nan, 130.0, 140.0], statuses=statuses), config)
    assert np.isnan(df.loc[2021, "licence_growth_log"])
    assert np.isnan(df.loc[2022, "licence_growth_log"])  # no jump from 2020 to 2022
    assert np.isnan(df.loc[2022, "licence_lag_1"])
    assert df.loc[2022, "licence_lag_2"] == 110
    assert df.loc[2021, "licence_rolling_mean_3"] == pytest.approx(105)
    assert df.loc[2021, "licence_window_observations"] == 2


def test_zero_base_gives_empty_growth_not_infinity(config):
    df = _engineered(_series([0.0, 10.0, 20.0, 30.0, 40.0]), config)
    assert np.isnan(df.loc[2020, "licence_growth_log"])


def test_registration_features_stay_empty_around_an_unverified_total(config):
    df = _engineered(_series([1.0, 2.0, 3.0, 4.0, 5.0], registrations=[100.0, 50.0, np.nan, 20.0, 40.0]), config)
    assert df.loc[2020, "total_registrations_growth_log"] == pytest.approx(np.log(0.5))
    assert np.isnan(df.loc[2022, "total_registrations_lag_1"])
    assert np.isnan(df.loc[2022, "total_registrations_growth_log"])
    assert df.loc[2023, "total_registrations_growth_log"] == pytest.approx(np.log(2))


def test_flag_reaches_rows_whose_window_uses_the_flagged_value(config):
    df = _engineered(_series([1.0, 2.0, 3.0, 4.0, 5.0], flags=["", "L99", "", "", ""]), config)
    assert list(df["features_use_flagged_licence"]) == [False, True, True, True, False]


# --- No leakage ---------------------------------------------------------------

@pytest.mark.parametrize("cutoff", [2020, 2021, 2022])
def test_changing_future_years_leaves_every_earlier_feature_unchanged(config, cutoff):
    """Section 12.1: features for year t may use nothing later than t."""
    values = [100.0, 120.0, 90.0, 150.0, 130.0]
    registrations = [50.0, 30.0, 70.0, 20.0, 60.0]
    original = _engineered(_series(values, registrations), config)

    mutated_values = [v if y <= cutoff else v * 7 + 1 for y, v in zip(YEARS, values)]
    mutated_registrations = [v if y <= cutoff else v * 7 + 1 for y, v in zip(YEARS, registrations)]
    flags = ["" if y <= cutoff else "L99" for y in YEARS]
    mutated = _engineered(_series(mutated_values, mutated_registrations, flags=flags), config)

    columns = ENGINEERED_NOT_TARGET + ["licence_count", "total_registrations"]
    pd.testing.assert_frame_equal(original.loc[:cutoff, columns], mutated.loc[:cutoff, columns])
    # The target must respond, otherwise this test would prove nothing.
    assert original.loc[cutoff, "target_licence_count"] != mutated.loc[cutoff, "target_licence_count"]


def test_current_year_does_reach_the_rolling_features(config):
    original = _engineered(_series([100.0, 120.0, 90.0, 150.0, 130.0]), config)
    changed = _engineered(_series([100.0, 120.0, 999.0, 150.0, 130.0]), config)
    assert original.loc[2021, "licence_rolling_mean_3"] != changed.loc[2021, "licence_rolling_mean_3"]


def test_series_do_not_share_values(config):
    a = _series([1.0, 2.0, 3.0, 4.0, 5.0], district="A", vehicle="Car")
    b = _series([100.0, 200.0, 300.0, 400.0, 500.0], district="A", vehicle="Motorcycle")
    c = _series([1000.0, 2000.0, 3000.0, 4000.0, 5000.0], district="B", vehicle="Car")
    df = add_target(add_features(pd.concat([a, b, c], ignore_index=True), config), config)
    row = df[(df["district"] == "A") & (df["vehicle_type"] == "Motorcycle") & (df["year"] == 2020)].iloc[0]
    assert row["licence_lag_1"] == 100
    assert row["target_licence_count"] == 300


def test_series_with_a_missing_year_stops_the_build(config):
    with pytest.raises(ValueError, match="expected"):
        add_features(_series([1.0, 2.0, 3.0, 4.0, 5.0]).drop(index=2), config)


# --- Helpers ------------------------------------------------------------------

def test_parse_cell_list():
    assert _parse_cell_list("") == []
    assert _parse_cell_list("Motor Cars@2019;Total@2020") == [("Motor Cars", 2019), ("Total", 2020)]


def test_config_excludes_monthly_columns(config):
    names = {c["name"] for c in config["columns"]}
    assert not names & {"month", "quarter", "month_sin", "month_cos"}


def test_features_never_include_audit_or_target_columns(config):
    features = {c["name"] for c in config["columns"] if c["role"] == "feature"}
    assert features == {
        "vehicle_type", "licence_count", "total_registrations", "licence_lag_1", "licence_lag_2", "licence_growth_log",
        "licence_rolling_mean_3", "licence_rolling_std_3", "total_registrations_lag_1", "total_registrations_growth_log",
    }


# --- The real dataset ---------------------------------------------------------

@pytest.fixture(scope="module")
def real(config):
    cells = load_cells()
    corrections = load_corrections()
    base, dataset = build(cells, corrections, config, load_extraction_config())
    return cells, corrections, base, dataset


def _row(dataset, district, vehicle, year):
    return dataset[(dataset["district"] == district) & (dataset["vehicle_type"] == vehicle) & (dataset["year"] == year)].iloc[0]


@needs_extraction
def test_shape_and_keys(real, config):
    dataset = real[3]
    assert dataset.shape == (375, 39)
    assert list(dataset.columns) == [c["name"] for c in config["columns"]]
    assert not dataset.duplicated(["district", "year", "vehicle_type"]).any()
    assert dataset["district"].nunique() == 25
    assert (dataset.groupby(["district", "vehicle_type"])["year"].apply(list).map(lambda y: y == YEARS)).all()


@needs_extraction
def test_clearly_incorrect_values_are_missing_with_originals_kept(real):
    dataset = real[3]
    for vehicle, printed in (("Motorcycle", 9057), ("Car", 389), ("Three-wheeler", 575)):
        row = _row(dataset, "Ampara", vehicle, 2019)
        assert np.isnan(row["licence_count"])
        assert row["licence_count_printed"] == printed
        assert row["licence_value_status"] == STATUS_SET_MISSING
        assert row["licence_correction_id"] == "L01"
    jaffna = _row(dataset, "Jaffna", "Motorcycle", 2021)
    assert np.isnan(jaffna["licence_count"])
    assert jaffna["licence_count_printed"] == 13091
    assert jaffna["licence_correction_id"] == "L02"


@needs_extraction
def test_only_those_four_licence_values_are_missing(real):
    dataset = real[3]
    missing = dataset[dataset["licence_count"].isna()]
    assert sorted(zip(missing["district"], missing["year"], missing["vehicle_type"])) == [
        ("Ampara", 2019, "Car"), ("Ampara", 2019, "Motorcycle"), ("Ampara", 2019, "Three-wheeler"),
        ("Jaffna", 2021, "Motorcycle"),
    ]


@needs_extraction
def test_other_jaffna_2021_categories_are_kept(real):
    dataset = real[3]
    assert pd.notna(_row(dataset, "Jaffna", "Car", 2021)["licence_count"])
    assert pd.notna(_row(dataset, "Jaffna", "Three-wheeler", 2021)["licence_count"])


@needs_extraction
@pytest.mark.parametrize("district, vehicle, year, anomaly_id, printed", [
    ("Kandy", "Motorcycle", 2023, "L03", 120945),
    ("Mullaitivu", "Motorcycle", 2019, "L04", 23786),
    ("Badulla", "Motorcycle", 2019, "L06", 25814),
    ("Kilinochchi", "Car", 2023, "L08", 2356),
    ("Kurunegala", "Motorcycle", 2023, "L11", 394975),
])
def test_uncertain_values_stay_in_the_dataset_and_are_flagged(real, district, vehicle, year, anomaly_id, printed):
    row = _row(real[3], district, vehicle, year)
    assert row["licence_count"] == printed
    assert row["licence_flagged"]
    assert anomaly_id in row["licence_flag_ids"]


@needs_extraction
def test_cell_flagged_by_two_entries_records_both(real):
    assert _row(real[3], "Badulla", "Three-wheeler", 2019)["licence_flag_ids"] == "L06;L07"


@needs_extraction
def test_every_value_equals_the_extraction_or_is_an_approved_missing(real):
    """Independent of the build: read straight from the extracted cells."""
    cells, _, _, dataset = real
    licences = cells[(cells["metric"] == "vehicle_population") & cells["vehicle_type"].isin(["Motorcycle", "Car", "Three-wheeler"])]
    printed = licences.set_index(["district", "year", "vehicle_type"])["number"]
    joined = dataset.set_index(["district", "year", "vehicle_type"])
    pd.testing.assert_series_equal(joined["licence_count_printed"].sort_index(), printed.sort_index(), check_names=False)
    observed = joined[joined["licence_count"].notna()]
    assert (observed["licence_count"] == observed["licence_count_printed"]).all()


@needs_extraction
def test_all_targets_recomputed_independently_from_the_extracted_cells(real):
    """Rebuilt without the build code, from the cells and the two rejected groups."""
    cells, _, _, dataset = real
    licences = cells[(cells["metric"] == "vehicle_population") & cells["vehicle_type"].isin(["Motorcycle", "Car", "Three-wheeler"])]
    lookup = {(r.district, r.vehicle_type, r.year): r.number for r in licences.itertuples()}
    rejected = {("Ampara", v, 2019) for v in ("Motorcycle", "Car", "Three-wheeler")} | {("Jaffna", "Motorcycle", 2021)}
    for row in dataset.itertuples():
        key = (row.district, row.vehicle_type, row.year + 1)
        if row.year == 2023 or key in rejected:
            assert np.isnan(row.target_licence_count), key
        else:
            assert row.target_licence_count == lookup[key], key


@needs_extraction
def test_usable_target_counts(real):
    dataset = real[3]
    assert dataset["has_target"].sum() == 299
    assert dataset["has_target_and_level"].sum() == 295
    assert dataset["target_status"].value_counts().to_dict() == {
        TARGET_AVAILABLE: 299, TARGET_NO_NEXT_YEAR: 75, TARGET_SET_MISSING: 1}
    assert (dataset.loc[dataset["year"] == 2023, "has_target"] == False).all()  # noqa: E712


@needs_extraction
def test_kandy_motorcycle_features_match_hand_calculation(real):
    """Printed series: 104208, 103777, 96454, 120945, 120945."""
    dataset = real[3]
    row = _row(dataset, "Kandy", "Motorcycle", 2021)
    assert row["licence_count"] == 96454
    assert row["licence_lag_1"] == 103777
    assert row["licence_lag_2"] == 104208
    assert row["licence_growth_log"] == pytest.approx(np.log(96454 / 103777))
    assert row["licence_rolling_mean_3"] == pytest.approx((104208 + 103777 + 96454) / 3)
    assert row["licence_rolling_std_3"] == pytest.approx(np.std([104208, 103777, 96454], ddof=1))
    assert row["target_licence_count"] == 120945


@needs_extraction
def test_jaffna_gap_flows_through_features_and_target(real):
    dataset = real[3]
    assert np.isnan(_row(dataset, "Jaffna", "Motorcycle", 2020)["target_licence_count"])
    assert _row(dataset, "Jaffna", "Motorcycle", 2020)["target_status"] == TARGET_SET_MISSING
    after = _row(dataset, "Jaffna", "Motorcycle", 2022)
    assert np.isnan(after["licence_lag_1"])
    assert np.isnan(after["licence_growth_log"])
    assert after["licence_lag_2"] == 133106


@needs_extraction
def test_ampara_2019_target_is_kept_because_only_its_features_are_rejected(real):
    row = _row(real[3], "Ampara", "Motorcycle", 2019)
    assert row["target_licence_count"] == 125991
    assert row["has_target"]
    assert not row["has_target_and_level"]


@needs_extraction
def test_unverified_totals_are_missing_and_all_others_match_the_print(real):
    dataset = real[3].drop_duplicates(["district", "year"])
    missing = dataset[dataset["total_registrations"].isna()]
    assert len(missing) == 12
    assert set(missing["total_registrations_status"]) == {"flagged_not_verified"}
    assert missing["total_registrations_printed"].notna().all()
    assert sorted(missing.loc[missing["district"] == "Anuradhapura", "year"]) == [2019, 2020, 2021]
    kept = dataset[dataset["total_registrations"].notna()]
    assert len(kept) == 113
    assert (kept["total_registrations"] == kept["total_registrations_printed"]).all()


@needs_extraction
def test_totals_are_the_same_across_a_districts_vehicle_types(real):
    spread = real[3].groupby(["district", "year"])["total_registrations_printed"].nunique()
    assert (spread == 1).all()


@needs_extraction
def test_no_category_registrations_or_monthly_columns_in_the_dataset(real):
    columns = set(real[3].columns)
    assert not columns & {"new_registrations", "reg_lag_1", "reg_lag_2", "reg_growth_pct", "change_from_lag_2",
                          "month", "quarter", "month_sin", "month_cos", "split"}


@needs_extraction
def test_every_row_has_provenance_and_existing_source_pdfs(real):
    dataset = real[3]
    for column in ["licence_source_id", "licence_source_file", "licence_source_url", "licence_pdf_sha256",
                   "registrations_source_id", "registrations_source_file", "retrieved_date"]:
        assert dataset[column].ne("").all() and dataset[column].notna().all(), column
    for name in set(dataset["licence_source_file"]) | set(dataset["registrations_source_file"]):
        assert (RAW_DIR / name).exists(), name


@needs_extraction
def test_integrity_check_passes_and_catches_each_kind_of_damage(real, config):
    dataset = real[3]
    verify_dataset(dataset, config)

    changed = dataset.copy()
    changed.loc[changed["licence_count"].notna().idxmax(), "licence_count"] += 1
    with pytest.raises(ValueError, match="differs from the printed"):
        verify_dataset(changed, config)

    unexplained = dataset.copy()
    unexplained.loc[unexplained["licence_count"].notna().idxmax(), "licence_count"] = np.nan
    with pytest.raises(ValueError, match="no approved decision"):
        verify_dataset(unexplained, config)

    unverified = dataset.copy()
    position = unverified.index[unverified["total_registrations_status"] == "flagged_not_verified"][0]
    unverified.loc[position, "total_registrations"] = unverified.loc[position, "total_registrations_printed"]
    with pytest.raises(ValueError, match="flagged Totals"):
        verify_dataset(unverified, config)

    with pytest.raises(ValueError, match="expected 375"):
        verify_dataset(dataset.iloc[:-1], config)

    infinite = dataset.copy()
    infinite["licence_growth_log"] = infinite["licence_growth_log"].astype(float)
    infinite.loc[infinite.index[1], "licence_growth_log"] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        verify_dataset(infinite, config)


@needs_extraction
def test_corrections_log_records_every_change_with_source_and_reason(real):
    cells, corrections, _, dataset = real
    log = build_corrections_log(cells, dataset, corrections)
    assert log["action"].value_counts().to_dict() == {ACTION_KEPT_FLAGGED: 31, ACTION_TOTAL_MASKED: 12, ACTION_SET_MISSING: 6}
    for column in ["anomaly_id", "original_value_printed", "source_pdf", "pdf_page", "source_url", "reason", "decision", "decision_date"]:
        assert log[column].astype(str).ne("").all(), column
    ampara = log[(log["district"] == "Ampara") & (log["row_label"] == "Motor Bicycles")].iloc[0]
    assert ampara["original_value_printed"] == "9,057"
    assert ampara["value_in_dataset_v2"] == "missing"
    assert ampara["source_pdf"] == "DCS_Ampara_2024_T9_3.pdf"


@needs_extraction
def test_flagged_cells_match_between_corrections_and_dataset(real):
    corrections, dataset = real[1], real[3]
    labels = dataset.drop_duplicates(["vehicle_type"]).set_index("licence_row_label")["vehicle_type"]
    expected = set()
    for row in corrections.itertuples():
        for label, year in _parse_cell_list(row.cells_flagged):
            expected.add((row.district, year, labels[label]))
    flagged = dataset[dataset["licence_flagged"]]
    assert set(zip(flagged["district"], flagged["year"], flagged["vehicle_type"])) == expected
    assert len(expected) == 30


def test_dictionary_documents_every_column(config):
    text = data_dictionary_markdown(config)
    for column in config["columns"]:
        assert f"`{column['name']}`" in text
        assert column["description"]
    assert "month_sin" in text  # the exclusion is explained


@needs_extraction
def test_dictionary_and_dataset_columns_match(real, config):
    assert set(real[3].columns) == {c["name"] for c in config["columns"]}


# --- Outputs ------------------------------------------------------------------

def _paths(folder):
    return {
        "base_csv": folder / "base.csv", "dataset_csv": folder / "dataset.csv",
        "corrections_log_csv": folder / "log.csv", "dictionary_md": folder / "dictionary.md",
        "manifest_json": folder / "manifest.json",
    }


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@needs_extraction
def test_run_writes_only_to_given_paths_and_is_repeatable(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    before = (_sha(V1_DATASET), V1_DATASET.stat().st_mtime_ns)
    manifest = run(**_paths(first))
    run(**_paths(second))

    assert sorted(p.name for p in first.iterdir()) == ["base.csv", "dataset.csv", "dictionary.md", "log.csv", "manifest.json"]
    assert _sha(first / "dataset.csv") == _sha(second / "dataset.csv")
    assert manifest["dataset_sha256"] == _sha(first / "dataset.csv")
    assert manifest["rows"] == 375
    assert manifest["target_values"] == 299
    assert json.loads((first / "manifest.json").read_text(encoding="utf-8"))["dataset_version"].startswith("modelling_dataset_v2_")
    assert (_sha(V1_DATASET), V1_DATASET.stat().st_mtime_ns) == before


@needs_extraction
def test_written_file_reloads_with_the_same_values(tmp_path, real):
    run(**_paths(tmp_path))
    reloaded = pd.read_csv(tmp_path / "dataset.csv")
    dataset = real[3].reset_index(drop=True)
    assert reloaded.shape == dataset.shape
    for column in ["licence_count", "target_licence_count", "licence_growth_log", "total_registrations"]:
        pd.testing.assert_series_equal(reloaded[column], dataset[column], check_exact=False)


@pytest.mark.parametrize("target", [
    REPO_ROOT / "data" / "processed" / "modelling_dataset_v1.csv",
    REPO_ROOT / "data" / "processed" / "modelling_base_2024.csv",
])
def test_run_refuses_v1_output_paths(tmp_path, target):
    paths = _paths(tmp_path)
    paths["dataset_csv"] = target
    with pytest.raises(ValueError, match="Refusing"):
        run(**paths)


@pytest.mark.skipif(not V1_DATASET.exists(), reason="v1 dataset not present locally")
def test_dataset_v1_is_still_the_frozen_version():
    assert _sha(V1_DATASET).startswith(V1_HASH_PREFIX)
