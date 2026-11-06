# Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka

*A data-driven decision-support system for freelance mechanics.*
Final Year Project, HND Computing, ESOFT Metro Campus.

## What this is

This system uses real Sri Lankan vehicle-registration statistics and district-level data to identify where mechanic-service opportunity is likely to be stronger, for a selected vehicle category (motorcycle first, then car and three-wheeler) and a future period. It ranks districts, explains each ranking using SHAP, and presents results through an interactive Streamlit/Plotly dashboard. It never claims an exact mechanic-job count unless a genuine observed job-demand dataset supports it — see the disclaimer in every recommendation view.

## Project status

This repository is being built spec-first. See:
- `CLAUDE.md` — project context, conventions, and hard rules for every development session.
- `specs/development/DEV-PLAN.md` — build order and dependency graph.
- `specs/development/DEV-001.md` … `DEV-017.md` — one specification per module.
- `specs/reference/REF-001.md` … `REF-009.md` — stable reference material (data dictionary, canonical lists, ML architecture, NFRs, ethics, risks, domain rationale, technology stack, ADR log).
- `specs/COVERAGE.md` — requirement-to-spec traceability matrix.
- `TODO.md` — the dependency-ordered execution checklist; current progress lives here.

Implementation proceeds specification by specification, in the order defined in `DEV-PLAN.md`, starting from real data acquisition (DEV-002/DEV-003) through to the dashboard (DEV-013) and reproducibility checks (DEV-017).

## Setup (once implementation begins)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Full run instructions (data pipeline → training → dashboard) will be completed here as part of DEV-017 (Reproducibility & Deployment Readiness), once the pipeline exists end-to-end.

## Important note

All predictions and rankings produced by this system are relative, model-based opportunity estimates derived from historical and proxy data. They do not guarantee customer numbers, employment, or income. See `specs/reference/REF-007-domain-rationale-terminology.md` and the disclaimer text in `CLAUDE.md` Section 15.
