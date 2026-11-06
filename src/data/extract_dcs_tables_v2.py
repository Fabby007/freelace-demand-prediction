"""Version 2 extraction of DCS handbook Tables 9.3 and 9.4 from local PDFs.

Replaces nothing: `extract_dcs_handbook.py` and its output stay as they are, so
Dataset v1 remains reproducible (REF-009 ADR-036). This module never uses the
network and never edits a PDF.

Differences from v1, each fixing an observed failure:

- Rows come from the PDF's horizontal ruling lines, so a value and its label
  stay together even when they sit on different text lines. v1 lost the first
  four values of every Anuradhapura Table 9.3 row this way.
- The year header is read separately on each page, so a repeated page header is
  no longer read as data.
- An empty cell stays blank. v1 wrote "-" for it, which looks like a printed dash.
- `n.a` is kept as printed.
- The printed Total row is extracted, as `is_total_row`.
- Labels are matched to a fixed list of table rows. Anything else is reported,
  never guessed.

Printed values are never corrected here. See `validate_dcs_extraction.py`.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "dcs_handbooks"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CONFIGS_DIR = REPO_ROOT / "configs"
CONFIG_YAML = CONFIGS_DIR / "dcs_extraction_v2.yaml"
VEHICLE_LOOKUP_CSV = CONFIGS_DIR / "vehicle_category_lookup.csv"
V1_INTERIM_CSV = INTERIM_DIR / "dcs_multi_district_2024_raw.csv"
V2_CELLS_CSV = INTERIM_DIR / "dcs_extracted_cells_2024_v2.csv"

STATUS_VALUE = "value"
STATUS_DASH = "dash"
STATUS_NOT_AVAILABLE = "not_available"
STATUS_NOT_REPORTED = "not_reported"
STATUS_BLANK = "blank"
STATUS_MALFORMED = "malformed"

_YEAR = re.compile(r"^(19|20)\d{2}$")
_VALUE_TOKEN = re.compile(r"^(?:[\d,]+|-|n/r|n\.a)$", re.IGNORECASE)
_WELL_FORMED_NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)$")
_TABLE_FILE = re.compile(r"^DCS_(?P<district>.+)_(?P<edition>\d{4})_T9_(?P<table>[34])$")
_ROW_TOLERANCE = 1.5
_MIN_BAND_HEIGHT = 3.0
# Fragments of one number sit on one text line; further apart they are separate entries.
_SAME_LINE_TOLERANCE = 3.0
_MAX_FRAGMENT_GAP = 1.0
_NUMERIC_FRAGMENT = re.compile(r"^[\d,]+$")
# English text printed in one word after Sinhala/Tamil text, e.g. "<Sinhala>-Total".
_TRAILING_ENGLISH = re.compile(r"[A-Za-z]{3,}$")
# A value can be misaligned towards the label column by up to this many column widths.
_VALUE_REGION_COLUMNS = 0.75
_MIN_RULE_WIDTH = 20


@dataclass
class ParsedRow:
    label: str | None  # matched label, or None when it could not be resolved
    label_text: str  # the English words found in the row, as printed
    values: list[str]
    statuses: list[str]
    page: int
    fragments_joined: bool = False


@dataclass
class ParsedTable:
    years: list[int] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    total: ParsedRow | None = None
    title: str = ""
    source_note: str = ""
    english_text: str = ""  # all English text in the PDF, used to confirm the district
    issues: list[tuple[str, str]] = field(default_factory=list)  # (check_id, detail)


def load_config(path: Path = CONFIG_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _is_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def _text_rows(words: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - word["top"]) <= _ROW_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    return rows


def _find_year_header(rows: list[list[dict]]) -> tuple[list[dict], int] | None:
    """The first text row with at least three consecutive years. This excludes
    title ranges such as "2019 - 2023" and value rows such as 2057, 2000, 2057."""
    for index, row in enumerate(rows):
        year_words = [w for w in row if _YEAR.match(w["text"])]
        numbers = [int(w["text"]) for w in year_words]
        if len(numbers) >= 3 and all(b - a == 1 for a, b in zip(numbers, numbers[1:])):
            return year_words, index
    return None


def _horizontal_rules(page) -> list[float]:
    positions = sorted(e["top"] for e in page.edges if e["orientation"] == "h" and e["width"] > _MIN_RULE_WIDTH)
    rules: list[float] = []
    for y in positions:
        if not rules or y - rules[-1] > _MIN_BAND_HEIGHT:
            rules.append(y)
    return rules


def _center(word: dict) -> float:
    return (word["top"] + word["bottom"]) / 2


def _match_label(label_text: str, known_labels: list[str]) -> str | None:
    """The longest known label that ends the row's English text. Wrapped lines
    are joined first; stray tokens from the translation lines come earlier."""
    cleaned = " ".join(label_text.split())
    for label in sorted(known_labels, key=len, reverse=True):
        if cleaned == label or cleaned.endswith(" " + label):
            return label
    return None


def _cell_status(value: str) -> str:
    lowered = value.lower()
    if value == "":
        return STATUS_BLANK
    if value == "-":
        return STATUS_DASH
    if lowered == "n.a":
        return STATUS_NOT_AVAILABLE
    if lowered == "n/r":
        return STATUS_NOT_REPORTED
    return STATUS_VALUE if _WELL_FORMED_NUMBER.match(value) else STATUS_MALFORMED


def _merge_touching_fragments(value_words: list[dict]) -> tuple[list[dict], bool]:
    """Rejoin one number that the PDF split into touching words ('1' + '07,285').
    Measured across the PDFs, such fragments are at most 0.1pt apart and separate
    columns at least 18.9pt apart, so the split is unambiguous."""
    merged: list[dict] = []
    joined_any = False
    for word in sorted(value_words, key=lambda w: w["x0"]):
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and abs(previous["top"] - word["top"]) <= _SAME_LINE_TOLERANCE
            and abs(word["x0"] - previous["x1"]) <= _MAX_FRAGMENT_GAP
            and _NUMERIC_FRAGMENT.match(previous["text"])
            and _NUMERIC_FRAGMENT.match(word["text"])
        ):
            merged[-1] = {**previous, "text": previous["text"] + word["text"], "x1": word["x1"]}
            joined_any = True
        else:
            merged.append(dict(word))
    return merged, joined_any


def _assign_cells(value_words: list[dict], columns_x1: list[float]) -> tuple[list[str], bool]:
    """Place each value in the nearest column by right edge. Two separate values
    landing in one column are kept visibly joined with '|', which marks the cell
    malformed rather than inventing a number from them."""
    merged, joined_any = _merge_touching_fragments(value_words)
    columns: list[list[str]] = [[] for _ in columns_x1]
    for word in sorted(merged, key=lambda w: w["x0"]):
        nearest = min(range(len(columns_x1)), key=lambda i: abs(columns_x1[i] - word["x1"]))
        columns[nearest].append(word["text"])
    return ["|".join(column) for column in columns], joined_any


def _parse_page(page, page_index: int, table: ParsedTable, known_labels: list[str], total_label: str) -> None:
    words = page.extract_words()
    rows = _text_rows(words)
    table.english_text += " " + " ".join(w["text"] for w in words if _is_ascii(w["text"]))
    header = _find_year_header(rows)
    if header is None:
        table.issues.append(("no_year_header", f"page {page_index + 1}"))
        return
    year_words, header_index = header

    page_years = [int(w["text"]) for w in year_words]
    if not table.years:
        table.years = page_years
        table.title = " ".join(
            w["text"] for row in rows[:header_index] for w in row if _is_ascii(w["text"])
        )
    elif page_years != table.years:
        table.issues.append(("year_header_mismatch", f"page {page_index + 1}: {page_years} vs {table.years}"))

    for row in rows[header_index:]:
        text = " ".join(w["text"] for w in row if _is_ascii(w["text"]))
        if text.lower().startswith("source"):
            table.source_note = text

    rules = _horizontal_rules(page)
    header_y = _center(year_words[0])
    bands = [(a, b) for a, b in zip(rules, rules[1:]) if a > header_y]
    if not bands:
        table.issues.append(("no_ruling_lines", f"page {page_index + 1}"))
        return

    # A band below the header row can still hold "Type of Vehicle"; such a band has no value words.
    spacing = statistics.median(b["x1"] - a["x1"] for a, b in zip(year_words, year_words[1:]))
    band_words = [[w for w in words if a <= _center(w) < b] for a, b in bands]

    def value_words_in(cell_words: list[dict], first_column_x1: float) -> list[dict]:
        boundary = first_column_x1 - _VALUE_REGION_COLUMNS * spacing
        return [w for w in cell_words if w["x1"] >= boundary and _VALUE_TOKEN.match(w["text"])]

    # Calibrate columns from rows holding exactly one value per year. Header text
    # is offset from the data, so it is only a starting point for finding them.
    n_years = len(page_years)
    rough_first = year_words[0]["x1"] + spacing * 0.25
    complete = []
    for cell_words in band_words:
        found, _ = _merge_touching_fragments(value_words_in(cell_words, rough_first))
        found.sort(key=lambda w: w["x0"])
        if len(found) == n_years:
            complete.append([w["x1"] for w in found])
    if complete:
        columns_x1 = [statistics.median(col) for col in zip(*complete)]
    else:
        columns_x1 = [w["x1"] for w in year_words]
        table.issues.append(("columns_not_calibrated", f"page {page_index + 1}"))

    for cell_words in band_words:
        value_words = value_words_in(cell_words, columns_x1[0])
        if not value_words:
            continue

        value_ids = {id(w) for w in value_words}
        boundary = columns_x1[0] - _VALUE_REGION_COLUMNS * spacing
        stray = [
            w["text"] for w in cell_words
            if id(w) not in value_ids and w["x1"] >= boundary and _is_ascii(w["text"]) and re.search(r"\d", w["text"])
        ]

        label_words = []
        for text_row in _text_rows([w for w in cell_words if id(w) not in value_ids]):
            for w in text_row:
                if w["x1"] >= boundary:
                    continue
                if _is_ascii(w["text"]):
                    if re.search(r"[A-Za-z/]", w["text"]):
                        label_words.append(w["text"].lstrip("-"))
                else:
                    trailing = _TRAILING_ENGLISH.search(w["text"])
                    if trailing:
                        label_words.append(trailing.group())
        label_text = " ".join(label_words).strip()

        values, joined = _assign_cells(value_words, columns_x1)
        row = ParsedRow(
            label=_match_label(label_text, known_labels + [total_label]),
            label_text=label_text,
            values=values,
            statuses=[_cell_status(v) for v in values],
            page=page_index + 1,
            fragments_joined=joined,
        )
        if stray:
            table.issues.append(("unread_text_in_value_column", f"{label_text!r}: {stray}"))
        if row.label == total_label:
            if table.total is not None:
                table.issues.append(("duplicate_total_row", f"page {page_index + 1}"))
            table.total = row
        else:
            table.rows.append(row)


def parse_table_pdf(pdf_path: Path, table_id: str, config: dict | None = None) -> ParsedTable:
    """Parse one Table 9.3/9.4 PDF. Structural problems are recorded in
    `ParsedTable.issues`, never hidden and never repaired by guessing."""
    import pdfplumber

    config = config or load_config()
    spec = config["tables"][table_id]
    known_labels = spec["labels"] + spec["optional_labels"]
    total_label = config["total_label"]

    table = ParsedTable()
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            _parse_page(page, page_index, table, known_labels, total_label)

    seen: set[str] = set()
    for row in table.rows:
        if row.label is None:
            table.issues.append(("unrecognised_label", f"{row.label_text!r} on page {row.page}: {row.values}"))
        elif row.label in seen:
            table.issues.append(("duplicate_label", f"{row.label!r} on page {row.page}"))
        else:
            seen.add(row.label)
    for label in spec["labels"]:
        if label not in seen:
            table.issues.append(("missing_expected_label", label))
    if table.total is None:
        table.issues.append(("missing_total_row", ""))
    if table.years != config["expected_years"]:
        table.issues.append(("unexpected_years", str(table.years)))
    if spec["title_keyword"].lower() not in table.title.lower():
        table.issues.append(("title_mismatch", table.title))
    return table


def _numeric(value: str, status: str) -> str:
    return value.replace(",", "") if status == STATUS_VALUE else ""


def _load_provenance(v1_csv: Path) -> dict[str, tuple[str, str]]:
    """source_id -> (source_url, retrieved_date), recorded when the PDFs were downloaded."""
    provenance: dict[str, tuple[str, str]] = {}
    if v1_csv.exists():
        with open(v1_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                provenance.setdefault(row["source_id"], (row["source_url"], row["retrieved_date"]))
    return provenance


def _load_vehicle_lookup(path: Path = VEHICLE_LOOKUP_CSV) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {row["raw_name"].strip(): row["canonical_name"].strip() for row in csv.DictReader(f)}


def _district_names(path: Path = CONFIGS_DIR / "dcs_district_url_segments.csv") -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {row["canonical_district"].strip().replace(" ", ""): row["canonical_district"].strip()
                for row in csv.DictReader(f)}


@dataclass(frozen=True)
class Cell:
    district: str
    year: int
    metric: str
    table_id: str
    row_label: str
    vehicle_type: str
    is_total_row: bool
    value_raw: str
    value_numeric: str
    cell_status: str
    fragments_joined: bool
    page: int
    source_id: str
    source_file: str
    pdf_sha256: str
    source_url: str
    retrieved_date: str
    source_note: str
    handbook_edition_year: int


def extract_all(raw_dir: Path = RAW_DIR, config: dict | None = None,
                v1_csv: Path = V1_INTERIM_CSV) -> tuple[list[Cell], list[dict]]:
    """Parse every Table 9.3/9.4 PDF in raw_dir. Returns (cells, structural_issues)."""
    config = config or load_config()
    vehicle_lookup = _load_vehicle_lookup()
    districts = _district_names()
    provenance = _load_provenance(v1_csv)
    cells: list[Cell] = []
    issues: list[dict] = []

    for pdf_path in sorted(raw_dir.glob("DCS_*_T9_[34].pdf")):
        match = _TABLE_FILE.match(pdf_path.stem)
        if match is None or int(match["edition"]) != config["handbook_edition_year"]:
            continue
        district = districts.get(match["district"], match["district"])
        table_id = f"9.{match['table']}"
        metric = config["tables"][table_id]["metric"]
        source_id = pdf_path.stem
        url, retrieved = provenance.get(source_id, ("", ""))
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

        table = parse_table_pdf(pdf_path, table_id, config)
        if match["district"].lower() not in table.english_text.replace(" ", "").lower():
            table.issues.append(("district_not_named_in_pdf", match["district"]))
        for check_id, detail in table.issues:
            issues.append({"check_id": check_id, "district": district, "metric": metric,
                           "table_id": table_id, "detail": detail, "source_file": pdf_path.name})

        all_rows = table.rows + ([table.total] if table.total is not None else [])
        for row in all_rows:
            is_total = row is table.total
            label = row.label if row.label is not None else row.label_text
            for year, value, status in zip(table.years, row.values, row.statuses):
                cells.append(Cell(
                    district=district, year=year, metric=metric, table_id=table_id,
                    row_label=label,
                    vehicle_type="" if is_total else vehicle_lookup.get(row.label or "", ""),
                    is_total_row=is_total, value_raw=value, value_numeric=_numeric(value, status),
                    cell_status=status, fragments_joined=row.fragments_joined, page=row.page,
                    source_id=source_id, source_file=pdf_path.name, pdf_sha256=digest,
                    source_url=url, retrieved_date=retrieved, source_note=table.source_note,
                    handbook_edition_year=int(match["edition"]),
                ))
    return cells, issues


def write_cells_csv(cells: list[Cell], out_path: Path) -> None:
    if out_path.resolve() == V1_INTERIM_CSV.resolve():
        raise ValueError(f"Refusing to overwrite the Dataset v1 extraction: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(Cell.__dataclass_fields__))
        writer.writeheader()
        for cell in cells:
            writer.writerow(asdict(cell))
    logger.info("Wrote %d cells to %s", len(cells), out_path)
