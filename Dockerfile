FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

FROM python:3.12-slim
RUN groupadd --gid 10001 preflight && useradd --uid 10001 --gid preflight --create-home preflight
WORKDIR /app
COPY --from=build --chown=preflight:preflight /app /app
COPY --chown=preflight:preflight data ./data
COPY --chown=preflight:preflight samples ./samples
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER preflight
EXPOSE 8000
CMD ["uvicorn", "preflight.web.app:application", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
