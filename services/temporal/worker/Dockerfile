# The actual worker.py/activities.py/workflows.py run from a bind mount —
# service_data/data/temporal/worker/ at runtime (compose.yml), your live,
# freely-editable copy — never from what's COPY'd into this image (see
# docs/services/temporal/temporal.md's "Where your workflow code actually
# lives" section for why). Changing what packages the worker needs still
# means editing pyproject.toml, re-running `uv lock`, and rebuilding;
# changing the workflow/activity code itself only needs a container restart.
#
# The .py files ARE still baked in here too, but to /template, not /app —
# purely as a seed for the entrypoint below to copy into /app the first
# time the bind mount shows up empty (fresh clone, restored backup, etc.).
# A plain `COPY *.py /app/` wouldn't survive that: the bind mount replaces
# /app's contents at container start regardless of what the image put
# there, so seeding has to happen at runtime, from a path the mount
# doesn't touch.
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
COPY *.py /template/
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# Self-seeding: an empty bind mount (fresh clone, restored backup — nothing
# ever ran the one-time seed) means no worker.py, so the container would
# otherwise just crash-loop with "can't open file 'worker.py'" forever.
# Only fires when /app is actually empty — once real code lands there
# (from this seed or your own edits), it's left alone on every future
# restart, same "edit freely, never overwritten" guarantee as before.
CMD ["/bin/sh", "-c", "[ -f worker.py ] || cp /template/*.py .; exec python worker.py"]
