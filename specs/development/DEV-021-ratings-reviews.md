# DEV-021 — Ratings & Reviews

## Specification ID
DEV-021

## Feature/Module Name
Ratings & Reviews

## Purpose
Let a logged-in customer submit, edit, and delete a rating/review for a mechanic, and let anyone viewing a mechanic's profile see the review list and computed average rating.

## Background/Context
MARKETPLACE_EXTENSION.md Section 4.1; REF-011 Section 3.6 (`Review`); REF-013 Section 4 (rules in full).

## Related Requirements
FR-M06, FR-M07, FR-M11 (mechanic viewing own reviews).

## User Roles
Customer (submit/edit/delete own review). Mechanic (view own reviews, read-only). Admin (moderate — remove/restore; full admin UI is DEV-022, but this spec defines the underlying moderation actions/model state).

## Preconditions
DEV-018 (auth), DEV-019 (mechanic profiles to review), DEV-020 (profile page the review section attaches to) complete.

## User Stories/Use Cases
- As a customer who contacted a mechanic outside the system, I want to come back and leave a star rating and a written review.
- As a customer, I want to change my mind and edit my review later, without creating a duplicate entry.
- As a customer, I want to delete my own review if I no longer want it public.
- As a mechanic, I want to see what customers have said about me.
- As an admin, I need a way to remove a review that is abusive or clearly fake (full UI in DEV-022; this spec provides the model/action).

## Functional Requirements
- FR1 Define `Review` SQLAlchemy model exactly per REF-011 Section 3.6, including the `(customer_id, mechanic_id)` unique constraint and the `rating` `CheckConstraint(1..5)`.
- FR2 On a mechanic's profile page, show a "Leave a review" form to a logged-in customer who has **not** yet reviewed this mechanic, or an "Edit your review" form (pre-filled) if they have.
- FR3 Reject review submission attempts by non-customers (mechanics, admins, anonymous visitors) — anonymous visitors are redirected to login; mechanics/admins see the review form is simply not offered (role check server-side, not just UI hiding).
- FR4 Implement review edit (updates the existing row, `updated_at` refreshed) and delete (hard delete, customer's own data-ownership action — REF-013 Section 4) for the owning customer only.
- FR5 Implement average-rating and review-count computation as a single aggregate query (`AVG`/`COUNT` over `status='visible'` rows for the mechanic), reused by both DEV-020's search-result cards and this spec's profile-page display so the two numbers can never diverge.
- FR6 Render the review list (reviewer name, rating, text, date) on the mechanic profile page, most recent first, excluding `status='removed_by_admin'` rows.
- FR7 Render the review-disclaimer sentence (REF-013 Section 4, verbatim or materially equivalent) directly adjacent to the review list on every page that shows reviews.
- FR8 Implement the admin moderation actions (`remove_review(review_id)` → sets `status='removed_by_admin'`; `restore_review(review_id)` → sets `status='visible'`) as functions callable by DEV-022's admin routes; this spec does not build the admin UI itself.

## Business Rules
See REF-013 Section 4 in full: one review per customer per mechanic (edit, not duplicate); rating required 1–5; review text required with a minimum length; average rating excludes admin-removed reviews; admin removal is soft (reversible), customer deletion is hard (permanent).

## Data Requirements
Reads/writes: `Review`. Reads (for display): `User` (reviewer name), `MechanicProfile`.

## Database/Schema Changes
Adds `review` table per REF-011 Section 3.6.

## API Requirements
None.

## Backend Behavior
`app/routes/customer.py` (or a dedicated `app/routes/reviews.py`) holds submit/edit/delete routes, scoped under the customer's own session; moderation functions live in `app/models/review.py` or a small `app/services/moderation.py`, called from DEV-022.

## Frontend Behavior
Review form: a 1–5 star-selector (small vanilla-JS widget for UX, but the underlying `<select>`/radio value is what's actually submitted and validated server-side) plus a text area.

## UI States
- **No existing review (customer, logged in):** blank "Leave a review" form.
- **Existing review (customer, logged in):** pre-filled "Edit your review" form, with a "Delete my review" option.
- **Not logged in / non-customer role:** review list is visible; the submission form is replaced with a "Log in as a customer to leave a review" prompt (not shown at all to mechanics/admins viewing the page).
- **No reviews yet:** "No reviews yet — be the first to review this mechanic" message instead of an empty list.

## Validation
`rating`: required, integer 1–5 (WTForms `NumberRange` + DB `CheckConstraint`, defense in depth per REF-012 Section 5). `review_text`: required, minimum length (proposed 10 characters), maximum length (proposed 1000 characters) to prevent abuse.

## Permissions
Per REF-012 Section 3: submit/edit/delete own review — customer only, own review only. Remove/restore — admin only (function defined here, exposed by DEV-022).

## Error Cases
- A customer attempting to submit a second, separate review for the same mechanic (bypassing the UI, e.g. a direct POST) — rejected by the database unique constraint, surfaced as a clear "you've already reviewed this mechanic — edit your existing review instead" message, not a raw database error.
- A customer attempting to edit/delete another customer's review by guessing a review ID — HTTP 403, no content leaked about the review's existence.

## Edge Cases
- A mechanic with zero reviews — average rating displayed as "No ratings yet," never as 0 or blank (0 would misleadingly imply a real 0-star average).
- A review submitted for a mechanic whose profile is later edited (e.g. district changed) — the review remains attached to the mechanic, unaffected by unrelated profile edits.
- An admin-removed review's effect on an already-computed average rating shown elsewhere (e.g. a cached search page) — since averages are computed live (REF-011 Section 2), no stale-cache invalidation issue exists.

## Security Considerations
Ownership check (`current_user.id == review.customer_id`) on every edit/delete; role check (`role == 'customer'`) on every submit; review text is rendered via Jinja2's automatic autoescaping (no raw HTML injection from review content — no `|safe` filter is applied to user-submitted text anywhere).

## Dependencies
DEV-018 (Auth), DEV-019 (Mechanic Profiles), DEV-020 (Profile page host).

## Testing Requirements
`tests/marketplace/test_reviews.py` (40 tests, all passing): submit/edit/delete round-trip; duplicate-submission (second POST edits, not duplicates) and the DB-level race-condition backstop; non-customer roles (mechanic, admin, anonymous) all rejected from submitting, and from a blocked mechanic's page; every rating-boundary and review-text-length case (0, 6, -1, missing rating; too-short, too-long, missing text); CSRF required; ownership enforcement on edit (an "editor" only ever touches their own row) and delete (403-equivalent 404 on another customer's review, never leaking its existence); DB constraints (`CHECK` on rating range, `UNIQUE` on customer+mechanic) verified directly, not only through the app layer; average-rating computation (multi-review average, zero-review `None`, admin-removed exclusion, and the bulk-vs-single computation provably matching); real ratings/review lists rendered on the public profile, the mechanic's own dashboard, and search-result cards; the real rating-based sort (higher-rated first, unrated after all rated ones); the customer's own "My Reviews" page and its empty state; the two admin moderation functions directly; and three regression checks confirming DEV-019/DEV-020 rules are untouched.

## Acceptance Criteria
- [x] `Review` model matches REF-011 Section 3.6 exactly, including both `CheckConstraint`s and the `UniqueConstraint` — the uniqueness rule's exact scope (unconditional, not `status='visible'`-scoped) is a documented implementation decision, see REF-009 ADR-032.
- [x] Customer can submit, edit, and delete their own review; cannot create a duplicate (the second submission edits the existing row) or touch another customer's review — verified by test, including that the edit/delete routes take no `review_id` in the URL at all (same stronger-than-required ownership pattern DEV-019 established: nothing to guess).
- [x] Average rating/review count correct and consistent between the search-result card (DEV-020), the public profile page, and the mechanic's own dashboard (FR-M11) — all three call the same `compute_rating_stats`/`compute_rating_stats_bulk` functions, with `compute_rating_stats()` itself implemented as a thin wrapper over the bulk version so the two code paths are provably identical, not independently maintained.
- [x] Admin moderation functions (`remove_review`/`restore_review`) work correctly and are excluded/included from the average and list as specified — verified directly (function-level tests) and end-to-end (a removed review disappears from the profile page's list and average).
- [x] Review disclaimer sentence visible wherever reviews are shown — the public profile page and the mechanic's own dashboard (REF-013 Section 4's literal scope); the customer's own "My Reviews" page does not repeat it, consistent with REF-013 Section 4 naming only those two surfaces.
- [x] All tests in `tests/marketplace/test_reviews.py` pass (40/40); full marketplace suite 118/118; ML test suite unaffected (191/191 alone; combined-suite result recorded in TODO.md Phase 19).

## Additional implementation notes (added post-implementation)
- **DEV-020's rating-sort dependency-sequencing gap is now closed.** `app/routes/marketplace.py::_search_mechanics()` no longer falls back to alphabetical-only ordering (REF-009 ADR-031's temporary state) — it now orders by a correlated `AVG(rating)` subquery, descending, `NULLS LAST`, with name as the tie-break. Every "No ratings yet" placeholder (search cards, public profile, mechanic dashboard) now renders the real computed value once reviews exist, via one shared Jinja macro (`_review_helpers.html::render_rating_summary`), so there is exactly one place that decides how to display "no rating yet" vs. a real number.
- **Customer "My Reviews" page implemented**, replacing the DEV-018/DEV-019 stub the nav bar already linked to (`customer.reviews`) — lists the customer's own reviews (any status, with a "Hidden by moderator" tag if admin-removed) with a link to each mechanic's profile and a direct delete action. Not explicitly itemized in DEV-021's FR list, but a natural, low-risk completion of an already-declared nav feature, directly serving FR4's "customer may edit/delete their own review" via a second, convenient entry point (in addition to the profile page itself).
- **Mechanic's own dashboard (DEV-019's `mechanic_dashboard.html`) updated** to show the real average rating and full review list, reusing the identical `_review_helpers.html` macros the public profile uses — satisfies FR-M11 ("mechanic viewing own reviews").
- **CSRF tokens are session-bound, not page-bound** — a subtlety that broke four tests during development (fixed, not weakened): the review form only renders for an authenticated customer, so a test simulating an anonymous/mechanic/admin submission attempt must fetch its CSRF token from a page that renders a form for *that* viewer (e.g. `/login` while anonymous), not from the mechanic profile page itself.

## Definition of Done
All acceptance criteria met; DEV-020's average-rating display and this spec's own computation are provably the same query/result, not two independently-maintained numbers — verified structurally (`compute_rating_stats()` delegates to `compute_rating_stats_bulk()`) and by a dedicated test (`test_bulk_rating_stats_matches_single_computation`).
