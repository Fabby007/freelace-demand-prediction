"""Canonical entry point for regenerating the processed dataset.

Discovered during DEV-005 (2026-08-15): `clean_dataset.run()` alone
unconditionally regenerates `data/processed/modelling_base_*.csv` from the
raw interim data, which silently wipes the DMT cross-validation flags
applied afterward by `validate_against_dmt.run()` (DEV-003, Section 10
step 6). Any code path that regenerates the processed file - including
test fixtures - must go through this single function instead of calling
`clean_dataset.run()` directly, so the file on disk is never left in a
partially-built (cleaned-but-not-cross-validated) state depending on
execution order. See REF-009 ADR-006.
"""
from __future__ import annotations

from pathlib import Path

from src.data.clean_dataset import INTERIM_DIR, PROCESSED_DIR
from src.data.clean_dataset import run as clean_run
from src.data.validate_against_dmt import run as validate_run

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def build(
    interim_csv: Path = INTERIM_DIR / "dcs_multi_district_2024_raw.csv",
    processed_csv: Path = PROCESSED_DIR / "modelling_base_2024.csv",
    dmt_report_path: Path = REPORTS_DIR / "dmt_cross_validation.md",
) -> Path:
    clean_run(interim_csv, processed_csv)
    validate_run(processed_csv, dmt_report_path)
    return processed_csv


if __name__ == "__main__":
    build()
