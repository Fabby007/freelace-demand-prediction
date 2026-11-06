"""Build Dataset v2: next-year revenue licences as the target (REF-009 ADR-037).

Reads the v2 extraction and the approved decisions in
`data/corrections/source_anomalies_v2.csv`, and writes only to new versioned paths.
Dataset v1, its code and its configs are not used or changed.

No value is invented here. A value is either as printed in the PDF, or missing
because an approved decision says so. Every feature for year t uses only years up
to t, and only the target looks at t+1.

Run with: python -m src.features.build_dataset_v2
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data.extract_dcs_tables_v2 import REPO_ROOT, V2_CELLS_CSV, load_config as load_extraction_config
from src.data.validate_dcs_extraction import (
    CORRECTIONS_CSV,
    METRIC_LICENCES,
    METRIC_REGISTRATIONS,
    TOTAL_FLAGGED,
    _with_numbers,
    verify_total_registrations,
)

logger = logging.getLogger(__name__)

CONFIG_YAML = REPO_ROOT / "configs" / "dataset_v2.yaml"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "v2"
REPORT_DIR = REPO_ROOT / "reports" / "dataset_v2"
BASE_CSV = OUTPUT_DIR / "modelling_base_v2.csv"
DATASET_CSV = OUTPUT_DIR / "modelling_dataset_v2.csv"
CORRECTIONS_LOG_CSV = REPORT_DIR / "applied_corrections_v2.csv"
DICTIONARY_MD = REPORT_DIR / "data_dictionary_v2.md"
MANIFEST_JSON = REPORT_DIR / "dataset_v2_manifest.json"

GROUP_KEYS = ["district", "vehicle_type"]
STATUS_VALUE = "value"
STATUS_SET_MISSING = "set_missing"
TARGET_AVAILABLE = "available"
TARGET_SET_MISSING = "set_missing_next_year"
TARGET_NO_NEXT_YEAR = "no_next_year"
ACTION_SET_MISSING = "set_to_missing"
ACTION_KEPT_FLAGGED = "kept_and_flagged"
ACTION_TOTAL_MASKED = "total_left_missing_in_features"


def load_config(path: Path = CONFIG_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_cell_list(text: str) -> list[tuple[str, int]]:
    """'Motor Cars@2019;Total@2019' -> [('Motor Cars', 2019), ('Total', 2019)]"""
    if not text:
        return []
    return [(label, int(year)) for label, year in (item.rsplit("@", 1) for item in text.split(";"))]


def load_cells(path: Path = V2_CELLS_CSV) -> pd.DataFrame:
    cells = pd.read_csv(path, dtype=str, keep_default_na=False)
    cells["year"] = cells["year"].astype(int)
    return _with_numbers(cells)


def load_corrections(path: Path = CORRECTIONS_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _correction_lookups(corrections: pd.DataFrame, cells: pd.DataFrame) -> tuple[dict, dict]:
    """(district, row_label, year) -> anomaly id(s), for licence cells to set missing
    and to flag. A decision naming a cell that does not exist stops the build."""
    existing = set(zip(*(cells.loc[cells["metric"] == METRIC_LICENCES, col] for col in ("district", "row_label", "year"))))
    set_missing: dict[tuple, str] = {}
    flagged: dict[tuple, list[str]] = {}
    for row in corrections.itertuples():
        for column, is_flag in (("cells_to_set_missing", False), ("cells_flagged", True)):
            for label, year in _parse_cell_list(getattr(row, column)):
                key = (row.district, label, year)
                if key not in existing:
                    raise ValueError(f"{row.anomaly_id} names a cell that was not extracted: {key}")
                if is_flag:
                    flagged.setdefault(key, []).append(row.anomaly_id)
                else:
                    set_missing[key] = row.anomaly_id
    both = set(set_missing) & set(flagged)
    if both:
        raise ValueError(f"Cells both set to missing and kept as flagged: {sorted(both)}")
    return set_missing, flagged


def build_base(cells: pd.DataFrame, corrections: pd.DataFrame, config: dict, extraction_config: dict) -> pd.DataFrame:
    """One row per district, year and vehicle type, with corrections applied."""
    set_missing, flagged = _correction_lookups(corrections, cells)

    licences = cells[(cells["metric"] == METRIC_LICENCES) & cells["vehicle_type"].isin(config["vehicle_types"])]
    base = pd.DataFrame({
        "district": licences["district"],
        "year": licences["year"],
        "vehicle_type": licences["vehicle_type"],
        "licence_row_label": licences["row_label"],
        "licence_count_printed": licences["number"],
        "licence_source_id": licences["source_id"],
        "licence_source_file": licences["source_file"],
        "licence_source_page": licences["page"].astype(int),
        "licence_source_url": licences["source_url"],
        "licence_pdf_sha256": licences["pdf_sha256"],
        "licence_source_note": licences["source_note"],
        "retrieved_date": licences["retrieved_date"],
    })

    keys = list(zip(base["district"], base["licence_row_label"], base["year"]))
    base["licence_correction_id"] = [set_missing.get(key, "") for key in keys]
    base["licence_value_status"] = np.where(base["licence_correction_id"] != "", STATUS_SET_MISSING, STATUS_VALUE)
    base["licence_count"] = base["licence_count_printed"].where(base["licence_correction_id"] == "")
    base["licence_flag_ids"] = [";".join(flagged.get(key, [])) for key in keys]
    base["licence_flagged"] = base["licence_flag_ids"] != ""

    totals = verify_total_registrations(cells, extraction_config)
    registrations = cells[(cells["metric"] == METRIC_REGISTRATIONS) & cells["is_total_row"]][
        ["district", "year", "source_id", "source_file", "page"]
    ].rename(columns={"source_id": "registrations_source_id", "source_file": "registrations_source_file",
                      "page": "registrations_source_page"})
    registrations["registrations_source_page"] = registrations["registrations_source_page"].astype(int)
    totals = totals[["district", "year", "printed_total", "verification_status"]].rename(
        columns={"printed_total": "total_registrations_printed", "verification_status": "total_registrations_status"})
    totals["total_registrations"] = totals["total_registrations_printed"].where(
        totals["total_registrations_status"] != TOTAL_FLAGGED)

    base = base.merge(totals, on=["district", "year"], how="left", validate="many_to_one")
    base = base.merge(registrations, on=["district", "year"], how="left", validate="many_to_one")
    return base.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)


def _require_complete_series(df: pd.DataFrame, config: dict) -> None:
    """Lags rely on row position, so every series must hold every year, in order."""
    for (district, vehicle_type), group in df.groupby(GROUP_KEYS):
        if list(group["year"]) != config["years"]:
            raise ValueError(f"Series {district}/{vehicle_type} has years {list(group['year'])}, expected {config['years']}")


def _log_ratio(current: pd.Series, previous: pd.Series) -> pd.Series:
    """ln(current / previous), empty if either is missing or not positive."""
    valid = (current > 0) & (previous > 0)
    return np.log(current.where(valid) / previous.where(valid))


def add_features(base: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Features for year t, using only years up to and including t."""
    _require_complete_series(base, config)
    df = base.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
    licences = df.groupby(GROUP_KEYS, sort=False)["licence_count"]

    df["licence_lag_1"] = licences.shift(1)
    df["licence_lag_2"] = licences.shift(2)
    df["licence_growth_log"] = _log_ratio(df["licence_count"], df["licence_lag_1"])

    window = config["rolling_window_years"]
    min_observations = config["rolling_min_observations"]
    df["licence_rolling_mean_3"] = licences.transform(lambda s: s.rolling(window, min_periods=min_observations).mean())
    df["licence_rolling_std_3"] = licences.transform(lambda s: s.rolling(window, min_periods=min_observations).std())
    df["licence_window_observations"] = licences.transform(
        lambda s: s.notna().astype(int).rolling(window, min_periods=1).sum()).astype(int)

    registrations = df.groupby(GROUP_KEYS, sort=False)["total_registrations"]
    df["total_registrations_lag_1"] = registrations.shift(1)
    df["total_registrations_growth_log"] = _log_ratio(df["total_registrations"], df["total_registrations_lag_1"])

    df["features_use_flagged_licence"] = df.groupby(GROUP_KEYS, sort=False)["licence_flagged"].transform(
        lambda s: s.astype(int).rolling(window, min_periods=1).max().astype(bool))
    return df


def add_target(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Next year's licences for the same series. A missing next-year value gives a
    missing target; it is never filled."""
    horizon = config["target_horizon_years"]
    df = df.sort_values(GROUP_KEYS + ["year"]).reset_index(drop=True)
    grouped = df.groupby(GROUP_KEYS, sort=False)

    df["target_licence_count"] = grouped["licence_count"].shift(-horizon)
    df["target_year"] = df["year"] + horizon
    next_status = grouped["licence_value_status"].shift(-horizon)
    df["target_status"] = np.select(
        [next_status.isna(), next_status == STATUS_SET_MISSING],
        [TARGET_NO_NEXT_YEAR, TARGET_SET_MISSING],
        default=TARGET_AVAILABLE,
    )
    df["target_flag_ids"] = grouped["licence_flag_ids"].shift(-horizon).fillna("")
    df["target_flagged"] = df["target_flag_ids"] != ""
    df["has_target"] = df["target_licence_count"].notna()
    df["has_target_and_level"] = df["has_target"] & df["licence_count"].notna()
    return df


def _ordered_columns(config: dict, stages: tuple[str, ...]) -> list[str]:
    return [c["name"] for c in config["columns"] if c["stage"] in stages]


def verify_dataset(df: pd.DataFrame, config: dict) -> None:
    """Integrity rules that must hold before anything is written."""
    districts = df["district"].nunique()
    expected_rows = config["expected_districts"] * len(config["years"]) * len(config["vehicle_types"])
    problems = []
    if districts != config["expected_districts"] or len(df) != expected_rows:
        problems.append(f"expected {expected_rows} rows over {config['expected_districts']} districts, got {len(df)} over {districts}")
    if df.duplicated(["district", "year", "vehicle_type"]).any():
        problems.append("duplicate district-year-vehicle rows")
    observed = df["licence_count"].notna()
    if not (df.loc[observed, "licence_count"] == df.loc[observed, "licence_count_printed"]).all():
        problems.append("a licence value differs from the printed value")
    if not (df.loc[~observed, "licence_value_status"] == STATUS_SET_MISSING).all():
        problems.append("a licence value is missing with no approved decision")
    registrations = df["total_registrations"].notna()
    if not (df.loc[registrations, "total_registrations"] == df.loc[registrations, "total_registrations_printed"]).all():
        problems.append("a Total differs from the printed value")
    if (df["total_registrations_status"] == TOTAL_FLAGGED).ne(~registrations).any():
        problems.append("Totals left empty do not match the flagged Totals")
    numeric = df.select_dtypes("number")
    if np.isinf(numeric.to_numpy(dtype=float)).any():
        problems.append("an infinite value")
    non_negative = ["licence_count", "licence_lag_1", "licence_lag_2", "target_licence_count", "total_registrations"]
    if (df[non_negative] < 0).any().any():
        problems.append("a negative count")
    required = ["district", "year", "vehicle_type", "licence_source_id", "licence_source_url", "registrations_source_id", "retrieved_date"]
    if (df[required].isna() | (df[required] == "")).any().any():
        problems.append("missing provenance")
    if problems:
        raise ValueError("Dataset v2 failed integrity checks: " + "; ".join(problems))


def build_corrections_log(cells: pd.DataFrame, df: pd.DataFrame, corrections: pd.DataFrame) -> pd.DataFrame:
    """Every affected value: original, what v2 holds, source and reason."""
    decisions = corrections.set_index("anomaly_id")
    licences = cells[cells["metric"] == METRIC_LICENCES].set_index(["district", "row_label", "year"])
    rows = []

    def add(anomaly_id, action, district, metric_row, year, in_v2):
        entry = decisions.loc[anomaly_id]
        rows.append({
            "action": action, "anomaly_id": anomaly_id, "district": district, "year": year,
            "table_id": metric_row["table_id"], "row_label": metric_row["row_label"],
            "original_value_printed": metric_row["value_raw"], "value_in_dataset_v2": in_v2,
            "source_pdf": metric_row["source_file"], "pdf_page": metric_row["page"], "source_url": metric_row["source_url"],
            "reason": entry["finding"], "decision": entry["decision"], "decision_date": entry["decision_date"],
        })

    for entry in corrections.itertuples():
        for label, year in _parse_cell_list(entry.cells_to_set_missing):
            cell = licences.loc[(entry.district, label, year)]
            add(entry.anomaly_id, ACTION_SET_MISSING, entry.district, {**cell.to_dict(), "row_label": label}, year, "missing")
        for label, year in _parse_cell_list(entry.cells_flagged):
            cell = licences.loc[(entry.district, label, year)]
            add(entry.anomaly_id, ACTION_KEPT_FLAGGED, entry.district, {**cell.to_dict(), "row_label": label}, year, cell["value_raw"])

    registrations = cells[(cells["metric"] == METRIC_REGISTRATIONS) & cells["is_total_row"]].set_index(["district", "year"])
    masked = df[df["total_registrations_status"] == TOTAL_FLAGGED].drop_duplicates(["district", "year"])
    for row in masked.itertuples():
        cell = registrations.loc[(row.district, row.year)]
        anomaly_id = "R13" if row.district == "Anuradhapura" else "R14"
        add(anomaly_id, ACTION_TOTAL_MASKED, row.district, {**cell.to_dict(), "row_label": "Total"}, row.year, "missing")

    return pd.DataFrame(rows).sort_values(["action", "district", "year", "row_label"]).reset_index(drop=True)


def data_dictionary_markdown(config: dict) -> str:
    def table(columns: list[dict]) -> list[str]:
        lines = ["| Column | Type | Stage | Calculation | Description |", "|---|---|---|---|---|"]
        for c in columns:
            formula = f"`{c['formula']}`" if c.get("formula") else ""
            lines.append(f"| `{c['name']}` | {c['type']} | {c['stage']} | {formula} | {c['description']} |")
        return lines

    titles = [
        ("key", "Row key"), ("time", "Time"), ("feature", "Model features"), ("target", "Target"),
        ("quality", "Data quality"), ("audit", "Audit only, never model inputs"), ("provenance", "Provenance"),
    ]
    lines = [
        "# Dataset v2: Data Dictionary",
        "",
        "Generated from `configs/dataset_v2.yaml`. One row per district, year and vehicle type.",
        "",
        "Year t means the row's own year. Features use years up to t only; only the target uses t+1.",
    ]
    for role, title in titles:
        columns = [c for c in config["columns"] if c["role"] == role]
        lines += ["", f"## {title}", ""] + table(columns)
    lines += ["", "## Deliberately excluded", "", "| Columns | Reason |", "|---|---|"]
    lines += [f"| {c['name']} | {c['reason']} |" for c in config["excluded_columns"]]
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(cells: pd.DataFrame, corrections: pd.DataFrame, config: dict, extraction_config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (base, dataset), in the column order given by the config."""
    base = build_base(cells, corrections, config, extraction_config)
    dataset = add_target(add_features(base, config), config)
    verify_dataset(dataset, config)
    return base[_ordered_columns(config, ("base",))], dataset[_ordered_columns(config, ("base", "engineered"))]


def run(
    cells_csv: Path = V2_CELLS_CSV,
    corrections_csv: Path = CORRECTIONS_CSV,
    base_csv: Path = BASE_CSV,
    dataset_csv: Path = DATASET_CSV,
    corrections_log_csv: Path = CORRECTIONS_LOG_CSV,
    dictionary_md: Path = DICTIONARY_MD,
    manifest_json: Path = MANIFEST_JSON,
) -> dict:
    """Build and write Dataset v2. Only the given output paths are written."""
    logging.basicConfig(level=logging.INFO)
    outputs = [base_csv, dataset_csv, corrections_log_csv, dictionary_md, manifest_json]
    for path in outputs:
        if "v1" in path.name or path.parent.resolve() == (REPO_ROOT / "data" / "processed").resolve():
            raise ValueError(f"Refusing to write outside the v2 output folders: {path}")

    config = load_config()
    cells = load_cells(cells_csv)
    corrections = load_corrections(corrections_csv)
    base, dataset = build(cells, corrections, config, load_extraction_config())
    log = build_corrections_log(cells, dataset, corrections)

    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(base_csv, index=False, lineterminator="\n")
    dataset.to_csv(dataset_csv, index=False, lineterminator="\n")
    log.to_csv(corrections_log_csv, index=False, lineterminator="\n")
    dictionary_md.write_text(data_dictionary_markdown(config), encoding="utf-8", newline="\n")

    content_hash = _sha256(dataset_csv)
    manifest = {
        "dataset_version": f"{config['dataset_name']}_{content_hash[:12]}",
        "dataset_sha256": content_hash,
        "built_date": date.today().isoformat(),
        "rows": len(dataset),
        "columns": dataset.shape[1],
        "target_values": int(dataset["has_target"].sum()),
        "target_and_level": int(dataset["has_target_and_level"].sum()),
        "inputs": {cells_csv.name: _sha256(cells_csv), corrections_csv.name: _sha256(corrections_csv)},
    }
    manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("Built %s", manifest["dataset_version"])
    return manifest


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
