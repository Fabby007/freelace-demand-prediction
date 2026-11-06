# MARKETPLACE EXTENSION — Mechanic Discovery Web Platform

**Status:** COMPLETE (2026-08-21) — DEV-018 through DEV-024 all implemented and verified. This extension, not part of the original Final Project Documentation, is now fully built. See TODO.md's "Marketplace extension (DEV-018–024) — COMPLETE" entry and DEV-024.md for the final verification record.
**Date approved:** 2026-08-21
**Relationship to the core project:** This is an **additive extension** to the Mechanic Service Demand Opportunity Prediction and Recommendation System. It does not replace, weaken, or reinterpret any requirement in `MASTER_PROMPT.md`, `CLAUDE.md`, or `specs/development/DEV-001` through `DEV-017`. Those specs remain the source of truth for the ML research system exactly as they were before this extension. See Section 8 below for exactly how the two subsystems relate.

---

## 1. Purpose

Build a simple web platform where customers can register, log in, search for freelance mechanics or garages operating in Sri Lanka, view mechanic profiles, and contact a mechanic directly using their displayed mobile/contact number. Mechanics maintain their own profile; customers leave ratings and reviews. This is a **discovery/directory marketplace**, not a booking, dispatch, or transaction platform.

This purpose is distinct from, and additional to, the original project's core user question ("which districts show the strongest predicted service opportunity"). The marketplace answers a different question for a different moment in the user journey: *"which specific mechanic can a customer contact right now, and which district looks like a good opportunity for a mechanic to focus on."* Both questions are served by the same academic project, through two deliberately separated subsystems.

## 2. Scope

### 2.1 In scope
- Customer registration, login, logout.
- Customer search/browse/filter of mechanic listings (district, vehicle type, service type).
- Mechanic profile pages showing contact number, district, vehicle types handled, services offered, years of experience, description, and ratings/reviews.
- Mechanic registration, login, logout, profile create/edit, optional profile photo.
- Customer-submitted ratings and reviews (1–5 stars + text) per mechanic.
- Admin authentication and moderation: manage customer accounts, manage mechanic accounts/profiles, manage/remove reviews, block/deactivate accounts.
- A mechanic-facing "Opportunity Insights" page that reuses the existing ML backend (XGBoost prediction, SHAP explanation, district ranking) read-only, unchanged.

### 2.2 Explicitly out of scope
The following are **not** implemented under this extension, regardless of how naturally they might seem to follow from "mechanic marketplace" conventions elsewhere:
- Booking, appointment scheduling, or a request/accept/reject workflow.
- Mechanic availability status or online/offline presence.
- Live GPS tracking or distance-based/proximity search.
- Payment processing of any kind.
- In-app chat or messaging between customer and mechanic.
- Job-status tracking (e.g. "in progress," "completed").
- Dispatch/matching logic (PickMe-style automatic assignment).

A customer's entire interaction model is: **search → view profile → read contact number → contact the mechanic outside the system** (phone call, SMS, in person). Nothing in this extension automates or mediates what happens after the customer sees the number.

## 3. User roles

Three roles, all within one `users` table with a `role` discriminator (see REF-011). No multi-tenant organizations, no sub-roles, no permission-group system — this directly supersedes CLAUDE.md Section 4's "no customer-facing role" statement for the marketplace subsystem specifically (see Section 8.3 below for how this is reconciled, not silently overridden).

| Role | Can do |
|---|---|
| Customer | Register, log in/out, edit own account info, search/filter mechanics, view mechanic profiles and contact numbers, submit/edit/delete own ratings and reviews. |
| Mechanic | Register, log in/out, create/edit own profile (photo, contact number, district, vehicle types, services, experience, description), view own ratings/reviews, view Opportunity Insights. |
| Admin | Log in, view/manage/block customer accounts, view/manage/block mechanic accounts and profiles, remove/restore reviews, cannot be self-registered (see DEV-018/DEV-022 for provisioning). |

## 4. Functional requirements

### 4.1 Customer
- FR-M01 Register an account (name, email, password).
- FR-M02 Log in / log out.
- FR-M03 View/edit own basic account information.
- FR-M04 Search mechanics by district, vehicle type, service type (any combination).
- FR-M05 View a mechanic's full profile, including contact number.
- FR-M06 Submit a rating (1–5) and review text for a mechanic; edit or delete own review.
- FR-M07 View existing ratings/reviews and the computed average rating for a mechanic.

### 4.2 Mechanic
- FR-M08 Register an account and create a profile (name, contact number, district, vehicle types handled, services offered, years of experience, description, optional profile photo).
- FR-M09 Log in / log out.
- FR-M10 Edit own profile; cannot edit another mechanic's profile.
- FR-M11 View own ratings/reviews.
- FR-M12 View the Opportunity Insights page (district ranking, SHAP explanation, disclaimer) for a selected vehicle category/period.

### 4.3 Admin
- FR-M13 Log in via a separate, non-self-service admin authentication path.
- FR-M14 View, block/unblock, and delete customer accounts.
- FR-M15 View, block/unblock, and delete mechanic accounts and their profiles.
- FR-M16 Remove (hide) a review; restore a previously removed review.

## 5. Non-functional requirements

- **Separation:** marketplace code, data, and dependencies must not modify or depend on `src/`, `dashboard/`, `data/raw|interim|processed`, `models/`, or `mlruns/` in a way that couples their release cycles. The marketplace may *read* `src/` (for Opportunity Insights only) but never write into the ML system's data or model artifacts, and the ML pipeline never reads marketplace data.
- **Simplicity:** server-rendered HTML (Flask/Jinja2), minimal JavaScript, SQLite storage — no SPA framework, no microservices, consistent with REF-004 Section 5's anti-over-engineering constraint, which applies to this extension as much as the original system.
- **Security:** hashed passwords, session-based auth, CSRF protection on all state-changing forms, server-side role checks on every route, server-side ownership checks on every edit/delete action (see REF-012).
- **Usability:** clean, responsive HTML/CSS layout usable on desktop and mobile browsers without a dedicated mobile app (consistent with REF-004 Section 3's original "no mobile application required" scope line).
- **Honesty:** ratings/reviews are presented as user-submitted opinions, not verified completed-job records (see REF-013 Section 4). Opportunity Insights carries the exact Appendix C.3 disclaimer, unchanged, per CLAUDE.md Section 15's non-negotiable rule.
- **Data integrity:** no fabricated customer/mechanic/review records presented as real collected data. Development/demo seed accounts are permitted only if clearly labelled as development/demo data (see REF-005's no-fabrication rule, which extends here).

## 6. Explicit exclusions (restated for traceability)

See Section 2.2. These items appear in `specs/reference/REF-004-nfr-and-scope-boundaries.md` Section 4 as *original-system* future extensions and must not be conflated with this marketplace's own out-of-scope list — the two lists exist for different reasons (REF-004's list is "not yet built for the ML system"; this extension's list is "will not be built for the marketplace, on principle, per the approved feature request").

## 7. Relationship to the existing ML system

### 7.1 Two workflows, kept apart

```
Customer workflow (marketplace, database-backed):
  Customer -> search/filter (SQL query over MechanicProfile/Service/Review) -> mechanic profile -> contact mechanic directly (outside the system)

Mechanic workflow (ML decision-support, unchanged from the original system):
  Mechanic -> "Opportunity Insights" page -> existing RankingEngine.rank() (DEV-012)
           -> XGBoost prediction (DEV-008) + SHAP explanation (DEV-010) + opportunity bands
           -> Appendix C.3 disclaimer
```

### 7.2 Boundary rules (non-negotiable, extending CLAUDE.md's Hard Rules to this extension)

- A customer search, filter selection, or profile view is **never** written into `data/raw`, `data/interim`, `data/processed`, or used as a feature, label, or training signal for any model in `src/models/`. This holds even though a customer's district filter and a model's district ranking output are conceptually related — they must not be merged into one dataset or one pipeline without a future, explicitly approved specification that changes the research methodology (per the original instruction).
- A mechanic's `district` field on their marketplace profile is a **self-reported business location for discovery purposes**, not a validated data point in the vehicle-registration research dataset. It must never be described in the UI or code as "training data" or "observed demand."
- The Opportunity Insights page calls into `src/recommendation/ranking_engine.py`, `src/explainability/shap_explainer.py`, and (optionally) `src/nlp/sbert_router.py` exactly as `dashboard/app.py` does — read-only, no new prediction logic is written inside `app/`. If the ranking/SHAP interface needs to change to support both consumers, that change happens in `src/`, governed by the existing DEV-008/DEV-010/DEV-012 specs, not by ad hoc logic duplicated inside the Flask app.
- The Streamlit dashboard (`dashboard/`) is **not removed, replaced, or degraded** by this extension. See Section 7.3.

### 7.3 Status of the Streamlit dashboard

The existing Streamlit + Plotly dashboard (DEV-013) remains the primary ML analysis/demonstration surface for the research system and stays fully functional and unmodified by this extension. It is not the new marketplace's frontend (the marketplace uses Flask/Jinja2/HTML/CSS per Section 6 of this extension and REF-010) and it is not replaced by the marketplace's Opportunity Insights page.

**Decision for this planning stage (logged as REF-009 ADR-026):** the Streamlit dashboard remains a **separate, independent ML dashboard**. The Flask marketplace's Opportunity Insights page (DEV-023) is a *second, additional* presentation of a subset of the same underlying `src/` logic (ranking + SHAP for a selected vehicle category/period), built directly against the Python functions in `src/recommendation/` and `src/explainability/`, not by embedding or iframing the Streamlit app. Whether a future specification collapses these into one presentation layer is explicitly left open and is not decided here — see Section 10 of this document and DEV-023's Open Questions.

## 8. Reconciling this extension with existing documentation

Per CLAUDE.md Section 21 (Source-of-Truth Hierarchy), a conflict between levels must be flagged, not silently resolved, and the original documented requirement preserved unless the user explicitly confirms a deviation. The following conflicts were identified while writing this plan; the user's own extension request (this session, 2026-08-21) constitutes that explicit confirmation for each one, and each is additionally logged as an ADR in REF-009.

### 8.1 CLAUDE.md Section 4 — "no customer-facing role... do not invent one"
**Conflict:** CLAUDE.md explicitly instructs against inventing a customer-facing role or multi-tenant account system for *the mechanic demand prediction system*. This extension adds exactly that, but as a **separate marketplace subsystem**, not as a feature of the ML decision-support system itself.
**Resolution:** CLAUDE.md's rule is preserved as written for the ML system (Sections 1–24 of CLAUDE.md still describe that system alone, unchanged). A new CLAUDE.md section (Section 25, see the CLAUDE.md diff for this extension) states plainly that the marketplace is a separate, explicitly-approved subsystem with its own roles, and that the original rule continues to apply to the ML dashboard/recommendation system.

### 8.2 REF-004 Section 3 — "Interface: Web dashboard for analysis and recommendation... No mobile application is required for the first release"
**Conflict:** the original scope table describes exactly one interface (the Streamlit dashboard). This extension adds a second, independent web interface (the Flask marketplace).
**Resolution:** REF-004's scope table describes the original system's scope and is left verbatim (it is a reproduction of the source documentation and must not be edited to look like it always included a marketplace). This extension's existence and boundary are instead recorded here and in REF-010, with an ADR cross-reference in REF-009.

### 8.3 Technology stack (REF-008)
**Conflict:** REF-008 pins Streamlit as "no other frontend framework" and does not mention Flask, SQLite-as-primary-store, or Jinja2/HTML/CSS as an application layer.
**Resolution:** REF-008 is left unchanged as the ML system's canonical stack. A new reference spec, REF-010, defines the marketplace's own stack (Flask, Jinja2, HTML/CSS, SQLite via SQLAlchemy) as an **addendum scoped to `app/` only**, logged as REF-009 ADR-027. CLAUDE.md Section 5's "do not change this stack" rule is respected — the ML stack is not changed; a second, separate stack is added for a second, separate subsystem.

### 8.4 No other contradictions found
The marketplace's data model (Section 3 of REF-011), roles (Section 3 above), and ML boundary rules (Section 7.2 above) do not conflict with any other REF or DEV spec. No existing DEV-001–017 spec, test, or dataset is modified by this extension.

## 9. Files created or updated by this planning pass

**Created:**
- `MARKETPLACE_EXTENSION.md` (this file)
- `specs/reference/REF-010-marketplace-web-architecture.md`
- `specs/reference/REF-011-marketplace-database-schema.md`
- `specs/reference/REF-012-marketplace-roles-permissions-security.md`
- `specs/reference/REF-013-marketplace-ui-business-rules.md`
- `specs/development/DEV-018-web-foundation-database-auth.md`
- `specs/development/DEV-019-mechanic-profiles-user-roles.md`
- `specs/development/DEV-020-mechanic-search-discovery.md`
- `specs/development/DEV-021-ratings-reviews.md`
- `specs/development/DEV-022-admin-dashboard-management.md`
- `specs/development/DEV-023-ml-opportunity-insights-integration.md`
- `specs/development/DEV-024-web-testing-security-integration.md`

**Updated:**
- `TODO.md` — new Phases 16–22 appended (marketplace), existing Phases 0–15 untouched.
- `specs/development/DEV-PLAN.md` — new Stages 17–23 appended, existing Stages 1–16 untouched.
- `specs/reference/REF-009-architecture-decisions.md` — ADR-026, ADR-027, ADR-028 appended.
- `specs/COVERAGE.md` — new Part 2 (marketplace requirement traceability) appended.
- `CLAUDE.md` — new Section 25 appended (extension pointer + role/stack reconciliation).

No existing file content in `specs/development/DEV-001` through `DEV-017`, `specs/reference/REF-001` through `REF-008`, `src/`, `dashboard/`, or `tests/` is modified.

## 10. Open questions — resolved during implementation (2026-08-21)

1. **Resolved (DEV-023):** Opportunity Insights was built as an independently-rendered Flask view calling `RankingEngine.rank()` directly, not sharing Streamlit rendering code — see REF-009 ADR-034. The Streamlit dashboard remains untouched and independent (REF-009 ADR-026, confirmed still accurate).
2. **Resolved (DEV-019):** `Service` uses a small fixed starter list, auto-seeded idempotently at app startup, extendable only by an admin thereafter (no such admin CRUD UI was built, since it was never required beyond the starter list — DEV-022's mechanic/review management didn't need it).
3. **Resolved (DEV-024):** image-content validation beyond the existing extension + magic-byte-sniff check was formally evaluated and explicitly deferred, with documented reasoning (see DEV-024.md's FR7 section) — not implemented, not left silently open.

## 11. Stop condition — superseded

The original stop condition ("no application code implemented as part of this pass") applied only to the initial planning pass. Implementation has since proceeded through DEV-018–024 across subsequent, explicitly-instructed sessions, and is now complete — see Section 1's Status line and TODO.md's "Marketplace extension (DEV-018–024) — COMPLETE" entry.
