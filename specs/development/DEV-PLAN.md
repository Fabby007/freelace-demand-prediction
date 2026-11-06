# DEV-PLAN — Development Plan & Dependency Index

**Status:** Approved planning artifact
**Source:** Section 25 (Implementation Plan) of the Final Project Documentation, mapped to DEV-IDs per MASTER_PROMPT.md Section 7.

---

## 1. Purpose

This is the build-order index for `specs/development/`. It mirrors the source documentation's Section 25 phase sequence but expresses it as explicit spec-to-spec dependencies so that build order is unambiguous. Do not mark a stage below complete while any of its constituent DEV specs are incomplete (MASTER_PROMPT.md Stage 7 / CLAUDE.md Section 23).

## 2. Priority note (Section 25 closing note, verbatim)

> "The highest-priority path is real data → target definition → clean dataset → baseline/XGBoost → SHAP → ranking → dashboard. LSTM and SBERT should not delay the core model if the data pipeline is still incomplete."

This means: DEV-009 (LSTM) and DEV-011 (SBERT) are **not blockers** for DEV-012 (Ranking) or DEV-013 (Dashboard) reaching a working state on the XGBoost path. DEV-013 depends on DEV-011 for the NL query *panel*, but the dashboard's core ranking/map/trend/SHAP panels must work end-to-end on XGBoost + SHAP + Ranking alone before LSTM or SBERT are wired in. If LSTM proves not viable (Section 15, Section 23.5 — insufficient sequence density), XGBoost remains the production model and the project is still complete per Section 5 scope.

## 3. Stage order and dependency graph

| # | Stage | DEV-ID(s) | Depends on |
|---|---|---|---|
| 1 | Foundation & setup | DEV-001 | — |
| 2 | Data-source confirmation & target decision | DEV-002 | DEV-001 |
| 3 | Data acquisition | DEV-003 | DEV-002 |
| 4 | Extraction, cleaning & validation | DEV-004 | DEV-003, REF-002 |
| 5 | Feature engineering | DEV-005 | DEV-004 |
| 6 | Dataset assembly & split | DEV-006 | DEV-005, REF-001 |
| 7 | Baseline + XGBoost (core prediction path) | DEV-007, DEV-008 | DEV-006 (DEV-008 depends on DEV-007) |
| 8 | LSTM comparison (conditional on data density) | DEV-009 | DEV-006 (parallel to DEV-008; non-blocking per Section 2 above) |
| 9 | Explainability (SHAP) | DEV-010 | DEV-008 |
| 10 | NLP query layer (SBERT) | DEV-011 | DEV-008, REF-003 |
| 11 | Ranking & recommendation engine | DEV-012 | DEV-008, DEV-010 |
| 12 | Dashboard (Streamlit/Plotly) | DEV-013 | DEV-010, DEV-011, DEV-012 |
| 13 | Evaluation & experiment tracking | DEV-014 | DEV-008 (and DEV-009 where applicable); ongoing from Stage 7 onward, consolidated here |
| 14 | Testing | DEV-015 | Cross-cutting; written incrementally alongside DEV-004 through DEV-013, consolidated here |
| 15 | Documentation & viva prep | DEV-016 | All prior DEV specs substantially complete |
| 16 | Reproducibility & deployment readiness | DEV-017 | DEV-014 |

## 4. Dependency graph (text form)

```
DEV-001
  └─ DEV-002
       └─ DEV-003
            └─ DEV-004 (+ REF-002)
                 └─ DEV-005
                      └─ DEV-006 (+ REF-001)
                           ├─ DEV-007
                           │    └─ DEV-008
                           │         ├─ DEV-010 (SHAP)
                           │         │    └─ DEV-012 (Ranking) ←── DEV-008
                           │         ├─ DEV-011 (SBERT, + REF-003)
                           │         └─ DEV-014 (Evaluation, ongoing)
                           └─ DEV-009 (LSTM — parallel, non-blocking)
                                └─ DEV-014 (feeds in if LSTM selected)

DEV-010 + DEV-011 + DEV-012 ──► DEV-013 (Dashboard)

DEV-015 (Testing) — cross-cutting, alongside DEV-004..DEV-013
DEV-014 (Evaluation) ──► DEV-017 (Reproducibility & Deployment)
All DEV specs substantially complete ──► DEV-016 (Documentation & Viva)
```

## 5. Rules governing this plan

- Work through specs in dependency order, one at a time (MASTER_PROMPT.md Stage 5). Do not jump ahead to a later spec while an earlier dependency is incomplete unless explicitly told to.
- DEV-009 (LSTM) may be built in parallel with DEV-008 (XGBoost) once DEV-006 is done, but the production path (DEV-010 → DEV-012 → DEV-013) is only ever gated on DEV-008, per Section 2 above.
- DEV-011 (SBERT) requires a working prediction pipeline (DEV-008) to route into, but does not gate DEV-012 (Ranking).
- DEV-015 (Testing) is written incrementally alongside each relevant DEV spec, not deferred to the end, then consolidated/verified as its own spec.
- DEV-016 (Documentation & Viva Prep) is the last substantive spec, once all prior specs are functionally complete.
- DEV-017 (Reproducibility & Deployment Readiness) closes out the project once DEV-014 (evaluation/experiment tracking) is in place.

## 6. Related artifacts

- `TODO.md` — checklist-granularity mirror of this plan.
- `specs/COVERAGE.md` — requirement-to-spec traceability (Stage 3 deliverable).

---

## 7. EXTENSION — Mechanic Discovery Web Platform (DEV-018–024)

**Status:** COMPLETE (2026-08-21). All seven specs (DEV-018–024) implemented and verified — 184 marketplace tests, full 191-test ML suite unchanged, 375/375 in the final combined run. See `MARKETPLACE_EXTENSION.md` for the full plan and the four marketplace reference specs (REF-010–013).

This is an **additive extension**, not a continuation of the original Sections 1–6 build order above. It has its own dependency chain, rooted only in DEV-018 (not in any of DEV-001–017), and its own `app/` codebase entirely separate from `src/`/`dashboard/`. Sections 1–6 above remain the exact, unmodified plan for the original ML research system.

### 7.1 Dependency note — relationship to Phases 14–15

DEV-018–024 do **not** depend on DEV-016 (Documentation & Viva Prep) or DEV-017 (Reproducibility & Deployment Readiness) being complete. They depend only on DEV-008 (XGBoost), DEV-010 (SHAP), and DEV-012 (Ranking Engine) — already complete — for the one integration point (DEV-023). The marketplace extension may therefore be implemented in parallel with, or after, closing out Phases 14–15, at the user's discretion; neither blocks the other.

### 7.2 Stage order and dependency graph (marketplace)

| # | Stage | DEV-ID | Depends on |
|---|---|---|---|
| 17 | Web foundation, database & authentication | DEV-018 | — (independent of DEV-001–017) |
| 18 | Mechanic profiles & user roles | DEV-019 | DEV-018 |
| 19 | Mechanic search & discovery | DEV-020 | DEV-019 |
| 20 | Ratings & reviews | DEV-021 | DEV-018, DEV-019, DEV-020 |
| 21 | Admin dashboard & management | DEV-022 | DEV-018, DEV-019, DEV-021 |
| 22 | ML Opportunity Insights web integration | DEV-023 | DEV-018 (marketplace side); DEV-008, DEV-010, DEV-012 (ML side, already complete) |
| 23 | Web application testing, security & final integration | DEV-024 | DEV-018, DEV-019, DEV-020, DEV-021, DEV-022, DEV-023 (all functionally complete) |

### 7.3 Dependency graph (text form)

```
DEV-018 (Foundation, DB, Auth)
  └─ DEV-019 (Mechanic Profiles)
       ├─ DEV-020 (Search & Discovery)
       │    └─ DEV-021 (Ratings & Reviews)
       │         └─ DEV-022 (Admin Dashboard) ── also needs DEV-018, DEV-019
       └─ (DEV-021, DEV-022 as above)

DEV-018 ──► DEV-023 (Opportunity Insights) ◄── DEV-008, DEV-010, DEV-012 (existing ML system, unchanged)

DEV-018, DEV-019, DEV-020, DEV-021, DEV-022, DEV-023 ──► DEV-024 (Testing, Security & Final Integration)
```

### 7.4 Rules governing this extension plan

- Work through DEV-018–024 in dependency order, same discipline as Section 5 above.
- DEV-023 is the **only** spec permitted to import from `src/`; no other marketplace spec (DEV-018–022, DEV-024) may import ML-system modules or touch `data/`, `models/`, or `mlruns/`.
- DEV-024 (Testing, Security & Final Integration) is not started until DEV-018–023 are functionally complete, mirroring DEV-015's role for the original system — but unlike DEV-015, this is a single consolidated audit spec rather than one written incrementally alongside each prior spec, since the marketplace's authorization matrix (REF-012) is most meaningfully verified once every role-gated route exists.
- No DEV-018–024 spec may modify `specs/development/DEV-001`–`DEV-017`, `specs/reference/REF-001`–`REF-008`, `src/`, `dashboard/`, or the non-marketplace contents of `tests/`.

### 7.5 Related artifacts (marketplace)

- `MARKETPLACE_EXTENSION.md` — the full extension plan this section indexes.
- `specs/reference/REF-010-marketplace-web-architecture.md`
- `specs/reference/REF-011-marketplace-database-schema.md`
- `specs/reference/REF-012-marketplace-roles-permissions-security.md`
- `specs/reference/REF-013-marketplace-ui-business-rules.md`
- `TODO.md` — Phases 16–22 mirror this section at checklist granularity.
