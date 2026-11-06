# COVERAGE — Requirement-to-Spec Traceability Matrix

**Stage:** Stage 3 of MASTER_PROMPT.md's 7-stage workflow.
**Purpose:** Confirm every functional requirement, non-functional requirement, data rule, modelling rule, testing rule, and deliverable from the source documentation maps to at least one development spec, reference spec, or `TODO.md` item, before any implementation code is written (MASTER_PROMPT.md Stage 3: "Do not proceed to Stage 4 until coverage is complete").

---

## 1. Functional Requirements (Section 21, FR-01…FR-12)

| ID | Requirement | Covered by |
|---|---|---|
| FR-01 | Import real vehicle and district data from documented sources | DEV-002, DEV-003; TODO Phase 1–2 |
| FR-02 | Clean and normalize district and vehicle-category names | DEV-004; REF-002; TODO Phase 3 |
| FR-03 | Create lag, growth and trend features without future leakage | DEV-005; TODO Phase 4 |
| FR-04 | Train and load an XGBoost prediction model | DEV-008; TODO Phase 6 |
| FR-05 | Train an LSTM model when the selected dataset supports sequence modelling | DEV-009; TODO Phase 7 |
| FR-06 | Calculate SHAP explanations for XGBoost predictions | DEV-010; TODO Phase 8 |
| FR-07 | Rank districts for a selected vehicle category and period | DEV-012; TODO Phase 9 |
| FR-08 | Display results on an interactive Sri Lanka district map | DEV-013; TODO Phase 11 |
| FR-09 | Display historical trends and top recommendations | DEV-013; TODO Phase 11 |
| FR-10 | Accept a natural-language query and use SBERT to map it to a supported category | DEV-011; TODO Phase 10 |
| FR-11 | Display source, model and limitation information | DEV-013 (data-source/model-version panel, disclaimer); TODO Phase 11 |
| FR-12 | Export selected results or provide a reproducible analysis view if time permits | DEV-013 (explicitly best-effort); TODO Phase 11 |

## 2. Non-Functional Requirements (Section 22)

| NFR | Covered by |
|---|---|
| Reproducibility | DEV-017; REF-004 Section 2; TODO Phase 15 |
| Explainability | DEV-010, DEV-012; REF-004 Section 2 |
| Usability | DEV-013; REF-004 Section 2 |
| Performance | DEV-013 (Performance NFR — few-second response); REF-004 Section 2 |
| Maintainability | DEV-001 folder structure; CLAUDE.md Section 6; REF-004 Section 2 |
| Data integrity | DEV-004 (source_id provenance); REF-004 Section 2 |
| Security/privacy | REF-005; CLAUDE.md Section 13 |
| Portability | DEV-001, DEV-017; REF-004 Section 2 |

## 3. Scope Boundaries Table (Section 5)

Reproduced and enforced verbatim in `specs/reference/REF-004-nfr-and-scope-boundaries.md` Section 3, and reflected in CLAUDE.md Section 19. All DEV specs' "Preconditions"/"Business Rules" respect these boundaries (e.g. DEV-009 treats LSTM as conditional, not guaranteed; DEV-013 has no mobile-app requirement).

## 4. Data Acquisition Workflow Steps 1–9 (Section 10)

| Step | Covered by |
|---|---|
| 1. Create source register before downloading | DEV-002 |
| 2. Download/store raw snapshot unedited in data/raw | DEV-003 |
| 3. Extract required table via repeatable method | DEV-003 |
| 4. Normalize district/vehicle-category names via lookup | DEV-003 (pass-through) → DEV-004 (logic), REF-002 |
| 5. Convert numeric strings; preserve missing as missing | DEV-003, DEV-004 |
| 6. Validate extracted totals against source/DMT | DEV-003 |
| 7. Append source metadata to each observation | DEV-003, DEV-004 |
| 8. Write cleaned observations to data/processed | DEV-004 |
| 9. Run automated validation tests before modelling | DEV-004, DEV-015 |
| 10.1 Kandy proof-of-concept → validate 2-3 districts → scale to 25 | DEV-003 |

## 5. Data Cleaning Rules (Section 11)

| Rule | Covered by |
|---|---|
| District normalisation | DEV-004, REF-002 |
| Vehicle-category normalisation | DEV-004, REF-002 |
| Duplicate handling via source-priority rule | DEV-004 |
| Missing values investigated, never auto-zeroed | DEV-004 |
| Outliers compared against source before action | DEV-004 |
| Numeric conversion preserving raw archive | DEV-004 |
| Time sorting before lag features | DEV-004 |
| Scaling (XGBoost none; LSTM train-only) | DEV-004 (note), DEV-009 (LSTM scaling) |
| Categorical encoding | DEV-008/DEV-009 (as needed) |
| Train-test separation before leak-prone transforms | DEV-004, DEV-006 |

## 6. Feature Engineering Rules + Leakage Rule (Section 12, 12.1)

| Rule | Covered by |
|---|---|
| Current/lagged level, growth, rolling trend, time, district context, vehicle intensity, category, target lags | DEV-005 |
| Leakage rule (no feature uses data from period ≥ t) | DEV-005 (unit-tested); Hard Rule in CLAUDE.md Section 20 |

## 7. XGBoost Training Steps 1–6 (Section 14.2)

| Step | Covered by |
|---|---|
| 1. Chronological split | DEV-006 |
| 2. Train simple baseline first | DEV-007 |
| 3. Train XGBoost on same target/split | DEV-008 |
| 4. Tune params on train/validation only | DEV-008 |
| 5. Select on validation; report test once | DEV-008 |
| 6. Save model + feature list + dataset version | DEV-008, DEV-014 (registry) |

## 8. LSTM Sequence/Model/Comparison Rules (Section 15)

| Rule | Covered by |
|---|---|
| Conditional on sequence density | DEV-009 (explicit conditionality check) |
| Sequence construction (6–12 month lookback, train-only scaling) | DEV-009 |
| Model design (1–2 LSTM layers, dropout, dense output, early stopping, checkpoint) | DEV-009 |
| Fair comparison vs. XGBoost on identical held-out periods | DEV-009, DEV-014 |

## 9. SBERT Interaction Steps 1–5 (Section 16.1)

| Step | Covered by |
|---|---|
| 1. Embed query | DEV-011 |
| 2. Compare to category descriptions | DEV-011 |
| 3. Highest match selects pipeline | DEV-011 |
| 4. Ranking engine returns top districts | DEV-012 (consumer) |
| 5. SHAP provides reasons | DEV-010 (consumer via DEV-012) |
| Safe-fallback for unsupported/ambiguous queries | DEV-011 |

## 10. SHAP Global/Local Explanation Requirements (Section 17)

| Requirement | Covered by |
|---|---|
| Global SHAP summary across test set | DEV-010 |
| Local per-district positive/negative contributions | DEV-010 |
| SHAP aligns with model feature schema (test) | DEV-010, DEV-015 |

## 11. Ranking Engine Steps 1–6 (Section 18)

| Step | Covered by |
|---|---|
| 1. Receive category/period | DEV-012 |
| 2. Predict per district | DEV-012 (via DEV-008) |
| 3. Sort districts | DEV-012 |
| 4. Convert to opportunity bands | DEV-012 |
| 5. Extract SHAP reasons for top districts | DEV-012 (via DEV-010) |
| 6. Return top-N with trend + limitation note | DEV-012 |

## 12. Dashboard Controls and Panels (Section 19)

| Item | Covered by |
|---|---|
| Vehicle type / period / district / top-N selectors, NL query box | DEV-013 |
| Choropleth map, ranking table/chart, trend chart, forecast panel, SHAP panel, data-source/model-version panel, disclaimer note | DEV-013 |

## 13. Model Evaluation Strategy (Section 23)

| Item | Covered by |
|---|---|
| Baselines (23.1) | DEV-007 |
| Regression metrics — MAE, RMSE, R² (23.2) | DEV-014 |
| Ranking metrics — Spearman, top-k overlap (23.3) | DEV-014 |
| Time-aware validation (23.4) | DEV-006, DEV-014 |
| LSTM evaluation (23.5) | DEV-009, DEV-014 |

## 14. Experiment Tracking/Reproducibility Items (Section 24)

| Item | Covered by |
|---|---|
| GitHub | DEV-001 |
| MLflow or W&B | DEV-014 (choice logged as ADR in REF-009) |
| requirements.txt/pyproject.toml | DEV-001, DEV-017 |
| Configuration files | DEV-005, DEV-006, DEV-008, DEV-009 (`configs/`) |
| Data source register | DEV-002 |
| Random seeds | DEV-008, DEV-009, DEV-014, DEV-017 |
| Model registry folder | DEV-014 |

## 15. Testing Strategy (Section 26)

| Category | Covered by |
|---|---|
| Data tests (26.1) | DEV-004, DEV-015 |
| Model tests (26.2) | DEV-008, DEV-009, DEV-010, DEV-015 |
| Dashboard tests (26.3) | DEV-011, DEV-012, DEV-013, DEV-015 |

## 16. Risks/Limitations Table (Section 27)

Reproduced verbatim and mapped to mitigating specs in `specs/reference/REF-006-risks-assumptions-limitations.md` Section 3. **These are documented cautions to be communicated (dashboard disclaimer, reporting), not defects to "fix away"** — e.g. "short annual time series" is handled by DEV-009's conditionality check, not by forcing LSTM to run regardless of data density; "no direct mechanic-demand target" is handled by DEV-002's Preferred/Fallback framework, not by inventing a target.

## 17. Ethical/Legal/Governance Rules (Section 28)

Reproduced verbatim in `specs/reference/REF-005-ethical-legal-governance.md`; applied across DEV-002, DEV-003, DEV-004, DEV-012, DEV-013, DEV-016 (see REF-005 Section 3 application table).

## 18. Deliverables List (Section 29)

| # | Deliverable | Covered by |
|---|---|---|
| 1 | Documented real-data collection and extraction pipeline | DEV-002, DEV-003 |
| 2 | Cleaned district-time-vehicle dataset with provenance | DEV-004 |
| 3 | Baseline forecasting model | DEV-007 |
| 4 | Trained XGBoost primary model | DEV-008 |
| 5 | LSTM comparison model (if data supports it) | DEV-009 |
| 6 | SHAP explainability module | DEV-010 |
| 7 | SBERT NL query matching module | DEV-011 |
| 8 | District ranking and recommendation engine | DEV-012 |
| 9 | Streamlit/Plotly dashboard | DEV-013 |
| 10 | MLflow/W&B experiment history and GitHub repository | DEV-001, DEV-014 |
| 11 | Model evaluation and error-analysis report | DEV-014, DEV-016 |
| 12 | Technical documentation, user guide, viva material | DEV-016 |

## 19. Data Dictionary (Appendix A)

Reproduced verbatim in `specs/reference/REF-001-data-dictionary.md`; enforced by DEV-004 (base columns), extended by DEV-005 (engineered columns), consumed by DEV-006 (assembly), DEV-008/DEV-009 (modelling).

## 20. Folder Structure (Appendix B)

Reproduced verbatim (extended with `specs/`) in `specs/reference/REF-008-technology-stack.md` Section 3 and `CLAUDE.md` Section 12; created by DEV-001.

## 21. Disclaimer Wording (Appendix C.3)

Reproduced verbatim in `CLAUDE.md` Section 15 and `specs/reference/REF-007-domain-rationale-terminology.md`. Required on every recommendation-bearing view — enforced as a Business Rule / Acceptance Criterion in DEV-012 (generation) and DEV-013 (display, persistent across panels).

---

## 22. Ambiguities, Data-Driven Decision Points, and Open Questions

Per MASTER_PROMPT.md Stage 3, these are explicitly **not defects** — they are decision points intentionally left open by the source documentation, to be resolved once real data is examined:

1. **Monthly vs. yearly granularity** (Section 9) — "Final granularity is determined by the best common resolution across sources." Resolved in DEV-006 once real source coverage is known; not fixed in advance.
2. **Preferred vs. Fallback target path** (Section 8) — depends entirely on whether a real mechanic-demand dataset can be found. Resolved in DEV-002's Target Decision Record; propagates wording/framing requirements to DEV-012/DEV-013/DEV-016.
3. **Whether LSTM is built at all** (Section 15) — conditional on sequence density; DEV-009 documents the conditionality assessment and may legitimately conclude "experimental-only" or "skip."
4. **Exact district-name spellings** (Section 11) — REF-002's 25-district list is a working canonical list pending confirmation against actual DCS handbook text during DEV-004.
5. **Duplicate-resolution source-priority rule** (Section 11) — the exact tie-break rule across handbook editions is left to be defined during DEV-004 and logged as an ADR.
6. **Opportunity-band threshold rule** (Section 18 step 4) — "quantiles or a documented training-data rule" — the exact mechanism is chosen during DEV-012 and logged as an ADR if not already implied by the data.
7. **MLflow vs. Weights & Biases** (Section 24) — an explicit "or" in the source doc; the choice is logged as an ADR in REF-009 once made (DEV-014).
8. **Whether car/three-wheeler categories are modelled in the first build** (Section 5) — "Cars and three-wheelers can be added if data quality is sufficient" — contingent on data availability discovered during DEV-002/DEV-003, not a fixed commitment.
9. **Production model selection (XGBoost vs. LSTM)** (Section 23.5) — genuinely depends on comparative evaluation results in DEV-014; not decided in advance.

No other ambiguities, internal inconsistencies, or coverage gaps were identified in the source documentation as reproduced in `MASTER_PROMPT.md`.

---

## 23. Coverage conclusion

Every FR, NFR, data rule, modelling rule, testing rule, and deliverable enumerated in MASTER_PROMPT.md Section 10 has at least one owning DEV spec, REF spec, or `TODO.md` phase, as tabulated above. **Stage 3 is complete.** Implementation may proceed to Stage 4 (already expressed via `specs/development/DEV-PLAN.md`) and Stage 5 (spec-by-spec implementation, starting at DEV-002 per the dependency order — DEV-001's scaffolding/env/config work remains open in `TODO.md` Phase 0 pending user confirmation on git/GitHub setup).

---

# PART 2 — Marketplace Extension Coverage (2026-08-21)

This part covers only the approved Mechanic Discovery Web Platform extension (`MARKETPLACE_EXTENSION.md`, DEV-018–024, REF-010–013). Parts 1 (above) and the original FR-01…FR-12 remain the traceability record for the ML research system and are unaffected by this part.

## 24. Marketplace Functional Requirements (MARKETPLACE_EXTENSION.md Section 4)

| ID | Requirement | Covered by |
|---|---|---|
| FR-M01 | Customer registration | DEV-018 |
| FR-M02 | Customer login/logout | DEV-018 |
| FR-M03 | Customer view/edit own account info | DEV-018 |
| FR-M04 | Search mechanics by district/vehicle type/service type | DEV-020 |
| FR-M05 | View mechanic profile + contact number | DEV-020 |
| FR-M06 | Submit/edit/delete a rating and review | DEV-021 |
| FR-M07 | View existing ratings/reviews and average rating | DEV-020, DEV-021 |
| FR-M08 | Mechanic registration + profile creation | DEV-018, DEV-019 |
| FR-M09 | Mechanic login/logout | DEV-018 |
| FR-M10 | Mechanic edit own profile (not others') | DEV-019 |
| FR-M11 | Mechanic view own ratings/reviews | DEV-019, DEV-021 |
| FR-M12 | Mechanic view Opportunity Insights | DEV-023 |
| FR-M13 | Admin authentication (non-self-service) | DEV-018, DEV-022 |
| FR-M14 | Admin manage customer accounts | DEV-022 |
| FR-M15 | Admin manage mechanic accounts/profiles | DEV-022 |
| FR-M16 | Admin remove/restore reviews | DEV-021 (functions), DEV-022 (UI) |

## 25. Marketplace Non-Functional Requirements (MARKETPLACE_EXTENSION.md Section 5)

| NFR | Covered by |
|---|---|
| Separation from the ML system | REF-010 Section 4; DEV-023 (sole integration point); DEV-024 FR5 (verification) |
| Simplicity (no SPA/microservices) | REF-010 Section 2; REF-004 Section 5 (reused) |
| Security (hashing, sessions, CSRF, RBAC, ownership) | REF-012; DEV-018, DEV-019, DEV-021, DEV-022; DEV-024 FR2 |
| Usability (responsive HTML/CSS) | REF-013 Section 2; DEV-024 FR4 |
| Honesty (review disclaimer, Appendix C.3 disclaimer) | REF-013 Sections 4–5; DEV-021, DEV-023 |
| Data integrity (no fabricated accounts/reviews) | MARKETPLACE_EXTENSION.md Section 5; REF-011 Section 3.3 (labelled seed data) |

## 26. Explicit Exclusions Coverage (MARKETPLACE_EXTENSION.md Section 2.2)

Booking, appointment scheduling, availability/online status, live GPS tracking, payments, in-app chat, job-status tracking, and dispatch/matching are each confirmed absent from REF-011's schema (Section 4, no `Booking`/`Payment`/`Chat`/`Job`/`Availability` entity) and from every DEV-018–024 Functional Requirements list — verified by inspection during this planning pass, to be re-verified by DEV-024's audit once implemented.

## 27. Marketplace/ML Boundary Rule Coverage

| Rule | Covered by |
|---|---|
| Customer searches/ratings never become ML training data | MARKETPLACE_EXTENSION.md Section 7.2; DEV-020, DEV-021 (no write path to `data/`) |
| Mechanic's marketplace `district` is not a research observation | MARKETPLACE_EXTENSION.md Section 7.2; REF-011 Section 3.2 |
| Opportunity Insights reuses `src/` read-only, no duplicated prediction logic | DEV-023 FR1, FR5; REF-010 Section 4 |
| Streamlit dashboard preserved, unmodified | REF-009 ADR-026; DEV-024 FR5 |
| Two disclaimers (marketplace review disclaimer vs. Appendix C.3) never merged | REF-013 Section 5; DEV-021, DEV-023; DEV-024 FR4 |

## 28. Marketplace coverage conclusion

Every functional requirement, non-functional requirement, and explicit exclusion in `MARKETPLACE_EXTENSION.md` has at least one owning DEV-018–024 spec or REF-010–013 spec, as tabulated above. No requirement from Parts 1–22 (the original ML system) was altered, weakened, or reinterpreted to accommodate this extension.

**Implementation status (updated 2026-08-21): COMPLETE.** DEV-018 through DEV-024 have all been implemented and verified — 184 marketplace tests, the original 191-test ML suite unchanged, 375/375 in the final combined run (DEV-024's sign-off). DEV-024's own audit additionally corrected three cells in REF-012's authorization matrix that had been over-specified during planning (documentation corrections, not scope changes — see REF-009's dated note and DEV-024.md's "Audit findings" section) and closed eight genuine, narrow test-coverage gaps. No functional defect was found in the marketplace application code itself during that audit.
