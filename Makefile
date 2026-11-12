.PHONY: check lint typecheck test
check: lint typecheck test

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy --strict src/preflight

test:
	uv run --locked pytest

.PHONY: serve demo eval smoke
serve:
	uv run --locked python -m preflight.web

demo:
	uv run --locked python -m preflight.demo

eval:
	uv run --locked python -m preflight.eval --check

smoke:
	uv run --locked python scripts/live_model_smoke.py
