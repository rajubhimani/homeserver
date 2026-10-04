# The code location image: Dagster plus this repo's pipeline code
# (definitions.py), built in. That's Dagster's documented way on Kubernetes
# and for Dagster+ code locations, and since 2026-10-04 Compose uses the same
# image, so one build runs on both. To change a pipeline: edit
# user-code/definitions.py, rebuild (homeserver.py update dagster), done.
# (Before, the code was a bind-mounted, edit-in-place copy under
# service_data/; docs/services/dagster/dagster.md, "Where your pipeline code
# lives".)
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
COPY definitions.py /opt/dagster/app/

EXPOSE 4000

CMD ["dagster", "api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-f", "definitions.py"]
