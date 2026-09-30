# experiments/shared-postgres

Question being tested: can `firefly`, `forgejo`, and `guacamole` — all on
`postgres:18.4-alpine` in production — share **one** Postgres instance
(separate database per app) instead of each running its own dedicated
container? This repo's established convention (see the `homeserver-postgres`
skill) is one dedicated Postgres per service; this experiment checks
whether that convention is actually necessary or just historical.

**Not part of the real stack.** Not managed by `homeserver.py`, not on the
`SERVICES_*` tiers, not on the shared `homeserver` Docker network. Runs
fully isolated — own network, own container names (`*-test`), own ports
(19002/19102/19107), fresh named volumes. Safe to run alongside the real
`firefly`/`forgejo`/`guacamole` containers with zero interaction.

**Fresh/empty databases, not your real data.** Each app will show its
first-run setup wizard. This tests the architecture (does it start cleanly,
how does resource usage look, does anything about one app's schema collide
with another's), not a data migration — see the top-level conversation if a
real migration is ever wanted later; that's a much higher-risk, separate
exercise (full backups, one service at a time, on the real branch).

## Run it

```bash
cd experiments/shared-postgres
cp .env.example .env   # already done if you're reading this after setup — has real generated values
docker compose up -d
```

Then:
- Firefly: http://localhost:19102/ (first-run setup wizard)
- Forgejo: http://localhost:19002/ (first-run setup wizard)
- Guacamole: http://localhost:19107/ (login `guacadmin` / `guacadmin` — schema pre-loads this like production does)

Check the shared instance directly:

```bash
docker exec -it postgres-shared-test psql -U postgres -l   # lists all 3 databases
docker stats postgres-shared-test                           # resource usage of ONE instance serving all 3
```

## What to look for

- Do all 3 apps actually come up healthy against the shared instance?
- `postgres-shared-test`'s memory/CPU under all 3 apps at once, vs. what 3
  separate dedicated instances would cost combined (each currently capped
  at 384M in production — see each service's own `compose.yml`).
- Any connection-count pressure (`max_connections=60` here, vs. 20 each x 3
  = 60 total if they stayed separate — same ceiling, one pool instead of
  three, worth watching if any single app's connection pool spikes).
- Anything Guacamole-specific: its schema bootstrap is more involved than
  firefly/forgejo's (needs `guacamole/schema.sql` pre-loaded, not just an
  empty database) — confirm it doesn't collide with the other two
  databases' objects (it shouldn't; Postgres databases are fully isolated
  namespaces even within one server instance, but worth confirming
  empirically rather than assuming).

## Tear down

```bash
docker compose down -v   # -v removes the volumes too — this is throwaway data
```

Removes every container, the dedicated network, and every volume this
experiment created. Nothing under `service_data/` or the `homeserver`
network is touched.
