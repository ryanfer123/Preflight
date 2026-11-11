.PHONY: check lint typecheck test
check: lint typecheck test

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy --strict src/preflight

test:
	uv run --locked pytest
