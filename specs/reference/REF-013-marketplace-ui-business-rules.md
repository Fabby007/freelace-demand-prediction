# REF-013 — Marketplace UI Conventions & Business Rules

**Status:** Approved reference specification (extension)
**Source:** `MARKETPLACE_EXTENSION.md` Sections 2, 5, 7; approved 2026-08-21.

---

## 1. Purpose

Canonical UI/UX conventions and marketplace business rules (search behavior, rating/review rules, disclaimer wording) shared across DEV-019 through DEV-023, so each spec links here instead of re-deciding these rules independently.

## 2. UI/UX conventions

- **Templates:** every page extends `app/templates/base.html`, which provides the shared navigation bar (role-aware: shows "My Profile"/"Opportunity Insights" for a logged-in mechanic, "My Reviews"/"Account" for a logged-in customer, "Admin" only for an admin, "Login"/"Register" for anonymous visitors), a footer, and a single shared `<link>` to `static/css/style.css`.
- **Responsive layout:** CSS uses relative units and a simple flexbox/grid layout with a mobile breakpoint; mechanic-card search results reflow from a multi-column grid (desktop) to a single column (mobile). No separate mobile app or mobile-specific template set (consistent with REF-004's original "no mobile application required" scope line, now extended to this second interface).
- **Visual tone:** simple, professional, minimal — no large marketing/hero sections, no unrelated animation. This is a directory tool, not a consumer brand site.
- **Mechanic result cards** (search/listing page) show: name, profile photo (or a default placeholder avatar if none uploaded), district, years of experience, vehicle types handled (as small badges/tags), 1–3 headline services, average rating (stars + numeric, e.g. "4.3 (12 reviews)" — until DEV-021 exists, a static "No ratings yet" per DEV-020's rating-sort dependency-sequencing note), and a "View Profile" link/button. The full contact number is deliberately **not** shown on the card — only on the profile page — so browsing the list doesn't itself function as a bulk phone-number scrape (a light, sensible friction point, not a hard security control).
- **Mechanic profile page** shows every field in REF-011 Section 3.2 plus the vehicle types/services (Sections 3.4–3.5), the full contact number, and the review list with the computed average rating.
- **Empty states:** a search with zero matching mechanics shows a clear "No mechanics found for these filters" message, never a blank page or a misleading "loading" spinner left hanging — consistent in spirit with the ML dashboard's existing "missing-period data" rule (DEV-013).

## 3. Search and filter rules (DEV-020)

- Filters: district (single-select from REF-002's 25 canonical names), vehicle type (single-select from the 3 canonical values), service type (single-select from the `Service` lookup list). All three are optional and combinable (AND semantics — a mechanic must match every filter that is set, per REF-011 Section 6's query shape). This is the complete, final filter set.
- **Free-text mechanic-name search was removed (2026-08-21, UI/UX refinement, approved).** DEV-020's original build included an optional name field; on review, a customer — often searching during a vehicle breakdown — cannot be expected to know a specific mechanic's name in advance, so the field added no genuine search value over district/vehicle-type/service and was removed from the form, the filter logic, and the results-page query string entirely. This does not affect how a mechanic's name is *displayed*: it still appears on every result card and every profile page exactly as before, per Section 2 above.
- Results are sorted by average rating (descending), with mechanics that have zero reviews shown after rated ones, not hidden — a new mechanic with no reviews yet must still be discoverable.
- Blocked/deactivated accounts never appear in search results or are reachable via a direct profile URL (return a 404/"not found" state, not the profile, per REF-012's authorization posture).
- No live-distance/GPS-based search or sorting — district-level filtering is the entire geographic mechanism for this version, per the explicit exclusion in the extension request.

## 4. Ratings & reviews rules (DEV-021)

- **Rating range:** integer 1–5 (inclusive), required on every review.
- **Review text:** required, minimum length enforced at the form layer (proposed: 10 characters, to discourage empty/low-effort spam without being an onerous bar) — an implementation decision, logged as an ADR if changed materially from this proposal.
- **One review per customer per mechanic:** a customer who reviews a mechanic a second time **edits** their existing review (REF-011 Section 3.6's uniqueness constraint) rather than creating a duplicate. The UI reflects this directly — a customer visiting a mechanic's profile they've already reviewed sees an "Edit your review" form pre-filled with their existing rating/text, not a fresh blank "Submit a review" form.
- **Review ownership:** a customer may edit or delete their own review at any time (FR-M06). No other customer may edit it.
- **Average rating:** computed live as `AVG(rating)` over all `status='visible'` reviews for a mechanic (REF-011 Section 2); reviews an admin has removed (`status='removed_by_admin'`) are excluded from both the average and the visible list, but retained in the database for audit/moderation history rather than hard-deleted (admin removal is a soft delete; a customer's own deletion of their own review is a hard delete — the customer is exercising their own data-ownership right, not being moderated).
- **No booking-verification requirement.** Because there is no booking system, a review is never gated on "did this customer actually book/complete a job" — there is no such record to check. This must be stated plainly, adjacent to the review list on every mechanic profile page:

  > "Ratings and reviews are submitted directly by platform users and are not verified against any completed-job or booking record."

  This sentence (or a materially equivalent one) is the marketplace's own disclaimer, distinct from and in addition to the ML system's Appendix C.3 disclaimer (Section 5 below) — the two serve different purposes and must not be merged into one sentence.
- **Admin moderation:** an admin may remove a review (e.g. abusive language, clearly fake, spam) via DEV-022's admin panel; removal is logged with a timestamp (via `updated_at`) and is reversible (restore action), not a hard delete, so moderation actions themselves remain auditable.

## 5. ML/marketplace boundary and disclaimer placement

- The **Appendix C.3 disclaimer** (CLAUDE.md Section 15, verbatim: *"Predictions are based on available historical and proxy data. They indicate relative service opportunity and do not guarantee customer numbers, employment or income."*) appears **only** on the Opportunity Insights page (DEV-023) — the one marketplace surface that shows ML predictions/rankings — exactly as it appears on every recommendation-bearing panel of the existing Streamlit dashboard. It must not be watered down, paraphrased, or omitted on that page (CLAUDE.md Section 20's non-negotiable rule extends here).
- The **marketplace review disclaimer** (Section 4 above) appears wherever ratings/reviews are displayed (mechanic profile page, mechanic's own "my reviews" view). It is a **different** disclaimer for a **different** kind of uncertainty (unverified user opinion, vs. model-based forecast uncertainty) and the two must never be combined into a single blended sentence that would blur what each is actually disclaiming.
- Mechanic search, filtering, and ranking-by-rating on the marketplace is **ordinary database sorting** (Section 3 above) and must never be described in any UI copy, code comment, or documentation as a "prediction," "opportunity score," or "ranking" in the ML sense — those terms are reserved for DEV-012's actual model output, to avoid a customer or mechanic confusing "top-rated mechanic in Kandy" (a review-average sort) with "Kandy is a high-opportunity district" (an XGBoost/SHAP-backed forecast). See MARKETPLACE_EXTENSION.md Section 7 for the full boundary rule.

## 6. Related specs

- DEV-019 (Mechanic Profiles & User Roles) — implements Section 2's profile page.
- DEV-020 (Mechanic Search & Discovery) — implements Section 3.
- DEV-021 (Ratings & Reviews) — implements Section 4.
- DEV-023 (ML Opportunity Insights Web Integration) — implements Section 5's disclaimer placement.
- CLAUDE.md Section 15 — the Appendix C.3 disclaimer this file references, unchanged.
