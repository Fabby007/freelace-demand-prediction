# REF-008 — Technology Stack Reference

**Status:** Approved reference specification
**Source:** Section 30 and Appendix B of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

Canonical technology stack and folder structure. Per MASTER_PROMPT.md Section 0 (Hard Rules): "Do not change the technology stack ... without a documented, justified technical reason recorded in an ADR (Architecture Decision Record) inside `specs/reference/`" (REF-009).

## 2. Section 30 — Final Technology Stack (verbatim table)

| Layer | Technology | Purpose |
|---|---|---|
| Programming | Python 3.10+ | Main implementation language |
| Data processing | Pandas, NumPy | Cleaning, transformation, feature engineering |
| Tabular ML | XGBoost, scikit-learn | Primary model, metrics, validation, baselines |
| Deep learning | TensorFlow / Keras | LSTM model |
| NLP | sentence-transformers / SBERT | Semantic query understanding |
| Explainability | SHAP | Feature-attribution explanations |
| Dashboard | Streamlit | Web application |
| Visualisation | Plotly | Interactive charts and choropleth maps |
| Experiment tracking | MLflow or Weights & Biases | Parameters, metrics and artefacts |
| Version control | Git + GitHub | Code history and collaboration |
| Development | VS Code / Jupyter Notebook | Implementation and analysis |
| Data storage | CSV / Parquet; optional SQLite | Processed dataset and application data |

## 3. Appendix B — Suggested Project Folder Structure (verbatim, extended with `specs/` per MASTER_PROMPT.md Section 8)

```
mechanic-demand-project/
├── specs/
│   ├── development/        (DEV-001 ... DEV-017, DEV-PLAN.md)
│   ├── reference/           (REF-001 ... REF-009)
│   └── COVERAGE.md
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── notebooks/
├── src/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── explainability/
│   ├── nlp/
│   └── recommendation/
├── dashboard/
├── models/
├── reports/
├── tests/
├── configs/
├── CLAUDE.md
├── TODO.md
├── requirements.txt
└── README.md
```

## 4. Notes on optional choices

- **MLflow or Weights & Biases:** the source doc leaves this an "or" choice. Whichever is selected first must be recorded as an ADR in REF-009 (with rationale — e.g. local-only vs. cloud-hosted tracking) before DEV-014 work begins, since the two are not mixed arbitrarily mid-project.
- **SQLite:** optional, only for the app layer if needed by the dashboard; not a requirement. CSV/Parquet under `data/` is the primary storage per CLAUDE.md "Database conventions."

## 5. Related specs

- REF-009 (Architecture Decision Records) — logs any deviation from this stack or any implementation-level choice within it (e.g. MLflow vs W&B, Parquet vs CSV as the default processed format).
- DEV-001 (Project Foundation) — installs and pins this stack.
- DEV-014 (Model Evaluation & Experiment Tracking) — implements the MLflow/W&B choice.
