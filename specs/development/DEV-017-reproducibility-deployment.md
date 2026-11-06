# DEV-017 — Reproducibility & Deployment Readiness

## Specification ID
DEV-017

## Feature/Module Name
Reproducibility & Deployment Readiness

## Purpose
Finalize dependency pinning, README setup/run instructions, and a concrete reproducibility check so the project can be run from a clean environment and yield the same trained model within normal nondeterminism.

## Background/Context
Source doc Section 22 (Portability NFR), Section 24 (Experiment Tracking, Reproducibility and Version Control).

## Related Requirements
- Section 22 (Portability), Section 24
- REF-004 (NFRs), REF-008 (Technology Stack)

## User Roles
None (infrastructure/deliverable spec).

## Preconditions
DEV-014 (Evaluation & Experiment Tracking) complete.

## User Stories/Use Cases
- As the developer/assessor, I need to be able to clone the repository, install dependencies from `requirements.txt`, and reproduce the trained model and dashboard without additional undocumented setup.

## Functional Requirements
1. Finalize and pin `requirements.txt` / `pyproject.toml` with exact versions of the full REF-008 stack.
2. Write `README.md` with setup instructions (environment creation, dependency install) and run instructions (data pipeline, training, dashboard launch).
3. Perform a reproducibility check: re-run the pipeline from the frozen dataset version (DEV-006) and configuration (`configs/`) and confirm the same trained model results within normal library-level nondeterminism (Section 22 Reproducibility NFR) — document the check and its outcome.
4. Confirm random seeds are recorded and applied wherever the stack supports them (XGBoost, TensorFlow/Keras, scikit-learn splits).

## Business Rules
- Reproducibility check must use the actual frozen dataset version and config files, not a fresh/re-extracted dataset (which could legitimately differ if new handbook editions were published).
- README instructions must be complete enough that a person unfamiliar with the codebase can run it end-to-end using only the README.

## Data Requirements
None new — relies on DEV-006's frozen dataset and DEV-005/006/008/009's config files.

## Database/Schema Changes
None.

## API Requirements
None.

## Backend Behavior
N/A beyond environment/config finalization.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
- Fresh virtual environment + `requirements.txt` install succeeds without manual intervention.
- Reproducibility check produces the same (or acceptably close, given documented nondeterminism sources) trained model metrics as the original run.

## Permissions
N/A.

## Error Cases
- A dependency that can't be pinned to an exact reproducible version across platforms (e.g. a GPU-specific TensorFlow build) — document the platform assumption explicitly in the README rather than silently failing to reproduce.

## Edge Cases
- Minor nondeterminism from GPU-accelerated training (if used) despite fixed seeds — document as an accepted, normal limitation (Section 22 explicitly allows "normal library-level nondeterminism").

## Security Considerations
No secrets committed; any required API tokens (e.g. Kaggle) documented as environment variables in the README, not hardcoded.

## Dependencies
- DEV-014 (Model Evaluation & Experiment Tracking)

## Testing Requirements
- Clean-environment install test.
- Reproducibility check (documented run-compare).

## Acceptance Criteria
- [ ] `requirements.txt`/`pyproject.toml` finalized and pinned.
- [ ] README with complete setup + run instructions.
- [ ] Reproducibility check performed and documented, with outcome recorded.
- [ ] Random seeds recorded and applied where supported.

## Definition of Done
All acceptance criteria met; a fresh clone of the repository can be set up and run end-to-end using only the README, and the reproducibility check confirms stable results.
