# REF-004 — Non-Functional Requirements & System Constraints

**Status:** Approved reference specification
**Source:** Section 22 and Section 5 of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

Single source of truth for the project's non-functional requirements (NFRs) and scope boundaries. Every DEV spec whose acceptance criteria touch performance, reproducibility, explainability, usability, maintainability, data integrity, security/privacy, or portability must link here rather than restate the requirement.

## 2. Section 22 — Non-Functional Requirements (verbatim)

- **Reproducibility:** the same dataset version and configuration should reproduce the same trained model within normal library-level nondeterminism.
- **Explainability:** each top recommendation should have model-based explanatory factors.
- **Usability:** a user should be able to choose a vehicle category and view recommendations without understanding ML terminology.
- **Performance:** dashboard predictions for a pre-trained model should return within a few seconds on a normal laptop.
- **Maintainability:** extraction, preprocessing, modelling and dashboard code should be separated into modules.
- **Data integrity:** processed values must be traceable to a raw source.
- **Security/privacy:** do not collect unnecessary personal data.
- **Portability:** the project should run from a documented Python environment using requirements.txt or pyproject.toml.

## 3. Section 5 — Project Scope and Boundaries (verbatim table)

| Area | Included in the project | Boundary / rule |
|---|---|---|
| Domain | Freelance mechanic service opportunity in Sri Lanka | The core implementation focuses on mechanics. |
| Initial vehicle category | Motorcycles | Cars and three-wheelers can be added if data quality is sufficient. |
| Geography | Sri Lankan administrative districts | The design supports all 25 districts, subject to consistent data availability. |
| Time | Yearly or monthly historical observations | Final granularity is determined by the best common resolution across sources. |
| Prediction output | Relative demand/opportunity score, forecast, or district ranking | Exact job counts are only allowed if a genuine job-demand target is available. |
| Data | Real observed data from government, Kaggle or permitted public sources | No fabricated rows or invented labels for model training. |
| Interface | Web dashboard for analysis and recommendation | No mobile application is required for the first release. |
| Expansion | Other freelance service categories | Only considered after the mechanic system is complete and validated. |

## 4. Out-of-scope items (Section 31 — Future Extensions, verbatim, NOT to be implemented in the current build)

- Car-mechanic and three-wheeler-mechanic submodels using the same vehicle-data pipeline (beyond what Section 5 already permits when data quality allows).
- More detailed service categories (electrical repair, tyre work, scheduled maintenance) if a suitable target dataset exists.
- Finer geographic granularity (divisional/city level) if reliable data becomes available.
- Near-real-time public signals if a lawful and stable source exists.
- Other freelance services (electricians, plumbers) using appropriate domain data, only after the mechanic implementation is complete.
- User feedback collection to evaluate whether recommendations are useful in practice.

## 5. Over-engineering constraint (MASTER_PROMPT.md Hard Rules)

No microservices, no Kubernetes, no enterprise auth systems, no unnecessary abstraction layers, no message queues, no container orchestration, no multi-service architecture — unless the user explicitly asks for it later. This is a final-year academic project that must be maintainable, explainable in a viva, and reproducible, not a production SaaS platform.

## 6. Related specs

All DEV specs; especially DEV-017 (Reproducibility & Deployment Readiness) for Reproducibility/Portability, DEV-013 (Dashboard) for Usability/Performance, DEV-010/DEV-012 for Explainability, DEV-004 for Data integrity, REF-005 for Security/privacy detail.
