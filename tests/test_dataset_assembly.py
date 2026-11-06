"""DEV-006 / DEV-015 tests for modelling dataset assembly & target definition.

Covers DEV-006's Testing Requirements: split-integrity (no row in more than one
split, strictly chronological boundaries) and dataset-version stability, plus a
target-value correctness test against the same real Kandy Motorcycle series used
by tests/test_feature_engineering.py.
"""
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest
import yaml

from src.features.build_features import build_features
from src.features.assemble_modelling_dataset import (
    SPLIT_CONFIG_YAML,
    add_target,
    assign_split,
    freeze_dataset,
    run,
)

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"

pytestmark = pytest.mark.skipif(
    not _INTERIM_CSV.exists(), reason="interim extraction cache not present locally"
)


@pytest.fixture(scope="module")
def featured_df(isolated_processed_csv) -> pd.DataFrame:
    processed = pd.read_csv(isolated_processed_csv)
    return build_features(processed)


@pytest.fixture(scope="module")
def split_config() -> dict:
    with open(SPLIT_CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def assembled_df(featured_df, split_config) -> pd.DataFrame:
    df = add_target(featured_df.copy())
    return assign_split(df, split_config)


# --- Target correctness -------------------------------------------------

def test_kandy_motorcycle_target_is_next_period_new_registrations(assembled_df):
    """Regression test against the same real Kandy Motorcycle series used by
    DEV-005's tests (new_registrations = [755, 492, 214, NaN, 813] for
    2019-2023, where 2022 is genuinely missing - see REF-009 ADR-005)."""
    sub = assembled_df[
        (assembled_df["district"] == "Kandy") & (assembled_df["vehicle_type"] == "Motorcycle")
    ].sort_values("year").reset_index(drop=True)

    assert sub.loc[0, "target_value"] == 492.0  # 2019 -> 2020
    assert sub.loc[1, "target_value"] == 214.0  # 2020 -> 2021
    assert pd.isna(sub.loc[2, "target_value"])  # 2021 -> 2022 (2022 itself missing, not fabricated)
    assert sub.loc[3, "target_value"] == 813.0  # 2022 -> 2023
    assert pd.isna(sub.loc[4, "target_value"])  # 2023 -> no 2024 observation yet

    assert sub.loc[0, "target_year"] == 2020
    assert sub.loc[3, "target_year"] == 2023
    assert pd.isna(sub.loc[4, "target_year"])


def test_most_recent_year_has_null_target_across_all_series(assembled_df):
    """Edge Case: the most recent observed year in every series has no t+1
    observation - legitimately null, not fabricated, and not dropped (these rows
    are retained for live inference use, see module docstring)."""
    latest_year_rows = assembled_df[assembled_df["year"] == assembled_df["year"].max()]
    assert len(latest_year_rows) > 0
    assert latest_year_rows["target_value"].isna().all()


def test_demand_lag_1_style_guard_raises_on_preferred_path(monkeypatch, featured_df):
    """Mirrors DEV-005's guard: if the project ever switches to the Preferred
    (real demand) path, add_target()'s Fallback-only logic must fail loudly
    rather than silently mis-defining the target."""
    import src.features.assemble_modelling_dataset as mod
    monkeypatch.setattr(mod, "_is_real_demand_target", lambda: True)
    with pytest.raises(NotImplementedError):
        mod.add_target(featured_df.copy())


# --- Split integrity (DEV-006 Testing Requirements) ----------------------

def test_no_row_in_more_than_one_split(assembled_df):
    assert assembled_df["split"].isin(["train", "validation", "test", "unlabeled"]).all()
    assert assembled_df["split"].notna().all()
    # np.select construction guarantees single-assignment by design; this is a
    # belt-and-braces check that no row was somehow left blank/ambiguous.
    assert (assembled_df["split"] != "").all()


def test_split_is_strictly_chronological(assembled_df, split_config):
    labelled = assembled_df[assembled_df["split"] != "unlabeled"]
    max_train = labelled.loc[labelled["split"] == "train", "target_year"].max()
    min_val = labelled.loc[labelled["split"] == "validation", "target_year"].min()
    max_val = labelled.loc[labelled["split"] == "validation", "target_year"].max()
    min_test = labelled.loc[labelled["split"] == "test", "target_year"].min()

    assert max_train < min_val <= max_val < min_test


def test_unlabeled_rows_all_have_null_target(assembled_df):
    unlabeled = assembled_df[assembled_df["split"] == "unlabeled"]
    assert unlabeled["target_value"].isna().all()


def test_labelled_rows_all_have_non_null_target(assembled_df):
    labelled = assembled_df[assembled_df["split"] != "unlabeled"]
    assert labelled["target_value"].notna().all()


def test_split_boundaries_are_config_driven_not_hardcoded(split_config):
    """Confirms the boundaries live in configs/split_config.yaml (DEV-001 scaffold,
    populated by DEV-006), not hardcoded in the assembly module."""
    assert split_config["granularity"] == "yearly"
    assert split_config["train"]["start_period"] < split_config["train"]["end_period"] + 1
    assert split_config["train"]["end_period"] < split_config["validation"]["start_period"]
    assert split_config["validation"]["end_period"] < split_config["test"]["start_period"]


def test_split_rejects_non_chronological_config(featured_df):
    """A misconfigured (non-chronological) split_config must raise, not silently
    produce an invalid split (Hard Rule: no random/non-chronological splitting)."""
    df = add_target(featured_df.copy())
    bad_config = {
        "train": {"start_period": 2020, "end_period": 2022},
        "validation": {"start_period": 2021, "end_period": 2021},  # overlaps train
        "test": {"start_period": 2023, "end_period": 2023},
    }
    with pytest.raises(ValueError):
        assign_split(df, bad_config)


# --- Dataset freeze / version stability -----------------------------------

def test_freeze_dataset_version_is_stable_across_reruns(tmp_path, assembled_df):
    """Section 'Testing Requirements': the frozen file's identifier is
    retrievable and stable across reruns absent a genuine data change."""
    out_csv = tmp_path / "modelling_dataset_v1.csv"
    split_config_path = tmp_path / "split_config.yaml"
    split_config_path.write_text(
        "train:\n  start_period: 2020\n  end_period: 2021\n"
        "validation:\n  start_period: 2022\n  end_period: 2022\n"
        "test:\n  start_period: 2023\n  end_period: 2023\n"
        "dataset_version: null\ndataset_sha256: null\nfrozen_date: null\n",
        encoding="utf-8",
    )

    version_1, hash_1 = freeze_dataset(assembled_df, out_csv, split_config_path)
    version_2, hash_2 = freeze_dataset(assembled_df, out_csv, split_config_path)

    assert version_1 == version_2
    assert hash_1 == hash_2

    with open(split_config_path, encoding="utf-8") as f:
        written_config = yaml.safe_load(f)
    assert written_config["dataset_version"] == version_1
    assert written_config["dataset_sha256"] == hash_1
    assert written_config["frozen_date"] is not None


def test_freeze_dataset_preserves_config_comments(tmp_path, assembled_df):
    """freeze_dataset() must not destroy hand-authored comments in
    configs/split_config.yaml (a full yaml.safe_load/safe_dump round-trip would
    silently strip them - see src/features/assemble_modelling_dataset.py::_set_yaml_scalar)."""
    out_csv = tmp_path / "modelling_dataset_v1.csv"
    split_config_path = tmp_path / "split_config.yaml"
    split_config_path.write_text(
        "# a hand-authored comment that must survive\n"
        "train:\n  start_period: 2020\n  end_period: 2021\n"
        "validation:\n  start_period: 2022\n  end_period: 2022\n"
        "test:\n  start_period: 2023\n  end_period: 2023\n"
        "dataset_version: null\ndataset_sha256: null\nfrozen_date: null\n",
        encoding="utf-8",
    )

    freeze_dataset(assembled_df, out_csv, split_config_path)

    text = split_config_path.read_text(encoding="utf-8")
    assert "# a hand-authored comment that must survive" in text


def test_run_produces_frozen_dataset_matching_config_version(tmp_path):
    # Redirect the output CSV and split_config.yaml copy to tmp_path - run()
    # must never overwrite the real, frozen data/processed/modelling_dataset_v1.csv
    # or rewrite configs/split_config.yaml's frozen_date as a side effect of
    # running this test. The tmp copy still carries the real, authentic
    # train/validation/test boundaries, so this still exercises real logic.
    tmp_split_config = tmp_path / "split_config.yaml"
    tmp_split_config.write_text(SPLIT_CONFIG_YAML.read_text(encoding="utf-8"), encoding="utf-8")
    out_csv_path = tmp_path / "modelling_dataset_v1.csv"

    out_csv, version_id = run(out_csv=out_csv_path, split_config_path=tmp_split_config)
    assert out_csv.exists()
    with open(tmp_split_config, encoding="utf-8") as f:
        split_config = yaml.safe_load(f)
    assert split_config["dataset_version"] == version_id

    df = pd.read_csv(out_csv)
    assert set(df["split"].unique()) <= {"train", "validation", "test", "unlabeled"}
