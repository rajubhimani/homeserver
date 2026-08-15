# Temporal

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Durable execution engine for reliable distributed workflows — automatic retries, state persistence, and long-running processes that survive crashes.
**Port:** `8138` (host) → `8080` (container, `temporal-ui`) | **Data:** DB in a named volume; no `DATA_ROOT`-scoped app data | **Requires:** Postgres

## Setup

```bash
cp services/temporal/.env.example services/temporal/.env
# set POSTGRES_PASSWORD
mkdir -p service_data/data/temporal/worker
cp services/temporal/worker/*.py service_data/data/temporal/worker/   # optional — the starter workflows below
uv run homeserver.py dev up temporal
```

Open `https://temporal.<domain>/` (or `http://<host>:8138` in dev) — no login/setup wizard, the UI is open to anyone who can reach it (see Notes).

## Architecture — 5 containers, only 2 come from Temporal's own official compose set

- `temporal-db` — Postgres, `DB=postgres12` driver (works for any Postgres 12+, not a version pin — this repo uses `postgres:18.4-alpine` like every other service here, not the `postgres:16` the official `.env` happens to pin)
- `temporal` — `temporalio/auto-setup` image: provisions the schema on first start, then runs the actual server (frontend/history/matching/internal-worker services bundled in one process)
- `temporal-admin-tools` — the `tctl`/`temporal` CLI, for ad-hoc admin/debug commands (`docker exec -it temporal-admin-tools temporal ...`)
- `temporal-ui` — the web UI
- `temporal-worker` — **not part of Temporal's own official compose set.** See below.

## `temporal-worker` — a placeholder, not an official Temporal component

Unlike Airflow or Dagster, Temporal doesn't execute your workflow logic itself — a **Worker** is just a regular process (any language, official SDKs exist for Go/Java/Python/TypeScript/.NET/PHP/Ruby) that connects out to the Temporal frontend (`temporal:7233`) and runs whatever Workflow/Activity code you give it. There's no generic "Temporal worker" image to pull, because a worker with no code is meaningless — it's exactly as service-specific as Dagster's user-code container, and for the same reason gets the same one exception to this repo's image-only convention: `services/temporal/worker/Dockerfile` (`python:3.13-slim` + `pip install temporalio docker`) installs dependencies only.

## Where your workflow code actually lives

`services/temporal/worker/*.py` is a **git-tracked template**, not what actually runs — the Dockerfile doesn't `COPY` them in. The container reads them from a bind mount: `service_data/data/temporal/worker/` (gitignored, your live copy). The Setup step above seeds it once from the template; after that the two are independent — edit freely in `service_data/`, it never touches git, and a `git pull` on this repo never overwrites your own workflow code. Same relationship as `.env.example`/`.env`, just for a whole directory instead of a few variables.

Changing the code only needs a restart, not a rebuild:

```bash
docker restart temporal-worker
```

`worker/` ships five real, working workflows instead of a truly empty scaffold — each one demonstrates a different reason to reach for Temporal specifically, and each is runnable from `temporal-admin-tools` right now:

**`RunContainerWorkflow`** — resource-bounded execution. The worker has `${DOCKER_SOCKET}` mounted; its Activity calls the Docker SDK with explicit `mem_limit`/`cpu_count`, so a step's actual container never has an unbounded footprint on the host — the same pattern as Airflow's `DockerOperator`.

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver \
  --type RunContainerWorkflow \
  --input '{"image": "alpine:3.21", "command": ["echo", "hello"], "mem_limit": "128m", "cpu_count": 1}'
```

**`RetryableActivityWorkflow`** — durability. `flaky_activity` fails on its first two calls and succeeds on the third; the Workflow code has zero retry logic written — Temporal's `RetryPolicy` handles it. Watch it retry live: start it, then open the workflow in the UI and look at its Event History (`ActivityTaskStarted`/`ActivityTaskFailed` pairs before the final success).

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver \
  --type RetryableActivityWorkflow \
  --input '"demo-1"'
```

**`ApprovalWorkflow`** — durable state across arbitrarily long waits, resumed by an external Signal, inspectable at any time via a Query (Signals push data *in*; Queries read state back *out* without affecting execution — the two are normally taught as a pair). Start it (it'll sit paused), check on it, then approve it whenever:

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver --type ApprovalWorkflow --workflow-id approval-demo-1
docker exec -it temporal-admin-tools temporal workflow query --address temporal:7233 \
  --workflow-id approval-demo-1 --type status        # -> "pending"
docker exec -it temporal-admin-tools temporal workflow signal --address temporal:7233 \
  --workflow-id approval-demo-1 --name approve
docker exec -it temporal-admin-tools temporal workflow query --address temporal:7233 \
  --workflow-id approval-demo-1 --type status        # -> "approved"
```

**`OrderFulfillmentSagaWorkflow`** — the Saga pattern, Temporal's actual flagship real-world use case: this exact shape (a distributed transaction across services, with compensation if a later step fails) is how Uber dispatches rides, Netflix handles billing retries, and Amazon does multi-warehouse fulfillment, at production scale. Reserve inventory → charge payment → create shipment, all plain sequential code — no separate saga-definition DSL, no hand-tracking of which steps already committed. `amount > 1000` simulates a declined payment so both outcomes are real:

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver --type OrderFulfillmentSagaWorkflow --workflow-id saga-1 \
  --input '{"order_id": "ord-1", "amount": 50}'      # succeeds
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver --type OrderFulfillmentSagaWorkflow --workflow-id saga-2 \
  --input '{"order_id": "ord-2", "amount": 5000}'    # declined -> compensates (releases inventory)
```

A real bug this caught during development, worth knowing about if you write your own compensation logic: the plain `raise RuntimeError(...)` a first version of `charge_payment_activity` used got retried by Temporal's *default* policy — indefinitely, since a declined payment looks identical to a transient fault unless you say otherwise. The workflow never reached its `except` block to compensate; it just sat retrying forever. Fix: raise `temporalio.exceptions.ApplicationError(..., non_retryable=True)` for genuine business-decision failures.

**`MaterializeDagsterAssetWorkflow`** — cross-service architecture. Calls Dagster's GraphQL API (`http://dagster-webserver:3000/graphql`) to launch a job, then polls until it finishes — durably: if this worker crashes mid-poll, Temporal replays and keeps waiting, no state lost, something a plain polling script can't do. `example_cross_service_pipeline` in `docs/services/airflow.md`'s Airflow DAGs starts this on a schedule — the capstone example: **Airflow schedules, Temporal durably orchestrates, Dagster materializes assets with lineage**, each tool doing the one thing it's actually best at. Verified working end to end (`docker exec airflow-scheduler airflow dags trigger example_cross_service_pipeline`, run completed with state `success`).

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver --type MaterializeDagsterAssetWorkflow --input '"report_job"'
```

Keep the `activities.py`/`workflows.py` split if an activity needs a non-deterministic import (`docker`, `requests`, anything with I/O) — Temporal's sandbox rejects those inside a workflow's own module even when only the activity uses them (bit this exact setup during development; see the comment at the top of `activities.py`).

**Native scheduling**, independent of Airflow: any workflow can run on a cron without a separate scheduler service. Modern Temporal uses first-class Schedule objects (`temporal schedule create`), not the deprecated `cron_schedule` workflow-start parameter:

```bash
docker exec -it temporal-admin-tools temporal schedule create --address temporal:7233 \
  --schedule-id daily-retry-demo --cron "0 6 * * *" \
  --workflow-id daily-run --task-queue homeserver --type RetryableActivityWorkflow --input '"scheduled"'
```

## Resource caps — deliberately conservative starting points

Every container here has a `deploy.resources.limits.memory` cap (`temporal-db` 512M, `temporal` 768M, `temporal-ui` 256M, `temporal-admin-tools` 128M, `temporal-worker` 256M) — small enough that this doesn't crowd out the rest of the stack on a shared host, at the cost of being tight under real production workflow volume. If `temporal` (the server) gets OOM-killed under load (`docker inspect temporal --format '{{.State.OOMKilled}}'`), raise its cap first — it's the one actually doing frontend/history/matching work; the others are much less likely to need it.

## Notes

- **No built-in auth on the UI or the `temporal-worker`/`temporal-admin-tools` connection to the server** — anyone who can reach `temporal.<domain>` can see and operate on every workflow. Fine for a single-user homelab behind Cloudflare Tunnel; if this ever needs to be shared, put it behind Authentik (this stack already has it) rather than relying on Temporal's own (enterprise-only) auth.
- `DYNAMIC_CONFIG_FILE_PATH` points at `dynamicconfig/development-sql.yaml` — Temporal's own official "development" config (`system.forceSearchAttributesCacheRefreshOnRead: true`), fine for a homelab's workflow volume; their docs explicitly say not to use it in a real production deployment (immediate-consistency search-attribute reads have a real perf cost at scale).
- Elasticsearch is **not** deployed — the official compose set has an Elasticsearch variant for advanced visibility queries; this uses the plain SQL (Postgres) visibility store instead, which covers normal workflow search/filtering fine and is one less container to run.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
