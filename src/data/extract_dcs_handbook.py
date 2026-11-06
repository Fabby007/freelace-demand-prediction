"""Extraction of DCS District Statistical Handbook vehicle-registration tables.

Implements DEV-003 (Data Acquisition & Extraction Pipeline), Section 10 steps 2-7
and the Section 10.1 Kandy proof-of-concept -> multi-district scale-up sequence.

Source URL pattern discovered and verified 2026-08-15 (see
data/source_register.csv and specs/development/DEV-003-data-acquisition.md):

    https://www.statistics.gov.lk/HandBook/{url_segment}/{year}
        -> cover PDF, links to Chapter01..Chapter12 PDFs
    https://www.statistics.gov.lk/statistical%20Hbook/{year}/{url_segment}/Chapter09.pdf
        -> Transport chapter index, links to tables 9.1-9.5
    https://www.statistics.gov.lk/statistical%20Hbook/{year}/{url_segment}/9.4.pdf
        -> "New Vehicle Registrations in District" table (multi-year columns)
    https://www.statistics.gov.lk/statistical%20Hbook/{year}/{url_segment}/9.3.pdf
        -> "No. of Revenue License issued for Motor Vehicles in District" table
           (used as the vehicle_population/stock proxy - REF-001)

This module only extracts raw observations. It intentionally does NOT normalize
district/vehicle-category names or convert "-" to 0 - that is DEV-004's job
(REF-002, source doc Section 11). Raw PDF text is preserved verbatim per row.
"""
from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "dcs_handbooks"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
URL_SEGMENTS_CSV = REPO_ROOT / "configs" / "dcs_district_url_segments.csv"

USER_AGENT = "Mozilla/5.0 (compatible; MechanicDemandProject/1.0; academic research)"
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite to a public government server

TABLE_IDS = {
    "new_registrations": "9.4",
    "vehicle_stock": "9.3",
}


@dataclass(frozen=True)
class RawObservation:
    district_raw: str
    district_canonical: str
    year: int
    vehicle_type_raw: str
    value_raw: str
    metric: str  # "new_registrations" | "vehicle_population"
    source_id: str
    source_url: str
    retrieved_date: str
    handbook_edition_year: int


def load_url_segments() -> dict[str, list[str]]:
    """Load canonical_district -> ordered list of URL segments to try."""
    segments: dict[str, list[str]] = {}
    with open(URL_SEGMENTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            canonical = row["canonical_district"].strip()
            segment = row["url_segment"].strip()
            segments.setdefault(canonical, [])
            if segment not in segments[canonical]:
                segments[canonical].append(segment)
    return segments


def _get(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None
    time.sleep(REQUEST_DELAY_SECONDS)
    if resp.status_code != 200 or resp.headers.get("Content-Type", "").split(";")[0] != "application/pdf":
        logger.info("Non-PDF or non-200 response for %s (status=%s, content-type=%s)",
                     url, resp.status_code, resp.headers.get("Content-Type"))
        return None
    return resp


def fetch_table_pdf(canonical_district: str, handbook_edition_year: int, table_id: str,
                     url_segments: dict[str, list[str]]) -> tuple[Path, str] | None:
    """Download one table PDF for a district/handbook-edition-year, trying known
    URL-segment spelling variants. Returns (local_path, resolved_url) or None if
    no variant resolved to a real PDF."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    variants = url_segments.get(canonical_district, [canonical_district])
    for segment in variants:
        url = (
            f"https://www.statistics.gov.lk/statistical%20Hbook/"
            f"{handbook_edition_year}/{segment}/{table_id}.pdf"
        )
        resp = _get(url)
        if resp is not None:
            safe_table_id = table_id.replace(".", "_")
            out_path = RAW_DIR / f"DCS_{canonical_district.replace(' ', '')}_{handbook_edition_year}_T{safe_table_id}.pdf"
            out_path.write_bytes(resp.content)
            logger.info("Downloaded %s -> %s", url, out_path)
            return out_path, url
    logger.warning(
        "No working URL segment found for district=%s edition=%s table=%s (tried: %s)",
        canonical_district, handbook_edition_year, table_id, variants,
    )
    return None


_YEAR_WORD = re.compile(r"^(19|20)\d{2}$")
_VALUE_TOKEN = re.compile(r"^(?:[\d,]+|-|n/r|N/R)$")
# Deliberately excludes digits (0-9): a genuine vehicle-type label never
# contains a digit in these tables, so requiring pure letters/punctuation
# (plus at least one letter, via the lookahead) prevents a row where a
# label and its values ended up merged together (observed in some
# Tamil-majority district PDFs, see MIXED-row handling below) from being
# misread as one long "label". Word-initial punctuation is allowed (e.g.
# the second word of "Commercial (Bus)" is the standalone token "(Bus)").
_LABEL_WORD = re.compile(r"^(?=.*[A-Za-z])[A-Za-z()/.'\-]+$")
_FOOTER_MARKERS = ("total", "source", "district statistical", "statistics division",
                   "divisional secretary", "department of motor traffic")
_ROW_TOP_TOLERANCE = 1.5  # points; groups words into the same visual row


def _group_words_into_rows(words: list[dict]) -> list[list[dict]]:
    """Cluster words (as returned by pdfplumber's extract_words) into visual
    rows by their 'top' coordinate. Handles the sub-pixel top jitter seen in
    these handbook PDFs (words on the same printed row can differ by <2pt)."""
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - word["top"]) <= _ROW_TOP_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    return rows


def parse_multi_year_table(pdf_path: Path) -> tuple[list[int], list[tuple[str, list[str]]]]:
    """Parse a Table 9.3/9.4-style PDF using word-level x-position clustering
    (not plain text splitting).

    Rationale (see specs/development/DEV-003-data-acquisition.md and
    REF-006 "different handbook formats" risk): pdfplumber's plain
    extract_text() sometimes splits a single large comma-grouped number
    (e.g. '154,948') into two separate word fragments ('1' and '54,948')
    due to font-kerning irregularities in these bilingual PDFs. Naive
    whitespace tokenization then miscounts values per row. Instead, this
    parser reads word bounding boxes directly: it locates the year-header
    row's x-position for each year column, then for every subsequent
    numeric row assigns each word fragment to its nearest year column by
    x-position and concatenates same-column fragments in left-to-right
    order to reconstruct the true raw value (e.g. '1' + '54,948' -> '154,948').

    Returns (years, [(vehicle_type_label, [raw_value_per_year]), ...]).
    Raw values are returned as the exact text found ("-", "n/r", or
    "1,234"), never converted or zero-filled here (DEV-004's responsibility).
    """
    import pdfplumber

    years: list[int] = []
    year_x0: list[float] = []
    rows: list[tuple[str, list[str]]] = []

    with pdfplumber.open(pdf_path) as pdf:
        words = [w for page in pdf.pages for w in page.extract_words()]

    row_groups = _group_words_into_rows(words)

    # Locate the year-header row: the row with the most pure-4-digit-year words.
    header_idx, header_row = max(
        enumerate(row_groups),
        key=lambda item: sum(1 for w in item[1] if _YEAR_WORD.match(w["text"])),
        default=(None, None),
    )
    if header_row is not None:
        year_words = [w for w in header_row if _YEAR_WORD.match(w["text"])]
        if len(year_words) >= 2:
            years = [int(w["text"]) for w in year_words]
            year_x0 = [w["x0"] for w in year_words]

    if not years:
        return years, rows

    # Restrict processing to the table *body*: strictly after the year
    # header, up to (and excluding) the first footer-looking row (Total /
    # Source / handbook title text). Rows outside this range - e.g. the page
    # title above the header, which can itself contain a stray "2019 - 2023"
    # year range that would otherwise be misread as a data row - must never
    # be treated as vehicle-type entries.
    body_rows: list[list[dict]] = []
    for row in row_groups[header_idx + 1:]:
        joined_lower = " ".join(w["text"] for w in row).lower()
        if any(marker in joined_lower for marker in _FOOTER_MARKERS):
            break
        body_rows.append(row)

    def _row_value_words(row: list[dict]) -> list[dict]:
        return [w for w in row if _VALUE_TOKEN.match(w["text"])]

    def _row_label_words(row: list[dict]) -> list[dict]:
        # "n/r" ("not reported") matches _VALUE_TOKEN but, containing only
        # letters and '/', would also match _LABEL_WORD - explicitly
        # exclude anything that's a value token so classification stays
        # mutually exclusive (otherwise an "n/r" cell gets double-counted
        # as both a value and a spurious one-word label, corrupting the
        # label/value pairing for that row and every row after it).
        return [w for w in row if _LABEL_WORD.match(w["text"]) and not _VALUE_TOKEN.match(w["text"])]

    # Column x-positions in these Excel-exported PDFs are right-aligned per
    # cell, but the header row's own text (e.g. "2019") is offset from the
    # data columns by a constant amount. Calibrate column positions from an
    # actual data row instead of the header when possible: pick the first
    # pure-value row whose word count already equals len(years) (no
    # split-number ambiguity), and use its word x1 positions as the column
    # reference. Fall back to the header's x-positions otherwise.
    pure_value_rows = [row for row in body_rows if row and len(_row_value_words(row)) == len(row)]
    calibration_row = next((r for r in pure_value_rows if len(r) == len(years)), None)
    if calibration_row is not None:
        column_x1 = [w["x1"] for w in sorted(calibration_row, key=lambda w: w["x0"])]
    else:
        column_x1 = [x0 + 20 for x0 in year_x0]  # rough fallback offset

    def _assign_columns(value_words: list[dict]) -> list[str]:
        """Assign word fragments to nearest year column by right edge (x1),
        then concatenate fragments sharing a column in left-to-right order
        (repairs numbers split across word fragments, e.g.
        '1' + '54,948' -> '154,948')."""
        columns: list[list[str]] = [[] for _ in years]
        for w in sorted(value_words, key=lambda w: w["x0"]):
            nearest = min(range(len(column_x1)), key=lambda i: abs(column_x1[i] - w["x1"]))
            columns[nearest].append(w["text"])
        return ["".join(col) if col else "-" for col in columns]

    def _emit(label: str, value_words: list[dict]) -> None:
        label = label.strip()
        if not label or label.lower() == "type of vehicle" or not value_words:
            return
        if len(value_words) > 2 * len(years):
            # Implausible number of value-word fragments for this row
            # (at most ~2 fragments per column expected, per the
            # number-splitting artifact) - a pairing/boundary error
            # somewhere, surface it rather than emit a corrupted row.
            logger.warning(
                "Row '%s' has %d value-word fragments for %d year columns - skipping",
                label, len(value_words), len(years),
            )
            return
        rows.append((label, _assign_columns(value_words)))

    pending_label: str | None = None
    pending_values: list[dict] | None = None

    for row in body_rows:
        value_words = _row_value_words(row)
        label_words = _row_label_words(row)
        # Classify by *content present*, not by requiring every word in the
        # row to match: a row can contain stray non-ASCII noise alongside
        # its real values (observed: a wrapped second line of a Tamil
        # translation landing on the same visual row as that entry's
        # numbers) without that noise changing what the row means. Only
        # treat a row as "mixed" (both a label and values together) when it
        # contains *no* non-ASCII words - that pattern is the genuine
        # same-line label+values layout (observed in some Tamil-majority
        # district PDFs), not a wrapping artifact.
        has_non_ascii = any(ord(ch) > 127 for w in row for ch in w["text"])
        # Genuine same-line label+values layout only when there's no
        # non-ASCII noise mixed in; otherwise treat any value_words present
        # as a values row (prioritizing not losing numbers over trusting an
        # incidental label caught alongside wrapping noise) and let the
        # surrounding pending_label/pending_values pairing re-attach it to
        # its real label from an adjacent clean row.
        is_mixed_row = bool(value_words) and bool(label_words) and not has_non_ascii
        is_value_row = bool(value_words) and not is_mixed_row
        is_label_row = bool(label_words) and not value_words and not is_mixed_row

        if is_value_row:
            if pending_label is not None:
                _emit(pending_label, value_words)
                pending_label = None
                pending_values = None
            else:
                pending_values = value_words
            continue

        if is_label_row:
            label_text = " ".join(w["text"] for w in row)
            if label_text.strip().lower() == "type of vehicle":
                # The column-header sub-line (e.g. under the Sinhala column
                # title, before any real data row). Must never be buffered
                # as a pending label - doing so would consume the *next*
                # row's values under the wrong label and cascade a
                # one-row shift through the rest of the table.
                continue
            if pending_values is not None:
                _emit(label_text, pending_values)
                pending_values = None
                pending_label = None
            else:
                # Append rather than overwrite: an English label can itself
                # wrap across two consecutive pure-label rows (observed:
                # "Land Vehicle" then "(Small)" on separate lines), which
                # must reconstruct as one label, not discard the first part.
                pending_label = f"{pending_label} {label_text}" if pending_label else label_text
            continue

        if is_mixed_row:
            # A single row mixing label words and value words together,
            # with no non-ASCII noise (observed in some Tamil-majority
            # district PDFs, where the English label and its numbers can
            # land on the same or a near-identical visual row instead of
            # separate lines).
            _emit(" ".join(w["text"] for w in label_words), value_words)
            pending_label = None
            pending_values = None
            continue

        # Row is neither a clean label, a clean value row, nor a usable
        # mix (e.g. pure non-ASCII Sinhala/Tamil text) - ignore it; it
        # carries no data this parser can use.

    return years, rows


def extract_district_observations(canonical_district: str, handbook_edition_year: int,
                                    url_segments: dict[str, list[str]]) -> list[RawObservation]:
    """Full extraction for one district/handbook edition: new_registrations (9.4)
    and vehicle_population/stock proxy (9.3)."""
    observations: list[RawObservation] = []
    retrieved_date = date.today().isoformat()

    for metric, table_id in TABLE_IDS.items():
        result = fetch_table_pdf(canonical_district, handbook_edition_year, table_id, url_segments)
        if result is None:
            continue
        local_path, resolved_url = result
        years, rows = parse_multi_year_table(local_path)
        if not years:
            logger.warning("Could not find a year header in %s - skipping", local_path)
            continue
        table_id_slug = table_id.replace(".", "_")
        for label, vals in rows:
            for year, val in zip(years, vals):
                observations.append(
                    RawObservation(
                        district_raw=canonical_district,
                        district_canonical=canonical_district,
                        year=year,
                        vehicle_type_raw=label,
                        value_raw=val,
                        metric=metric,
                        source_id=f"DCS_{canonical_district.replace(' ', '')}_{handbook_edition_year}_T{table_id_slug}",
                        source_url=resolved_url,
                        retrieved_date=retrieved_date,
                        handbook_edition_year=handbook_edition_year,
                    )
                )
    return observations


def write_interim_csv(observations: list[RawObservation], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(RawObservation.__dataclass_fields__.keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for obs in observations:
            writer.writerow(obs.__dict__)
    logger.info("Wrote %d raw observations to %s", len(observations), out_path)


def run_proof_of_concept(handbook_edition_year: int = 2024) -> Path:
    """Section 10.1: Kandy proof-of-concept extraction."""
    logging.basicConfig(level=logging.INFO)
    url_segments = load_url_segments()
    observations = extract_district_observations("Kandy", handbook_edition_year, url_segments)
    out_path = INTERIM_DIR / f"dcs_kandy_{handbook_edition_year}_raw.csv"
    write_interim_csv(observations, out_path)
    return out_path


def run_multi_district(districts: list[str], handbook_edition_year: int = 2024) -> Path:
    """Section 10.1 step 2/3: validate structure on additional districts, then scale."""
    logging.basicConfig(level=logging.INFO)
    url_segments = load_url_segments()
    all_observations: list[RawObservation] = []
    for district in districts:
        all_observations.extend(
            extract_district_observations(district, handbook_edition_year, url_segments)
        )
    out_path = INTERIM_DIR / f"dcs_multi_district_{handbook_edition_year}_raw.csv"
    write_interim_csv(all_observations, out_path)
    return out_path


if __name__ == "__main__":
    run_proof_of_concept()
