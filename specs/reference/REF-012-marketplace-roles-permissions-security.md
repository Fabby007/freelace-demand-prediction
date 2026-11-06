# REF-012 — Marketplace Roles, Permissions & Security Requirements

**Status:** Approved reference specification (extension)
**Source:** `MARKETPLACE_EXTENSION.md` Sections 3, 5; approved 2026-08-21.

---

## 1. Purpose

Canonical authorization matrix and security requirements for the marketplace. DEV-018 through DEV-024 must implement exactly this matrix; no route may grant an action beyond what this table allows without a documented deviation logged in REF-009.

## 2. Authentication

- **Password storage:** `werkzeug.security.generate_password_hash` (PBKDF2-SHA256 by default) at registration; `check_password_hash` at login. Plaintext passwords are never logged, stored, or emailed.
- **Session management:** Flask-Login manages the session cookie (`session['_user_id']` under the hood); `SECRET_KEY` is read from an environment variable (or a local `.env` file excluded via `.gitignore`), never hardcoded or committed.
- **Login/logout:** `flask_login.login_user()` / `logout_user()`; `@login_required` on every route that requires an authenticated session.
- **Registration:** two distinct customer/mechanic registration forms (different required fields), both writing a `User` row with the appropriate `role`. Admin accounts are **not** self-registerable through any public form — see DEV-018/DEV-022 for provisioning (a seeded/CLI-created account, clearly labelled as such, consistent with the no-fabricated-data rule).
- **Session fixation / CSRF:** Flask-WTF's CSRF token required on every POST/PUT/DELETE form; Flask's session cookie uses its default secure signing (`itsdangerous`).
- **Open-redirect protection:** the login route's `next=` query parameter (used to return a user to the page they originally requested after `@login_required` redirected them) is validated by `app/utils/security.py::is_safe_redirect_target()` — only a same-origin relative path is followed; any absolute/external target is discarded in favour of the home page. Implemented in DEV-018, verified by manual test that `/login?next=https://evil.example` does not redirect off-site after a genuine login.

## 3. Authorization matrix

| Action | Customer | Mechanic (self) | Mechanic (other) | Admin |
|---|---|---|---|---|
| Register/login/logout | Yes | Yes | Yes | No (provisioned only) |
| View own account info | Yes | Yes (via profile dashboard) | — | Yes (any account, via the user list) |
| Edit own account info (name/email) | Yes | No (not an approved FR-M requirement — see DEV-024 audit note below) | No | Yes (any account, for moderation) |
| Search/browse mechanics | Yes | Yes | Yes | Yes |
| View a mechanic profile + contact number | Yes | Yes | Yes | Yes |
| Create/edit own mechanic profile | N/A | Yes | No | No direct content edit — block/unblock/delete the account instead (DEV-022) |
| Submit a review for a mechanic | Yes | No (mechanics do not review mechanics) | No | No |
| Edit/delete own review | Yes (own review only) | N/A | N/A | No direct edit — may hide/restore, see "Remove/restore a review" below |
| View own reviews (mechanic) | N/A | Yes | No | Yes |
| View Opportunity Insights | No | Yes | N/A | No (not a mechanic-facing tool; admins may view via a mechanic test account if needed, not a documented requirement) |
| Block/unblock a user account | No | No | No | Yes |
| Delete a customer or mechanic account (permanent) | No | No | No | Yes (never own account, never another admin — DEV-022) |
| Remove/restore a review | No | No | No | Yes |

**DEV-024 audit note (2026-08-21):** three cells above were corrected from an earlier, over-specified draft of this matrix. "Edit own account info" originally listed "Mechanic (self): Yes," but no such route was ever built and, on audit, no such requirement exists in `MARKETPLACE_EXTENSION.md`'s approved FR-M08–FR-M12 list either — only "edit own profile" (FR-M10, DEV-019's `MechanicProfile` fields) was ever approved. Per CLAUDE.md Section 21's hierarchy, `MARKETPLACE_EXTENSION.md` (which reproduces the approved feature list) outranks this reference spec, so the matrix is corrected to match the approved scope rather than a mechanic-account-edit page being built to match an over-specified matrix cell — consistent with DEV-024's explicit "do not add new major features" instruction. Similarly, "Create/edit own mechanic profile" and "Edit/delete own review" originally implied admin could directly edit profile/review content; DEV-022 FR3 always deliberately scoped admin mechanic-management down to block/unblock/delete (never content editing), and review moderation was always DEV-021 FR8's soft remove/restore (never content editing) — both cells now describe what was actually specified and built.

Rules embodied by this table, stated explicitly because they are the ones most likely to be gotten wrong in implementation:
- **A mechanic cannot edit another mechanic's profile** (Section "Mechanic Requirements" of the extension request, verbatim) — enforced by comparing `current_user.id == mechanic_profile.user_id` server-side on every edit route, never inferred from which link the UI happened to show.
- **A customer cannot access admin functionality**, and **a mechanic cannot administer the system** — enforced by a `role`-checking decorator on every `/admin/*` route (see Section 4), not by simply hiding admin links in the navigation template.
- **Ownership of a review**: only the reviewing customer (or an admin, for moderation) may edit/delete it — enforced by comparing `current_user.id == review.customer_id` (or `current_user.role == 'admin'`).

## 4. Role-based route protection

Every route under `app/routes/` declares its required role(s) via a decorator (e.g. `@role_required('mechanic')`, `@role_required('admin')`) applied **in addition to** `@login_required` where relevant. Public routes (home page, search, mechanic profile view, login, both registration forms) require no authentication. The decorator returns HTTP 403 (not a silent redirect that could be mistaken for success) when a logged-in user of the wrong role attempts a protected action, and redirects to login when no session exists at all.

`/admin/*` routes are additionally namespaced under a single Flask Blueprint (`admin_bp`) registered with a `url_prefix='/admin'`, so the role check can also be applied once at the blueprint level as defense in depth, not only per-view.

## 5. Input validation and file upload security

- **Server-side validation is authoritative.** All form fields (registration, profile edit, review submission) are validated via Flask-WTF/WTForms validators (`DataRequired`, `Email`, `Length`, `NumberRange`) on the server, regardless of any HTML5 `required`/`pattern` attributes or client-side JS used for UX. Client-side validation is a convenience, never a security boundary.
- **Rating bounds:** `rating` must be an integer in `[1, 5]`, enforced both by a WTForms `NumberRange` validator and a database `CheckConstraint` (REF-011 Section 3.6) — defense in depth.
- **Profile photo upload** (mechanic profile, "if practical" per the extension request):
  - Allowed extensions: `.png`, `.jpg`, `.jpeg` only, checked against the actual filename extension **and** rejected if the extension doesn't match typical image magic bytes (basic sniff) where feasible without adding a heavy new dependency.
  - Maximum file size enforced both client-side (UX) and server-side (`MAX_CONTENT_LENGTH` in Flask config, e.g. 2 MB) — server-side is the enforced limit.
  - Stored filename is **never** the user-supplied filename — generate a random/UUID-based filename on save to prevent path traversal or filename-collision attacks, and store the resulting relative path in `MechanicProfile.profile_image_path`.
  - Uploaded files are stored under `app/static/images/mechanics/`, a location that is never executed as code by the web server.
  - Deeper content-level validation (e.g. re-encoding the image via Pillow to strip any embedded payload) is optional hardening, flagged in DEV-024, not required for DEV-019's Definition of Done — see MARKETPLACE_EXTENSION.md Open Question 3.
- **No SQL injection surface:** all database access goes through SQLAlchemy's ORM/parameterized query interface; no raw string-interpolated SQL is used anywhere in `app/`.
- **No secrets in version control:** `SECRET_KEY`, and any future credential, is read from environment variables or a gitignored `.env` file; `instance/marketplace.db` itself is also gitignored (it can contain real, if minimal, user email addresses once the app is used).

## 6. What is explicitly not implemented (documented, not silently skipped)

- **HTTPS/TLS termination** — out of scope for this academic project's local/demo deployment; noted as a production consideration, not implemented, consistent with REF-004's anti-over-engineering constraint. Passwords are still hashed at rest regardless of transport security.
- **Rate limiting on login/registration** (brute-force protection) — optional hardening, may be added in DEV-024 if time permits, not a blocking requirement.
- **Email verification / password reset flows** — not required by the approved feature list (registration/login/logout only); adding them would be inventing scope beyond what was requested, so they are not built unless a future specification explicitly asks for them.
- **Multi-factor authentication, OAuth/social login** — explicitly out of scope; no such requirement exists in the approved feature list.

## 7. Related specs

- DEV-018 (Web Application Foundation, Database & Authentication) — implements Section 2.
- DEV-019 (Mechanic Profiles & User Roles) — implements the profile-ownership rule and photo upload (Section 5).
- DEV-021 (Ratings & Reviews) — implements the review-ownership rule.
- DEV-022 (Admin Dashboard & Management) — implements the admin-only rows of Section 3.
- DEV-024 (Web Application Testing, Security & Final Integration) — verifies this entire matrix by test, including negative tests (a customer attempting an admin action must be rejected, etc.).
- REF-011 (Marketplace Database Schema) — the tables this matrix governs.
- REF-005 (Ethical, Legal & Data-Governance Rules) — the ML system's existing privacy/security posture, which this file extends into the marketplace's own data (real names, emails, contact numbers) rather than contradicts.
