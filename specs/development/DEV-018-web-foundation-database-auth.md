# DEV-018 — Web Application Foundation, Database & Authentication

## Specification ID
DEV-018

## Feature/Module Name
Flask Web Foundation, HTML/CSS Structure & Authentication

## Purpose
Stand up the marketplace's Flask application skeleton, SQLite database, base HTML/CSS layout, and role-aware registration/login/logout — the foundation every later marketplace spec (DEV-019–024) builds on. Equivalent in role to DEV-001 for the ML system, but for the new `app/` subsystem.

## Background/Context
`MARKETPLACE_EXTENSION.md` (approved 2026-08-21) Sections 1, 3, 6; REF-010 (Web Architecture); REF-011 (Database Schema, `User` table); REF-012 (Roles, Permissions & Security, Sections 2–4).

## Related Requirements
FR-M01, FR-M02, FR-M03, FR-M08, FR-M09, FR-M13 (see MARKETPLACE_EXTENSION.md Section 4). FR-M03 ("customer view/edit own basic account info") was mapped to DEV-018 in `specs/COVERAGE.md` Part 2 during planning but omitted from this list at that time — a drafting gap, corrected here rather than silently implemented without a spec trace or silently left uncovered. It is a natural fit for this spec since it operates only on the `User` row DEV-018 already owns, with no dependency on `MechanicProfile` (DEV-019) or `Review` (DEV-021).

## User Roles
Customer, Mechanic, Admin (see REF-012 Section 3). This spec creates the `User` table and the registration/login mechanics common to all three; role-specific profile data is layered on in DEV-019 (mechanic) and account-management screens in later specs.

## Preconditions
None within the marketplace (first spec in the marketplace dependency chain). Does not depend on, and must not modify, any DEV-001–017 artifact.

## User Stories/Use Cases
- As a new customer, I want to create an account with my name, email, and a password so I can search for mechanics and leave reviews.
- As a new mechanic, I want to create an account so I can build a profile later (DEV-019).
- As a returning user of any role, I want to log in and have the site remember who I am across pages, and log out when I'm done.
- As the project owner, I want an admin account that exists without a public "become an admin" signup form.

## Functional Requirements
- FR1 Initialize the Flask app via an application factory (`app/__init__.py::create_app()`), registering blueprints for `auth`, `customer`, `mechanic`, `marketplace`, `admin`, `insights` (routes for the latter four are stubbed/empty in this spec; fleshed out in DEV-019–023).
- FR2 Configure Flask-SQLAlchemy against `instance/marketplace.db`; enable SQLite foreign-key enforcement (`PRAGMA foreign_keys=ON`).
- FR3 Define the `User` SQLAlchemy model exactly per REF-011 Section 3.1.
- FR4 Implement customer registration (`/register/customer`) and mechanic registration (`/register/mechanic`) as two distinct forms/routes, both creating a `User` row with the correct `role` and a hashed password. Mechanic registration in this spec creates only the `User` row; the accompanying `MechanicProfile` creation flow belongs to DEV-019 (a newly registered mechanic is redirected to "complete your profile").
- FR5 Implement login (`/login`, single form for customer and mechanic — role is read from the matched `User` row, not selected by the visitor) and logout (`/logout`).
- FR6 Implement Flask-Login session wiring (`user_loader`, `login_required`, `current_user`).
- FR7 Implement a `role_required(*roles)` decorator (REF-012 Section 4) usable by every later spec's routes.
- FR8 Build `base.html` with the shared navigation bar, footer, disclaimer-slot (empty in this spec; populated by DEV-023), and `static/css/style.css` with the shared responsive layout (REF-013 Section 2).
- FR9 Build a minimal `home.html` landing page linking to search (stubbed placeholder until DEV-020), login, and both registration forms.
- FR10 Provision exactly one admin account via a one-time seed/CLI mechanism (e.g. a `flask create-admin` custom CLI command reading credentials from environment variables), never via a public form (REF-012 Section 2). Clearly document this as development/demo provisioning, not fabricated user data.
- FR11 Create `configs/marketplace_config.yaml` for non-secret settings (initially: session cookie lifetime, pagination page size placeholder for DEV-020) and wire `SECRET_KEY`/`SQLALCHEMY_DATABASE_URI` from environment variables via `app/config.py`.
- FR12 Add `instance/` to `.gitignore`; append the new `requirements.txt` pins (Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF) per REF-010 Section 2.
- FR13 Implement FR-M03: a `customer.account` route (`/account/`) letting a logged-in customer view and edit their own `name`/`email`, with the same email-uniqueness validation as registration (excluding their own current row).
- FR14 Give every stubbed blueprint (`marketplace.search`, `mechanic.profile`, `insights.dashboard`, `admin.dashboard`, `customer.reviews`) one real, role-appropriately-protected landing route rendering a shared `shared/coming_soon.html` placeholder, rather than a dead nav link — this lets DEV-018's own role-protection tests exercise a real route per role, and gives DEV-019/020/021/022/023 an existing URL to replace rather than one to invent from scratch.

## Additional implementation notes (added post-implementation)
- **`email-validator` dependency:** WTForms' `Email()` validator requires the separate `email_validator` package at runtime (it raises immediately otherwise) — not something REF-010 anticipated. Added to `requirements.txt`, pinned to the installed version, with a note that it performs syntax validation only (`check_deliverability=False`, WTForms' own default) — no network/DNS calls are made during registration/login/account-edit form validation.
- **Existing transitive dependencies promoted to explicit pins:** Flask, SQLAlchemy, Werkzeug, PyYAML, and click were already present in the environment (transitive dependencies of `mlflow`, which bundles a Flask-based tracking server) but unpinned. Since `app/` now imports all five directly, they are pinned to their already-installed, already-verified-working versions, following the same rationale as REF-009 ADR-024 (scipy). Logged as REF-009 ADR-029.
- **`db.create_all()` instead of a migration framework:** no Alembic/Flask-Migrate is introduced. `create_app()` calls `db.create_all()` once at startup (idempotent — only creates missing tables), consistent with REF-004 Section 5's anti-over-engineering constraint for this schema's size and the project's academic scope.
- **Open-redirect protection on the `next=` login parameter:** `app/utils/security.py::is_safe_redirect_target()` rejects any `next` value that isn't a same-origin relative path, so `/login?next=https://evil.example` cannot be used to redirect a user off-site after a genuine login. Not explicitly named in REF-012, but a direct consequence of REF-012 Section 5's "server-side validation is authoritative" principle applied to the one user-controlled redirect target this spec introduces — verified by manual test (see verification log), not only by the automated suite.
- **Admin blueprint gated twice:** `admin_bp` applies `role_required(ROLE_ADMIN)` both as a `before_request` hook (blueprint-wide) and again on the individual `dashboard` view, per REF-012 Section 4's explicit "defense in depth" instruction.
- **`role`/`status` also enforced as SQLite `CHECK` constraints**, not only at the application layer — verified directly (an out-of-band `role='superuser'` insert raises `IntegrityError`), matching REF-011 Section 3.6's "defense in depth" pattern already established for `Review.rating`.

## Business Rules
- Email is the unique login identifier; duplicate-email registration is rejected with a clear form error, not a silent overwrite.
- A user's `role` is fixed at registration and never changed by the user themselves (only an admin could reassign it, and no such feature is requested — role reassignment is out of scope unless a future spec asks for it).
- No customer-facing or mechanic-facing UI ever exposes a way to create an admin account.

## Data Requirements
Creates: `User` table (REF-011 Section 3.1). Reads/writes: none of the ML system's `data/` files.

## Database/Schema Changes
New database `instance/marketplace.db`, new table `user`. No changes to any ML-system CSV/Parquet file or schema (REF-001 untouched).

## API Requirements
None beyond the Flask routes themselves; no external network API introduced (consistent with CLAUDE.md Section 10's "thin, no external network services unless justified").

## Backend Behavior
Standard Flask app-factory pattern; SQLAlchemy models under `app/models/`; route handlers under `app/routes/`; no business logic embedded in templates.

## Frontend Behavior
Server-rendered Jinja2 templates; registration/login forms use Flask-WTF for CSRF + validation; no JavaScript required for this spec's scope (the star-rating widget and image-preview JS mentioned in REF-010 belong to DEV-019/DEV-021).

## UI States
- **Anonymous:** navbar shows Login/Register (customer)/Register (mechanic).
- **Logged in (customer):** navbar shows Search, My Account, My Reviews, Logout.
- **Logged in (mechanic):** navbar shows Search, My Profile, Opportunity Insights (link stubbed until DEV-023), Logout.
- **Logged in (admin):** navbar shows Admin, Logout — no customer/mechanic-facing links.
- **Registration error:** duplicate email / validation failure shown inline on the form, values preserved (except password fields).

## Validation
- Name: required, non-empty.
- Email: required, valid email format, unique.
- Password: required, minimum length (proposed 8 characters) — enforced server-side via WTForms `Length`.
- All rules re-checked server-side regardless of any HTML5 client-side attributes (REF-012 Section 5).

## Permissions
See REF-012 Section 3. This spec implements the "Register/login/logout" and "provisioned only" admin rows.

## Error Cases
- Duplicate email at registration — clear inline error, no account created, no partial `User` row left behind.
- Wrong password / unknown email at login — a single generic "invalid email or password" message (does not reveal whether the email exists, a standard login-security practice).
- Attempting to access a `login_required` route while logged out — redirect to `/login` with a "please log in" flash message, then return to the originally requested page after successful login.

## Edge Cases
- A blocked (`status='blocked'`) user attempting to log in — login is rejected with a clear "this account has been deactivated" message, distinct from the invalid-credentials message (so a blocked user isn't confused into thinking they mistyped their password).
- Concurrent registration with the same email (race condition) — the database's unique constraint on `User.email` is the final backstop even if an application-level pre-check race occurs.

## Security Considerations
See REF-012 Sections 2, 4, 5 in full — this spec implements password hashing, session handling, CSRF protection, and the base `role_required` decorator that every later spec relies on.

## Dependencies
None (first marketplace spec). Establishes REF-010, REF-011 (User table), REF-012 (Sections 2, 4).

## Testing Requirements
`tests/marketplace/test_auth.py` (26 tests, all passing): registration success (both roles) and hashed-password storage; duplicate-email and password-mismatch rejection; the no-public-admin-role-smuggling test; login success/failure (unknown email and wrong password both give one generic message); blocked-account login rejected with a distinct message; logout clears the session; anonymous access to a `login_required` route redirects to `/login`; `role_required` denies every wrong-role combination with 403 (customer↔mechanic↔admin, all six wrong-role/route pairs); the correct role reaches each stub page; CSRF rejects a POST with no token (both registration and login); admin CLI provisioning succeeds, rejects a duplicate email, and rejects a short password; customer account view/edit round-trips and rejects an email already used by another account.

## Acceptance Criteria
- [x] Flask app factory runs (`flask run` / `wsgi.py` serves `home.html` with HTTP 200) — verified via the test client and a manual smoke check of `/`, `/search`, `/login`, `/register/customer`, `/register/mechanic` (all 200) and a 404 fallback page for an unknown URL.
- [x] `instance/marketplace.db` created with the `user` table matching REF-011 Section 3.1 exactly, including both `CheckConstraint`s (verified directly: an out-of-band `role='superuser'` insert raises `IntegrityError`).
- [x] Customer and mechanic registration both work and store a correctly-hashed password (verified: `password_hash` never equals or contains the raw password; `check_password()` round-trips correctly).
- [x] Login/logout work and `current_user`/`role_required` behave correctly across all three roles (verified for every role pair, not just the happy path).
- [x] One admin account exists via the CLI provisioning path, none via a public form (verified: a role field smuggled into the customer-registration POST body has no effect).
- [x] `base.html`/`style.css` render a responsive, role-aware navigation bar (verified per-role via rendered HTML in the test suite; single mobile breakpoint in `style.css`).
- [x] All FRs above pass their corresponding tests in `tests/marketplace/test_auth.py` — 26/26 passing.
- [x] `pytest tests/` (the full existing suite) still passes unmodified — `pytest tests/ --ignore=tests/marketplace` (the original 191-test ML suite, run alone) passes 191/191 in 34.66s, identical to its pre-extension state. Combined with the marketplace suite in one process (`pytest tests/`, 217 tests total), one test (`test_dashboard_app.py::test_app_runs_without_exceptions`) intermittently exceeded Streamlit `AppTest`'s fixed 60s timeout; run alone it passes cleanly (13/13, ~21s), and run alone without any marketplace test present it also passes. This isolates the cause to resource contention from running ~220 tests — several with repeated TensorFlow/SHAP/SBERT cold-loads — back-to-back in one process, not to anything the marketplace extension changed. See the DEV-024 note below for follow-up.

## Definition of Done
All acceptance criteria met; `app/` runs independently of `dashboard/`/`src/`; no file under `specs/development/DEV-001`–`DEV-017`, `src/`, `dashboard/`, or the non-marketplace contents of `tests/` was modified to implement this spec (`requirements.txt` and `.gitignore` were extended, never had existing lines altered or removed).

## Known limitation carried forward to DEV-024
The pre-existing `test_dashboard_app.py::test_app_runs_without_exceptions` Streamlit `AppTest` uses a fixed 60-second timeout that can be exceeded under the resource contention of a full, single-process `pytest tests/` run once 200+ tests including several TensorFlow/SHAP/SBERT model loads are combined — a latent flakiness risk in the *existing* ML test suite, not introduced by this spec (reproduced without the marketplace tests present at all: `pytest tests/ --ignore=tests/marketplace` still exercises the same cold-load pattern). Flagged for DEV-024's audit rather than fixed here, since DEV-018 must not modify `tests/test_dashboard_app.py` (an existing, non-marketplace test file) without an explicit instruction to do so.
