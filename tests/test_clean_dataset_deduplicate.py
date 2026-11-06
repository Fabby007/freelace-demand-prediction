"""DEV-004 / DEV-015 unit tests for src/data/clean_dataset.py::deduplicate().

Found missing during the DEV-015 audit: tests/test_data_cleaning.py's
Section 26.1 "no duplicated district-time-vehicle key" test only checks that
the FINAL processed output has no duplicate keys - it would pass equally
whether deduplicate() kept the correct row, the wrong row, or silently
dropped a real observation without justification. These tests exercise the
actual dedup RULE directly against synthetic examples modelled on the real
cases this project encountered (REF-009 ADR-025): most-recent-
edition-wins across editions; same-edition disagreement excluded, never
guessed.

Deliberately NOT gated behind the "interim extraction cache present" skipif
used by tests/test_data_cleaning.py - these are pure synthetic-data unit
tests on deduplicate() itself and must always run, regardless of whether the
real interim CSV happens to be present locally.
"""
import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd

from src.data.clean_dataset import deduplicate


def _dupe_row(district="Kandy", year=2023, vehicle_type="Motorcycle", metric="new_registrations",
              handbook_edition_year=2024, value_raw="100"):
    return {
        "district_canonical": district, "year": year, "vehicle_type": vehicle_type,
        "metric": metric, "handbook_edition_year": handbook_edition_year, "value_raw": value_raw,
    }


def test_deduplicate_keeps_most_recent_edition_on_cross_edition_duplicate():
    df = pd.DataFrame([
        _dupe_row(handbook_edition_year=2023, value_raw="90"),
        _dupe_row(handbook_edition_year=2024, value_raw="100"),
    ])
    result = deduplicate(df)
    assert len(result) == 1
    assert result.iloc[0]["handbook_edition_year"] == 2024
    assert result.iloc[0]["value_raw"] == "100"


def test_deduplicate_keeps_one_copy_of_agreeing_same_edition_duplicate():
    """A harmless double-parse (same edition, same value) - keep one row,
    not zero and not two."""
    df = pd.DataFrame([_dupe_row(value_raw="100"), _dupe_row(value_raw="100")])
    result = deduplicate(df)
    assert len(result) == 1
    assert result.iloc[0]["value_raw"] == "100"


def test_deduplicate_excludes_disagreeing_same_edition_duplicate_never_guesses():
    """The real Trincomalee 2019 Three-wheeler case (REF-009 ADR-006
    context): same handbook edition, same key, DISAGREEING raw values - both
    rows must be excluded, never resolved by silently picking one."""
    df = pd.DataFrame([
        _dupe_row(district="Trincomalee", year=2019, vehicle_type="Three-wheeler", value_raw="50"),
        _dupe_row(district="Trincomalee", year=2019, vehicle_type="Three-wheeler", value_raw="75"),
    ])
    result = deduplicate(df)
    assert len(result) == 0


def test_deduplicate_disagreeing_conflict_does_not_affect_other_keys():
    """A same-edition conflict for one key must not exclude unrelated,
    non-conflicting rows."""
    df = pd.DataFrame([
        _dupe_row(district="Trincomalee", year=2019, vehicle_type="Three-wheeler", value_raw="50"),
        _dupe_row(district="Trincomalee", year=2019, vehicle_type="Three-wheeler", value_raw="75"),
        _dupe_row(district="Kandy", year=2023, vehicle_type="Motorcycle", value_raw="200"),
    ])
    result = deduplicate(df)
    assert len(result) == 1
    assert result.iloc[0]["district_canonical"] == "Kandy"


def test_deduplicate_is_a_no_op_when_no_duplicates_exist():
    df = pd.DataFrame([
        _dupe_row(district="Kandy"),
        _dupe_row(district="Galle", value_raw="200"),
    ])
    result = deduplicate(df)
    assert len(result) == 2
