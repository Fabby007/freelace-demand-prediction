"""District boundary geometry acquisition (DEV-013 dependency).

DEV-013's Section 19.2 "Sri Lanka choropleth map" needs real district
boundary polygons - a plain lat/lon scatter cannot represent this
requirement. No boundary geometry existed anywhere in this project before
DEV-013 (DEV-002/DEV-003's data acquisition covered vehicle-registration and
population data only), so this is a genuinely new, narrowly-scoped source,
registered here the same way every other real source in this project is
registered (`data/source_register.csv`), not silently bundled.

Source: geoBoundaries (https://www.geoboundaries.org), ADM2 (district-level)
boundaries for Sri Lanka (ISO LKA), Open Data Commons Open Database License
1.0, built from OpenStreetMap contributions. This is a well-established,
freely-licensed, citable open geodata project, not an ad hoc scrape - see
`data/source_register.csv` row `geoBoundaries_LKA_ADM2` for the full
citation and licence.

Reconciliation with REF-002's canonical district list: geoBoundaries' 25
`shapeName` values are formatted as "<Name> District" (e.g. "Jaffna
District"); stripping that fixed suffix reproduces REF-002's 25 canonical
names exactly, including the "Monaragala" spelling already used throughout
this project (`configs/district_lookup.csv`) - verified in
`tests/test_district_geojson.py`, not assumed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
GEO_DIR = REPO_ROOT / "data" / "raw" / "geo"

GEOJSON_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/LKA/ADM2/"
    "geoBoundaries-LKA-ADM2_simplified.geojson"
)
GEOJSON_PATH = GEO_DIR / "sri_lanka_districts_adm2.geojson"
DISTRICT_LOOKUP_CSV = CONFIGS_DIR / "district_lookup.csv"

SHAPE_NAME_SUFFIX = " District"


def shape_name_to_canonical_district(shape_name: str) -> str:
    """geoBoundaries' "<Name> District" -> this project's canonical name."""
    if shape_name.endswith(SHAPE_NAME_SUFFIX):
        return shape_name[: -len(SHAPE_NAME_SUFFIX)]
    return shape_name


def load_geojson(path: Path = GEOJSON_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def geojson_canonical_districts(geojson: dict) -> set[str]:
    return {shape_name_to_canonical_district(f["properties"]["shapeName"]) for f in geojson["features"]}


def fetch(out_path: Path = GEOJSON_PATH, force: bool = False) -> Path:
    """Idempotent: does nothing if the file already exists, unless force=True -
    this is stable reference geometry, not something to silently re-download
    and potentially change underneath a running dashboard."""
    if out_path.exists() and not force:
        logger.info("District geojson already present at %s - not re-downloading.", out_path)
        return out_path

    logger.info("Downloading district boundary geojson from %s", GEOJSON_URL)
    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(response.content)
    return out_path


def run(out_path: Path = GEOJSON_PATH, district_lookup_path: Path = DISTRICT_LOOKUP_CSV) -> Path:
    logging.basicConfig(level=logging.INFO)
    fetch(out_path)

    geojson = load_geojson(out_path)
    geo_districts = geojson_canonical_districts(geojson)
    canonical_districts = set(pd.read_csv(district_lookup_path)["canonical_name"].unique())

    if geo_districts != canonical_districts:
        raise ValueError(
            "District geojson's districts (after stripping ' District') do not exactly match "
            f"REF-002's canonical district list. In geojson only: {geo_districts - canonical_districts}; "
            f"missing from geojson: {canonical_districts - geo_districts}."
        )

    logger.info("District geojson verified: all 25 canonical districts present at %s", out_path)
    return out_path


if __name__ == "__main__":
    run()
