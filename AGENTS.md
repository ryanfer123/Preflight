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
Tests use FakeExtractor when extraction is introduced in M3.

## Milestones
M0 tooling/docs; M1 models/identifiers; M2 checks/ledger/policy;
M3 extraction; M4 web; M5 evaluation/Docker/docs.
Keep make check green at each milestone and commit with a conventional message.
Current authorized delivery stops after M3. Web UI and evaluation remain M4-M5.
