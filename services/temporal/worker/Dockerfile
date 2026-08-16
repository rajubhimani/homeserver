# Dependencies only — the actual worker.py/activities.py/workflows.py are
# bind-mounted from service_data/data/temporal/worker/ at runtime (compose.yml),
# not copied in here. This file is the only git-tracked, image-baked part
# (see docs/services/temporal/temporal.md's "Where your workflow code actually lives"
# section for why) — changing what packages the worker needs still means
# editing pyproject.toml, re-running `uv lock`, and rebuilding; changing the
# workflow/activity code itself only needs a container restart.
#
# `uv sync --locked` fails the build outright if uv.lock is out of date
# instead of silently re-resolving. Multi-stage so the final image only
# carries the resulting .venv, not uv itself or its build/download cache.
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# The venv can't live under /app — compose.yml bind-mounts
# DATA_ROOT/worker:/app at runtime (your live workflow code), which would
# otherwise completely shadow it (hit this exact bug: "ModuleNotFoundError:
# No module named 'temporalio'" — the venv was there at build time, just
# invisible once the bind mount replaced /app's contents at container start).
FROM python:3.14-slim
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
CMD ["python", "worker.py"]
