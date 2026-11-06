"""Canonical value lists shared with the ML system's configuration.

Reuses `configs/district_lookup.csv` (REF-002) as the single source of
truth for the 25 canonical district names, rather than hand-copying a
second list into the marketplace — avoids the two lists silently drifting
apart. This reads a shared `configs/` file, not any ML *research data*
under `data/`, so it does not cross the marketplace/ML boundary
(MARKETPLACE_EXTENSION.md Section 7.2).
"""

import csv
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"
_DISTRICT_LOOKUP_PATH = _CONFIG_DIR / "district_lookup.csv"


def canonical_districts():
    """Return the 25 canonical Sri Lankan district names, sorted alphabetically."""
    if not _DISTRICT_LOOKUP_PATH.exists():
        return []
    with open(_DISTRICT_LOOKUP_PATH, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        names = {row["canonical_name"].strip() for row in reader if row.get("canonical_name")}
    return sorted(names)
