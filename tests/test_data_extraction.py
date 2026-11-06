"""DEV-003 / DEV-015 tests for the DCS handbook extraction pipeline.

Structural-consistency and spot-check tests per DEV-003's Testing Requirements
and Section 10.1 (Kandy proof-of-concept -> validate additional districts).
PDF-dependent tests are skipped when the local raw cache
(data/raw/dcs_handbooks/) is absent (e.g. a fresh clone without having run
the extraction scripts yet / without network access to statistics.gov.lk),
since re-downloading on every test run is neither required nor desirable.
"""
from pathlib import Path

import pytest

import src  # noqa: F401  (ADR-003 import order)
from src.data.extract_dcs_handbook import load_url_segments, parse_multi_year_table

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "dcs_handbooks"

KANDY_T9_4 = RAW_DIR / "DCS_Kandy_2024_T9_4.pdf"
KANDY_T9_3 = RAW_DIR / "DCS_Kandy_2024_T9_3.pdf"


def test_url_segments_cover_all_25_districts():
    segments = load_url_segments()
    assert len(segments) == 25
    for canonical, variants in segments.items():
        assert variants, f"{canonical} has no registered URL segment variants"


@pytest.mark.skipif(not KANDY_T9_4.exists(), reason="raw PDF cache not present locally")
def test_kandy_2024_t9_4_matches_manually_verified_values():
    """Regression test against values manually verified from the actual
    government PDF on 2026-08-15 (see data/source_register.csv)."""
    years, rows = parse_multi_year_table(KANDY_T9_4)
    assert years == [2019, 2020, 2021, 2022, 2023]

    by_label = dict(rows)
    assert by_label["Motor Cycle"] == ["755", "492", "214", "-", "813"]
    assert by_label["Car"] == ["2,532", "1,297", "120", "50", "56"]
    assert by_label["Three Wheeler"] == ["-", "-", "-", "-", "-"]
    # "Total" is an aggregate row and must never be extracted as a vehicle-type observation.
    assert "Total" not in by_label


@pytest.mark.skipif(not KANDY_T9_3.exists(), reason="raw PDF cache not present locally")
def test_kandy_2024_t9_3_matches_manually_verified_values():
    years, rows = parse_multi_year_table(KANDY_T9_3)
    assert years == [2019, 2020, 2021, 2022, 2023]

    by_label = dict(rows)
    assert by_label["Motor Bicycles"] == ["104,208", "103,777", "96,454", "120,945", "120,945"]


@pytest.mark.skipif(not (RAW_DIR / "DCS_Jaffna_2024_T9_4.pdf").exists(), reason="raw PDF cache not present locally")
def test_jaffna_2024_t9_4_matches_manually_verified_values():
    """Regression test against values independently verified from a second
    extraction library (pypdf) on 2026-08-15. Jaffna's PDF wraps several
    labels across two lines and mixes Tamil text into value rows, making it
    a good regression guard for the word-position-based parser."""
    years, rows = parse_multi_year_table(RAW_DIR / "DCS_Jaffna_2024_T9_4.pdf")
    by_label = dict(rows)
    assert by_label["Dual Purpose (Commercial)"] == ["296", "218", "-", "1", "-"]
    assert by_label["Lorry Trailer / Bowser"] == ["13389", "8073", "347", "1", "-"]
    assert by_label["Tractor Trailer / Bowser"] == ["129", "157", "307", "196", "100"]
    assert len(rows) == 17


@pytest.mark.parametrize("district", ["Colombo", "Galle", "Jaffna", "Batticaloa"])
def test_structure_consistent_across_validation_districts(district):
    """Section 10.1: validate structure/naming consistency on additional
    districts before scaling. Every district's Table 9.4 must parse to
    exactly 5 years and at least one vehicle-type row, with no row skipped
    due to a value/year-count mismatch."""
    path = RAW_DIR / f"DCS_{district.replace(' ', '')}_2024_T9_4.pdf"
    if not path.exists():
        pytest.skip("raw PDF cache not present locally")
    years, rows = parse_multi_year_table(path)
    assert years == [2019, 2020, 2021, 2022, 2023]
    assert len(rows) > 0
    for label, values in rows:
        assert len(values) == 5, f"{district}/{label} has {len(values)} values, expected 5"
