# Preflight design

## Goals and scope
Preflight will verify small-business invoices before payment and return PASS,
REVIEW or BLOCK with cited evidence. Deterministic Python decides; a model may
only extract fields and explain findings. M0-M1 establish typed contracts and
identifier validators; this delivery adds M2 checks/ledger/policy and M3 extraction.
Web UI, evaluation and Docker remain M4-M5 work.

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
  UPI handles permit ASCII letters in either case. IBAN also accepts standard
  four-character printed groups; other identifier whitespace remains invalid.
- GST state consistency compares a supplied two-digit registration state, not
  place of supply. Historical state codes are accepted for old invoices.
- Missing or blank identifiers and absent state context are unverifiable.
- IBAN supports ISO shape and mod-97 only in M1, not country-specific BBAN
  registries. UPI/IFSC checks validate syntax, not bank or PSP existence.
- No optional empty subsystem packages, service, evaluator or policy configuration
  are added before their milestone. No network is permitted during tests.

## M2-M3 assumptions
- Empty or all-unverifiable findings produce REVIEW; a partially verified PASS
  explicitly carries its unverifiable checks. Informational gaps score zero.
- Bank baselines bind domestic account and IFSC together. Every supplied payment
  rail must match an approved identifier; approvals are never automatic.
- Anomaly baselines use prior PASS invoices for the same vendor and currency.
  Zero MAD with a different amount is high severity; equal amounts score zero.
- Duplicates include all verdicts; hash matching is global, financial matching
  is vendor/currency scoped. Near duplicates use an inclusive prior 3-day window.
- Uploaded Authentication-Results are not a trusted receiver attestation.
  Reported failures are warning signals; reported passes never establish trust.
- Domains use bounded full-domain comparison, common confusables and zero-width
  stripping. This heuristic is not a complete Unicode confusable registry.
- Policy regex configuration is local and trusted; it is not document-controlled.
- Every populated extracted scalar must have value-bearing text evidence on its
  cited page before checks run. Text presence does not prove semantic association.
- Image-only extractions require REVIEW because snippets cannot be independently
  grounded without OCR. Blank-text PDF pages return ocr_unavailable.
- RFC email has no binary magic; MIME sniffing uses bounded recognizable headers.
  Attachments remain in memory. One invoice attachment can be selected automatically;
  multiple attachments or nested emails require REVIEW, never silent selection.
- Input limits: 10 MiB, 100 PDF pages, 200,000 text characters, 10 attachments,
  100 MIME parts and 20 levels. Native parser CPU/memory isolation is future work.
- Providers must support chat/completions and JSON-schema output; images also need
  a vision model. Transient retries are three attempts per request with 1/2-second
  backoff; invalid schema gets one retry. No real provider calls occur in tests.
- Missing core vendor/number/currency/total fields force REVIEW and no fabricated
  invoice row. Extraction/ingestion/evidence failures return typed report reasons.
- Vendor lookup defaults to exact local names; callers can select an explicit
  vendor_id. Neither model output nor uploaded email authenticates vendor identity.

## Identifier references
- [GST state master](https://docs.ewaybillgst.gov.in/apidocs/state-code.html)
- [GST registration structure](https://www.dor.gov.in/files/inline-documents/Report_on_GST_Registration_0.pdf)
- [SWIFT mod-97 guidance](https://www.swift.com/sites/default/files/documents/swift_solutions_faq_ibanplus.pdf)
