# REF-011 — Marketplace Database Schema

**Status:** Approved reference specification (extension)
**Source:** `MARKETPLACE_EXTENSION.md` Sections 3–4; approved 2026-08-21.
**Scope:** SQLite schema for `instance/marketplace.db`, accessed via Flask-SQLAlchemy models under `app/models/`. Entirely separate from the ML system's `data/` CSV/Parquet schema (REF-001), which this file does not modify.

---

## 1. Purpose

Canonical entity/relationship definition for the marketplace database, to be implemented as SQLAlchemy models in DEV-018/DEV-019/DEV-021. DEV specs must conform to this schema rather than inventing columns ad hoc; any new column or table introduced during implementation must be added here first, with an ADR in REF-009 if it deviates from what is defined below.

## 2. Design principles

- One entity per real-world concept the approved feature list actually requires (Section 7 of the extension request explicitly forbids inventing entities such as `Booking`, `Payment`, `Chat`, `Job`, or `Availability` — none of those appear below).
- Every foreign key is enforced at the database level (SQLite `PRAGMA foreign_keys=ON`, enabled in `app/extensions.py`).
- Passwords are never stored in plaintext or in a reversible format — only `password_hash` (see REF-012 Section 2).
- Average rating is **computed at query time** from `Review` rows, not cached as a denormalized column — at this project's expected scale (tens to low hundreds of mechanics/reviews for an academic demo), a live `AVG()`/`COUNT()` query is simpler and always accurate, avoiding cache-invalidation logic. This is an implementation decision (not a documented requirement) and may be revisited if a future specification demonstrates a real performance need — log any change as an ADR.

## 3. Entities

### 3.1 `User`
Base account for all three roles. A single table with a `role` discriminator column, rather than separate tables per role, keeps authentication/session logic uniform (one login form, one password check) while `MechanicProfile` (Section 3.2) carries every mechanic-specific field.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | integer | PK, autoincrement | |
| name | string | not null | |
| email | string | not null, unique | used as the login identifier |
| password_hash | string | not null | `werkzeug.security.generate_password_hash` output; never plaintext |
| role | string (enum) | not null, one of `customer`, `mechanic`, `admin` | |
| status | string (enum) | not null, default `active`, one of `active`, `blocked` | admin-controlled (DEV-022) |
| created_at | datetime | not null, default now | |

### 3.2 `MechanicProfile`
One row per mechanic account (1:1 with a `User` where `role='mechanic'`).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | integer | PK, autoincrement | |
| user_id | integer | FK → User.id, unique, not null | one profile per mechanic user |
| contact_number | string | not null | displayed to customers (FR-M05) |
| district | string | not null | one of REF-002's 25 canonical district names — reused for terminology consistency with the ML system, but this is a self-reported business-location field, not an ML research observation (see MARKETPLACE_EXTENSION.md Section 7.2) |
| years_experience | integer | not null, >= 0 | |
| description | text | nullable | free-text "about" section |
| profile_image_path | string | nullable | relative path under `app/static/images/`; see REF-012 Section 5 for upload rules |
| created_at | datetime | not null, default now | |
| updated_at | datetime | not null, default now, updated on edit | |

### 3.3 `Service` (lookup table)
Fixed starter list of service categories a mechanic may offer, extendable only by an admin (not by mechanics themselves, to keep the list canonical and avoid free-text drift — Open Question 2 in MARKETPLACE_EXTENSION.md).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | integer | PK, autoincrement | |
| name | string | not null, unique | e.g. "General Repair & Servicing", "Engine Diagnostics & Repair", "Electrical Work", "Tyre & Battery Service", "Body Work & Painting", "Scheduled Maintenance" |

Starter list proposed at DEV-019 implementation time (seed data, clearly labelled as seed/reference data, not fabricated user records — MARKETPLACE_EXTENSION.md Section 5).

### 3.4 `MechanicService` (join table)
Many-to-many between `MechanicProfile` and `Service`.

| Column | Type | Constraints |
|---|---|---|
| mechanic_id | integer | FK → MechanicProfile.id, part of composite PK |
| service_id | integer | FK → Service.id, part of composite PK |

### 3.5 `MechanicVehicleType` (attribute table, not a full lookup entity)
The vehicle types a mechanic handles. Reuses REF-002's fixed three-value canonical list (`Motorcycle`, `Car`, `Three-wheeler`) directly as a constrained string column rather than a separate `VehicleType` entity table — a dedicated entity would be unnecessary indirection for a fixed, closed set of three values (consistent with the "do not invent unnecessary entities" instruction).

| Column | Type | Constraints |
|---|---|---|
| mechanic_id | integer | FK → MechanicProfile.id, part of composite PK |
| vehicle_type | string (enum) | one of `Motorcycle`, `Car`, `Three-wheeler`, part of composite PK |

### 3.6 `Review`
A customer's rating/review of a mechanic.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | integer | PK, autoincrement | |
| customer_id | integer | FK → User.id, not null | must reference a `role='customer'` user (enforced in application logic, see DEV-021) |
| mechanic_id | integer | FK → MechanicProfile.id, not null | |
| rating | integer | not null, 1 <= rating <= 5 | enforced via `CheckConstraint` |
| review_text | text | not null, min length enforced at the form layer (see REF-013 Section 4) | |
| status | string (enum) | not null, default `visible`, one of `visible`, `removed_by_admin` | soft-delete for admin moderation (Section 4.4 below) |
| created_at | datetime | not null, default now | |
| updated_at | datetime | not null, default now, updated on edit | |

**Uniqueness rule:** at most one `visible`-lifecycle review per `(customer_id, mechanic_id)` pair — enforced by a unique constraint on `(customer_id, mechanic_id)`. A customer who wants to change their opinion **edits their existing review**; they do not create a second one (see REF-013 Section 4).

## 4. Relationships (ERD, text form)

```
User (1) ──────────< (1) MechanicProfile          [1:1, only for role='mechanic']
User (1, role=customer) ──────────< (N) Review     [1:N — a customer may write many reviews, one per mechanic]
MechanicProfile (1) ──────────< (N) Review          [1:N — a mechanic accumulates many reviews]
MechanicProfile (N) ──────────< MechanicService >────────── (N) Service      [M:N via join table]
MechanicProfile (1) ──────────< (N) MechanicVehicleType                       [1:N attribute rows, closed 3-value set]
```

No `Booking`, `Payment`, `Chat`, `Job`, or `Availability` table exists anywhere in this schema — see MARKETPLACE_EXTENSION.md Section 2.2 for why each is explicitly out of scope.

## 5. Indexes

- `User.email` — unique index (login lookup).
- `MechanicProfile.user_id` — unique index (1:1 enforcement, fast profile-by-user lookup).
- `MechanicProfile.district` — index (search/filter, FR-M04).
- `Review.mechanic_id` — index (average-rating aggregate query, profile page load).
- `Review(customer_id, mechanic_id)` — unique index (Section 3.6 uniqueness rule).

## 6. Search query shape (for DEV-020)

A district + vehicle-type + service-type filtered search is, in SQL terms:

```sql
SELECT mp.* FROM mechanic_profile mp
JOIN user u ON u.id = mp.user_id AND u.status = 'active'
LEFT JOIN mechanic_vehicle_type mvt ON mvt.mechanic_id = mp.id
LEFT JOIN mechanic_service ms ON ms.mechanic_id = mp.id
LEFT JOIN service s ON s.id = ms.service_id
WHERE (:district IS NULL OR mp.district = :district)
  AND (:vehicle_type IS NULL OR mvt.vehicle_type = :vehicle_type)
  AND (:service_name IS NULL OR s.name = :service_name)
GROUP BY mp.id;
```

Expressed via SQLAlchemy ORM queries in `app/routes/marketplace.py`, not raw SQL (see REF-012 Section 3 for the SQL-injection rationale). Blocked/inactive users (`User.status = 'blocked'`) must never appear in search results.

## 7. Related specs

- DEV-018 (Web Application Foundation, Database & Authentication) — creates `User` and the SQLAlchemy setup.
- DEV-019 (Mechanic Profiles & User Roles) — creates `MechanicProfile`, `Service`, `MechanicService`, `MechanicVehicleType`.
- DEV-020 (Mechanic Search & Discovery) — implements the query shape in Section 6.
- DEV-021 (Ratings & Reviews) — creates `Review`.
- REF-002 (District & Vehicle-Category Canonical Lists) — source of the `district` and `vehicle_type` value domains reused here.
- REF-012 (Roles, Permissions & Security) — ownership/authorization rules over these tables.
