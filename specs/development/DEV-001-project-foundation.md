# DEV-001 — Project Foundation, Environment & Repository Structure

## Specification ID
DEV-001

## Feature/Module Name
Project Foundation, Environment & Repository Structure

## Purpose
Establish the repository, folder skeleton, Python environment, dependency pinning, config scaffolding and version control so every later spec has a consistent place to add code, data, configs, tests and docs.

## Background/Context
The source documentation requires a modular, maintainable codebase (Section 22 "Maintainability") with an Appendix B-derived folder structure, Git/GitHub version control (Section 24), and a documented, pinned Python environment (Section 22 "Portability", Section 30). MASTER_PROMPT.md Section 8 extends Appendix B with the `specs/` SpecKit directory. This spec is the entry point for the whole project; every other DEV spec depends on it.

## Related Requirements
- NFR: Maintainability, Portability, Reproducibility (`specs/reference/REF-004-nfr-and-scope-boundaries.md`)
- Section 24 (Experiment Tracking, Reproducibility and Version Control) — GitHub, requirements.txt/pyproject.toml, configuration files
- Appendix B (folder structure), REF-008 (Technology Stack Reference)

## User Roles
None (infrastructure spec; no end-user-facing behavior). See CLAUDE.md Section 4 — no auth/role system in this project.

## Preconditions
None — this is the first spec.

## User Stories/Use Cases
- As the developer, I need a consistent folder layout so extraction, features, models, explainability, NLP, recommendation and dashboard code stay separated (Maintainability NFR).
- As the developer, I need pinned dependencies so the project is reproducible on another machine (Portability NFR).
- As the developer, I need config scaffolding so feature lists/target name/split dates/model params are not hardcoded later.

## Functional Requirements
1. Initialize a Git repository (and GitHub remote, when the user is ready to create/authorize one — repository creation and any push to a remote requires explicit user confirmation, per the assistant's own operating rules; do not create or push to a remote without asking).
2. Create the full Appendix-B-derived folder structure (Section 12 of CLAUDE.md / REF-008 Section 3): `specs/development/`, `specs/reference/`, `data/raw/`, `data/interim/`, `data/processed/`, `notebooks/`, `src/data/`, `src/features/`, `src/models/`, `src/explainability/`, `src/nlp/`, `src/recommendation/`, `dashboard/`, `models/`, `reports/`, `tests/`, `configs/`.
3. Create a Python 3.10+ virtual environment (documented in README, not committed).
4. Create `requirements.txt` (or `pyproject.toml`) pinning the exact stack from REF-008 Section 2.
5. Create `configs/` scaffolding: placeholder config files for feature lists, target name, chronological split dates, and model hyperparameters (populated with real values later by DEV-005/DEV-006/DEV-008/DEV-009; scaffolded here as empty/templated so downstream specs have a fixed location to write to).
6. Create `.gitignore` covering typical Python/venv/data artefacts (raw/interim/processed data and trained model binaries are excluded from version control by default unless the user decides otherwise — record that decision as an ADR if it deviates from a "commit everything" assumption).
7. Create root `README.md` stub (fully populated by DEV-017) and root `TODO.md`/`CLAUDE.md` (already created — see Stage 2 output).

## Business Rules
- No feature/module implementation happens under this spec beyond scaffolding — this spec creates structure, not application logic.
- Folder names and structure must match REF-008 Section 3 exactly; do not add extra top-level folders without an ADR.

## Data Requirements
None (no data is collected under this spec).

## Database/Schema Changes
None.

## API Requirements
None.

## Backend Behavior
N/A — infrastructure only.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
- Verify every folder in REF-008 Section 3 exists after setup.
- Verify `requirements.txt`/`pyproject.toml` installs cleanly in a fresh virtual environment.

## Permissions
N/A — no auth system (CLAUDE.md Section 11).

## Error Cases
- Dependency installation failure — record the failing package/version and resolve before proceeding; do not silently drop a required stack component (e.g. do not remove SHAP or TensorFlow because installation is inconvenient — Hard Rule, MASTER_PROMPT.md Section 0).

## Edge Cases
- Windows vs. Unix path handling in scripts (this project is developed on Windows per the environment; use `pathlib` and OS-agnostic path handling throughout to avoid hardcoded path separators).

## Security Considerations
- `.gitignore` must exclude any credentials/API keys used for data acquisition (e.g. Kaggle API token) — never commit secrets.

## Dependencies
None (root spec).

## Testing Requirements
- A smoke test that imports each top-level `src/` package successfully (added once packages exist; can be a placeholder here, implemented fully once DEV-003 onward add real modules).

## Acceptance Criteria
- [x] Folder structure matches REF-008 Section 3 exactly.
- [x] `requirements.txt`/`pyproject.toml` exists and pins the full REF-008 stack — plus transitively-required pins discovered during install (`pyarrow` ADR-002, `torch` ADR-003, `setuptools` ADR-004); full stack verified to install and import together in one process (`tests/test_environment.py`, passing).
- [x] `configs/` contains placeholder files for feature list, target name, split dates, and model hyperparameters.
- [x] Git repository is initialized locally.
- [x] `.gitignore` excludes venv, data artefacts, and secrets appropriately.

## Definition of Done
All acceptance criteria met; folder structure, environment, and config scaffolding exist. **Not yet committed** — all work is staged in the local git repository but no commit has been made (commits are only created on explicit user request, per operating constraints); TODO.md Phase 0 items are checked off only once each is genuinely satisfied.
