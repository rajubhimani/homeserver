# definitions.py runs from a bind mount — service_data/data/dagster/user-code/
# at runtime (compose.yml), your live, freely-editable copy — never from
# what's COPY'd into this image (see docs/services/dagster/dagster.md's
# "Where your pipeline code actually lives"). Dagster has no generic
# pre-built "just runs" webserver/daemon the way Airflow or Temporal's
# server do — a code location IS your pipeline code by definition.
#
# definitions.py IS still baked in here too, but to /template, not
# /opt/dagster/app — purely as a seed for the entrypoint below to copy in
# the first time the bind mount shows up empty (fresh clone, restored
# backup, etc.). A plain `COPY definitions.py /opt/dagster/app/` wouldn't
# survive that: the bind mount replaces that directory's contents at
# container start regardless of what the image put there, so seeding has
# to happen at runtime, from a path the mount doesn't touch.
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
COPY definitions.py /template/
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /opt/dagster/app

EXPOSE 4000

# Self-seeding: an empty bind mount (fresh clone, restored backup — nothing
# ever ran the one-time seed) means no definitions.py, so the container
# would otherwise just fail to import a code location every time it's
# started. Only fires when definitions.py is actually missing — once real
# code lands there (from this seed or your own edits), it's left alone on
# every future restart, same "edit freely, never overwritten" guarantee as
# before.
CMD ["/bin/sh", "-c", "[ -f definitions.py ] || cp /template/definitions.py .; exec dagster api grpc -h 0.0.0.0 -p 4000 -f definitions.py"]
