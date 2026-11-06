"""Tests for the Dataset v2 EDA notebook and report.

The numbers are recomputed here with separate code, directly from Dataset v2, so
that a mistake in the notebook would not simply be repeated. Running the notebook
writes only to tmp_path.
"""
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "eda_dataset_v2.ipynb"
DATASET = ROOT / "data" / "processed" / "v2" / "modelling_dataset_v2.csv"
MANIFEST = ROOT / "reports" / "dataset_v2" / "dataset_v2_manifest.json"
EDA_DIR = ROOT / "reports" / "eda_v2"
FINDINGS_JSON = EDA_DIR / "eda_findings.json"
REPORT = EDA_DIR / "eda_report.md"
VEHICLES = ["Motorcycle", "Car", "Three-wheeler"]

needs_dataset = pytest.mark.skipif(not DATASET.exists(), reason="Dataset v2 not present locally")


@pytest.fixture(scope="module")
def nb():
    nbformat = pytest.importorskip("nbformat")
    return nbformat.read(NOTEBOOK, as_version=4)


@pytest.fixture(scope="module")
def findings():
    return json.loads(FINDINGS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(DATASET)


def _code(nb):
    return "\n".join(c.source for c in nb.cells if c.cell_type == "code")


# --- The notebook as a document -----------------------------------------------

def test_notebook_ran_without_errors_and_is_in_order(nb):
    code_cells = [c for c in nb.cells if c.cell_type == "code"]
    assert code_cells
    assert all(c.execution_count is not None for c in code_cells)
    assert [c.execution_count for c in code_cells] == sorted(c.execution_count for c in code_cells)
    assert not [o for c in code_cells for o in c.outputs if o.output_type == "error"]
    assert not [o for c in code_cells for o in c.outputs if o.output_type == "stream" and o.name == "stderr"]


def test_every_chart_is_explained_directly_below_it(nb):
    charts = 0
    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code" and "save_figure(fig," in cell.source and "def save_figure" not in cell.source:
            charts += 1
            below = nb.cells[i + 1]
            assert below.cell_type == "markdown", cell.source[:60]
            assert "What it shows." in below.source and "Why it matters." in below.source, cell.source[:60]
    assert charts == 22


def test_findings_answer_the_three_viva_questions(nb):
    finding_cells = [c.source for c in nb.cells if c.cell_type == "markdown" and c.source.startswith("### Finding")]
    assert len(finding_cells) == 11
    for text in finding_cells:
        for part in ["What did we discover?", "Why does it matter?", "How could it affect our ML methodology?", "Observation or assumption?"]:
            assert part in text, text[:50]


def test_notebook_answers_each_research_question(nb):
    text = "\n".join(c.source for c in nb.cells if c.cell_type == "markdown")
    for question in ["How do licence counts vary across districts?", "How stable are fleet indicators over time?",
                     "Which features appear useful?", "How might suspicious values affect results?",
                     "Does the dataset support meaningful rankings?"]:
        assert question in text


def test_notebook_does_not_train_models_or_write_data(nb):
    code = _code(nb)
    for forbidden in ["sklearn", "xgboost", "tensorflow", ".fit(", "to_csv", "to_parquet", "to_excel", "src.models", "fillna(0", ".interpolate(", "ffill", "bfill"]:
        assert forbidden not in code, forbidden
    # Only the chart and findings outputs are written, under OUTPUT_DIR.
    assert re.findall(r"\.write_text\(", code) == [".write_text("]
    assert "OUTPUT_DIR / \"eda_findings.json\"" in code


def test_notebook_holds_no_absolute_or_machine_paths(nb):
    assert not re.search(r"[A-Za-z]:\\\\|/Users/|Temp\\\\", NOTEBOOK.read_text(encoding="utf-8"))


def test_notebook_uses_seaborn_and_matplotlib(nb):
    code = _code(nb)
    assert "import seaborn as sns" in code and "import matplotlib.pyplot as plt" in code


def test_all_charts_exist_and_match_the_findings(findings):
    on_disk = sorted(p.name for p in (EDA_DIR / "figures").glob("*.png"))
    assert on_disk == sorted(findings["figures"])
    assert findings["figure_count"] == len(on_disk) == 22
    assert all((EDA_DIR / "figures" / name).stat().st_size > 5000 for name in on_disk)


def test_feature_target_analysis_excludes_the_hold_out_year(nb, findings):
    assert findings["feature_target_max_target_year"] == 2022
    assert 'df["target_year"] < HOLD_OUT_TARGET_YEAR' in _code(nb)
    assert "HOLD_OUT_TARGET_YEAR = 2023" in _code(nb)


# --- Independent recalculation ------------------------------------------------

@needs_dataset
def test_dataset_is_still_the_frozen_version():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == manifest["dataset_sha256"]


@needs_dataset
def test_size_counts(df, findings):
    assert df.shape == (375, 39) == (findings["rows"], findings["columns"])
    assert df["target_licence_count"].notna().sum() == 299 == findings["target_values"]
    assert not df.duplicated(["district", "year", "vehicle_type"]).any()
    assert findings["development_rows"] == ((df["target_year"] <= 2022) & df["target_licence_count"].notna()).sum() == 224


@needs_dataset
def test_skewness(df, findings):
    values = df["licence_count"].dropna()
    assert stats.skew(values) == pytest.approx(findings["skew_raw"], abs=0.005)
    assert stats.skew(np.log10(values)) == pytest.approx(findings["skew_log"], abs=0.005)


@needs_dataset
def test_stability_figures(df, findings):
    change = (np.exp(df["licence_growth_log"].dropna()) - 1).abs() * 100
    assert len(change) == findings["growth_observations"] == 295
    assert change.median() == pytest.approx(findings["median_absolute_change_pct"], abs=0.05)
    assert (change <= 10).mean() * 100 == pytest.approx(findings["share_within_10_pct"], abs=0.05)


@needs_dataset
def test_between_district_variance(df, findings):
    for vehicle in VEHICLES:
        part = df[df["vehicle_type"] == vehicle]
        part = part[part.groupby("district")["licence_count"].transform(lambda s: s.notna().all())]
        logged = np.log10(part["licence_count"])
        by_district = logged.groupby(part["district"])
        between = (by_district.size() * (by_district.mean() - logged.mean()) ** 2).sum()
        assert between / ((logged - logged.mean()) ** 2).sum() * 100 == pytest.approx(findings["between_district_variance_share"][vehicle], abs=0.05)


@needs_dataset
def test_top_five_share_in_2022(df, findings):
    for vehicle in VEHICLES:
        values = df[(df["vehicle_type"] == vehicle) & (df["year"] == 2022)]["licence_count"].sort_values(ascending=False)
        assert values.head(5).sum() / values.sum() * 100 == pytest.approx(findings["top_5_share_2022"][vehicle], abs=0.05)


@needs_dataset
def test_registration_fall_uses_one_row_per_district(df, findings):
    totals = df.drop_duplicates(["district", "year"]).groupby("year")["total_registrations_printed"].sum()
    assert totals[2019] == 342064 and totals[2022] == 20488
    assert (1 - totals[2022] / totals[2019]) * 100 == pytest.approx(findings["registrations_fall_2019_2022_pct"], abs=0.05)


@needs_dataset
def test_rank_stability(df, findings):
    correlations = []
    for vehicle in VEHICLES:
        table = df[df["vehicle_type"] == vehicle].pivot(index="district", columns="year", values="licence_count")
        for year in range(2019, 2023):
            pair = table[[year, year + 1]].dropna()
            correlations.append(stats.spearmanr(pair[year], pair[year + 1]).statistic)
    assert min(correlations) == pytest.approx(findings["level_rank_spearman_min"], abs=0.0005)
    assert max(correlations) == pytest.approx(findings["level_rank_spearman_max"], abs=0.0005)


@needs_dataset
def test_kurunegala_passes_gampaha_only_in_2023_on_a_flagged_value(df):
    motorcycles = df[df["vehicle_type"] == "Motorcycle"].pivot(index="year", columns="district", values="licence_count")
    assert (motorcycles.idxmax(axis=1).loc[2019:2022] == "Gampaha").all()
    assert motorcycles.idxmax(axis=1).loc[2023] == "Kurunegala"
    row = df[(df["district"] == "Kurunegala") & (df["vehicle_type"] == "Motorcycle") & (df["year"] == 2023)].iloc[0]
    assert row["licence_flagged"]


@needs_dataset
def test_growth_is_an_exact_function_of_level_and_lag(df):
    rows = df.dropna(subset=["licence_count", "licence_lag_1", "licence_growth_log"])
    assert (np.log(rows["licence_count"]) - np.log(rows["licence_lag_1"]) - rows["licence_growth_log"]).abs().max() < 1e-9


@needs_dataset
def test_sensitivity_figures(df, findings):
    dev = df[(df["target_year"] <= 2022) & df["target_licence_count"].notna() & df["licence_count"].notna()]
    change = (dev["target_licence_count"] / dev["licence_count"] - 1).abs() * 100
    clean = change[~dev["target_flagged"] & ~dev["features_use_flagged_licence"]]
    assert len(change) == findings["sensitivity_all_rows"] and len(clean) == findings["sensitivity_clean_rows"]
    assert change.mean() == pytest.approx(findings["sensitivity_change_abs"]["all_mean"], abs=0.05)
    assert clean.mean() == pytest.approx(findings["sensitivity_change_abs"]["clean_mean"], abs=0.05)


@needs_dataset
def test_within_year_correlation_for_registration_growth(df, findings):
    dev = df[(df["target_year"] <= 2022) & df["target_licence_count"].notna() & df["licence_count"].notna()].copy()
    dev["change"] = np.log(dev["target_licence_count"] / dev["licence_count"])
    rows = dev.dropna(subset=["total_registrations_growth_log", "change"])
    group = rows.groupby(["vehicle_type", "target_year"])
    x = rows["total_registrations_growth_log"] - group["total_registrations_growth_log"].transform("mean")
    y = rows["change"] - group["change"].transform("mean")
    stored = findings["feature_target"]["total_registrations_growth_log"]["rho_change_within_year"]
    assert stats.spearmanr(x, y).statistic == pytest.approx(stored, abs=0.0005)


# --- The report ---------------------------------------------------------------

def test_report_has_required_sections():
    text = REPORT.read_text(encoding="utf-8")
    for heading in ["Dataset overview", "Key visualizations and findings", "Data-quality limitations", "Recommendations for feature selection and ML"]:
        assert heading in text


def test_report_images_exist():
    text = REPORT.read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert len(images) >= 8
    for image in images:
        assert (EDA_DIR / image).exists(), image


def test_report_quotes_the_computed_numbers(findings):
    text = REPORT.read_text(encoding="utf-8")
    quoted = [
        "57,830", "31,233", "2.29", "-0.85", "98,598", "11,428", "28,827", "45.4%", "46.4%", "67.0%", "342,064", "20,488", "94.0%",
        "89.0", "97.5", "105.9", "103.0", "0.937", "0.995", "-0.581", "+0.060", "9.4%", "5.3%", "174.8%", "25.4%", "38.3%", "3.8%",
        "24,800", "31,732", "491", "401", "1,428",
    ]
    for value in quoted:
        assert value in text, value
    assert f"{findings['median_absolute_change_pct']}%" in text
    assert str(findings["robust_outliers"]) in text


def test_report_lists_every_new_outlier_candidate(findings):
    text = REPORT.read_text(encoding="utf-8").lower()
    names = {"motorcycle": "motorcycles", "car": "cars", "three-wheeler": "three-wheelers"}
    for candidate in findings["new_outlier_list"]:
        district, vehicle, year = candidate.lower().split(" ")
        assert f"{district} {names[vehicle]} {year}" in text, candidate


def test_report_does_not_present_a_model_result_or_job_counts():
    text = REPORT.read_text(encoding="utf-8").lower()
    assert "no model has been trained" in text
    assert "job count" not in text


# --- Re-running ---------------------------------------------------------------

@needs_dataset
def test_notebook_reruns_from_scratch_and_writes_only_to_its_output_folder(tmp_path, nb, findings):
    """A clean re-run reproduces the findings exactly and leaves the dataset alone."""
    nbclient = pytest.importorskip("nbclient")
    import copy

    before = (hashlib.sha256(DATASET.read_bytes()).hexdigest(), DATASET.stat().st_mtime_ns)
    fresh = copy.deepcopy(nb)
    for cell in fresh.cells:
        if cell.cell_type == "code":
            cell.outputs, cell.execution_count = [], None

    previous = os.environ.get("EDA_OUTPUT_DIR")
    os.environ["EDA_OUTPUT_DIR"] = str(tmp_path)
    try:
        nbclient.NotebookClient(fresh, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(ROOT / "notebooks")}}).execute()
    finally:
        if previous is None:
            del os.environ["EDA_OUTPUT_DIR"]
        else:
            os.environ["EDA_OUTPUT_DIR"] = previous

    assert json.loads((tmp_path / "eda_findings.json").read_text(encoding="utf-8")) == findings
    assert len(list((tmp_path / "figures").glob("*.png"))) == 22
    assert (hashlib.sha256(DATASET.read_bytes()).hexdigest(), DATASET.stat().st_mtime_ns) == before
