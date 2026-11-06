"""Safety fixtures shared by the whole test suite (REF-009 ADR-035).

Tests may read real project files, but anything they generate must go to a
temporary folder, so running pytest can never overwrite a dataset, model or
report.
"""
import inspect
from pathlib import Path

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pytest

from src.evaluation.experiment_tracking import log_run

_INTERIM_CSV = Path(__file__).resolve().parents[1] / "data" / "interim" / "dcs_multi_district_2024_raw.csv"


@pytest.fixture(scope="session")
def isolated_processed_csv(tmp_path_factory) -> Path:
    """The processed dataset, rebuilt once per session from the real interim
    file through the canonical build() (ADR-006), with both of its outputs in
    a temporary folder."""
    from src.data.build_processed_dataset import build

    out_dir = tmp_path_factory.mktemp("processed")
    processed_csv = out_dir / "modelling_base_2024.csv"
    build(_INTERIM_CSV, processed_csv, out_dir / "dmt_cross_validation.md")
    return processed_csv


@pytest.fixture(scope="session", autouse=True)
def _isolate_experiment_tracking_defaults(tmp_path_factory):
    """Point log_run()'s default output folders at a temporary folder.

    The run() functions pass mlruns_dir but offer no way to pass
    fallback_log_dir, so an MLflow failure during a test would otherwise write
    to the real reports/ folder. Defaults are replaced by parameter name, and
    restored after the session.
    """
    original = log_run.__defaults__
    names = list(inspect.signature(log_run).parameters)[-len(original):]
    defaults = dict(zip(names, original))
    out_dir = tmp_path_factory.mktemp("experiment_tracking")
    defaults["mlruns_dir"] = out_dir / "mlruns"
    defaults["fallback_log_dir"] = out_dir / "fallback"
    log_run.__defaults__ = tuple(defaults[name] for name in names)
    yield
    log_run.__defaults__ = original
