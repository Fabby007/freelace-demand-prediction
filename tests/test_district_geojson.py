"""DEV-013 / DEV-015 tests for src/data/fetch_district_geojson.py.

Found missing during the DEV-015 audit: the module's own docstring and
`data/source_register.csv`'s `geoBoundaries_LKA_ADM2` row both claimed this
file existed and verified the district-name reconciliation "programmatically
... not merely assumed" (REF-009 ADR-019), but no such test file had actually
been written - a real "claimed test coverage that doesn't exist" gap.
"""
from pathlib import Path
from unittest.mock import patch

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest

from src.data.fetch_district_geojson import (
    GEOJSON_PATH,
    fetch,
    geojson_canonical_districts,
    load_geojson,
    run,
    shape_name_to_canonical_district,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRICT_LOOKUP_CSV = REPO_ROOT / "configs" / "district_lookup.csv"


# --- shapeName -> canonical district name -----------------------------------

def test_shape_name_to_canonical_district_strips_suffix():
    assert shape_name_to_canonical_district("Jaffna District") == "Jaffna"
    assert shape_name_to_canonical_district("Monaragala District") == "Monaragala"


def test_shape_name_to_canonical_district_leaves_names_without_suffix_unchanged():
    """Defensive: a future geoBoundaries release changing its naming
    convention must not silently mis-map - a name without the expected
    suffix passes through unchanged rather than being truncated wrongly."""
    assert shape_name_to_canonical_district("Colombo") == "Colombo"


# --- geojson -> set of canonical districts ----------------------------------

def test_geojson_canonical_districts_extracts_and_converts():
    fake_geojson = {"features": [
        {"properties": {"shapeName": "Kandy District"}},
        {"properties": {"shapeName": "Galle District"}},
    ]}
    assert geojson_canonical_districts(fake_geojson) == {"Kandy", "Galle"}


# --- fetch(): idempotent, no unnecessary network calls ----------------------

def test_fetch_does_not_download_when_file_already_exists(tmp_path):
    existing = tmp_path / "geojson.json"
    existing.write_text('{"features": []}', encoding="utf-8")

    with patch("src.data.fetch_district_geojson.requests.get") as mock_get:
        result = fetch(out_path=existing)

    mock_get.assert_not_called()
    assert result == existing


def test_fetch_downloads_when_file_missing(tmp_path):
    target = tmp_path / "geojson.json"

    class FakeResponse:
        content = b'{"features": []}'
        def raise_for_status(self):
            pass

    with patch("src.data.fetch_district_geojson.requests.get", return_value=FakeResponse()) as mock_get:
        result = fetch(out_path=target)

    mock_get.assert_called_once()
    assert result.exists()
    assert result.read_bytes() == b'{"features": []}'


# --- run(): raises on mismatch, never silently renders a wrong map ---------

def test_run_raises_on_district_mismatch(tmp_path):
    mismatched_geojson_path = tmp_path / "geojson.json"
    mismatched_geojson_path.write_text(
        '{"features": [{"properties": {"shapeName": "Nonexistent District"}}]}', encoding="utf-8",
    )
    with pytest.raises(ValueError, match="do not exactly match"):
        run(out_path=mismatched_geojson_path, district_lookup_path=DISTRICT_LOOKUP_CSV)


def test_run_succeeds_when_all_districts_reconcile(tmp_path):
    canonical_districts = pd.read_csv(DISTRICT_LOOKUP_CSV)["canonical_name"].unique()
    matching_geojson_path = tmp_path / "geojson.json"
    features = [{"properties": {"shapeName": f"{name} District"}} for name in canonical_districts]
    import json
    matching_geojson_path.write_text(json.dumps({"features": features}), encoding="utf-8")

    result = run(out_path=matching_geojson_path, district_lookup_path=DISTRICT_LOOKUP_CSV)
    assert result == matching_geojson_path


# --- Real downloaded geojson (read-only, already fetched by DEV-013) -------
#
# Scoped with a per-test skipif decorator, NOT a module-level `pytestmark` -
# a module-level pytestmark would apply to every test in this file
# (including the synthetic-data unit tests above, which must always run
# regardless of whether the real geojson happens to be present locally).

_skip_if_no_real_geojson = pytest.mark.skipif(
    not GEOJSON_PATH.exists(), reason="district geojson not fetched locally"
)


@_skip_if_no_real_geojson
def test_real_geojson_has_exactly_25_districts():
    geojson = load_geojson(GEOJSON_PATH)
    assert len(geojson["features"]) == 25


@_skip_if_no_real_geojson
def test_real_geojson_reconciles_exactly_with_canonical_district_list():
    """The actual claim in REF-009 ADR-019 and data/source_register.csv -
    verified here, not merely asserted in prose."""
    geojson = load_geojson(GEOJSON_PATH)
    geo_districts = geojson_canonical_districts(geojson)
    canonical_districts = set(pd.read_csv(DISTRICT_LOOKUP_CSV)["canonical_name"].unique())
    assert geo_districts == canonical_districts


@_skip_if_no_real_geojson
def test_real_geojson_includes_monaragala_spelling():
    """This project's canonical spelling (not 'Moneragala') - the specific
    example REF-009 ADR-019 calls out as verified, not assumed."""
    geojson = load_geojson(GEOJSON_PATH)
    assert "Monaragala" in geojson_canonical_districts(geojson)
