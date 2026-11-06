# DEV-006 — Modelling Dataset Assembly & Target Definition

## Specification ID
DEV-006

## Feature/Module Name
Modelling Dataset Assembly & Target Definition

## Purpose
Assemble the final long-format district/time/vehicle_type modelling table, freeze and version it, define `target_value` concretely per the DEV-002 decision, and create the chronological train/validation/test split used by every model.

## Background/Context
Source doc Section 9 (Proposed Dataset Design), Section 8 (Target framing), Section 23.4 (time-aware validation). This spec is the hinge between data engineering (DEV-002–005) and modelling (DEV-007–009): every model trains against the exact dataset version frozen here.

## Related Requirements
- Section 9, Section 8, Section 23.4
- REF-001 (Data Dictionary)
- Hard Rule: no random train/test splitting for future-period prediction (MASTER_PROMPT.md Section 0)

## User Roles
None (backend pipeline).

## Preconditions
DEV-005 complete: feature-engineered dataset exists. DEV-002's Target Decision Record is finalized.

## User Stories/Use Cases
- As the developer, I need one frozen, versioned dataset file that every model (baseline, XGBoost, LSTM) trains against, so comparisons between models are fair and reproducible.
- As the developer, I need a chronological (not random) split so evaluation genuinely reflects future-period prediction performance.

## Functional Requirements
1. Assemble the final long-format table: one row per district × time period × vehicle_type (Section 9), using the schema in REF-001.
2. Concretely populate `target_value` per the DEV-002 Target Decision Record:
   - Preferred path: `target_value` = the real observed mechanic-demand signal.
   - Fallback path: `target_value` = the chosen real vehicle-market proxy (e.g. future `new_registrations`), with this fact recorded prominently in this spec and propagated as a labelling/wording requirement to DEV-012/DEV-013.
3. Determine final time granularity (yearly vs. monthly) based on the best common resolution actually available across sources (Section 5, Section 9) — this is a **data-driven decision point**, not a defect if it resolves to yearly-only. Record the decision and reasoning here.
4. Freeze the modelling dataset: write a versioned file (e.g. `data/processed/modelling_dataset_v1.parquet`) and record its version identifier (date/hash) so DEV-008/DEV-009/DEV-014 can cite an exact dataset version in the model registry (Section 24).
5. Create the chronological train/validation/test split:
   - Sort by time period.
   - Assign the earliest periods to train, a subsequent window to validation, and the most recent period(s) to test — no shuffling, no random assignment.
   - Districts/vehicle types are grouped within each time period so the model is evaluated on genuinely future periods, not random historical rows (Section 23.4).
   - Record exact split boundary dates/periods in `configs/split_config.*` (config-driven, not hardcoded — DEV-001 scaffold populated here).

## Business Rules
- Never use random train/test splitting for a model predicting future periods (Hard Rule).
- The frozen dataset version referenced by a trained model (DEV-008/DEV-009) must never be silently replaced by a newer extraction without a new version identifier and an explicit note that comparisons across versions aren't apples-to-apples.

## Data Requirements
Output: the frozen, versioned modelling dataset (REF-001 schema, all DEV-005 engineered columns present) plus the split configuration (train/validation/test period boundaries).

## Database/Schema Changes
Introduces the "frozen modelling dataset" artifact and its versioning convention; schema itself is REF-001.

## API Requirements
None.

## Backend Behavior
Dataset assembly and split logic in `src/features/` or `src/data/` (co-located with related pipeline code, per Maintainability NFR); split boundaries read from `configs/split_config.*`.

## Frontend Behavior
N/A. (The dashboard's data-source/model-version panel, DEV-013, displays the frozen dataset version.)

## UI States
N/A.

## Validation
- Confirm no row appears in more than one of train/validation/test.
- Confirm the split is strictly chronological (max period in train < min period in validation < min period in test, per district/vehicle series as applicable).
- Confirm `target_value` is populated consistent with the DEV-002 decision (no silent mixing of real-target and proxy-target rows without a flag).

## Permissions
N/A.

## Error Cases
- Insufficient distinct time periods to form three genuinely separate chronological splits (e.g. only 3 years of data total) — flag explicitly; do not force an artificial split that leaves validation/test with near-zero rows. Document the constraint and the accepted approach (e.g. simpler holdout) as an ADR.

## Edge Cases
- A district/vehicle-category series that only has data within the training window and none in validation/test — legitimately excluded from validation/test evaluation for that series; do not fabricate rows to fill the gap.

## Security Considerations
None beyond upstream provenance/no-fabrication rules.

## Dependencies
- DEV-005 (Feature Engineering Pipeline)
- REF-001 (Data Dictionary)
- DEV-002 (for the Target Decision Record)

## Testing Requirements
- Split-integrity test (no row in more than one split; strictly chronological boundaries).
- Dataset-version test: the frozen file's identifier is retrievable and stable across reruns absent a genuine data change.

## Acceptance Criteria
- [x] Final long-format dataset assembled per REF-001 schema — `data/processed/modelling_dataset_v1.csv`, 375 rows x 32 columns (all DEV-004/DEV-005 columns plus `target_value`, `target_year`, `target_data_quality_flag`, `split`), produced by `src/features/assemble_modelling_dataset.py::run()`.
- [x] `target_value` populated consistent with the DEV-002 Preferred/Fallback decision — Fallback path: `target_value` at a (district, vehicle_type, year) row is the next period's `new_registrations` for the same series (`groupby(...).shift(-1)`), computed in `add_target()`. Guarded with a `NotImplementedError` (mirroring DEV-005's pattern) if `configs/target_config.yaml` is ever switched to `is_real_demand_target: true` without this function being revisited. Hand-verified against the real Kandy Motorcycle series (`tests/test_dataset_assembly.py::test_kandy_motorcycle_target_is_next_period_new_registrations`), including the genuinely-missing-2022 case (target for 2021 is null, not fabricated).
- [x] Time granularity decision (yearly vs. monthly) made and documented — **yearly**, confirmed as the real, best-common source resolution (5 distinct years, 2019-2023; no district/vehicle series has monthly data). Recorded in `configs/split_config.yaml` (`granularity: yearly`) and REF-001 Section 5.
- [x] Modelling dataset frozen with a recorded version identifier — content-hash-derived (`modelling_dataset_v1_<sha256[:12]>`, currently `modelling_dataset_v1_1310eaead622`), written to `configs/split_config.yaml`'s `dataset_version`/`dataset_sha256`/`frozen_date` fields by `freeze_dataset()`; stable across reruns absent a genuine data change (see REF-009 ADR-009 for why content-hash rather than date-based).
- [x] Chronological train/validation/test split created and recorded in `configs/split_config.*` — boundaries keyed by `target_year` (the year being predicted): train = 2020-2021 (102 rows), validation = 2022 (49 rows), test = 2023 (47 rows); 177 rows with a null `target_value` are `split = "unlabeled"` (excluded from all three, retained for live inference). See REF-009 ADR-008 for the rationale behind this thin 2/1/1 split, forced by the real 5-year yearly series.
- [x] Split-integrity tests pass — `tests/test_dataset_assembly.py`, 12/12 passing, covering: no row in more than one split, strict chronology (`max(train target_year) < min(validation target_year) <= max(validation target_year) < min(test target_year)`), unlabeled rows all have null target and vice versa, config-driven boundaries (not hardcoded), a misconfigured/non-chronological split config raises rather than silently producing an invalid split, and dataset-version stability across reruns.

Additional decisions made and logged as ADRs during this phase: disposition of the 100 DCS/DMT-flagged rows (REF-006 Section 5.1) — disclosed via `target_data_quality_flag`, not excluded or down-weighted (REF-009 ADR-007); CSV chosen over Parquet for the frozen dataset, with a content-hash version identifier (REF-009 ADR-009).

## Definition of Done
All acceptance criteria met; the frozen, versioned dataset (`data/processed/modelling_dataset_v1.csv`) and split configuration (`configs/split_config.yaml`) are ready for DEV-007 (Baseline) and DEV-008/DEV-009 (XGBoost/LSTM) to consume identically; `tests/test_dataset_assembly.py` (12/12) is part of the automated test suite and passes; full project test suite is 42/42 passing.
