# PostHog self-hosting — research notes (deferred)

Not implemented in this stack. Captured here so a future attempt doesn't have to re-derive this from scratch. See the corresponding entry in [`TODO.md`](../../TODO.md).

## Why it was deferred

Initial assumption (from PostHog's own high-level docs) was a normal-sized deployment: web app + plugin server + ClickHouse + Postgres + Redis + Kafka + MinIO, ~7 containers, 16GB RAM recommended. That's heavier than anything else in this stack but still plausible as "one more service."

Digging into the actual compose files changed that picture substantially:

- The real self-hosted ("hobby") deployment is defined across **`docker-compose.base.yml`** (PostHog's internal dev/monorepo compose) plus **`docker-compose.hobby.yml`** (an override layered on top) — together they bring up **30–40 containers**, not 7.
- Services involved include: full **Temporal** workflow engine (`temporal`, `temporal-admin-tools`, `temporal-ui`, `temporal-django-worker`), **Kafka + Zookeeper**, **ClickHouse**, **MinIO/SeaweedFS** object storage, half a dozen **Rust microservices** (`capture`, `replay-capture`, `property-defs-rs`, `personhog-replica`, `personhog-router`, `feature-flags`, `hypercache-server`, `cyclotron-janitor`, `cymbal`), multiple **ingestion workers** (`ingestion-general`, `ingestion-sessionreplay`, `ingestion-error-tracking`, `ingestion-logs`, `ingestion-traces`), plus `recording-api`, `browserless`, `livestream`, and PostHog's own **Caddy** reverse proxy.
- The **official install path isn't a drop-in compose file** — it's `bin/deploy-hobby`, an interactive bash script that clones PostHog's entire git repository onto the target machine, copies both compose files into place, generates secrets, and manages its own domain/TLS via Caddy. That's structurally different from every other service in this stack (a self-contained `<service>/compose.yml` managed by `homeserver.py`) — PostHog's deployment wants to own the whole machine's ingress, not slot in behind `nginx-plain`.

Given that mismatch — both the resource cost and the deployment model — this was deferred rather than hand-ported service-by-service, which would risk an incomplete or subtly broken result given how interdependent those ~40 containers are (Kafka topics, Temporal namespaces, ClickHouse schemas all wired together by the hobby compose file in ways not meant to be split apart).

## If revisiting this later

Options, roughly in order of effort:

1. **Run PostHog on its own separate host/VM** via the official `deploy-hobby` script, and only reverse-proxy to it from `nginx-plain` here (a single upstream block, same as any external service) — avoids fighting the deployment model entirely.
2. **Use PostHog Cloud** (their hosted offering) if self-hosting the analytics engine isn't actually a hard requirement — likely the pragmatic choice unless data residency/cost specifically demands self-hosting.
3. **Attempt a genuine trimmed-down self-hosted compose** — would require reading PostHog's Kafka topic wiring and Temporal namespace setup closely enough to know what's safe to cut for a single-tenant low-volume use case (e.g. dropping `browserless`, `livestream`, some ingestion variants). Nontrivial and likely to drift from upstream's tested configuration; would need re-validating after every PostHog upstream version bump.
4. **Re-check upstream** — PostHog's deployment story may simplify over time; worth a fresh look at `docker-compose.hobby.yml` and `bin/deploy-hobby` before assuming today's shape is permanent.

## What was chosen instead

Plausible (see the "batch A/B" service list this was considered alongside) covers the core self-hosted analytics need with a normal 2–3 container Postgres+ClickHouse compose that fits this stack's per-service pattern cleanly — added instead of PostHog this pass.
