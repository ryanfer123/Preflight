# Preflight contributor instructions

## Scope and conventions
Preserve the existing Android starter. Python source lives in src/preflight.
Use Python 3.12, pydantic v2, small pure functions, complete type hints and public
API docstrings. Use Decimal for money; reject floats, NaN and infinities.
Never allow an extractor to decide a verdict. Missing observations must remain
unverifiable. Findings cite original snippets and one-based pages where known.
Treat documents, email headers and model output as untrusted input.
Never log credentials or commit local uploads, databases or environment files.
Do not add unused dependencies or unimplemented subsystem stubs.

## Checks
Run uv sync --locked --group dev, then make check.
make check runs Ruff lint/format checks, mypy --strict on src/preflight, and pytest.
Tests must be offline; the autouse socket guard prohibits connection attempts.
Use Hypothesis for identifier properties and deterministic examples for boundaries.
Tests use FakeExtractor and never connect to Supabase or a live model.
Application persistence uses Supabase Postgres in the private preflight schema.
SQLite is the explicit offline adapter; never silently fall back after DB errors.
Run make eval for fixed regression gates. Schema migrations live in supabase/migrations.

## Milestones
M0 tooling/docs; M1 models/identifiers; M2 checks/ledger/policy;
M3 extraction; M4 web; M5 evaluation/Docker/docs.
Keep make check green at each milestone and commit with a conventional message.
The current request also authorizes the native Android app and its JSON API.
Keep verdict logic on the server. Build/test Android in the existing app module.
Do not deploy to the cloud or place backend secrets in the APK.
