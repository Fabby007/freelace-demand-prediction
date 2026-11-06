"""Tests for the v2 DCS extractor and its validation checks (REF-009 ADR-036).

The PDFs are read from data/raw/ but never changed. Everything written goes to
tmp_path. Validation-check tests use small, clearly artificial tables that exist
only to exercise each rule; they are not project data.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib

import src  # noqa: F401  (ADR-003 import order - must precede pandas/numpy too)

import pandas as pd
import pytest

from src.data.extract_dcs_tables_v2 import (
    RAW_DIR,
    REPO_ROOT,
    V1_INTERIM_CSV,
    _assign_cells,
    _cell_status,
    _find_year_header,
    _match_label,
    extract_all,
    load_config,
    parse_table_pdf,
    write_cells_csv,
)
from src.data.validate_dcs_extraction import (
    FLAG_COLUMNS,
    TOTAL_FLAGGED,
    TOTAL_VERIFIED,
    TOTAL_YEAR_CAVEAT,
    _with_numbers,
    check_against_dmt_national,
    check_dips_and_spikes,
    check_identical_columns_across_districts,
    check_identical_year_columns,
    check_licences_copied_from_registrations,
    check_missing_category_cells,
    check_registrations_against_licences,
    check_sum_to_total,
    check_total_registrations_against_peers,
    check_totals_against_dmt_national,
    check_year_on_year_against_national_pattern,
    compare_with_v1,
    review_flags,
    run,
    validate,
    verify_total_registrations,
)

CORRECTIONS_CSV = REPO_ROOT / "data" / "corrections" / "source_anomalies_v2.csv"

needs_pdfs = pytest.mark.skipif(
    not (RAW_DIR / "DCS_Anuradhapura_2024_T9_3.pdf").exists(), reason="raw PDF cache not present locally"
)


def _word(text, x0, x1, top=100.0):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 8}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Parsing helpers ----------------------------------------------------------

def test_year_header_requires_consecutive_years():
    title = [_word("2019", 0, 10), _word("-", 11, 12), _word("2023", 13, 20)]
    values = [_word("2057", 0, 10), _word("2000", 20, 30), _word("2057", 40, 50)]
    header = [_word(str(y), i * 20, i * 20 + 10) for i, y in enumerate(range(2019, 2024))]
    year_words, index = _find_year_header([title, values, header])
    assert index == 2
    assert [w["text"] for w in year_words] == ["2019", "2020", "2021", "2022", "2023"]


def test_split_number_is_rejoined_into_its_own_column():
    # Observed: "146,982" in the first column, then "1" + "41,902" in the second.
    words = [_word("146,982", 180, 218), _word("1", 252, 257), _word("41,902", 257, 278)]
    values, joined = _assign_cells(words, [218.0, 278.0])
    assert values == ["146,982", "141,902"]
    assert joined is True


def test_values_on_separate_text_lines_share_a_row():
    # Observed in Anuradhapura Table 9.3.
    words = [_word("17109", 190, 218, top=182), _word("18137", 430, 454, top=188.5)]
    values, _ = _assign_cells(words, [218.0, 454.0])
    assert values == ["17109", "18137"]


def test_empty_cell_stays_blank_not_dash():
    values, _ = _assign_cells([_word("5", 210, 218)], [218.0, 278.0])
    assert values == ["5", ""]
    assert _cell_status(values[1]) == "blank"


def test_two_separate_values_in_a_column_are_not_invented_into_one_number():
    words = [_word("12", 200, 212), _word("34", 214, 226)]  # 2pt apart: too far to be one number
    values, joined = _assign_cells(words, [220.0, 300.0])
    assert values[0] == "12|34"
    assert joined is False
    assert _cell_status(values[0]) == "malformed"


@pytest.mark.parametrize("raw, expected", [
    ("1,234", "value"), ("154948", "value"), ("0", "value"), ("-", "dash"), ("n.a", "not_available"),
    ("n/r", "not_reported"), ("", "blank"), ("1,23", "malformed"), ("12,34,56", "malformed"),
])
def test_cell_status(raw, expected):
    assert _cell_status(raw) == expected


def test_label_matching_ignores_stray_tokens_but_never_guesses():
    known = ["Land Vehicle", "Land Vehicle (Small)", "Lorry Trailer / Bowser", "Grade A", "Total"]
    assert _match_label("Land Vehicle (Small)", known) == "Land Vehicle (Small)"
    assert _match_label("/ / Lorry Trailer / Bowser", known) == "Lorry Trailer / Bowser"
    assert _match_label("A A Grade A", known) == "Grade A"
    assert _match_label("Some Unknown Vehicle", known) is None


# --- Real PDFs ----------------------------------------------------------------

@pytest.fixture(scope="module")
def extracted():
    cell_objects, issues = extract_all()
    return pd.DataFrame([asdict(c) for c in cell_objects]), issues


def _table(cells, district, table_id):
    subset = cells[(cells["district"] == district) & (cells["table_id"] == table_id)]
    return subset.pivot(index="row_label", columns="year", values="value_raw")


@needs_pdfs
def test_anuradhapura_licences_are_recovered(extracted):
    table = _table(extracted[0], "Anuradhapura", "9.3")
    assert list(table.loc["Motor Bicycles"]) == ["181790", "176189", "181442", "185110", "186540"]
    assert list(table.loc["Motor Cars"]) == ["17109", "15622", "18479", "18184", "18137"]
    assert list(table.loc["Three Weelers"]) == ["38834", "35157", "36420", "34887", "35679"]


@needs_pdfs
def test_badulla_matches_values_read_from_the_rendered_page(extracted):
    table = _table(extracted[0], "Badulla", "9.4")
    assert list(table.loc["Motor Cycle"]) == ["6,559", "3,902", "219", "603", "280"]
    assert list(table.loc["Car"]) == ["525", "355", "70", "21", "15"]


@needs_pdfs
def test_trincomalee_page_header_is_not_read_as_data(extracted):
    cells = extracted[0]
    table = _table(cells, "Trincomalee", "9.4")
    assert list(table.columns) == [2019, 2020, 2021, 2022, 2023]
    assert list(table.loc["Motor Cycle"]) == ["6192", "3751", "118", "129", "534"]
    assert list(table.loc["Other Special Purpose Vehicle"]) == ["-", "-", "-", "-", "-"]


@needs_pdfs
def test_grade_a_is_kept_as_printed_and_not_mapped_to_car(extracted):
    cells, issues = extracted
    grade_a = cells[(cells["district"] == "Trincomalee") & (cells["row_label"] == "Grade A")]
    assert list(grade_a["value_raw"]) == ["138", "103", "15", "4", "7"]
    assert set(grade_a["vehicle_type"]) == {""}
    assert any(i["district"] == "Trincomalee" and i["detail"] == "Car" for i in issues)


@needs_pdfs
def test_total_row_extracted_for_every_table_and_year(extracted):
    totals = extracted[0][extracted[0]["is_total_row"]]
    assert len(totals) == 25 * 2 * 5
    assert set(totals["cell_status"]) == {"value"}
    assert set(totals["vehicle_type"]) == {""}  # never treated as a vehicle category


@needs_pdfs
def test_every_column_adds_up_to_its_printed_total(extracted):
    """Independent proof that values are in the right rows and columns."""
    numbers = extracted[0].assign(number=pd.to_numeric(extracted[0]["value_numeric"], errors="coerce"))
    keys = ["district", "table_id", "year"]
    totals = numbers[numbers["is_total_row"]].set_index(keys)["number"]
    sums = numbers[~numbers["is_total_row"]].groupby(keys)["number"].sum()
    assert len(totals) == 250
    assert (sums - totals).abs().max() == 0


@needs_pdfs
def test_all_three_study_categories_present_except_documented_gap(extracted):
    cells = extracted[0]
    found = cells.groupby(["metric", "vehicle_type"])["district"].nunique()
    assert found["vehicle_population", "Motorcycle"] == 25
    assert found["vehicle_population", "Car"] == 25
    assert found["vehicle_population", "Three-wheeler"] == 25
    assert found["new_registrations", "Motorcycle"] == 25
    assert found["new_registrations", "Three-wheeler"] == 25
    assert found["new_registrations", "Car"] == 24  # Trincomalee prints "Grade A" instead


@needs_pdfs
def test_only_the_documented_structural_issues_remain(extracted):
    assert sorted((i["district"], i["check_id"], i["detail"]) for i in extracted[1]) == [
        ("Hambantota", "missing_expected_label", "Ambulance"),
        ("Trincomalee", "missing_expected_label", "Car"),
        ("Trincomalee", "missing_expected_label", "Motor Lorry (Commercial)"),
    ]


@needs_pdfs
def test_printed_non_numbers_are_kept_as_printed_never_zeroed(extracted):
    cells = extracted[0]
    assert (cells[cells["cell_status"] != "value"]["value_numeric"] == "").all()
    galle = cells[(cells["district"] == "Galle") & (cells["row_label"] == "Commercial (Bus)") & (cells["year"] == 2020)]
    assert galle.iloc[0]["cell_status"] == "not_reported"
    ampara = cells[(cells["district"] == "Ampara") & (cells["row_label"] == "Motor Tricycle Van") & (cells["year"] == 2019)]
    assert ampara.iloc[0]["value_raw"] == "n.a"
    assert ampara.iloc[0]["cell_status"] == "not_available"


@needs_pdfs
def test_every_cell_has_provenance(extracted):
    cells = extracted[0]
    for column in ["source_id", "source_file", "pdf_sha256", "source_url", "retrieved_date"]:
        assert (cells[column] != "").all(), column


@needs_pdfs
def test_v1_parser_output_is_not_affected_by_v2():
    """v2 is a separate module, so Dataset v1 stays reproducible."""
    from src.data.extract_dcs_handbook import parse_multi_year_table

    _, rows = parse_multi_year_table(RAW_DIR / "DCS_Anuradhapura_2024_T9_3.pdf")
    assert dict(rows)["Motor Cars"] == ["-", "-", "-", "-", "18137"]


# --- Validation checks, on small artificial tables ----------------------------

def _frame(rows):
    """rows: (district, metric, year, row_label, vehicle_type, number, is_total)"""
    df = pd.DataFrame(rows, columns=["district", "metric", "year", "row_label", "vehicle_type", "number", "is_total_row"])
    df["source_file"] = "test.pdf"
    df["page"] = 1
    df["cell_status"] = df["number"].map(lambda n: "value" if pd.notna(n) else "dash")
    df["value_raw"] = df["number"].map(lambda n: "-" if pd.isna(n) else str(n))
    df["source_note"] = "Source - Divisional secretary's office"
    return df


LICENCE = "vehicle_population"
REGISTRATION = "new_registrations"


def test_sum_check_flags_a_mismatch_and_passes_a_match():
    good = _frame([("A", LICENCE, 2020, "Cars", "Car", 10, False), ("A", LICENCE, 2020, "Total", "", 10, True)])
    assert check_sum_to_total(good, 0) == []
    bad = _frame([("A", LICENCE, 2020, "Cars", "Car", 9, False), ("A", LICENCE, 2020, "Total", "", 10, True)])
    assert [f["check_id"] for f in check_sum_to_total(bad, 0)] == ["sum_differs_from_total"]


def test_identical_year_columns_are_flagged():
    labels = ["a", "b", "c", "d", "e"]
    rows = [("A", LICENCE, year, label, "", 100 + i, False) for year in (2022, 2023) for i, label in enumerate(labels)]
    flags = check_identical_year_columns(_frame(rows), 5)
    assert [(f["check_id"], f["year"]) for f in flags] == [("identical_year_columns", 2023)]


def test_one_changed_value_means_columns_are_not_identical():
    labels = ["a", "b", "c", "d", "e"]
    rows = [("A", LICENCE, 2022, label, "", 100 + i, False) for i, label in enumerate(labels)]
    rows += [("A", LICENCE, 2023, label, "", 100 + i + (i == 4), False) for i, label in enumerate(labels)]
    assert check_identical_year_columns(_frame(rows), 5) == []


def test_copy_between_districts_is_flagged_for_both():
    labels = ["a", "b", "c", "d", "e"]
    rows = [("A", LICENCE, 2019, label, "", 100 + i, False) for i, label in enumerate(labels)]
    rows += [("B", LICENCE, 2020, label, "", 100 + i, False) for i, label in enumerate(labels)]
    flags = check_identical_columns_across_districts(_frame(rows), 5)
    assert sorted(f["district"] for f in flags) == ["A", "B"]


def test_licence_column_repeating_registrations_is_flagged():
    rows = [("A", LICENCE, 2019, label, "", value, False) for label, value in zip("abcd", (11, 22, 33, 44))]
    rows += [("A", REGISTRATION, 2019, label, "", value, False) for label, value in zip("wxyz", (11, 22, 33, 44))]
    assert [f["district"] for f in check_licences_copied_from_registrations(_frame(rows), 4, 10)] == ["A"]


def test_year_on_year_is_judged_against_the_same_year_median():
    """A 40% fall across all districts is a national pattern; the same fall in one
    district alone is an anomaly."""
    together = _frame([
        (d, LICENCE, y, "Cars", "Car", v, False)
        for d in "ABC" for y, v in ((2019, 1000), (2020, 600))
    ])
    assert check_year_on_year_against_national_pattern(together, 0.25, 100) == []

    alone = _frame([
        (d, LICENCE, y, "Cars", "Car", v, False)
        for d, vs in {"A": (1000, 1010), "B": (1000, 1020), "C": (1000, 600)}.items()
        for y, v in zip((2019, 2020), vs)
    ])
    flags = check_year_on_year_against_national_pattern(alone, 0.25, 100)
    assert [f["district"] for f in flags] == ["C"]


def test_dip_between_neighbours_is_flagged():
    rows = [("A", LICENCE, y, "Bikes", "Motorcycle", v, False)
            for y, v in ((2020, 133106), (2021, 13091), (2022, 133837))]
    flags = check_dips_and_spikes(_frame(rows), 0.5)
    assert [(f["check_id"], f["year"]) for f in flags] == [("dip_between_neighbours", 2021)]


def test_registrations_large_against_licences_are_flagged():
    rows = [("A", REGISTRATION, 2019, "Car", "Car", 16778, False), ("A", LICENCE, 2019, "Motor Cars", "Car", 19371, False)]
    assert [f["check_id"] for f in check_registrations_against_licences(_frame(rows), 0.5)] == [
        "registrations_high_vs_licences"]


def test_national_checks_flag_only_an_excess():
    over = _frame([("A", REGISTRATION, 2022, "Three Wheeler", "Three-wheeler", 415, False)])
    assert [f["year"] for f in check_against_dmt_national(over)] == [2022]
    totals = _frame([("A", REGISTRATION, 2021, "Total", "", 34261, True), ("A", REGISTRATION, 2022, "Total", "", 20488, True)])
    assert [f["year"] for f in check_totals_against_dmt_national(totals, {2021: 33850, 2022: 20511})] == [2021]


def test_missing_cells_are_flagged_with_licences_more_severe():
    rows = [("A", LICENCE, 2019, "Cars", "Car", None, False), ("A", REGISTRATION, 2019, "Car", "Car", None, False)]
    severities = {f["metric"]: f["severity"] for f in check_missing_category_cells(_frame(rows))}
    assert severities == {LICENCE: "high", REGISTRATION: "low"}


def test_validate_never_changes_the_cells(extracted):
    cells = extracted[0]
    before = cells.copy(deep=True)
    flags = validate(cells, extracted[1], load_config())
    pd.testing.assert_frame_equal(cells, before)
    assert list(flags.columns) == FLAG_COLUMNS


# --- Flags on the real tables, and the documented anomalies -------------------

@pytest.fixture(scope="module")
def real_flags(extracted):
    return validate(extracted[0], extracted[1], load_config())


@needs_pdfs
@pytest.mark.parametrize("check_id, district, year", [
    ("licences_match_registrations", "Ampara", 2019),
    ("dip_between_neighbours", "Jaffna", 2021),
    ("identical_year_columns", "Kandy", 2023),
    ("column_identical_to_other_district", "Mullaitivu", 2019),
    ("column_identical_to_other_district", "Kilinochchi", 2020),
    ("yoy_against_national_pattern", "Badulla", 2020),
    ("yoy_against_national_pattern", "Kilinochchi", 2023),
    ("yoy_against_national_pattern", "Kalutara", 2022),
    ("yoy_against_national_pattern", "Gampaha", 2020),
    ("registrations_high_vs_licences", "Puttalam", 2019),
    ("largest_registration_not_motorcycle", "Jaffna", 2019),
    ("largest_registration_not_motorcycle", "Kandy", 2019),
])
def test_known_anomalies_are_detected(real_flags, check_id, district, year):
    match = real_flags[(real_flags["check_id"] == check_id) & (real_flags["district"] == district) & (real_flags["year"] == year)]
    assert not match.empty


@needs_pdfs
def test_no_sum_failures_on_the_real_tables(real_flags):
    assert not real_flags["check_id"].isin(["sum_differs_from_total", "total_row_unusable"]).any()


@needs_pdfs
def test_corrections_file_quotes_values_exactly_as_printed(extracted):
    """A proposed correction must cite what the PDF really prints."""
    cells = extracted[0]
    corrections = pd.read_csv(CORRECTIONS_CSV, dtype=str, keep_default_na=False)
    assert corrections["anomaly_id"].is_unique
    checked = 0
    for row in corrections.itertuples():
        if not row.printed_values:
            continue
        for item in row.printed_values.split(";"):
            label_year, printed = item.split("=")
            label, year = label_year.rsplit("@", 1)
            match = cells[(cells["district"] == row.district) & (cells["metric"] == row.metric)
                          & (cells["row_label"] == label) & (cells["year"] == int(year))]
            assert len(match) == 1, item
            assert match.iloc[0]["value_raw"].replace(",", "") == printed.replace(",", ""), (row.anomaly_id, item)
            checked += 1
    assert checked > 40


# --- Outputs go only where they are told --------------------------------------

def test_writer_refuses_the_v1_output_path():
    with pytest.raises(ValueError):
        write_cells_csv([], V1_INTERIM_CSV)


@needs_pdfs
def test_run_writes_only_to_given_paths_and_leaves_v1_and_pdfs_alone(tmp_path):
    protected = [V1_INTERIM_CSV, RAW_DIR / "DCS_Anuradhapura_2024_T9_3.pdf"]
    before = {path: (_sha256(path), path.stat().st_mtime_ns) for path in protected}

    summary = run(
        cells_csv=tmp_path / "cells.csv",
        flags_csv=tmp_path / "flags.csv",
        v1_diff_csv=tmp_path / "differences.csv",
        totals_csv=tmp_path / "totals.csv",
    )

    assert summary["cells"] == 3370
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cells.csv", "differences.csv", "flags.csv", "totals.csv"]
    assert {path: (_sha256(path), path.stat().st_mtime_ns) for path in protected} == before


@needs_pdfs
def test_comparison_with_v1_finds_the_recovered_licences(extracted):
    differences = compare_with_v1(extracted[0])
    recovered = differences[(differences["difference"] == "recovered_value_v1_lost")
                            & (differences["metric"] == LICENCE) & differences["vehicle_type"].isin(["Motorcycle", "Car", "Three-wheeler"])]
    assert set(recovered["district"]) == {"Anuradhapura"}
    assert len(recovered) == 12


# --- Approved decisions -------------------------------------------------------

@pytest.fixture(scope="module")
def corrections():
    return pd.read_csv(CORRECTIONS_CSV, dtype=str, keep_default_na=False).set_index("anomaly_id")


def test_only_clearly_incorrect_licences_are_set_to_missing(corrections):
    set_missing = corrections[corrections["decision_status"] == "approved_set_missing"]
    assert sorted(set_missing.index) == ["L01", "L02"]
    assert (set_missing["cells_to_set_missing"] != "").all()
    others = corrections[corrections["decision_status"] != "approved_set_missing"]
    assert (others["cells_to_set_missing"] == "").all()


@pytest.mark.parametrize("anomaly_id", ["L03", "L04", "L06"])
def test_uncertain_licences_stay_flagged_not_deleted(corrections, anomaly_id):
    assert corrections.loc[anomaly_id, "decision_status"] == "approved_keep_flagged"


def test_grade_a_stays_unresolved(corrections):
    assert corrections.loc["R07", "decision_status"] == "unresolved"


def test_dashes_stay_missing(corrections):
    assert corrections.loc["D01", "decision_status"] == "approved_keep_missing"


def test_every_decision_records_its_source_and_date(corrections):
    assert (corrections["decision"] != "").all()
    assert (corrections["decision_date"] != "").all()
    named = corrections[corrections["district"] != "ALL"]
    assert (named["source_pdf"] != "").all()
    assert "proposed" not in set(corrections["decision_status"])


@needs_pdfs
def test_source_pdfs_named_in_corrections_exist(corrections):
    for name in corrections.loc[corrections["source_pdf"] != "", "source_pdf"]:
        assert (RAW_DIR / name).exists(), name


@needs_pdfs
def test_cells_to_set_missing_exist_with_a_printed_value(extracted, corrections):
    cells = extracted[0]
    for row in corrections[corrections["cells_to_set_missing"] != ""].itertuples():
        for item in row.cells_to_set_missing.split(";"):
            label, year = item.rsplit("@", 1)
            match = cells[(cells["district"] == row.district) & (cells["metric"] == row.metric)
                          & (cells["row_label"] == label) & (cells["year"] == int(year))]
            assert len(match) == 1, item
            assert match.iloc[0]["cell_status"] == "value", item
            assert f"{item}=" in row.printed_values, item  # the original value is on record


@needs_pdfs
def test_extraction_keeps_values_as_printed_because_decisions_apply_later(extracted):
    cells = extracted[0]
    ampara = cells[(cells["district"] == "Ampara") & (cells["row_label"] == "Motor Bicycles") & (cells["year"] == 2019)]
    jaffna = cells[(cells["district"] == "Jaffna") & (cells["row_label"] == "Motor Bicycles") & (cells["year"] == 2021)]
    assert ampara.iloc[0]["value_raw"] == "9,057"
    assert jaffna.iloc[0]["value_raw"] == "13091"


@needs_pdfs
def test_every_validation_flag_has_a_documented_decision(extracted, corrections):
    """A new flag with no decision fails here, so problems cannot go undocumented."""
    config = load_config()
    flags = validate(extracted[0], extracted[1], config)
    reviewed = review_flags(flags, config["flag_review"], corrections.reset_index())
    undocumented = reviewed[(reviewed["anomaly_id"] == "") | (reviewed["decision_status"] == "")]
    assert undocumented.empty, undocumented[["check_id", "district", "year"]].to_string()


def test_flag_without_a_rule_is_left_visible():
    flags = pd.DataFrame([_flag_row("new_kind_of_problem")])
    decisions = pd.DataFrame({"anomaly_id": ["L01"], "decision_status": ["approved_set_missing"]})
    reviewed = review_flags(flags, [{"check_id": "other", "anomaly_id": "L01"}], decisions)
    assert reviewed.iloc[0]["anomaly_id"] == ""


def _flag_row(check_id):
    return dict(zip(FLAG_COLUMNS, [check_id, "high", "A", LICENCE, 2020, "", "", "", "", ""]))


@needs_pdfs
def test_every_registration_total_has_a_verification_status(extracted):
    table = verify_total_registrations(_with_numbers(extracted[0]), load_config())
    assert len(table) == 125
    assert set(table["verification_status"]) <= {TOTAL_VERIFIED, TOTAL_YEAR_CAVEAT, TOTAL_FLAGGED}
    assert table["sum_matches"].all()
    assert table["printed_total"].notna().all()  # nothing invented or removed


@needs_pdfs
def test_anuradhapura_totals_that_add_up_are_still_flagged(extracted):
    table = verify_total_registrations(_with_numbers(extracted[0]), load_config())
    flagged = table[(table["district"] == "Anuradhapura") & (table["verification_status"] == TOTAL_FLAGGED)]
    assert sorted(flagged["year"]) == [2019, 2020, 2021]


@needs_pdfs
def test_2021_carries_the_national_caveat(extracted):
    table = verify_total_registrations(_with_numbers(extracted[0]), load_config())
    assert set(table[table["year"] == 2021]["verification_status"]) == {TOTAL_YEAR_CAVEAT, TOTAL_FLAGGED}
    assert TOTAL_YEAR_CAVEAT not in set(table[table["year"] != 2021]["verification_status"])


def test_peer_check_flags_a_total_far_from_other_districts():
    rows = []
    for district, registrations in {"A": 100, "B": 110, "C": 90, "D": 10}.items():
        rows.append((district, REGISTRATION, 2020, "Total", "", registrations, True))
        rows.append((district, LICENCE, 2020, "Total", "", 1000, True))
    flags = check_total_registrations_against_peers(_frame(rows), 1.0)
    assert [f["district"] for f in flags] == ["D"]
