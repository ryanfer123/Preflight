# Preflight design

## Goals and scope
Preflight will verify small-business invoices before payment and return PASS,
REVIEW or BLOCK with cited evidence. Deterministic Python decides; a model may
only extract fields and explain findings. M0-M3 establish typed contracts, validators, checks, ledger and bounded extraction.
M4-M5 add the local web workbench, Supabase persistence, evaluation and packaging.

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
messages, one schema retry, escaping HTML and server-side database persistence. Email
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

## M4-M5 assumptions and interface decisions
- The later M4-M5 request extends the earlier M3 delivery limit. Preserve the
  Android starter and keep the server local with one worker and no authentication.
- Plain forms and native details/summary provide every flow without JavaScript.
  The interface uses indigo #4145b8, ink #17223b, muted #57627a, white #ffffff,
  ground #f4f6fb and divider #dce1ec. Avenir/Segoe system fonts keep it offline.
  A fixed workspace rail leads to a left-aligned invoice intake and decision guide;
  results put evidence beside a permanently visible verification-gap summary.
  No decorative charts or invented fraud statistics appear in the product.
- Signed double-submit CSRF tokens are process-local and expire on restart.
  Trusted hosts prevent DNS rebinding. Each file is capped at 10 MiB and the
  entire buffered multipart request at 21 MiB before parsing, including chunked
  requests. Upload bytes are discarded; reports, citations and history persist.
- Approval requires an already observed account, independent verification checkbox
  and a self-reported actor name. This is an audit note, not authenticated identity.
  Existing approvals retain a legacy label; new approvals record name and time.
  An approval adds a baseline and never rewrites past reports or approves payment.
- Fake mode accepts exact checked-in sample fixtures only and visibly identifies
  itself. Unrecognised uploads fail closed to REVIEW; there is no fabricated parser.
- The later database instruction selects Supabase/Postgres for application
  persistence. The connected account has no Preflight project; use the official
  local Supabase database image by default rather than changing unrelated hosted
  apps. Hosted Supabase uses an explicit TLS connection string, server-side only.
  SQLite remains an explicit offline test/evaluation adapter, never an automatic
  fallback after a PostgreSQL error. Money remains text plus Decimal in both.
- Supabase tables live in a private `preflight` schema, have RLS enabled, and grant
  no anonymous/browser access. The local backend connects as the schema owner;
  it has no authenticated end-user boundary. Migration/seed are explicit Compose
  tasks. Approvals and reports persist in Supabase alongside invoice history.
- Evaluation uses twenty equal seeded strata, 24 cases each (480 total). Every
  comparison runs the real pipeline against fresh in-memory SQLite, fixed time,
  trusted synthetic history and FakeExtractor. Seven ablations remove one check
  each; a naive baseline retains arithmetic and identifiers. No check is disabled
  by web inputs. Ground-truth labels exist only in evaluation code.
- Non-PASS means positive triage. Legitimate reviews count as friction, including
  prudent missing-data reviews. Each attack's precision/FPR reuses the same
  complete legitimate pool; rows cannot be summed. Confidence intervals are
  Wilson 95% using Decimal; correlated templates make them descriptive only.
- Bank attacks deliberately include missing bank observations and wrongly cited
  superseded accounts. Wrongly cited coherent historical quotes test amount
  semantic misses. Preserve these misses in measured output rather than tuning
  labels to inflate recall. This corpus is not production-prevalence evidence.
- Fixed CI limits are initial measured critical recall minus 5 percentage points
  and clean FPR plus 2 points. Only an explicit calibration flag can rewrite them;
  CI never recalibrates. No held-out or real-world accuracy claim is made.
- Live smoke tests use five synthetic invoices and explicit provider configuration,
  report field accuracy, terminal schema failures, provider failures and invalid
  citations. They never run in CI or transmit user uploads automatically.

- Real-provider testing exposed unbounded completion generation and local schema
  visibility differences. Provider requests now include a 2,048-token output cap
  and the trusted JSON schema in user-message context outside the untrusted
  document block. The system prompt remains constant and contains no documents.

## Native Android delivery
- The user's Android request extends the previous M5 boundary and authorizes
  adapting the starter into a native Kotlin Android application. Retain its
  existing Gradle tooling and add focused domain, data and presentation packages.
- Native Material controls and Android's Storage Access Framework handle file
  selection; no WebView or broad storage permission is needed. White surfaces,
  indigo #4145b8, ink #17223b, muted #57627a and ground #f4f6fb carry the existing
  identity into a compact, left-aligned mobile workbench. Verdicts use text/icons;
  missing observations and exact bank approval details remain prominent.
- The Python backend remains the sole verdict authority and connects to Supabase.
  A versioned JSON interface reuses the existing ingestion, pipeline, ledger and
  signed CSRF boundary. No Supabase/database/model secret is bundled in the APK.
- For local use, adb reverse maps device localhost:8000 to the existing loopback
  backend. The app uses that address by default; cleartext is limited to loopback.
  HTTPS server configuration is supported without embedded credentials. No cloud
  deployment, multi-user authentication or offline verdict fabrication is added.
- Six bundled synthetic samples exercise the actual API, not canned client
  verdicts. Fake/live extraction is labelled. Network and extraction failures
  remain explicit. Selected content is bounded to 10 MiB and never logged.
