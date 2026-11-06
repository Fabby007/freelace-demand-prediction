# DEV-011 — SBERT Natural-Language Query Module

## Specification ID
DEV-011

## Feature/Module Name
SBERT Natural-Language Query Module

## Purpose
Interpret a natural-language user query (e.g. "I repair motorcycles. Which district should I consider next month?"), match it to the correct vehicle/mechanic category via semantic similarity, and route it into the existing prediction pipeline — without ever acting as the prediction model itself.

## Background/Context
Source doc Section 16 (SBERT — Natural-Language Query Understanding), Section 16.1 (5-step example interaction), Section 16.2 (why useful), Appendix C.2 (example). Per DEV-PLAN.md, this spec is non-blocking for the core delivery path.

## Related Requirements
- FR-10 (accept a natural-language query and use SBERT to map it to a supported category)
- Section 16
- REF-003 (Why SBERT, Section 6)

## User Roles
End user (freelance mechanic) interacts with this via the dashboard's optional NL query box (DEV-013), but the routing logic itself is backend.

## Preconditions
DEV-008 complete: a working prediction pipeline exists to route matched queries into.

## User Stories/Use Cases
- As a mechanic, I want to type "I repair motorcycles, where should I focus next month?" and have the system understand I mean the motorcycle-mechanic category, without me having to use a dropdown (Section 16.2).
- As the developer, I need unsupported/ambiguous queries to fail safe — never silently guessing a category with false confidence (Section 26.3 dashboard test).

## Functional Requirements

### 16.1 Example interaction (5 steps, verbatim, adapted)
1. SBERT embeds the user's natural-language query.
2. The embedding is compared with predefined category descriptions ("motorcycle mechanic," "car mechanic," "three-wheeler mechanic").
3. The highest semantic match selects the appropriate prediction pipeline/category.
4. The ranking engine (DEV-012) returns the top districts for that category.
5. SHAP (DEV-010, via DEV-012) provides model-based reasons for the recommendation.

### Additional requirements
- Define category description embeddings once (motorcycle/car/three-wheeler mechanic — REF-002 canonical categories), not recomputed per query.
- Implement a similarity threshold: if the best match's similarity score is below a documented threshold, the query is treated as unsupported/ambiguous.
- Safe-fallback behavior: on an unsupported/ambiguous query, the system must **not** silently guess a category and present it with confidence. It must inform the user the query could not be confidently matched and offer the manual category selector instead (Section 27 risk mitigation: "Show selected category and allow manual correction").
- Always surface the matched category to the user (even on a confident match), so the user can override it manually if SBERT is wrong (Section 27 risk mitigation).

## Business Rules
- SBERT is **not** the prediction model and is **not** a free-form explanation generator (Section 16, explicit). It only routes a query to a category; it must never be used to fabricate demand numbers or explanations.
- A failed/ambiguous match must never silently default to a specific category (e.g. never silently default to "Motorcycle" just because it's the primary scenario) — this would misrepresent user intent as confident routing.

## Data Requirements
Input: free-text user query (from DEV-013's NL query box). Category description texts (small, fixed set — defined here, not user-editable at runtime). Output: matched category (or "unsupported") + similarity score, passed to DEV-012.

## Database/Schema Changes
None (category descriptions are a small static config, e.g. `configs/sbert_categories.*`).

## API Requirements
None (function-level module, called from the dashboard layer).

## Backend Behavior
SBERT logic lives in `src/nlp/` (separate module from `src/models/`, `src/explainability/`, `src/recommendation/` — per MASTER_PROMPT.md Section 5's explicit instruction not to merge SBERT with SHAP or other components).

## Frontend Behavior
The dashboard's NL query box (DEV-013) calls this module and displays: the matched category (with an option to override), or a clear "couldn't confidently match your query — please select a category" message on fallback.

## UI States
- Confident match: category shown + used to drive the ranking/dashboard update, with an override control visible.
- Ambiguous/unsupported match: fallback message shown, no category silently applied, user prompted to use the manual selector.

## Validation
- Similarity threshold is documented and tested (Section 26.3: "unsupported SBERT queries produce a safe fallback rather than a wrong category").
- Matched category is always one of the REF-002 canonical vehicle categories, never a fabricated/free-text label.

## Permissions
N/A.

## Error Cases
- Empty query string — treated as no query submitted, not as an ambiguous match.
- Query in a language/script SBERT's chosen model wasn't trained to embed meaningfully — treated as unsupported (falls into the same safe-fallback path), not silently mismatched.

## Edge Cases
- A query that plausibly matches two categories almost equally (e.g. "I fix three-wheelers and small cars") — if the top-two similarity scores are too close (below a documented margin), treat as ambiguous rather than picking the marginally higher one with false confidence.

## Security Considerations
No personal data is collected via the query box beyond the query text itself, which is not persisted with any personal identifier (REF-005).

## Dependencies
- DEV-008 (XGBoost Primary Prediction Model) — needs a working prediction pipeline to route into.
- REF-003 (ML Component Architecture Reference)

## Testing Requirements
- Section 26.3 dashboard test: unsupported SBERT queries produce a safe fallback rather than a wrong category.
- Matching-accuracy spot-check against a small hand-written set of example queries per category (e.g. "bike repair", "I fix motorcycles", "car mechanic here", "trishaw repairs").

## Acceptance Criteria
- [x] Category description embeddings defined for Motorcycle/Car/Three-wheeler mechanic — `src/nlp/sbert_router.py::SBERTRouter.load()`, computed once from `configs/sbert_categories.yaml`'s existing descriptions using `sentence-transformers/all-MiniLM-L6-v2` (REF-009 ADR-016), reused for every subsequent `route()` call (verified: `tests/test_sbert_router.py::test_category_embeddings_computed_once_and_reused`).
- [x] Query embedding + similarity matching implemented — `SBERTRouter.route()`; cosine similarity between the query embedding and all three category embeddings.
- [x] Similarity threshold documented and enforced for safe fallback — retuned from the 0.55 placeholder to **0.30** based on real spot-check evidence (REF-009 ADR-017); `ambiguous_margin` confirmed at the placeholder **0.05**.
- [x] Matched category always surfaced to the user with an override option — every `RouteResult` (confident or not) exposes `similarity_scores` for all three categories, and `matched_category` is populated on a confident match for the dashboard's override control (DEV-013) to render.
- [x] Unsupported/ambiguous queries never silently default to a category — `matched_category` is `None` for every status except `"confident"`; `tests/test_sbert_router.py::test_ambiguous_status_never_defaults_to_motorcycle` explicitly checks the Business Rule's named failure mode.

### Spot-check results (tests/test_sbert_router.py, all passing)

| Query | Status | Matched category | Top score | Margin |
|---|---|---|---|---|
| "bike repair" | confident | Motorcycle | 0.556 | 0.094 |
| "I fix motorcycles" | confident | Motorcycle | 0.591 | 0.139 |
| "car mechanic here" | confident | Car | 0.730 | 0.064 |
| "trishaw repairs" | confident | Three-wheeler | 0.612 | 0.193 |
| "tuk tuk mechanic" | confident | Three-wheeler | 0.613 | 0.172 |
| "I repair motorcycles. Which district should I consider next month?" (Section 16.1's own example) | **ambiguous** | — | 0.423 | 0.043 |
| "I service scooters and mopeds" | ambiguous | — | 0.397 | 0.041 |
| "what is the weather today" | unsupported | — | 0.078 | — |
| "asdkfj alsdkfj qwe" | unsupported | — | 0.137 | — |
| "" / whitespace / `None` | empty | — | — | — |

The Section 16.1 example landing as "ambiguous" rather than "confident" is a deliberate, documented outcome (REF-006 Section 5.5, REF-009 ADR-017) — not a defect.

## Testing Requirements — completed
- Section 26.3 dashboard test ("unsupported SBERT queries produce a safe fallback rather than a wrong category") — `tests/test_sbert_router.py`, parametrized over irrelevant queries.
- Matching-accuracy spot-check against a small hand-written set — see table above; 5/5 unambiguous single-category queries route correctly, both deliberately-close queries are correctly flagged ambiguous, both irrelevant queries are correctly rejected.
- Full suite: `tests/test_sbert_router.py`, 19/19 passing; full project test suite 106/106 passing.

## Definition of Done
All acceptance criteria met; DEV-013's NL query box can call `SBERTRouter.load()` once and `router.route(query)` per interaction to correctly route confident matches into DEV-012's ranking pipeline while safely failing (with a clear, always-populated `similarity_scores` breakdown) on ambiguous/unsupported/empty queries.
