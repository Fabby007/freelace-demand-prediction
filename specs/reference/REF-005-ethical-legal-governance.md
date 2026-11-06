# REF-005 — Ethical, Legal & Data-Governance Rules

**Status:** Approved reference specification
**Source:** Section 28 of the Final Project Documentation, reproduced verbatim below.

---

## 1. Purpose

Binding governance rules for every stage of data collection, modelling, and presentation. These rules are non-negotiable per MASTER_PROMPT.md Section 0 (Hard Rules) and apply across DEV-002, DEV-003, DEV-004, DEV-012, DEV-013, and DEV-016.

## 2. Section 28 — Ethical, Legal and Data-Governance Considerations (verbatim)

- Use aggregated public statistics wherever possible.
- Do not collect personal vehicle-owner information for this project.
- Respect website terms and access limits when scraping.
- Record dataset licences and attribution requirements.
- Do not present model output as a guarantee of income, employment or customer availability.
- Disclose data cut-off dates and major missing-data limitations.
- Keep source files and transformations reproducible so results can be audited.
- Avoid unfairly labelling a district as "bad"; use neutral opportunity bands and explain that model output is probabilistic.

## 3. Application by area

| Rule | Enforced primarily in |
|---|---|
| Use aggregated public statistics wherever possible | DEV-002, DEV-003 |
| Do not collect personal vehicle-owner information | DEV-002, DEV-003 |
| Respect website terms and access limits when scraping | DEV-003 |
| Record dataset licences and attribution requirements | DEV-002 (source register), REF-001/REF-008 |
| Do not present model output as a guarantee of income/employment/customers | DEV-012, DEV-013 (disclaimer, Appendix C.3) |
| Disclose data cut-off dates and major missing-data limitations | DEV-013 (data-source/model-version panel) |
| Keep source files and transformations reproducible | DEV-004, DEV-017 |
| Avoid unfairly labelling a district as "bad"; neutral opportunity bands | DEV-012 |

## 4. Related specs

- REF-006 (Risks, Assumptions & Limitations)
- DEV-012 (Ranking & Recommendation Engine) — opportunity-band neutrality and disclaimer wiring
- DEV-013 (Dashboard) — disclaimer display (Appendix C.3), data cut-off disclosure
