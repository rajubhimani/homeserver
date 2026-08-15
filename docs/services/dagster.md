# Dagster

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Data orchestrator built around software-defined assets — track lineage, materialize pipelines, and observe data quality.
**Port:** `8139` (host) → `3000` (container, `dagster-webserver`) | **Data:** DB in a named volume; no `DATA_ROOT`-scoped app data | **Requires:** Postgres

## Setup

```bash
cp services/dagster/.env.example services/dagster/.env
# set DAGSTER_POSTGRES_PASSWORD
mkdir -p service_data/data/dagster/user-code
cp services/dagster/user-code/definitions.py service_data/data/dagster/user-code/   # optional — the starter examples below
uv run homeserver.py dev up dagster
```

Open `https://dagster.<domain>/` (or `http://<host>:8139` in dev) — no login/setup wizard, the UI is open to anyone who can reach it (see Notes).

## Architecture — no official pre-built webserver/daemon image, unlike Airflow or Temporal

Dagster's self-hosted webserver+daemon aren't published as ready-to-run images — every other service in this stack runs from a published image with only config layered on top; Dagster's own [official Docker example](https://docs.dagster.io/deployment/oss/deployment-options/docker) builds them from a small Dockerfile instead (`pip install dagster dagster-webserver dagster-postgres dagster-docker` on a slim Python base). This deployment does the same shape on `python:3.14-slim`, but with dependencies declared in `pyproject.toml` and installed via `uv sync --locked` against a committed `uv.lock` instead of a bare `pip install` — `services/dagster/webserver-daemon/Dockerfile`, shared by both `dagster-webserver` and `dagster-daemon` (same package set, different entrypoint command).

**`dagster-user-code` is the reason this can't be a plain image at all** — it's the gRPC server exposing your actual pipeline code, and "your actual pipeline code" doesn't exist as a generic Docker Hub image by definition. See "Where your pipeline code actually lives" below for where `definitions.py` really is and why.

5 containers total: `dagster-db`, `dagster-user-code`, `dagster-webserver`, `dagster-daemon` (plus two named volumes: Postgres data and `io_manager_storage`, the default filesystem I/O manager's shared scratch space between the run-launcher container and whatever step container reads its output).

## Where your pipeline code actually lives

`services/dagster/user-code/definitions.py` is a **git-tracked template**, not what actually runs — `user-code/Dockerfile` only installs dependencies now, it doesn't `COPY` the file in. The container reads `definitions.py` from a bind mount: `service_data/data/dagster/user-code/` (gitignored, your live copy). The Setup step above seeds it once from the template; after that the two are independent — edit freely in `service_data/`, it never touches git, and a `git pull` on this repo never overwrites your own pipeline. Same relationship as `.env.example`/`.env`, just for a whole file instead of a few variables.

Changing `definitions.py` only needs a restart, not a rebuild:

```bash
docker restart dagster-user-code
```

(Dagster's docker-compose deployment doesn't auto-reload on file change — restarting is the documented way to pick up code changes; see [dagster-io/dagster#30824](https://github.com/dagster-io/dagster/issues/30824).)

**Every run and step container launched by `DockerRunLauncher`/`docker_executor` also needs this same mount** — they run the identical `homeserver/dagster-user-code` image, and since that image no longer bakes in `definitions.py`, a run/step container can't import the code it's supposed to execute without it. That's why the bind mount appears **three places**, all pointing at the same host path: `dagster-user-code`'s own `compose.yml` volume (uses `${DATA_ROOT}`), plus `dagster.yaml`'s `run_launcher.container_kwargs.volumes` and `definitions.py`'s own `docker_executor` `container_kwargs.volumes` (both hardcoded to the absolute host path, since `dagster.yaml` is baked into the image at build time — not compose-interpolated, so `${DATA_ROOT}` doesn't work there). Update all three if `service_data/` ever moves.

## Every run — and every step — launches as its own container, by default

This isn't an optional executor choice bolted on afterward — it's Dagster's own official `docker-compose` example's default configuration, carried over here: `dagster.yaml`'s `run_launcher` is `DockerRunLauncher` (every **run** gets its own container, via `dagster-webserver`/`dagster-daemon`'s mounted `${DOCKER_SOCKET}`), and `definitions.py`'s `docker_executor` additionally runs every **step within** a run as its own container. Both have `container_kwargs`/config caps (`mem_limit: 512m`, `nano_cpus: 1_000_000_000` — 1 CPU) so a run's actual resource footprint is bounded and explicit, the same pattern as Airflow's `DockerOperator` and Temporal's worker (see their own docs). Raise `webserver-daemon/dagster.yaml`'s copy if a *run launch* needs more (rebuild `dagster-webserver`+`dagster-daemon`, since that file is baked into their shared image); raise `definitions.py`'s copy in `service_data/data/dagster/user-code/` if a *step* needs more (just restart `dagster-user-code`, no rebuild — see "Where your pipeline code actually lives" above).

## Try the starter examples

Open the UI's **Assets** tab — you'll see `hello_homeserver` (simplest possible asset), a `raw_data` → `cleaned_data` → `report` chain plus `report_freshness_check` and `report_notification` (Declarative Automation — see below), `daily_sales` (partitioned — see below), `source_system_summary` (uses a Resource — see below), `orders_raw`/`orders_staged`/`orders_final` (one `@multi_asset` function producing all three — see below), and `customer_orders` (description/owners/kinds/column-schema metadata — see below). There's also a non-asset job, `ops_pipeline_job`, under the **Jobs** tab. Easiest way to run anything is the UI (select assets → **Materialize selected**, or a job → **Launchpad** → **Launch Run**) — each materialization/run launches as its own container per the section above, watch it happen with `docker ps` in another terminal while it runs.

From the CLI, `dagster asset materialize -f definitions.py` (the form Dagster's own docs lead with) only works run *locally against a file*, which doesn't apply here (nothing under `/opt/dagster/app` on `dagster-webserver` — `dagster-user-code` is the only container with `definitions.py` mounted, and it has no Docker socket to launch anything with). Target the already-deployed workspace over GraphQL instead — the same thing the UI's Materialize button does internally:

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "report_job"},
    "mode": "default"
  }
}'
```

The `raw_data`/`cleaned_data`/`report` chain is Dagster's actual differentiator, worth looking at closely: `cleaned_data`'s function signature is `def cleaned_data(raw_data: list[dict])` — that parameter name **is** the dependency declaration. Dagster inspects it and wires the lineage edge automatically; there's no `>>` operator or explicit DAG object anywhere, unlike the equivalent Airflow example (`example_etl_pipeline` in `docs/services/airflow.md`) which chains tasks explicitly. Open `report` in the UI's asset graph to see the inferred lineage rendered.

`report_freshness_check` is an **Asset Check** — Dagster's built-in data-quality concept (a pass/fail validation attached to a specific asset, shown right on that asset's page). Neither Airflow nor Temporal have a native equivalent; you'd hand-roll the same idea as a plain extra task.

`report_job` + `report_daily_schedule` show the scheduling side — toggle the schedule on from the **Schedules** tab (need `dagster-daemon` running, which it is) to have it run on its own at 6am daily instead of only on manual materialization.

**`report_notification`** shows a third scheduling paradigm: **Declarative Automation**, alongside the explicit Schedule above and the explicit Sensor below. Instead of either, it declares `automation_condition=AutomationCondition.eager()` — "materialize me whenever `report` updates" — and `dagster-daemon`'s built-in `default_automation_condition_sensor` handles the rest, no schedule or sensor function of your own. That sensor is off by default like any other sensor; turn it on from the **Sensors** tab (or the mutation below), then materialize `report_job` and watch `report_notification` appear on its own shortly after — verified it auto-materialized ~28s after `report`'s own materialization, with no manual trigger:

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -t 'mutation { startSensor(sensorSelector: {repositoryLocationName: "user_code", repositoryName: "__repository__", sensorName: "default_automation_condition_sensor"}) { ... on Sensor { sensorState { status } } } }'
```

**`daily_sales`** is Dagster's actual answer to "backdated ingestion from a source system" — a `DailyPartitionsDefinition`-partitioned asset. Each calendar day is an independent partition; materializing an old one *is* the backfill, not a separate concept layered on top (contrast with Airflow's `example_backfill.py`, which re-runs the whole DAG per missed day — see `docs/12-orchestration.md` for the real distinction). From the UI: open `daily_sales` → **Partitions** tab → pick a date (or a range) → **Materialize**. Via GraphQL, tag the run with the partition:

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["daily_sales"]}]},
    "mode": "default",
    "executionMetadata": {"tags": [{"key": "dagster/partition", "value": "2026-08-03"}]}
  }
}'
```

**`marker_file_sensor`** is Dagster's parallel to Airflow's Sensor — reacts to an external signal instead of a fixed schedule, same self-contained marker-file pattern as `example_sensor.py`. Turn it on from the **Sensors** tab (sensors default to off), then from *inside the `dagster-user-code` container specifically* — that's where sensor code actually executes, not `dagster-daemon` (bit this exact mismatch during development):

```bash
docker exec dagster-user-code touch /tmp/io_manager_storage/.dagster_sensor_trigger
```

**`source_system_summary`** uses a **Resource** (`SourceSystemResource`) — how an asset gets a configurable connection to something external (an API base URL, credentials) instead of hardcoding a client inline. The asset's `source_system: SourceSystemResource` parameter is a giveaway that it's a dependency injection, not a lineage edge — Dagster checks the `Definitions(resources=...)` dict for a matching key first, *then* falls back to treating the parameter as another asset. Swapping environments means changing the `SourceSystemResource(...)` value passed into `Definitions`, not the asset's code.

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["source_system_summary"]}]},
    "mode": "default"
  }
}'
```

**`orders_multi_asset`** produces `orders_raw`/`orders_staged`/`orders_final` as one `@multi_asset` function instead of three separate `@asset` functions — the point is that all three share data in memory within a single materialization (one source round-trip, no IO manager hop between them the way `cleaned_data` depends on `raw_data`'s output above). A real fit for tightly-coupled steps: one API call that naturally yields a raw, a staged, and a validated view of the same batch. Verified: materializing selects all 3 asset keys in one `launchPipelineExecution` call and all 3 appear as separate nodes in the asset graph.

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["orders_raw"]}, {"path": ["orders_staged"]}, {"path": ["orders_final"]}]},
    "mode": "default"
  }
}'
```

**`customer_orders`** is the "catalog" side of Dagster, none of the other assets above use any of it: `description`/`owners`/`kinds` set on the asset definition itself (fixed, shown on every run), plus per-materialization `metadata` computed fresh each time — a row count, a markdown preview table, and a real column-by-column schema via `TableSchema`/`TableColumn` that renders as an actual table on the asset's own UI page, not just prose. This is the difference between an asset graph and something that actually functions as documentation. Verified via GraphQL after materializing: `description`/`kinds: ["postgres"]`/`owners: [{"team": "data-eng"}]` all present on the asset node, and the materialization's `metadataEntries` show `row_count: 3`, the rendered markdown preview, and all 4 columns (`order_id`/`customer_email`/`amount`/`status`) with their types and descriptions intact.

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["customer_orders"]}]},
    "mode": "default"
  }
}'
```

**`ops_pipeline_job`** (`extract_numbers` → `total_numbers` → `print_total`) is the classic `@op`/`@job` style, included deliberately next to the asset examples so the two are easy to compare — same 3-step shape as `raw_data`/`cleaned_data`/`report`, but wired by explicit function calls (`print_total(total_numbers(extract_numbers()))`) instead of Dagster inferring an edge from a parameter name. Reach for this when a pipeline genuinely isn't shaped around producing/tracking data, or you're integrating code that's already op-shaped — see `docs/12-orchestration.md` for when ops fit better than assets.

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "ops_pipeline_job"},
    "mode": "default"
  }
}'
```

Dagster 1.13 also added partitioned Asset Checks (a check scoped to one partition instead of the whole asset), deliberately **not** included here — it requires `partitions_def` on an `AssetCheckSpec`, which Dagster itself flags with a `PreviewWarning` ("not considered ready for production use"), the same preview-status concern as the newer virtual-assets feature. Worth knowing it exists once it's stable; not included as a starter example while it isn't.

`report_job` is also the target of the cross-service capstone example: Temporal's `MaterializeDagsterAssetWorkflow` launches it via this same GraphQL API and durably waits for it, triggered on a schedule by Airflow's `example_cross_service_pipeline` DAG — **Airflow schedules, Temporal durably orchestrates, Dagster materializes assets with lineage**. See `docs/services/temporal.md` for the workflow side; verified working end to end.

## Resource caps on the platform's own containers

Separately from the per-run/per-step caps above, the 4 platform containers themselves have `deploy.resources.limits.memory` caps: `dagster-db` 512M, `dagster-user-code` 256M (just serves gRPC, lightweight), `dagster-webserver` 512M, `dagster-daemon` 384M — conservative starting points, same reasoning as Temporal's (see `docs/services/temporal.md`'s "Resource caps" section).

## Notes

- **No built-in auth on the UI** — same situation as Temporal (see `docs/services/temporal.md`'s Notes): anyone who can reach `dagster.<domain>` can see and operate on every pipeline. RBAC/SSO is a Dagster+ (paid) feature, not available in open-source Dagster. Fine for a single-user homelab behind Cloudflare Tunnel; put it behind Authentik's forward-auth if this ever needs to be shared.
- `docker_executor`/`DockerRunLauncher` (the container-per-run/per-step mechanism everything here relies on for resource limits) is a **beta** API per Dagster's own docs — stable enough to build on, but Dagster reserves the right to make breaking changes in a minor version bump, unlike the fully-stable core APIs (`@asset`, `Definitions`, etc.). Worth knowing before pinning a much newer Dagster version later without re-checking this specifically.
- Elasticsearch/advanced search isn't deployed — Postgres-backed run/schedule/event-log storage covers normal usage fine.
- `DAGSTER_CURRENT_IMAGE` on `dagster-user-code` must match that service's own `image:` tag in `compose.yml` — it's how the run launcher knows which image to use when it launches a new run container. If you ever rename the image tag, update both places together.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
