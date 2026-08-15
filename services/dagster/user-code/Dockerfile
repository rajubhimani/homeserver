# Dependencies only — definitions.py is bind-mounted from
# service_data/data/dagster/user-code/ at runtime (compose.yml), not copied
# in here (see docs/services/dagster.md's "Where your pipeline code actually
# lives"). Dagster has no generic pre-built "just runs" webserver/daemon the
# way Airflow or Temporal's server do — a code location IS your pipeline
# code by definition.
#
# Dependencies come from pyproject.toml/uv.lock (uv lock) — `uv sync --locked`
# fails the build outright if uv.lock is out of date instead of silently
# re-resolving. Multi-stage so the final image only carries the resulting
# .venv, not uv itself or its build/download cache.
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

FROM python:3.14-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /opt/dagster/app

EXPOSE 4000

CMD ["dagster", "api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-f", "definitions.py"]
