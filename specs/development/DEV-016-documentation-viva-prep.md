# DEV-016 — Documentation, Reporting & Viva Preparation

## Specification ID
DEV-016

## Feature/Module Name
Documentation, Reporting & Viva Preparation

## Purpose
Produce the technical documentation, user guide, model evaluation/error-analysis report, and viva/presentation material required as final deliverables.

## Background/Context
Source doc Section 29 (Project Deliverables, items 11–12), Section 32 (Viva/Presentation Explanation).

## Related Requirements
- Section 29, Section 32
- REF-003 (component rationale, reused directly as talking points)

## User Roles
None (documentation deliverable; audience is the academic assessor/viva panel).

## Preconditions
All prior DEV specs substantially complete (DEV-PLAN.md Section 3).

## User Stories/Use Cases
- As the developer/student, I need documentation and a user guide so the system is understandable and usable by someone who didn't build it.
- As the developer/student, I need a clear, honest error-analysis report and viva talking points so I can defend the project's methodology and results.

## Functional Requirements
1. **Technical documentation:** architecture overview (reuse REF-003 Section 3 architecture flow), module descriptions (per `src/` package), data pipeline description (DEV-002–DEV-006), model descriptions (DEV-007–DEV-009), explainability/NLP/ranking descriptions (DEV-010–DEV-012), dashboard description (DEV-013).
2. **User guide:** how to run the dashboard, what each control/panel does (reuse Section 19 descriptions), how to interpret opportunity bands and the disclaimer (reuse REF-007 wording rules).
3. **Model evaluation / error-analysis report:** consolidate DEV-014's evaluation report; add honest discussion of where/why the model underperforms (e.g. specific districts/vehicle types with sparse data), referencing REF-006's risk table explicitly rather than omitting known limitations.
4. **Viva/presentation material:** built directly from Section 32 (verbatim talking points, reproduced in REF-003 Sections 4–7): why mechanics, why XGBoost, why LSTM, why SBERT, why SHAP, plus the short explanation (Section 32.1) as an elevator-pitch script.

## Business Rules
- Documentation must not overstate results (e.g. must not claim job-count precision unless the Preferred target path genuinely supports it — DEV-002).
- Known limitations (REF-006) must be disclosed in the documentation, not omitted to make the project look more complete than it is.

## Data Requirements
Draws from: DEV-002 (source register), DEV-006 (dataset version/decisions), DEV-014 (evaluation report), REF-003 (component rationale), REF-006 (risks/limitations), REF-007 (terminology/wording).

## Database/Schema Changes
None.

## API Requirements
None.

## Backend Behavior
N/A.

## Frontend Behavior
N/A.

## UI States
N/A.

## Validation
Documentation reviewed against `specs/COVERAGE.md` to confirm every major requirement/deliverable is described somewhere in the final documentation set.

## Permissions
N/A.

## Error Cases
N/A.

## Edge Cases
N/A.

## Security Considerations
Documentation must not include any personal data inadvertently captured during development (REF-005).

## Dependencies
- All prior DEV specs (DEV-001 through DEV-015) substantially complete.
- REF-003, REF-006, REF-007

## Testing Requirements
Manual review checklist: every deliverable in Section 29 items 11–12 is present; every Section 32 talking point is covered in the viva material.

## Acceptance Criteria
- [ ] Technical documentation covers architecture, all modules, and the data pipeline.
- [ ] User guide covers dashboard usage and result interpretation.
- [ ] Model evaluation / error-analysis report is honest about limitations (references REF-006).
- [ ] Viva/presentation material covers all Section 32 talking points.

## Definition of Done
All acceptance criteria met; the documentation set is sufficient for someone unfamiliar with the project to run the dashboard, understand the results, and understand the reasoning behind each major design choice.
