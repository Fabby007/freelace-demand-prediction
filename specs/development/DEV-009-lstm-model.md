# DEV-009 — LSTM Time-Series Comparison Model

## Specification ID
DEV-009

## Feature/Module Name
LSTM Time-Series Comparison Model

## Purpose
Build a sequence-based LSTM forecaster, conditional on sufficient sequence density, and compare it fairly against XGBoost on identical targets/held-out periods — without delaying the core XGBoost/SHAP/ranking/dashboard path.

## Background/Context
Source doc Section 15 (LSTM — Time-Series Forecasting Model), Section 15.1–15.3, Section 23.5 (LSTM evaluation), Section 27 risk ("Short annual time series → LSTM may overfit or be unjustified"). Per DEV-PLAN.md Section 2, this spec is explicitly non-blocking for the core delivery path.

## Related Requirements
- FR-05 (train an LSTM model when the selected dataset supports sequence modelling)
- Section 15, Section 23.5
- REF-003 (Why LSTM, Section 5), REF-006 (short time-series risk)

## User Roles
None (backend/modelling spec).

## Preconditions
DEV-006 complete (frozen dataset + split). May proceed in parallel with DEV-008.

## User Stories/Use Cases
- As the developer, I need to test whether time-series structure (via LSTM) adds forecasting value beyond XGBoost, when the data is dense enough to justify it, without over-claiming success if it doesn't (Section 23.5: "if not, XGBoost remains the recommended production model").

## Functional Requirements

### Conditionality check (must run first)
Before building LSTM, assess whether the final dataset's sequence density (observations per district/vehicle-category series) is sufficient — per Section 15: "most meaningful with monthly or another dense resolution. If only a small number of yearly observations exist, treat LSTM results cautiously and possibly as an experimental comparison only." Record this assessment and its outcome in this spec (or as an ADR) before proceeding.

**Assessment completed (2026-08-15)** — `src/models/lstm_model.py::assess_sequence_density()`, run against the real frozen dataset (`data/processed/modelling_dataset_v1.csv`), persisted to `reports/lstm_sequence_density_assessment.json`. Result: **SKIP** (not "insufficient" but categorically unreachable), on two independent grounds:

1. **No monthly data exists.** `month` is null for 100% of rows (the dataset is confirmed yearly-only, REF-001 Section 5 granularity rule). Section 15.1's sequence-construction method is written specifically for monthly cadence ("sliding window of previous 6 or 12 months") — it does not apply at all, independent of row count.
2. **Even under a generous yearly reinterpretation** of the window (using `lstm.lookback_months` = 6 from `configs/model_params.yaml` as a period count instead of a month count), a series needs 6 + 1 = 7 consecutive non-null yearly observations to form even one (input-window, target) training pair. The dataset spans only 5 distinct years in total (2019–2023) — the maximum possible run for *any* series is 5, so **0 of 75** district × vehicle_type series can ever reach 7, regardless of missing-value patterns.

See REF-009 ADR-013 for the full reasoning and alternatives considered (including why even a "clearly labelled experimental" model was rejected — see Business Rules below), and REF-006 Section 5.4 for how this empirically confirms the pre-existing "short annual time series" risk. `tests/test_lstm_model.py` (8/8 passing) verifies both the real-data conclusion and that the assessment function genuinely branches on evidence (synthetic fixtures reach `proceed`/`experimental`/`skip` correctly, so this is not a hardcoded "always skip" result).

### 15.1 Sequence construction
- For monthly data: sliding window of previous 6 or 12 months to predict the next month.
- Sequences built separately within a district/vehicle-category series, or via a well-defined multi-series design.
- Scaling parameters (e.g. MinMax/StandardScaler) fitted on training data only — never on validation/test data, and never on the full dataset before the split.

### 15.2 Model design
- Input sequence layer.
- One or two LSTM layers.
- Dropout to reduce overfitting.
- Dense output layer for the forecast.
- Early stopping on validation loss.
- Model checkpoint for the best validation epoch.

### 15.3 Comparison with XGBoost
- LSTM and XGBoost must predict the same target over the same held-out periods before comparison.
- A more complex model is not automatically better — keep the model that performs reliably and can be explained (this also affects which model DEV-012's ranking engine ultimately calls into production).

## Business Rules
- If sequence density is insufficient, this spec's deliverable is the documented assessment and (optionally) a clearly labelled experimental-only comparison — not a forced production LSTM.
- LSTM must never be selected as production model over XGBoost without a genuine, reported performance justification (Section 23.5).
- Scaler must be fit on training data only (leakage rule extended to preprocessing, Section 11 and Section 15.1).

## Data Requirements
Input: frozen dataset + split (DEV-006), reshaped into sequences per Section 15.1. Output: trained LSTM model artifact (if built), its evaluation metrics on the same test periods as DEV-008.

## Database/Schema Changes
None beyond the model artifact under `models/` (kept separate from the XGBoost artifact).

## API Requirements
None.

## Backend Behavior
- LSTM code lives in `src/models/lstm_model.py` (or equivalent), separate module from XGBoost (Maintainability NFR).
- Sequence-building and scaling logic must be reusable/testable independent of the model architecture code.

## Frontend Behavior
N/A. (If LSTM becomes the production model, DEV-013's forecast panel would source from it instead of XGBoost — but per DEV-PLAN.md this is not assumed by default.)

## UI States
N/A.

## Validation
- Scaler fit only on training-period data (verified by a unit test).
- LSTM and XGBoost evaluated on identical held-out periods with identical metrics (Section 23.5).
- Early stopping / checkpointing genuinely selects the best validation-loss epoch, not the last epoch.

## Permissions
N/A.

## Error Cases
- Sequence density too low to form meaningful windows (e.g. fewer than the lookback length of observations per series) — do not force sequence construction; document the limitation and treat LSTM as out of scope for that series/vehicle type, per Section 15.

## Edge Cases
- Some districts/vehicle types have enough density for sequences, others don't — LSTM may be evaluated only on the subset with sufficient density; this must be stated explicitly, not glossed over.

## Security Considerations
None beyond general data-governance rules.

## Dependencies
- DEV-006 (Modelling Dataset Assembly & Target Definition)
- REF-003 (ML Component Architecture Reference), REF-006 (Risks — short time-series limitation)

## Testing Requirements
- Scaler-leakage test (fit on train only).
- Sequence-construction correctness test against a hand-built sample.
- Fair-comparison test: LSTM and XGBoost metrics computed on the exact same held-out rows/periods.

## Acceptance Criteria
- [x] Sequence-density conditionality assessment completed and documented (proceed / experimental-only / skip, with reasoning) — **SKIP**, on two independent grounds (no monthly data at all; 0/75 series reach the minimum 7-period run even under a generous yearly reinterpretation). See Conditionality check section above, `reports/lstm_sequence_density_assessment.json`, and REF-009 ADR-013.
- [x] If proceeding: sequences built per Section 15.1 with training-only scaling — **N/A**, not proceeding; no sequence-construction or scaling code was written (deliberately — see REF-009 ADR-013's "Alternatives considered" for why even a token/experimental version was rejected, not merely skipped for lack of time).
- [x] If proceeding: model built and trained per Section 15.2 with early stopping and checkpointing — **N/A**, same reason.
- [x] LSTM evaluated against XGBoost on identical target/held-out periods (Section 15.3, Section 23.5) — **N/A**; no LSTM predictions exist to compare. DEV-014's comparison report covers baseline (DEV-007) vs. XGBoost (DEV-008) only, with LSTM's absence explained by this spec/ADR-013 rather than silently omitted.
- [x] Production-model decision (XGBoost vs. LSTM) recorded with justification — **XGBoost**, by default and by the only model that was ever built (per Section 23.5: "if not [meaningful improvement], XGBoost remains the recommended production model" — here LSTM was never in contention to begin with, which is itself a valid instance of that same rule). Recorded in REF-009 ADR-013 and REF-006 Section 5.4.

## Testing Requirements — completed
- Scaler-leakage test — **N/A**, no scaler was fit (no sequences were built).
- Sequence-construction correctness test — **N/A**, no sequences were built.
- Fair-comparison test — **N/A**, no LSTM predictions exist to compare against XGBoost.
- Conditionality-check tests (in place of the above, since they are the actual DEV-009 deliverable here): `tests/test_lstm_model.py`, 8/8 passing — real-data assessment concludes "skip" with correct evidence, assessment output is JSON-serializable, and the decision function genuinely branches (synthetic fixtures correctly reach `proceed`/`experimental`/`skip`), proving the "skip" outcome is a real conclusion from real data, not a hardcoded default.

## Definition of Done
(b) applies: the conditionality assessment concludes sequence density is insufficient — categorically unreachable given the dataset's 5-year total span, not merely "thin" — and this is documented as a legitimate outcome (not a failure) per Section 15 and REF-006 Section 5.4. DEV-012/DEV-013 are not blocked and proceed on the XGBoost path (DEV-PLAN.md Section 2). Full project test suite is 76/76 passing.
