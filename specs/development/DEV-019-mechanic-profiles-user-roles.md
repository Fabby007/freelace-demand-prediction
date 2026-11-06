# DEV-019 — User Roles & Mechanic Profiles

## Specification ID
DEV-019

## Feature/Module Name
Mechanic Profile Management

## Purpose
Let a mechanic build and maintain the profile customers will discover and contact: contact number, district, vehicle types handled, services offered, years of experience, description, and optional profile photo.

## Background/Context
MARKETPLACE_EXTENSION.md Section 4.2; REF-011 Sections 3.2–3.5 (`MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType`); REF-012 Section 5 (photo upload security); REF-013 Section 2 (profile page layout).

## Related Requirements
FR-M08, FR-M10, FR-M11.

## User Roles
Mechanic (owns and edits their profile). Customer and Admin can view a mechanic profile (read-only for customers via DEV-020's profile page; admin's management view is DEV-022's concern, reusing this spec's data model).

## Preconditions
DEV-018 complete (a mechanic `User` account exists and can log in).

## User Stories/Use Cases
- As a newly registered mechanic, I want to be guided to complete my profile right after registration so my listing isn't blank.
- As a mechanic, I want to edit my contact number, district, services, vehicle types, experience, and description whenever they change.
- As a mechanic, I want to upload a profile photo so customers recognize me, but I want the app to work fine if I skip this.
- As a mechanic, I must not be able to edit anyone else's profile, even by guessing a URL.

## Functional Requirements
- FR1 Define `MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType` SQLAlchemy models exactly per REF-011 Sections 3.2–3.5.
- FR2 Seed the `Service` table with a starter canonical list (proposed: "General Repair & Servicing", "Engine Diagnostics & Repair", "Electrical Work", "Tyre & Battery Service", "Body Work & Painting", "Scheduled Maintenance"), clearly labelled as seed/reference data in the seeding script's docstring, editable only by an admin thereafter (DEV-022).
- FR3 Build a "complete your profile" flow: a mechanic with no `MechanicProfile` row is redirected there after login/registration until they save one; after that, they land on `mechanic_dashboard.html` by default.
- FR4 Build `mechanic_edit_profile.html`: form fields for contact number, district (dropdown, REF-002's 25 canonical names), years of experience, description, multi-select vehicle types (checkboxes, the 3 canonical values), multi-select services (checkboxes, from `Service`), and an optional photo upload.
- FR5 Implement profile save (create-or-update) — a mechanic with an existing profile editing the form updates the same row (`updated_at` refreshed), never creates a second `MechanicProfile` for the same user (enforced by REF-011's unique `user_id`).
- FR6 Implement `mechanic_dashboard.html`: shows the mechanic's own profile summary, a link to edit it, their average rating and review count (read-only here; full review list detail is DEV-021), and a link to Opportunity Insights (DEV-023).
- FR7 Implement profile photo upload per REF-012 Section 5 exactly: extension allow-list, server-side size limit, randomized stored filename, default placeholder avatar shown when no photo is set.

## Business Rules
- A mechanic may edit only their own profile — enforced by `current_user.id == mechanic_profile.user_id`, checked server-side on every edit/save request, not inferred from the UI.
- `years_experience` must be a non-negative integer; a mechanic entering a negative or non-numeric value sees a validation error, not a silently-clamped value.
- At least one vehicle type and at least one service should be selected before a profile is considered "complete" for search purposes (a profile with zero vehicle types/services is technically saveable but will never match any filtered search — DEV-020 — so the edit form should nudge, not block, this).

## Data Requirements
Reads/writes: `MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType` (REF-011). No ML-system `data/` files touched.

## Database/Schema Changes
Adds the four tables above to `instance/marketplace.db`, per REF-011.

## API Requirements
None.

## Backend Behavior
`app/routes/mechanic.py` holds the profile create/edit/view routes; `app/models/mechanic.py` holds the SQLAlchemy models; upload handling lives in a small helper (e.g. `app/utils/uploads.py`) reused later if other upload needs arise.

## Frontend Behavior
`mechanic_edit_profile.html` uses Flask-WTF form rendering; a small vanilla-JS snippet previews the selected photo before upload (pure UX convenience, not a security boundary — REF-012 Section 5 remains authoritative server-side).

## UI States
- **No profile yet:** forced-redirect "complete your profile" state.
- **Profile exists, view mode:** `mechanic_dashboard.html` summary.
- **Edit mode:** pre-filled form.
- **Save error:** validation errors shown inline, form re-rendered with entered values (except the file input, which browsers cannot repopulate — user must reselect the photo).

## Validation
Per FR4/Business Rules above; server-side WTForms validators for every field; photo upload validated per REF-012 Section 5.

## Permissions
Only the owning mechanic (`role='mechanic'`, matching `user_id`) may create/edit their profile. Admin may edit any profile for moderation purposes only (DEV-022), not through this spec's own routes.

## Error Cases
- Attempted edit of a `mechanic_id` that doesn't belong to `current_user` — HTTP 403, no data leaked about the other profile.
- Upload of a disallowed file type/oversized file — rejected with a clear inline error, profile fields otherwise unaffected (the rest of the form still saves if the photo alone is rejected, or the whole submission fails atomically — implementation decision, propose: whole submission fails atomically so a mechanic isn't left wondering why their photo didn't appear).

## Edge Cases
- Mechanic profile with zero services/vehicle types selected — saveable, but a note in the UI ("Add at least one vehicle type and service so customers can find you") is shown; the profile still appears in an unfiltered "browse all" search.
- Very long `description` text — enforce a reasonable max length (proposed 2000 characters) to prevent layout breakage and abuse, server-side.

## Security Considerations
REF-012 Section 5 in full (upload handling); ownership check per Business Rules above.

## Dependencies
DEV-018 (Web Application Foundation & Auth).

## Testing Requirements
`tests/marketplace/test_mechanic_profile.py` (28 tests, all passing): profile create/edit round-trip; ownership isolation (see the note on route design below); role restrictions (customer/admin/anonymous all rejected on both mechanic routes); DB relationship correctness (1:1 User↔MechanicProfile, M:N via MechanicService, 1:N MechanicVehicleType with delete-orphan cascade); vehicle-type/service selection save and replace correctly on edit; invalid form data (negative years, bad phone format, missing fields, a tampered/non-canonical vehicle-type value); profile viewing renders every saved field; photo upload accepts valid PNG/JPEG, rejects a disallowed extension, rejects a file whose content doesn't match its claimed extension, and rejects an oversized file (413); service seeding is present and idempotent; the profile-completion redirect fires correctly and only for a profile-less mechanic.

## Route design note (ownership enforcement)
`/mechanic/profile/edit` takes **no ID parameter** — it always resolves and mutates `current_user.mechanic_profile` only. This is a stronger ownership guarantee than a checked-and-rejected `mechanic_id` in the URL: there is no URL a mechanic could construct that even *names* another mechanic's profile, so "mechanic A cannot edit mechanic B's profile" is true by construction, not by a runtime check that could be forgotten on a future route. Verified by test (`test_editing_own_profile_never_affects_another_mechanics_profile`): mechanic A submits an edit while mechanic B's existing profile is present in the database, and B's row is asserted byte-for-byte unchanged afterward.

## Acceptance Criteria
- [x] All four models created and schema matches REF-011 exactly, including both `CheckConstraint`s (`years_experience >= 0`, `vehicle_type IN (...)`) and the unique `user_id` — all three verified directly against the database (an out-of-band violation of each raises `IntegrityError`), not only through the application layer.
- [x] Mechanic can create, view, and edit their own profile end-to-end through the UI.
- [x] Mechanic cannot edit another mechanic's profile — verified by test (see the route design note above), not by omission of a UI link.
- [x] Photo upload works for valid images and safely rejects invalid ones — extension allow-list, magic-byte content sniff, and the global 2MB size cap (yielding a dedicated 413 page) all verified by test.
- [x] `Service` seed data present (6 starter rows, auto-seeded idempotently at app startup) and admin-editable (hook only — no CRUD UI is built here; that is DEV-022).
- [x] All tests in `tests/marketplace/test_mechanic_profile.py` pass (28/28); full marketplace suite (`tests/marketplace/`) passes (54/54, including all pre-existing DEV-018 tests — one was updated, not weakened, to match DEV-019's intentional change to `/mechanic/profile`'s behavior, see Additional Implementation Notes).
- [x] Full existing ML test suite (`pytest tests/ --ignore=tests/marketplace`) remains unaffected. Across three separate runs during DEV-019 verification: 191/191 clean; 190/191 with the pre-existing `test_dashboard_app.py::test_app_runs_without_exceptions` flake (already documented in DEV-018.md) recurring; and 191/191 clean again. Re-verified independently both times the flake was absent and present: `pytest tests/test_dashboard_app.py` alone passed 13/13 in both a 21s and a 24s run, confirming the flake is a run-to-run timing issue under full-suite load, not a deterministic failure and not caused by DEV-019.
- [x] **Final combined-suite run** (`pytest tests/`, ML + marketplace together): **245/245 passed, 0 failures, 48.41s** — a completely clean run, `grep`-verified for zero `FAILED`/`ERROR` lines, including `test_dashboard_app.py::test_app_runs_without_exceptions`. This is the authoritative record for DEV-019 sign-off.

## Additional implementation notes (added post-implementation)
- **Public profile viewing intentionally NOT built here.** DEV-019's own User Roles section already scopes public/customer-facing profile viewing to DEV-020 ("read-only for customers via DEV-020's profile page"). This implementation adds only the mechanic's own self-view (`mechanic_dashboard.html`, role-gated to the owning mechanic) — no new anonymous/public route was added, consistent with the instruction not to start DEV-020's search/discovery/profile-viewing functionality here.
- **DEV-018's login route was extended, not just DEV-019's own files.** FR3 ("redirected there after login... until they save one") is inherently a login-time behavior, so `app/routes/auth.py::login()` gained one new branch: a mechanic with no `MechanicProfile` is redirected straight to `mechanic.edit_profile` (ahead of any `next=` target), with the rest of the login flow completely unchanged for every other case. One existing DEV-018 test (`test_stub_role_protected_pages_reachable_by_correct_role`) asserted `/mechanic/profile` returned a bare 200 for any authenticated mechanic — that assumption was specific to DEV-018's stub and is now genuinely different behavior (a 302 to the edit form for a profile-less mechanic, by design); the test was updated to assert the new, correct behavior rather than weakened or deleted.
- **Vehicle-type/service selections are replaced wholesale on every save**, not diffed — `profile.vehicle_type_rows` and `profile.services` are reassigned to the newly-submitted set each time (relying on SQLAlchemy's `cascade="all, delete-orphan"` for the former and its standard `secondary=` handling for the latter). Simpler than incremental diffing and correct at this data scale (a handful of rows per mechanic).
- **Service starter list is auto-seeded at app startup** (`seed_default_services()`, called from `create_app()` right after `db.create_all()`), not via a separate CLI command — idempotent (no-op once any `Service` row exists), so it never overwrites an admin's later edits (DEV-022) and needs no manual setup step before the app is first used. Logged as REF-009 ADR-030.
- **District choices are read from `configs/district_lookup.csv`** (`app/utils/canonical.py::canonical_districts()`) rather than a second hand-copied list, reusing REF-002's canonical source directly.

## Definition of Done
All acceptance criteria met; a mechanic's completed profile is immediately ready to be found by DEV-020's search once implemented.
