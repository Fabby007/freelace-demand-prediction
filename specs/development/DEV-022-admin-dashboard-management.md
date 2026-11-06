# DEV-022 — Admin Dashboard & Management

## Specification ID
DEV-022

## Feature/Module Name
Admin Dashboard & Management

## Purpose
Give the admin a single set of screens to view and manage customer accounts, mechanic accounts/profiles, and reviews — including blocking accounts and removing/restoring reviews.

## Background/Context
MARKETPLACE_EXTENSION.md Section 4.3; REF-012 Sections 3–4 (admin-only rows, blueprint-level role gating).

## Related Requirements
FR-M13, FR-M14, FR-M15, FR-M16.

## User Roles
Admin only. No customer- or mechanic-facing surface in this spec.

## Preconditions
DEV-018 (admin account provisioning, `role_required`), DEV-019 (mechanic profiles to manage), DEV-021 (reviews and moderation functions to expose) complete.

## User Stories/Use Cases
- As an admin, I want to see a list of all customer accounts and block one that's abusing the platform.
- As an admin, I want to see a list of all mechanic accounts/profiles and block one, e.g. for posting false information.
- As an admin, I want to review a list of all submitted reviews and remove one that's abusive or clearly fake, with the option to restore it if I made a mistake.
- As an admin, I want a single dashboard landing page summarizing counts (customers, mechanics, reviews, blocked accounts) so I have a quick overview.

## Functional Requirements
- FR1 Build `admin_dashboard.html`: summary counts (total customers, total mechanics, total reviews, blocked accounts, admin-removed reviews) and navigation to the three management views below.
- FR2 Build `manage_users.html` (or two views/tabs — customers and mechanics): paginated list of `User` rows filterable by role and status, with a block/unblock action per row.
- FR3 Build a mechanic-profile management view: list of `MechanicProfile` rows (joined to `User` for name/status) with a link to view the full profile and a block action (blocking the underlying `User` row is sufficient — REF-011 has no separate "active" flag on `MechanicProfile` itself, avoiding a redundant status field).
- FR4 Build `manage_reviews.html`: paginated list of all reviews (visible and admin-removed) with remove/restore actions, calling DEV-021's `remove_review`/`restore_review` functions directly rather than reimplementing the state transition.
- FR5 Implement account deletion (FR-M14/FR-M15 mention "delete" alongside block/unblock) as a distinct, explicitly-confirmed action separate from block/unblock — deleting a `User` cascades to their `MechanicProfile`/`Review` rows per standard FK cascade rules, documented clearly since it is irreversible (unlike block, which is reversible) and unlike review removal (which is soft).
- FR6 All admin routes live under the `/admin` URL prefix and are protected by `role_required('admin')` at the blueprint level (REF-012 Section 4), in addition to any per-view check.

## Business Rules
- Blocking a user is reversible (unblock); deleting a user is not — the UI must visually distinguish these two actions (e.g. different button styling, a confirmation dialog specifically for delete) so an admin does not confuse them.
- Blocking a mechanic immediately removes them from search results and makes their profile URL return "not found" (reuses DEV-020's existing exclusion logic for `status='blocked'` users — no separate mechanism needed).
- An admin cannot block or delete their own admin account through this UI (a basic self-lockout guard).
- Review removal/restoration reuses DEV-021's functions exactly; this spec adds no new review-state logic.

## Data Requirements
Reads/writes: `User`, `MechanicProfile` (via cascade/join), `Review` (status only, via DEV-021's functions).

## Database/Schema Changes
None beyond what DEV-018/019/021 already define — this spec is a management UI over existing tables, not a new schema.

## API Requirements
None.

## Backend Behavior
`app/routes/admin.py`, a single Flask Blueprint registered with `url_prefix='/admin'` and a blueprint-level `before_request` role check (REF-012 Section 4) as defense in depth alongside per-view `@role_required('admin')` decorators.

## Frontend Behavior
Plain HTML tables with action buttons/forms (block/unblock/delete/remove/restore), each a CSRF-protected POST form — no bulk-action JS required for this scale.

## UI States
- **Dashboard:** summary counts.
- **User list (filtered by role/status):** table with action buttons.
- **Review list (filtered by status):** table with remove/restore buttons.
- **Confirmation dialogs:** delete-account action requires an explicit confirm step (server-rendered confirm page or a JS `confirm()` as a UX convenience — server-side the action still requires the correct HTTP method, e.g. POST, not a GET link, so it can't be triggered by e.g. a prefetching browser or CSRF-forged link).

## Validation
Row IDs in every management action are validated to exist and be of the expected type before acting; a nonexistent ID returns a clear "not found" flash message, not a server error.

## Permissions
Admin only, enforced at the blueprint level (REF-012 Section 4) — a customer or mechanic hitting any `/admin/*` URL directly receives HTTP 403, never a redirect that could be mistaken for "logged in as admin."

## Error Cases
- Attempting to block/delete a nonexistent or already-deleted user — clear error, no crash.
- Attempting self-block/self-delete — explicitly rejected with a clear message (Business Rules above).

## Edge Cases
- Deleting a mechanic with existing reviews — cascade behavior must be decided and documented explicitly (proposed: reviews of a deleted mechanic are deleted along with the profile via FK cascade, since a review with no mechanic to attach to is meaningless; log as an ADR if this needs adjusting during implementation).
- Blocking (not deleting) a mechanic with existing reviews — reviews remain in the database (mechanic is merely hidden from search/profile access, not erased), consistent with the reversibility of "block."

## Security Considerations
Blueprint-level role gate (REF-012 Section 4); CSRF on every action form; every destructive action (delete) requires POST + explicit confirmation, never a bare GET link.

## Dependencies
DEV-018 (Foundation & Auth), DEV-019 (Mechanic Profiles), DEV-021 (Review moderation functions).

## Testing Requirements
`tests/marketplace/test_admin.py` (32 tests, all passing): every non-admin role (anonymous, customer, mechanic) rejected on every `/admin/*` GET route and on every POST action; admin dashboard renders accurate counts and reflects a review-removal change; user list shows/filters customer and mechanic rows and excludes admin rows entirely; block/unblock verified against real DEV-020 search visibility and real DEV-018 login behavior (including re-login after unblock); self-block/self-delete and admin-manages-admin all rejected (404, not merely hidden); delete cascades verified for both a customer (their written reviews) and a mechanic (profile, vehicle types, service associations, received reviews); CSRF required on delete; no password hash ever appears in an admin page; the mechanics list links to DEV-020's real profile page, extended so an admin (and only an admin) can view a blocked mechanic's full profile; review list/filter/remove/restore reuses DEV-021's functions and is verified against DEV-021's own `compute_rating_stats()`; nonexistent IDs handled safely for both users and reviews; a regression check that a role field smuggled into public registration still cannot create an admin account; two regression checks confirming DEV-019/DEV-021 ownership rules are untouched.

## Acceptance Criteria
- [x] Admin dashboard shows accurate summary counts — customers, mechanics, mechanic profiles, blocked accounts, total reviews, admin-removed reviews; verified against hand-computed expected values, not just "some number renders."
- [x] Admin can block/unblock/delete customer and mechanic accounts; effects verified against search (DEV-020) and login (DEV-018) behavior — a blocked mechanic disappears from `/search` and gets a "deactivated" message at login; unblocking restores both.
- [x] Admin can remove/restore reviews; effects verified against the average-rating computation (DEV-021) — `compute_rating_stats()` called directly in the test, not just checked via rendered HTML.
- [x] No non-admin role can reach any `/admin/*` route (verified by test, including a logged-out visitor) — every GET route and every POST action checked individually.
- [x] All tests in `tests/marketplace/test_admin.py` pass (32/32); full marketplace suite 150/150; ML test suite unaffected (191/191 alone; combined-suite result recorded in TODO.md Phase 20).

## Additional implementation notes (added post-implementation)
- **Cascade delete is ORM-level, verified empirically before use** — `cascade="all, delete-orphan"` added to both `User`-side relationship backrefs (`MechanicProfile.user`, `Review.customer`); `Review.mechanic`'s side already had it from DEV-021. A single `db.session.delete(user)` now correctly cascades in both directions. See REF-009 ADR-033 for the full reasoning and the alternatives considered.
- **Admin accounts are excluded from every management route, not just self-protected.** `_get_manageable_user_or_404()` 404s for any `role='admin'` target, which structurally satisfies "cannot block/delete own account" (an admin's own row is always `role='admin'`) and additionally rules out one admin managing another — a capability REF-012's matrix never documented. REF-012 Section 3 gained an explicit "Delete a customer or mechanic account" row to make this scope visible rather than implicit.
- **`/mechanic/<id>` (DEV-020) was extended, not duplicated, for admin viewing.** FR3's "link to view the full profile" reuses the exact same public profile route/template — for a non-admin viewer the behavior is completely unchanged (blocked → 404); for an admin viewer, the same route's underlying query is allowed to include blocked accounts, with a small "blocked and hidden from customer search" banner added to the template, visible only to admins. No second, admin-specific profile-rendering template was built.
- **A harmless hidden CSRF field was added to the (GET-only) filter forms** on `admin/users.html` and `admin/reviews.html`, so a valid session-bound token is always present on the page even when the results table has zero matching rows — otherwise there would be no form anywhere on the page to source a token from for the very first management action.

## Definition of Done
All acceptance criteria met; every management action produces the same effect a corresponding customer/mechanic-side spec (DEV-018/019/020/021) already defines for "blocked" or "removed" state, with no duplicated or divergent logic — verified directly (e.g. `compute_rating_stats()` called from the test after admin removal, not a re-implemented average) rather than only by inspection.
