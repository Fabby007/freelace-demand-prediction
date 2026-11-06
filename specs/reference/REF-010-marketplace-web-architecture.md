# REF-010 — Marketplace Web Architecture & Technology Stack Addendum

**Status:** Approved reference specification (extension)
**Source:** `MARKETPLACE_EXTENSION.md`; approved by the user 2026-08-21 as a new, additive subsystem.
**Scope:** Applies only to the new `app/` marketplace subsystem. Does not amend REF-008 (the ML system's canonical stack), which remains unchanged and governs `src/`, `dashboard/`, `configs/`, and the modelling pipeline exactly as before.

---

## 1. Purpose

Canonical technology stack, folder structure, and request-flow reference for the Mechanic Discovery Web Platform. DEV-018 through DEV-024 must link here rather than re-deciding these choices per spec.

## 2. Technology stack (addendum, logged as REF-009 ADR-027)

| Layer | Technology | Purpose | Why (vs. alternatives) |
|---|---|---|---|
| Backend framework | Flask (3.x) | Route handling, request/response, app factory | Smallest, most standard Python web framework; matches the user's explicit preference and REF-004's anti-over-engineering constraint. Django was considered and rejected as too large/opinionated for a directory-style CRUD app with no admin-panel-generation need beyond what DEV-022 builds directly. |
| Templating | Jinja2 (bundled with Flask) | Server-rendered HTML pages | No SPA framework; server-rendered pages are simplest to reason about, test, and demo in a viva. |
| ORM / database access | Flask-SQLAlchemy | Model definitions, queries, migrations-ready | Avoids hand-written SQL string interpolation (SQL-injection risk); standard, well-documented, minimal for this scale. |
| Database | SQLite | Persistent storage for users, profiles, services, reviews | REF-008 already lists SQLite as an optional app-layer store; matches "prefer SQLite for this academic project" instruction; zero server process to run/maintain. |
| Auth/session | Flask-Login | Login session management, `current_user`, `login_required` | Standard, small, avoids hand-rolling session/cookie security. |
| Password hashing | `werkzeug.security` (bundled with Flask) | `generate_password_hash` / `check_password_hash` | Already a Flask dependency — no new package needed for the single most security-critical operation in the app. |
| Forms / CSRF | Flask-WTF | Server-side form validation, CSRF tokens on every POST | CSRF protection is a stated security requirement (Section 8 of the extension request); Flask-WTF is the standard way to get it without hand-rolling token generation/verification. |
| Static assets | Plain CSS (`app/static/css/style.css`), no CSS framework required | Layout/styling | Keeps the dependency footprint at zero for the frontend; a minimal, self-written responsive stylesheet is sufficient for an academic project (see REF-013 Section 2 for UI conventions). |
| JavaScript | Vanilla JS, used sparingly (e.g. star-rating widget, image preview on upload) | Minor UX affordances only | No React/Angular/Vue per the explicit instruction; JS never carries business logic — all validation and authorization is re-checked server-side regardless of what client-side JS does. |

New `requirements.txt` additions (appended, not replacing any existing pin): `Flask`, `Flask-SQLAlchemy`, `Flask-Login`, `Flask-WTF`. Exact versions to be pinned at DEV-018 implementation time following the project's existing pinning convention (REF-004 Portability NFR); pin choice and any conflict resolution (analogous to REF-009 ADR-002/ADR-004 for the ML stack) is logged as its own ADR if a conflict arises.

## 3. Folder structure (proposed, not yet created on disk)

```
mechanic-demand-project/
├── app/                          # NEW — marketplace web application (separate from src/ and dashboard/)
│   ├── __init__.py                # Flask app factory, extension init (db, login_manager, csrf)
│   ├── config.py                  # Config classes (Development/Testing/Production), reads SECRET_KEY etc. from env
│   ├── extensions.py              # Shared SQLAlchemy/LoginManager/CSRFProtect instances
│   ├── cli.py                     # `flask create-admin` — the sole admin-provisioning path (added in DEV-018,
│   │                               #   not originally itemized below — REF-012 Section 2)
│   ├── utils/                     # decorators.py (role_required), security.py (open-redirect guard) — DEV-018;
│   │                               #   canonical.py (district list), uploads.py (photo upload) — DEV-019;
│   │                               #   none of these four were originally itemized below
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                # User (role discriminator: customer/mechanic/admin)
│   │   ├── mechanic.py             # MechanicProfile, MechanicService, MechanicVehicleType
│   │   ├── service.py              # Service (lookup table)
│   │   └── review.py               # Review
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py                 # registration, login, logout (customer + mechanic)
│   │   ├── customer.py             # customer account view/edit, own-review listing (DEV-021)
│   │   ├── mechanic.py             # mechanic profile create/edit, own dashboard (+ own ratings, DEV-021)
│   │   ├── marketplace.py          # public search/filter/listing/profile view (no auth required to browse)
│   │   ├── reviews.py              # review submit/delete (DEV-021) — not originally itemized below;
│   │   │                           #   kept separate from marketplace.py, which stays read-only
│   │   ├── admin.py                # admin auth + management routes
│   │   └── insights.py             # Opportunity Insights (DEV-023), mechanic-only, read-only into src/
│   ├── forms/                      # Flask-WTF form classes (registration, login, profile edit, review,
│   │                               #   search filters DEV-020, insights filters DEV-023 — CSRF-disabled
│   │                               #   read-only GET forms, not itemized individually below)
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── auth/                   # login.html, register_customer.html, register_mechanic.html
│   │   ├── customer/                # customer_profile.html
│   │   ├── mechanic/                # mechanic_dashboard.html, mechanic_edit_profile.html
│   │   ├── marketplace/             # mechanic_list.html, mechanic_profile.html
│   │   ├── admin/                   # admin_dashboard.html, manage_users.html, manage_reviews.html
│   │   └── insights/                 # opportunity_insights.html
│   └── static/
│       ├── css/style.css
│       ├── images/                  # default avatar, uploaded mechanic photos (see REF-012 Section 5)
│       └── js/                      # minor UX scripts only
├── instance/                       # NEW — Flask instance folder, gitignored (holds marketplace.db, never committed)
│   └── marketplace.db
├── wsgi.py                         # NEW — root-level entry point (`flask --app wsgi run`), added in DEV-018
├── tests/
│   └── marketplace/                 # NEW — marketplace test suite, kept alongside the existing ML tests/
│       ├── test_auth.py
│       ├── test_mechanic_profile.py
│       ├── test_search.py
│       ├── test_reviews.py
│       ├── test_admin.py
│       └── test_insights_integration.py
├── configs/
│   └── marketplace_config.yaml      # NEW — non-secret app config (pagination size, rating bounds, upload limits)
│
│   # --- everything below is the existing, unmodified ML system per REF-008 ---
├── specs/
├── data/
├── notebooks/
├── src/
├── dashboard/
├── models/
├── reports/
├── configs/                          # (existing ML configs remain; marketplace_config.yaml added alongside)
├── CLAUDE.md
├── MARKETPLACE_EXTENSION.md
├── TODO.md
├── requirements.txt
└── README.md
```

**Verification note (per the instruction "first verify whether it fits the existing project"):** `app/` sits at the repository root as a sibling of `src/` and `dashboard/`, not nested inside either — this preserves DEV-001's Appendix-B-derived structure exactly and adds no new top-level ML folders. `instance/` is Flask's own documented convention for exactly this purpose (local, non-version-controlled instance data) and must be added to `.gitignore` alongside the existing `.venv`/data-artifact/secrets entries. `tests/marketplace/` keeps `pytest tests/` (DEV-017's single-command test requirement) working for both subsystems without merging their test files together.

## 4. Request/response flow

```
Browser (HTML form / link)
   │  HTTP request
   ▼
Flask route (app/routes/*.py)
   │  - Flask-Login: is the user authenticated? which role?
   │  - Flask-WTF: validate form + CSRF token
   ▼
app/models/* (SQLAlchemy) ──► instance/marketplace.db (SQLite)
   │
   ▼
Jinja2 template (app/templates/*.html) ──► rendered HTML response
```

The Opportunity Insights route (`app/routes/insights.py`) is the one exception that also reaches into the ML system, strictly read-only:

```
app/routes/insights.py
   │  vehicle_type, period selected by the logged-in mechanic
   ▼
src/recommendation/ranking_engine.py :: RankingEngine.rank(...)   (DEV-012, unchanged)
   │  (which internally calls src/models, src/explainability per DEV-008/DEV-010)
   ▼
app/templates/insights/opportunity_insights.html
   │  renders ranking + SHAP reasons + Appendix C.3 disclaimer, verbatim
```

No route under `app/routes/` other than `insights.py` imports from `src/`. No module under `src/` imports from `app/`.

## 4.1 DEV-018 implementation note

`email-validator` was added as a required runtime dependency of WTForms' `Email()` validator (not anticipated when this file was first written), and `Flask`, `SQLAlchemy`, `Werkzeug`, `PyYAML`, `click` — already present transitively via `mlflow` — were promoted to explicit `requirements.txt` pins since `app/` now imports each directly. See REF-009 ADR-029.

## 5. Related specs

- DEV-018 (Web Application Foundation, Database & Authentication) — creates this structure.
- DEV-023 (ML Opportunity Insights Web Integration) — implements the one cross-subsystem integration point.
- REF-008 (Technology Stack Reference) — the unchanged ML-system stack this addendum sits alongside.
- REF-009 ADR-026, ADR-027 — Streamlit-dashboard-retained and stack-addendum decisions.
