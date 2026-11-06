"""Feature Engineering Pipeline (DEV-005).

Converts the cleaned processed dataset (DEV-004 output, REF-001 schema)
into model-ready features representing recent level, direction, and
momentum (source doc Section 12), under the strict no-leakage rule
(Section 12.1): "When predicting year t, every feature must be computable
using information available before year t."

All lag/growth/rolling features are computed strictly within each
(district, vehicle_type) group, sorted chronologically by year, using only
backward-looking pandas operations (`shift`, `shift().rolling()`). No
feature is ever derived from a full-dataset statistic computed across all
years - see `tests/test_feature_engineering.py` for the automated guarantee.

`population`/`population_density`/`vehicles_per_1000_people` are computed
correctly wherever population data is present, but are honestly null for
every row in the current dataset version: DCS Chapter 2 (Population and
Housing) has not yet been acquired (see data/source_register.csv,
source_id=DCS_Kandy_2024_Chapter02_Population, and TODO.md Phase 2 - this
is a DEV-003 acquisition gap, not a DEV-005 defect, and these columns are
"Recommended"/"Optional" per REF-001, not "Required"). `month`,
`quarter`, `month_sin`, `month_cos` are likewise never fabricated: the
dataset is yearly-only (see REF-001 Section 5 granularity rule), so no
cyclic month feature is computed at all (Edge Case, DEV-005 spec).

`demand_lag_1` (Functional Requirement 8, target lag) is deliberately NOT
computed: per DEV-002's Target Decision Record and
configs/target_config.yaml (`is_real_demand_target: false`), the project
follows the Fallback path - there is no real observed demand series to lag.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

FEATURE_LIST_YAML = CONFIGS_DIR / "feature_list.yaml"
TARGET_CONFIG_YAML = CONFIGS_DIR / "target_config.yaml"

GROUP_KEYS = ["district", "vehicle_type"]

# Section 12 engineered columns this module produces, in the order they are
# appended to REF-001 Section 6 once finalized.
ENGINEERED_COLUMNS = [
    "reg_lag_1",
    "reg_lag_2",
    "reg_growth_pct",
    "change_from_lag_2",
    "rolling_mean_3",
    "rolling_std_3",
    "quarter",
    "month_sin",
    "month_cos",
    "vehicles_per_1000_people",
]


def _is_real_demand_target() -> bool:
    with open(TARGET_CONFIG_YAML, encoding="utf-8") as f:
        target_config = yaml.safe_load(f)
    return bool(target_config.get("is_real_demand_target", False))


def add_lag_growth_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Section 12 groups 1-3: current/lagged level, growth, rolling trend.

    Every operation below is computed within a (district, vehicle_type)
    group sorted ascending by year, using only `shift`/`shift().rolling()`
    - by construction, the value at row t can only depend on rows strictly
    before t within its own group (see tests/test_feature_engineering.py).
    """
    df = df.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
    grouped = df.groupby(GROUP_KEYS, sort=False)["new_registrations"]

    df["reg_lag_1"] = grouped.shift(1)
    df["reg_lag_2"] = grouped.shift(2)

    # Mask a zero denominator to NaN *before* dividing, rather than dividing
    # then replacing +/-inf afterward - avoids ever materializing inf and
    # the pandas downcasting-on-replace deprecation warning that comes with it.
    safe_lag_1 = df["reg_lag_1"].where(df["reg_lag_1"] != 0)
    df["reg_growth_pct"] = (df["new_registrations"] - df["reg_lag_1"]) / safe_lag_1 * 100

    df["change_from_lag_2"] = df["new_registrations"] - df["reg_lag_2"]

    # rolling_mean_3 / rolling_std_3 for year t must use only t-1, t-2, t-3 -
    # shift(1) first so the rolling window never includes the current row.
    df["rolling_mean_3"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=3, min_periods=1).mean()
    )
    df["rolling_std_3"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=3, min_periods=2).std()
    )

    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Section 12 group 4: time features. `year` already exists. `quarter`
    and cyclic `month_sin`/`month_cos` are only computed where monthly
    granularity is genuinely present (Edge Case) - this dataset is
    yearly-only (REF-001 Section 5), so all three are left null rather
    than fabricated from an absent `month` value."""
    has_month = df["month"].notna().any()
    if has_month:
        df["quarter"] = ((df["month"].astype("Int64") - 1) // 3 + 1)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    else:
        logger.info("No monthly data present - quarter/month_sin/month_cos left null, not fabricated.")
        df["quarter"] = np.nan
        df["month_sin"] = np.nan
        df["month_cos"] = np.nan
    return df


def add_vehicle_intensity_feature(df: pd.DataFrame) -> pd.DataFrame:
    """Section 12 group 6: vehicles_per_1000_people. `population` (group 5)
    is already present as a pass-through column from DEV-004's output -
    currently null for every row (DEV-003 has not yet acquired DCS Chapter
    2 population tables; see module docstring), so this is honestly null
    too rather than fabricated."""
    safe_population = df["population"].where(df["population"] != 0)
    df["vehicles_per_1000_people"] = df["new_registrations"] / safe_population * 1000
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full Section 12 pipeline. `vehicle_type` (group 7, category) is
    already a column on the input and is retained unchanged. `demand_lag_1`
    (group 8) is deliberately omitted - see module docstring."""
    df = add_lag_growth_rolling_features(df)
    df = add_time_features(df)
    df = add_vehicle_intensity_feature(df)

    if _is_real_demand_target():
        raise NotImplementedError(
            "configs/target_config.yaml now indicates a real demand target, but "
            "demand_lag_1 (Section 12 group 8) is not implemented - this branch "
            "was never reached during Fallback-path development. Implement it "
            "before proceeding (must lag the real demand column exactly like "
            "reg_lag_1 lags new_registrations, with the same leakage guarantees), "
            "and update REF-001 Section 6 / configs/feature_list.yaml accordingly."
        )

    return df


def run(processed_csv: Path, out_csv: Path) -> Path:
    logging.basicConfig(level=logging.INFO)
    df = pd.read_csv(processed_csv)
    featured = build_features(df)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    featured.to_csv(out_csv, index=False)
    logger.info("Wrote %d feature-engineered rows to %s", len(featured), out_csv)
    return out_csv


if __name__ == "__main__":
    run(
        PROCESSED_DIR / "modelling_base_2024.csv",
        PROCESSED_DIR / "modelling_features_2024.csv",
    )
