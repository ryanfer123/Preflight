# Preflight design

## Goals and scope
Preflight will verify small-business invoices before payment and return PASS,
REVIEW or BLOCK with cited evidence. Deterministic Python decides; a model may
only extract fields and explain findings. This delivery implements M0 and M1:
tooling, typed contracts and identifier validators. M2-M5 are planned, not shipped.

## Non-goals
No payment execution, authentication, multi-tenancy, cloud deployment or model
training. Identifier syntax never establishes ownership or registration.

## Architecture
Planned flow: bounded upload + MIME sniffing -> PyMuPDF document text / email parser
-> Extractor protocol -> strict InvoiceExtraction -> normalized Invoice + Context
-> pure checks -> policy -> SQLite audit record -> Jinja2/HTMX result.
Extraction failures and missing observations remain explicit. Findings carry
field, exact source snippet and optional one-based page. M1 exposes identifiers
as valid, invalid or unverifiable; these are observations, never verdicts.
Money uses finite Decimal values exclusively. No verdict field exists in the
extraction contract. Unknown schema fields and coercive Python inputs are rejected.

## Threat model
Documents, email headers and model responses are attacker-controlled. Planned
controls include a 10 MB upload limit, MIME sniffing, document text only in user
messages, one schema retry, escaping HTML and local-only persistence. Email
Authentication-Results can be forged unless its receiving trust boundary is known;
it cannot independently establish sender integrity. Ledger approval requires
human verification through a trusted channel; remembering attacker bank details
would poison future comparisons. A checksum is not proof of authenticity.

## Policy and milestones
M0 scaffold/tooling; M1 models/identifiers; M2 pure checks, SQLite ledger and weighted
policy; M3 bounded extraction/providers; M4 accessible web UI; M5 offline seeded
evaluation, real metrics, Docker/Compose and demo documentation.
Planned policy: any critical -> BLOCK; any high or score at threshold -> REVIEW;
otherwise PASS, with required unverifiable checks surfaced for review.
Every milestone must pass make check and receive a conventional commit.
Evaluation will distinguish extraction failures from check misses and report
per-attack precision, recall and false-positive rate without calling synthetic
results real-world fraud accuracy.

## Assumptions
- Preserve the existing Android starter; Preflight is a separate Python package
  in this root. Initialize Git because the supplied directory has no repository.
- Python 3.12 is the supported runtime; uv creates the development environment.
- Identifier input must already be normalized: uppercase GSTIN/IFSC/IBAN,
  no embedded spaces; UPI handles permit ASCII letters in either case.
- GST state consistency compares a supplied two-digit registration state, not
  place of supply. Historical state codes are accepted for old invoices.
- Missing or blank identifiers and absent state context are unverifiable.
- IBAN supports ISO shape and mod-97 only in M1, not country-specific BBAN
  registries. UPI/IFSC checks validate syntax, not bank or PSP existence.
- No optional empty subsystem packages, service, evaluator or policy configuration
  are added before their milestone. No network is permitted during tests.

## Identifier references
- [GST state master](https://docs.ewaybillgst.gov.in/apidocs/state-code.html)
- [GST registration structure](https://www.dor.gov.in/files/inline-documents/Report_on_GST_Registration_0.pdf)
- [SWIFT mod-97 guidance](https://www.swift.com/sites/default/files/documents/swift_solutions_faq_ibanplus.pdf)
