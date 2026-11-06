"""Modelling Dataset Assembly & Target Definition (DEV-006).

Takes DEV-005's feature-engineered dataset (`data/processed/modelling_features_2024.csv`)
and produces the frozen, versioned modelling dataset every model (baseline, XGBoost,
LSTM) trains against: it adds `target_value` per the DEV-002 Fallback-path decision
and assigns each row to a chronological train/validation/test split (source doc
Section 9, Section 8, Section 23.4).

Target definition (Fallback path, configs/target_config.yaml):
`target_value` at a (district, vehicle_type, year) row is the *next* period's
`new_registrations` for that same series - a real, observable vehicle-market proxy
forecast, never a fabricated demand figure (DEV-002 Target Decision Record). This is
computed with a strictly-forward `shift(-1)` within each (district, vehicle_type)
group sorted by year, so target_value at year t always comes from year t+1 - a model
trained on this target only ever sees features from year <= t at prediction time,
preserving the Section 12.1 no-leakage rule at the target-construction step too.

Two real, honestly-null cases both leave target_value as NaN rather than fabricated
(never dropped, never zero-filled):
- The most recent observed year in a series (2023) has no t+1 observation yet. These
  rows are retained (not dropped) because they are exactly the rows a live dashboard
  would use for inference - features as of the latest year, predicting the next one.
- A t+1 observation that is itself genuinely missing in the source data (e.g. Kandy
  Motorcycle 2021 -> 2022 is missing, see REF-009 ADR-005) produces a null target,
  not a fabricated one - this is a pre-existing DEV-004 missing-value case propagating
  through, not a new gap introduced here.

Rows with a null target_value are excluded from every split (`split = "unlabeled"`)
since there is no ground truth to train or evaluate against - see DEV-006 Edge Cases.

DCS/DMT reconciliation flag (REF-006 Section 5.1): rather than excluding or
down-weighting the 100 flagged `new_registrations` rows, this stage discloses the
flag on the *target* side too (`target_data_quality_flag`) - see REF-009 ADR-007 for
the disposition rationale. Downstream specs (DEV-007/008/012/013) can choose to
down-weight or exclude using this flag; the frozen dataset itself never silently
drops a real observation.

Split boundaries are read from `configs/split_config.yaml` (config-driven, not
hardcoded) and keyed by `target_year` (the year being predicted), not the feature
row's own `year` - see REF-009 ADR-008 for why a 5-year yearly series only supports a
thin 2/1/1-year train/validation/test split.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

FEATURES_CSV = PROCESSED_DIR / "modelling_features_2024.csv"
FROZEN_CSV = PROCESSED_DIR / "modelling_dataset_v1.csv"
SPLIT_CONFIG_YAML = CONFIGS_DIR / "split_config.yaml"
TARGET_CONFIG_YAML = CONFIGS_DIR / "target_config.yaml"

GROUP_KEYS = ["district", "vehicle_type"]

DATASET_VERSION_PREFIX = "modelling_dataset_v1"


def _is_real_demand_target() -> bool:
    with open(TARGET_CONFIG_YAML, encoding="utf-8") as f:
        target_config = yaml.safe_load(f)
    return bool(target_config.get("is_real_demand_target", False))


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback-path target: target_value = next-period new_registrations for the
    same (district, vehicle_type) series (see module docstring). Raises loudly if
    the project ever switches to the Preferred (real demand) path, since this
    lead-of-new_registrations logic would then be the wrong target definition."""
    if _is_real_demand_target():
        raise NotImplementedError(
            "configs/target_config.yaml now indicates a real demand target, but "
            "add_target() implements the Fallback-path proxy definition "
            "(target_value = next-period new_registrations). Implement the "
            "Preferred-path definition (target_value = the real observed demand "
            "signal for the same period, not a lead of new_registrations) before "
            "proceeding, and update REF-001/DEV-006 accordingly."
        )

    df = df.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
    grouped = df.groupby(GROUP_KEYS, sort=False)

    df["target_value"] = grouped["new_registrations"].shift(-1)
    df["target_year"] = grouped["year"].shift(-1).astype("Int64")
    df["target_data_quality_flag"] = grouped["data_quality_flag"].shift(-1)

    return df


def assign_split(df: pd.DataFrame, split_config: dict) -> pd.DataFrame:
    """Assign each row to 'train' / 'validation' / 'test' / 'unlabeled' based on
    `target_year` against the boundaries in configs/split_config.yaml. Rows with a
    null target_value are always 'unlabeled', regardless of target_year, since
    there is no ground truth to train or evaluate against."""
    boundaries = {
        "train": (split_config["train"]["start_period"], split_config["train"]["end_period"]),
        "validation": (split_config["validation"]["start_period"], split_config["validation"]["end_period"]),
        "test": (split_config["test"]["start_period"], split_config["test"]["end_period"]),
    }

    train_end = boundaries["train"][1]
    val_start, val_end = boundaries["validation"]
    test_start = boundaries["test"][0]
    if not (train_end < val_start <= val_end < test_start):
        raise ValueError(
            "configs/split_config.yaml boundaries are not strictly chronological: "
            f"train ends {train_end}, validation is {val_start}-{val_end}, "
            f"test starts {test_start} (Hard Rule: no random splitting; strictly "
            "chronological boundaries required)."
        )

    # fillna(False).to_numpy(bool): target_year is nullable Int64 (has NA for the
    # most-recent-year rows), whose .between() result is a nullable boolean array -
    # np.select requires plain numpy bool ndarrays, and NA rows must be False here
    # regardless (they are handled by the target_value.isna() override below).
    conditions = [
        df["target_year"].between(lo, hi).fillna(False).to_numpy(dtype=bool)
        for lo, hi in boundaries.values()
    ]
    df["split"] = np.select(conditions, list(boundaries.keys()), default="unlabeled")
    df.loc[df["target_value"].isna(), "split"] = "unlabeled"

    return df


def _content_sha256(csv_path: Path) -> str:
    return hashlib.sha256(csv_path.read_bytes()).hexdigest()


def _set_yaml_scalar(text: str, key: str, value: str) -> str:
    """Replace a single top-level `key: ...` line's value in-place via regex
    rather than a full yaml.safe_load/safe_dump round-trip, which would silently
    strip every comment in configs/split_config.yaml (including the target_year-
    vs-year explanation and the ADR-008 reference) - both are hand-authored,
    load-bearing documentation, not just data."""
    pattern = re.compile(rf"^{re.escape(key)}:.*$", flags=re.MULTILINE)
    replacement = f"{key}: {value}"
    if not pattern.search(text):
        raise KeyError(f"configs/split_config.yaml has no top-level '{key}:' line to update")
    return pattern.sub(replacement, text, count=1)


def freeze_dataset(df: pd.DataFrame, out_csv: Path, split_config_path: Path) -> tuple[str, str]:
    """Write the frozen dataset to disk and record a content-derived version
    identifier (sha256 of the exact written bytes) plus the freeze date into
    configs/split_config.yaml, so the identifier is stable across reruns as long
    as the content is unchanged, and changes if and only if the content changes."""
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    content_hash = _content_sha256(out_csv)
    version_id = f"{DATASET_VERSION_PREFIX}_{content_hash[:12]}"
    frozen_date = date.today().isoformat()

    text = split_config_path.read_text(encoding="utf-8")
    text = _set_yaml_scalar(text, "dataset_version", version_id)
    text = _set_yaml_scalar(text, "dataset_sha256", content_hash)
    text = _set_yaml_scalar(text, "frozen_date", f"'{frozen_date}'")
    split_config_path.write_text(text, encoding="utf-8")

    return version_id, content_hash


def run(
    features_csv: Path = FEATURES_CSV,
    out_csv: Path = FROZEN_CSV,
    split_config_path: Path = SPLIT_CONFIG_YAML,
) -> tuple[Path, str]:
    logging.basicConfig(level=logging.INFO)
    df = pd.read_csv(features_csv)

    df = add_target(df)

    with open(split_config_path, encoding="utf-8") as f:
        split_config = yaml.safe_load(f)
    df = assign_split(df, split_config)

    version_id, content_hash = freeze_dataset(df, out_csv, split_config_path)
    logger.info(
        "Froze %d rows (%s) to %s [%s]",
        len(df), df["split"].value_counts().to_dict(), out_csv, version_id,
    )
    return out_csv, version_id


if __name__ == "__main__":
    run()
