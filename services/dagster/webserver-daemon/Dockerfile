# Shared image for both dagster-webserver and dagster-daemon — same package
# set for both, per Dagster's own official docker-compose example
# (dagster-io/dagster/examples/deploy_docker/Dockerfile_dagster). Neither
# needs your actual pipeline code — that lives only in ../user-code/.
#
# Dependencies come from pyproject.toml/uv.lock (uv lock), not a bare pip
# install — `uv sync --locked` fails the build outright if uv.lock is out of
# date instead of silently re-resolving, so what actually gets installed
# always matches what's committed. Multi-stage so the final image only
# carries the resulting .venv, not uv itself or its build/download cache.
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

ENV DAGSTER_HOME=/opt/dagster/dagster_home/
RUN mkdir -p $DAGSTER_HOME

COPY dagster.yaml workspace.yaml $DAGSTER_HOME

WORKDIR $DAGSTER_HOME
