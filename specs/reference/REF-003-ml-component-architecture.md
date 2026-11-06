# REF-003 — ML Component Architecture Reference

**Status:** Approved reference specification
**Source:** Section 13, Section 20, and Section 32.3–32.6 of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

Single source of truth for what each ML component does, its priority, and why it was chosen — used both by implementation specs (DEV-007 through DEV-013) and by DEV-016 (viva preparation). DEV specs must link here instead of re-explaining component rationale.

## 2. Section 13 — Machine Learning Strategy (component/role/priority table, verbatim)

| Component | Role | Priority |
|---|---|---|
| Baseline | Simple previous-period or moving-average forecast | Required |
| XGBoost | Primary tabular prediction model | Core |
| LSTM | Sequence/time-series forecasting comparison | Planned when data supports it |
| SHAP | Explain XGBoost predictions | Core |
| SBERT | Understand user queries and match categories | Interface/NLP layer |
| Ranking engine | Sort districts and create opportunity recommendations | Core |
| Streamlit + Plotly | Present results interactively | Core |

## 3. Section 20 — End-to-End System Architecture (verbatim)

Architecture flow: real data → extraction and validation → district/time/vehicle feature table → feature engineering → XGBoost and LSTM modelling → SHAP explanations → district ranking and recommendation → Streamlit/Plotly dashboard. SBERT operates at the user-interaction layer to understand natural-language requests and route them to the correct prediction category.

**Important:** SBERT is a routing/interface layer only. It does not predict district demand and is not a free-form explanation generator (Section 16). It sits alongside the prediction pipeline, not inside the prediction path.

## 4. Section 32.3 — Why XGBoost? (verbatim)

"The core dataset is tabular and may not be very large; XGBoost models nonlinear relationships in this type of data, handles heterogeneous features well, and can be explained using SHAP."

Also Section 14.3: multiple district-level features, potential missing values, nonlinear effects, limited historical data compared with deep-learning tasks. Practical, defendable primary model; integrates naturally with SHAP.

## 5. Section 32.4 — Why LSTM? (verbatim)

"Designed for sequential patterns; included to test whether time-series structure adds predictive value when monthly or sufficiently dense historical data is available; compared fairly against XGBoost rather than assumed to be better."

## 6. Section 32.5 — Why SBERT? (verbatim)

"Provides semantic understanding of user questions; does not predict demand; helps the interface understand that a question about 'bike repair' relates to the motorcycle-mechanic prediction category."

## 7. Section 32.6 — Why SHAP? (verbatim)

"Shows which input variables increased or decreased the prediction, making the model easier to inspect, explain and defend."

## 8. Component independence rule

Per MASTER_PROMPT.md Section 5: "Do not create additional development specs purely to raise the count, and do not merge unrelated modules into one spec (e.g., do not merge SHAP and SBERT — they are functionally distinct per Section 13's component table)." SHAP (DEV-010) and SBERT (DEV-011) must remain separately implemented and separately testable even though both sit "above" the core XGBoost prediction path.

## 9. Related specs

- DEV-007 (Baseline), DEV-008 (XGBoost), DEV-009 (LSTM), DEV-010 (SHAP), DEV-011 (SBERT), DEV-012 (Ranking Engine), DEV-013 (Dashboard)
- DEV-016 (Documentation & Viva Prep) — reuses Sections 4–7 above directly as talking points.
