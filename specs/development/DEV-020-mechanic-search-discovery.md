# DEV-020 — Mechanic Search & Discovery

## Specification ID
DEV-020

## Feature/Module Name
Mechanic Search & Discovery

## Purpose
Let anyone (customer, logged in or not) search and filter the mechanic directory by district, vehicle type, and service type, then view a full mechanic profile including contact number.

## Background/Context
MARKETPLACE_EXTENSION.md Section 4.1; REF-011 Section 6 (search query shape); REF-013 Sections 2–3 (card layout, filter/sort rules).

## Related Requirements
FR-M04, FR-M05, FR-M07 (average rating shown on results).

## User Roles
Public/Customer (primary consumer). Mechanics and admins can also browse (Section 3 of REF-012 — search is not role-restricted).

## Preconditions
DEV-019 complete (mechanic profiles exist to search over).

## User Stories/Use Cases
- As a customer, I want to filter mechanics by my district and the vehicle type I need serviced, so I only see relevant results.
- As a customer, I want to further narrow by service type (e.g. "Electrical Work").
- As a customer, I want to see each mechanic's rating before opening their profile.
- As a customer, I want to open a mechanic's profile and get their phone number so I can call them directly.

## Functional Requirements
- FR1 Build `mechanic_list.html`: filter form (district dropdown, vehicle-type dropdown, service-type dropdown — REF-013 Section 3) plus a results grid of mechanic cards. **Superseded (2026-08-21, UI/UX refinement, approved):** the optional free-text mechanic-name search originally included here was removed — a customer searching for a mechanic (often during a breakdown) is not expected to know a specific mechanic's name in advance, so name search added no real value over district/vehicle-type/service filtering. The mechanic's name is unaffected and continues to display normally on every result card and profile page — only the ability to *search by* name was removed. See REF-013 Section 3 for the corrected filter list.
- FR2 Implement the search query in `app/routes/marketplace.py` using SQLAlchemy ORM query composition (never raw SQL string interpolation), following REF-011 Section 6's query shape; excludes `status='blocked'` users.
- FR3 Compute and display each result's average rating and review count live (per REF-011 Section 2 / REF-013 Section 4) via a single aggregate query per page load (not N+1 per-card queries).
- FR4 Sort results by average rating descending, with zero-review mechanics included and shown after rated ones (REF-013 Section 3).
- FR5 Build `mechanic_profile.html`: full profile view (all REF-011 Section 3.2–3.5 fields), contact number, review list with average rating (list itself rendered by data DEV-021 owns; this spec's page includes the section, DEV-021 fills its content), and the review-disclaimer sentence (REF-013 Section 4).
- FR6 Pagination for result lists beyond a configurable page size (`configs/marketplace_config.yaml`, e.g. 12 per page) — a reasonable default given the expected academic-scale dataset, not a hard requirement to over-engineer around.
- FR7 Empty-state message when no mechanic matches the selected filters (REF-013 Section 2).

## Business Rules
- Filters are combinable with AND semantics; an unset filter means "no constraint on that dimension," not "empty results."
- Contact number is shown only on the profile page, never on the list/card view (REF-013 Section 2 — a deliberate friction point against bulk scraping).
- A blocked mechanic's profile URL returns a not-found state, not the profile (REF-012).

## Data Requirements
Reads: `MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType`, `Review` (for the aggregate rating), `User` (for name/status). No writes in this spec.

## Database/Schema Changes
None (read-only spec against DEV-019/DEV-021's tables).

## API Requirements
None.

## Backend Behavior
`app/routes/marketplace.py`: `GET /search` (list + filters), `GET /mechanic/<id>` (profile). Both public (no `login_required`).

## Frontend Behavior
Filter form submits via GET (so results are bookmarkable/shareable by URL query string, a small but genuinely useful UX property for a directory site); no JS required for core filtering. (The name-search debounce note that previously appeared here no longer applies — see FR1's superseded note.)

## UI States
- **Default (no filters):** all active mechanics, sorted by rating.
- **Filtered, results found:** matching cards.
- **Filtered, zero results:** empty-state message with a "clear filters" link.
- **Profile not found / blocked:** a generic "mechanic not found" page (never reveals whether the ID belongs to a blocked account specifically, to avoid leaking moderation state).

## Validation
Filter values are validated against their respective canonical lists (REF-002 districts, REF-011's 3 vehicle types, existing `Service` rows) server-side — an unrecognized filter value is ignored (treated as unset) rather than causing a 500 error.

## Permissions
Public read access; no authentication required for search/profile view (REF-012 Section 3).

## Error Cases
- Malformed/unexpected query-string values — ignored gracefully (see Validation), not a server error.
- Requesting a nonexistent mechanic ID — clean 404-style page, not a stack trace.

## Edge Cases
- A district or service filter with zero mechanics at all (not just zero for this combination) — same empty-state handling, no special case needed.
- A mechanic with a very high review count — pagination/aggregate query must remain performant at the expected academic-project scale (no specific load target beyond "responsive on a normal laptop," mirroring REF-004's Performance NFR for the ML dashboard).

## Security Considerations
No SQL injection surface (ORM only); no sensitive data exposed on the card view (Business Rules above); rate limiting not required at this scale (documented, not silently omitted — mirrors REF-012 Section 6).

## Dependencies
DEV-018 (Foundation), DEV-019 (Mechanic Profiles). Read-dependency (not blocking) on DEV-021 for the review list's content on the profile page — this spec's page structure accommodates it whether or not DEV-021 has landed yet, showing "No reviews yet" until it has.

## Testing Requirements
`tests/marketplace/test_search.py` (24 tests, all passing): filter by each dimension individually and combined; invalid/malformed filter values ignored gracefully; sort order (stable, see the rating-sort note below); pagination splits results across pages; blocked mechanics and profile-less mechanic accounts excluded from results and profile view; empty-state and clear-filters rendering; profile page shows every required field including the contact number and the review-disclaimer sentence, list/card page shows no contact number; a `tel:` link with digits-only href; default-avatar vs. uploaded-photo rendering; nonexistent and blocked mechanic IDs both return an identical 404; DEV-019's ownership rules (customer blocked from the edit route, one mechanic's edit never affecting another's public profile) re-verified unaffected; two boundary tests confirming the search route imports nothing from `src/` and makes zero writes to `data/`, `models/`, or `mlruns/`.

## Rating-sort dependency-sequencing note — RESOLVED by DEV-021 (2026-08-21)
FR3/FR4 describe the intended final behavior once real ratings exist. At the time DEV-020 was implemented, the `Review` table did not exist yet (its creation is DEV-021 FR1's job, not this spec's), so there was no aggregate to compute or sort by: every mechanic had an identical, absent rating, `_search_mechanics()` fell back to a name-only sort, and every card/profile showed a static "No ratings yet." DEV-021 has since implemented `Review` and updated `_search_mechanics()`'s `ORDER BY` to a real `AVG(rating)` correlated subquery (descending, `NULLS LAST`, name as tie-break) and every rating display to the real computed value — see DEV-021.md's Additional Implementation Notes. This section is left in place, marked resolved, as the historical record of the sequencing decision rather than silently rewritten.

## Acceptance Criteria
- [x] Search page returns correct, filtered results for every supported filter combination (district, vehicle type, service, name, and all combined) — verified by test, including that an unset filter never narrows results and an invalid value is silently ignored rather than erroring.
- [x] Average rating/review count displayed correctly and efficiently (no N+1 query pattern) — see the rating-sort note above for what "correctly" means at this stage; efficiency verified structurally: `_base_active_mechanics_query()` eager-loads `user`/`vehicle_type_rows`/`services` via `contains_eager`/`selectinload`, a small constant number of queries regardless of result-set size, not one query per mechanic per collection.
- [x] Contact number visible only on the profile page — verified by test that it is present on `/mechanic/<id>` and absent from `/search`'s card markup for the same mechanic.
- [x] Empty-state and not-found states render clear messages — "No mechanics found for these filters" (with a Clear filters link) and a generic 404 (identical for a nonexistent ID and a blocked mechanic's ID, leaking no moderation state) both verified by test.
- [x] All tests in `tests/marketplace/test_search.py` pass (24/24); full marketplace suite 78/78; ML test suite unaffected (see the verification log below).

## Additional implementation notes (added post-implementation)
- **`.any()` EXISTS-subquery filtering, not a literal `LEFT JOIN ... GROUP BY`.** REF-011 Section 6's SQL is illustrative of the filtering *semantics*, not a literal implementation mandate (its own text: "Expressed via SQLAlchemy ORM queries... not raw SQL"). `MechanicProfile.vehicle_type_rows.any(...)` / `.services.any(...)` reproduce the same AND-combinable filter semantics without needing `GROUP BY`/`DISTINCT` to deduplicate rows the way a literal multi-table `LEFT JOIN` would.
- **Service filter uses `service_id`, not `service_name`.** REF-011 Section 6's example binds `:service_name`; this implementation instead sends the `Service.id` as the query-string value (`?service=3`), validated against a live `Service.id` lookup. IDs avoid any ambiguity/matching cost from string comparison and match how the filter dropdown's `<option value=...>` naturally works. Functionally equivalent filtering behavior; a small, documented implementation choice, not a deviation from any documented requirement.
- **Public profile route lives on `marketplace_bp` at `/mechanic/<int:mechanic_id>`**, exactly as DEV-020's own Backend Behavior specifies — verified not to collide with `mechanic_bp`'s `/mechanic/profile` and `/mechanic/profile/edit` (Werkzeug's `<int:...>` converter only matches all-digit segments, so `"profile"` never matches `<int:mechanic_id>`).
- **"Years of experience" added to the search-result card**, beyond REF-013 Section 2's literal card field list (name, photo, district, vehicle types, services, rating, View Profile button) — requested explicitly for this implementation pass and low-risk/useful; noted here rather than silently added.

## Definition of Done
All acceptance criteria met; a customer can go from the home page to a specific mechanic's contact number in three clicks or fewer (home → search/filter → profile) — verified via a real `flask run` dev-server smoke test (`GET /search`, `GET /search?district=Kandy`, `GET /mechanic/<id>` all returning the expected status codes), not only the automated test client.
