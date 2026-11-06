# REF-007 — Domain Rationale & Terminology

**Status:** Approved reference specification
**Source:** Section 2 and Section 6 of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

Explains *why* vehicle-registration data is a valid signal for mechanic service opportunity, and fixes the exact wording conventions the system must use (and avoid) when presenting predictions. All user-facing text in DEV-012 (Ranking Engine) and DEV-013 (Dashboard) must follow the "correct interpretation" wording rules in Section 4 below.

## 2. Section 2 — Project Definition (verbatim)

**Working title:** Mechanic Service Demand Opportunity Prediction and Recommendation System — Sri Lanka.

The system collects and integrates real vehicle and district data, models historical patterns, predicts a future service-demand signal or opportunity indicator, ranks Sri Lankan districts, explains the reasons for each ranking, and presents the results in an interactive web application for freelance mechanics.

**2.1 Primary user:** A freelance or independent mechanic who wants data-driven guidance about where service and repair opportunities may be stronger. First scenario: motorcycle mechanic. Same structure also supports car mechanics and three-wheeler mechanics.

**2.2 Core user question:** "For the selected vehicle category and future period, which districts show the strongest predicted service opportunity, and what factors caused those districts to rank highly?"

## 3. Section 6 — Domain Rationale: Why Vehicle Data Can Support Mechanic Opportunity Analysis (verbatim)

A vehicle that is registered and used in a district becomes part of that district's service market. New vehicles require scheduled maintenance according to manufacturer recommendations, while older vehicles continue to create demand for repairs, tyre work, electrical work, replacement parts and general maintenance. Vehicle registrations and total vehicle population can help describe the potential market available to mechanics.

**6.1 New registrations:** measures vehicles registered during a specific reporting period. A large increase does not mean the district has the same number of new mechanic jobs — it means the serviceable vehicle base has grown, which can influence future maintenance opportunity.

**6.2 Total vehicle population:** different from new registrations. A district may have few new registrations but a large stock of older vehicles requiring more repair work. Include total vehicle population by type when reliable figures are available.

## 4. Correct vs. incorrect wording (Section 6.3, verbatim) — MUST be followed by all user-facing text

- **Good:** "Kandy shows a high predicted motorcycle-service opportunity for the selected period."
- **Good:** "Kandy ranks first because recent motorcycle registrations and vehicle-stock indicators are relatively strong."
- **Avoid:** "Kandy will definitely have 1,240 mechanic jobs," unless a real job-count label supports that statement.

## 5. Terminology definitions (for CLAUDE.md and onboarding of future sessions)

- **Opportunity/proxy target vs. real demand target:** a *real demand target* is an observed mechanic-demand signal (repair requests, bookings, completed jobs, workshop visits, maintenance transactions). A *proxy target* is a real, observable vehicle-market variable (e.g. future registrations) used as a stand-in when no real demand target is available, always presented as a relative opportunity indicator, never as a job count (Section 8).
- **District:** one of Sri Lanka's 25 official administrative districts (REF-002).
- **Vehicle category:** Motorcycle, Car, or Three-wheeler (REF-002); Motorcycle is the first/primary scenario.
- **New registrations vs. vehicle population:** new registrations = vehicles registered in a given period; vehicle population = total stock of registered/operating vehicles of that type in the district (Section 6.1–6.2). Both are distinct signals and must not be conflated.
- **Leakage:** using information from period ≥ t (the prediction target period) to construct a feature used to predict period t (Section 12.1).
- **Opportunity band:** a transparent Low / Moderate / High / Very High categorization of a district's predicted value, derived from quantiles or a documented training-data rule (Section 18 step 4).
- **source_id / provenance:** a unique identifier tracing every processed row back to its original source table/publication, required on every row (Appendix A, Section 26.1).
- **Walk-forward validation:** a time-aware validation approach where the model is evaluated on periods strictly after its training window, as opposed to random train/test splitting (Section 23.4).

## 6. Related specs

- DEV-012 (Ranking & Recommendation Engine) — must use Section 4 wording rules.
- DEV-013 (Dashboard) — must use Section 4 wording rules and display the Appendix C.3 disclaimer.
- CLAUDE.md — "Important terminology" section pulls directly from Section 5 above.
