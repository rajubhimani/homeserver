# Dependencies only — the actual worker.py/activities.py/workflows.py are
# bind-mounted from service_data/data/temporal/worker/ at runtime (compose.yml),
# not copied in here. This file is the only git-tracked, image-baked part
# (see docs/services/temporal.md's "Where your workflow code actually lives"
# section for why) — changing what packages the worker needs still means
# editing this and rebuilding; changing the workflow/activity code itself
# only needs a container restart.
FROM python:3.13-slim

WORKDIR /app
RUN pip install --no-cache-dir temporalio==1.31.0 docker==7.2.0

CMD ["python", "worker.py"]
