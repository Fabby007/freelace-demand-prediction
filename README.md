# Mechanic Service Demand Opportunity Prediction and Recommendation System - Sri Lanka

A data-driven decision-support system for freelance mechanics in Sri Lanka.
It uses published district-level vehicle statistics to compare the 25
districts and show where mechanic-service opportunity is likely to be
stronger for motorcycles, cars and three-wheelers.

> **Important:** Predictions are based on available historical and proxy
> data. They indicate relative service opportunity and do not guarantee
> customer numbers, employment or income.

## Overview

The project contains two separate applications. They run independently,
are started with separate commands and do not share a login.

**1. Opportunity dashboard (Streamlit, Plotly)**

- Code: `dashboard/` and `src/`
- Address: http://localhost:8501
- District map and district ranking with opportunity bands
  (Low, Moderate, High, Very High).
- Historical trend, estimate for the selected year and an explanation panel.
- Data-source information.
- Optional natural-language query box (SBERT) that selects the vehicle
  category.

**2. Mechanic discovery website (Flask, SQLite)**

- Code: `app/` and `wsgi.py`
- Address: http://127.0.0.1:5000
- Customer and mechanic registration, mechanic profiles and search.
- Ratings and reviews, and an admin area.
- Opportunity Insights page, which shows the same district results as the
  dashboard and links to it.

## Project structure

    app/                Flask website (routes, templates, forms, models)
    configs/            YAML and CSV settings, including the active engine
    dashboard/          Streamlit dashboard
    data/raw/           Source PDFs and the district boundary file
    data/interim/       Values extracted from the source PDFs
    data/processed/     Dataset v1 files; Dataset v2 is in processed/v2/
    data/corrections/   Register of source anomalies and corrections
    data/source_register.csv   Source, URL, licence and download date
    models/xgboost_v1/  Trained XGBoost model, encoder and metadata
    notebooks/          Exploratory data analysis of Dataset v2
    reports/            Dataset, EDA and evaluation reports with figures
    research/           Checksums of the v1 baseline files
    specs/              Development and reference specifications
    src/data/           PDF extraction, cleaning and validation
    src/features/       Feature engineering and dataset assembly
    src/models/         Baselines, XGBoost, LSTM check, v2 experiments
    src/evaluation/     Evaluation and experiment tracking (MLflow)
    src/explainability/ SHAP explanations
    src/nlp/            SBERT query routing
    src/recommendation/ v1 and v2 ranking engines
    tests/              pytest suite (tests/marketplace/ is the website)
    wsgi.py             Flask entry point
    requirements.txt    Pinned Python dependencies

## Requirements

- Windows 10 or 11. The project was developed and tested on Windows 11.
- Python 3.11 or 3.12. SciPy 1.17.1 requires Python 3.11 or newer, and
  TensorFlow 2.16.1 has no Python 3.13 builds. Tested with Python 3.12.10.
- About 4 GB of free disk space for the virtual environment.
- Internet access the first time the natural-language query box is used,
  to download the SBERT model `all-MiniLM-L6-v2` from Hugging Face.
  It is cached locally after that.

## Installation (Windows PowerShell)

    git clone https://github.com/Fabby007/freelace-demand-prediction.git
    cd freelace-demand-prediction
    py -3.12 -m venv .venv
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt

The `Set-ExecutionPolicy` line allows the activation script to run in the
current terminal only. In Command Prompt, activate with
`.venv\Scripts\activate.bat` instead.

## Configuration

No `.env` file is needed to run the project locally. The website reads
these optional environment variables:

- `MARKETPLACE_ENV` - `development`, `testing` or `production`.
  Default: `development`.
- `MARKETPLACE_SECRET_KEY` - Flask secret key. Required when
  `MARKETPLACE_ENV` is `production`. Default: a development-only key.
- `MARKETPLACE_DATABASE_URI` - SQLAlchemy database URI.
  Default: the SQLite file `instance/marketplace.db`, created automatically.
- `STREAMLIT_DASHBOARD_URL` - address used by the website's
  "Open Vehicle-Fleet Opportunity Dashboard" buttons.
  Default: `http://localhost:8501`.
- `MARKETPLACE_ADMIN_NAME`, `MARKETPLACE_ADMIN_EMAIL`,
  `MARKETPLACE_ADMIN_PASSWORD` - used by `create-admin` when the matching
  option is not given. No default.

PowerShell example (applies to the current terminal only):

    $env:MARKETPLACE_SECRET_KEY = "replace-with-a-long-random-value"
    $env:STREAMLIT_DASHBOARD_URL = "http://localhost:8501"

## Running the applications

Open two terminals in the project folder and activate the virtual
environment in each one.

Terminal 1 - Streamlit dashboard:

    streamlit run dashboard/app.py

Terminal 2 - Flask website:

    flask --app wsgi run

The website creates an empty SQLite database in `instance/` on first start.
No database is included in this repository.

To create the admin account (one time only; the password must be at least
8 characters):

    flask --app wsgi create-admin `
        --name "Admin" `
        --email "admin@example.com" `
        --password "choose-a-password"

(The backtick at the end of a line continues a PowerShell command.)

Customer and mechanic accounts are created through the website's
registration pages. Start the dashboard first if you want the website's
dashboard buttons to open it.

## Recommendation engines

`configs/recommendation_v2.yaml` selects the engine used by both the
dashboard and the Opportunity Insights page. v2 is the active engine.

**v2 - Vehicle-Fleet Service Opportunity (default)**

- Uses Dataset v2 (`data/processed/v2/modelling_dataset_v2.csv`):
  revenue-licence counts per district and vehicle type, 2019-2023.
- The estimate for a year is the previous year's revenue-licence count.
  No machine-learning model is loaded.
- This method was chosen because, on the final evaluation (target year
  2023), no machine-learning model was more accurate than the
  previous-year value.
- Districts are ranked within each vehicle type. The opportunity bands are
  the quarters of that ranking (Low, Moderate, High, Very High).
- Each district has a rule-based explanation built only from published
  values.
- The result describes relative licensed-vehicle fleet size. It does not
  measure mechanic jobs or service demand.

**v1 - XGBoost with SHAP**

- Uses Dataset v1: new vehicle registrations per district and vehicle
  type, 2019-2023.
- Predictions come from the XGBoost model in `models/xgboost_v1/`.
- SHAP explanations show the main positive and negative factors.

To switch engine, set `active_engine: v1` or `active_engine: v2` in
`configs/recommendation_v2.yaml`, then restart both applications.

## Data sources

Every source, with its URL, licence and download date, is listed in
`data/source_register.csv`.

1. **Department of Census and Statistics, District Statistical Handbook
   2024** - Table 9.3 (revenue licences issued) and Table 9.4 (new vehicle
   registrations) for all 25 districts. Main data for both datasets.
   Sri Lanka Government public statistical publication.
2. **Department of Motor Traffic, Vehicle Population 2014-2025** - used to
   cross-check the extracted figures (`reports/dmt_cross_validation.md`).
   Sri Lanka Government public publication.
3. **geoBoundaries, Sri Lanka ADM2 district boundaries** - used for the
   district map. Open Data Commons Open Database License (ODbL) 1.0,
   built from OpenStreetMap.

All statistics are published district-level totals. The datasets contain
no personal data. Missing values are never filled in or set to zero.
Corrections to source errors are logged in
`data/corrections/source_anomalies_v2.csv` and
`reports/dataset_v2/applied_corrections_v2.csv`.

## Models and evaluation

All validation is chronological: models are trained on earlier years and
tested on later years, never on a random split.

**Dataset v2 final evaluation** (target year 2023, 75 rows,
`reports/final_evaluation_v2/`)

| Approach                       |   MAE | MAPE (%) |
|--------------------------------|------:|---------:|
| Previous-year value            | 2,729 |     6.66 |
| Ridge regression on log change | 3,279 |     6.83 |
| Moving average of 2020-2022    | 4,574 |     9.82 |

The previous-year value performed best, so the v2 engine uses it.

**Dataset v1 evaluation** (test target year 2023,
`models/xgboost_v1/evaluation_report.md`)

On the 42 test rows that both could score, the previous-year baseline
(MAE 230.5) was more accurate than the tuned XGBoost model (MAE 306.4).
This result is reported in full rather than tuned away.

**LSTM:** assessed and not trained. The data is yearly and covers only
5 years (2019-2023), and a series needs at least 7 consecutive periods to
form one training example
(`reports/lstm_sequence_density_assessment.json`).

Experiment runs were tracked locally with MLflow. The run logs (`mlruns/`
and `mlruns_v2/`) are not included in this repository. The resulting
reports are in `reports/`.

## Running the tests

With the virtual environment active:

    python -m pytest -q

## Limitations

1. **Proxy target.** No recorded mechanic-job data exists for Sri Lanka.
   The project therefore uses published vehicle statistics as a proxy.
2. **Relative results only.** Results compare districts with each other.
   They are not job counts, customer numbers or income estimates.
3. **Short period.** The data is yearly and covers 2019-2023 only.
4. **One evaluation year.** The final evaluation covers a single target
   year, 2023.
5. **Coverage.** District licence totals add up to 57-85% of the
   Department of Motor Traffic national vehicle population, depending on
   vehicle type (2019 and 2023).
6. **Source quality.** Some published values are uncertain or were set to
   missing. They are flagged in the data and shown in the applications.
7. **Associations, not causes.** The models identify predictive
   associations, not causal effects.

The full list is in
`specs/reference/REF-006-risks-assumptions-limitations.md`.
