# Rocket.Chat

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Full-featured team chat — channels, DMs, threads, apps/bots, webhooks. The heaviest of this stack's chat playground trio (alongside Mattermost and Zulip): needs MongoDB running as a **replica set**, not a single instance, plus **NATS** as its default inter-instance message transporter even for one instance.

## Setup

```bash
cp services/rocketchat/.env.example services/rocketchat/.env
mkdir -p service_data/data/rocketchat/uploads
uv run homeserver.py dev up rocketchat
```

Open `https://rocketchat.<domain>/` (or `http://<host>:8142` in dev) — first-run setup wizard creates the admin account.

## Architecture

Five containers:

- **`mongodb-fix-permission`** (one-shot) — chowns the data volume to the image's own uid before MongoDB will start.
- **`mongodb`** — runs with `--replSet rs0` from the start; Rocket.Chat requires a replica set (not a plain standalone instance) because it tails MongoDB's oplog for real-time updates, via `MONGO_OPLOG_URL`.
- **`mongodb-init`** (one-shot) — runs `rs.initiate(...)` once. Idempotent — errors harmlessly on an already-initiated set, same pattern as this stack's `temporal-create-namespace`.
- **`nats`** — Rocket.Chat's default `TRANSPORTER` is `monolith+nats://`, so this is required even for a single Rocket.Chat instance, not just multi-instance deployments.
- **`rocketchat`** — the app itself.

**Two named volumes, not one** — MongoDB's official image declares `VOLUME` at both `/data/db` *and* `/data/configdb`; mounting only the first leaks an anonymous volume for the second on every container recreation (confirmed via `docker inspect`, same class of bug this stack's `homeserver-postgres` skill warns about for mismatched Postgres `VOLUME` paths). Both are named volumes here (`rocketchat-mongodb`, `rocketchat-mongodb-configdb`).

File uploads (`/app/uploads`, also a declared `VOLUME` on the Rocket.Chat image itself) are bind-mounted under `DATA_ROOT/uploads` instead, following this stack's normal app-data convention.

## Notes

- **Resource usage**: part of a "try it and see" playground — bring it up when you want it, down when you don't (`uv run homeserver.py dev down rocketchat`) rather than leaving 5 containers running idle. `down` snapshots both named MongoDB volumes automatically first.
- **Two real crashes hit and fixed during setup, both from live usage, not theoretical**: (1) with no `MAIL_URL` configured, an unhandled promise rejection from the missing-mail-config error trips Node's `EXIT_UNHANDLEDPROMISEREJECTION` policy and kills the process outright — fixed by routing `MAIL_URL=smtp://mailpit:1025` through the shared [Mailpit](mailpit.md) catcher, same pattern as Airflow. (2) the initial `1024M` memory cap was too tight — hit a real `FATAL ERROR: Reached heap limit ... JavaScript heap out of memory` crash just from loading the app's own home page; raised to `2048M` (observed ~630MB steady-state afterward, so this has real headroom, not just barely enough).
- **Rocket.Chat's mandatory (6.x+) setup wizard silently registers a "Cloud" workspace and can send real external email from Rocket.Chat's own SaaS infrastructure** (`cloud@rocket.chat`) to whatever admin address is entered during setup — this is separate from, and unrelated to, this stack's local `MAIL_URL`/Mailpit config; it's Rocket.Chat's own hosted service, not anything routed through the container. Confirmed via a direct query against the running instance:
  ```bash
  docker exec rocketchat-mongodb mongosh --quiet --eval '
    db = db.getSiblingDB("rocketchat");
    printjson(db.rocketchat_settings.findOne({_id: "Register_Server"}));
    printjson(db.rocketchat_settings.findOne({_id: "Cloud_Workspace_Id"}));
  '
  ```
  showed `Register_Server: true` and a real populated `Cloud_Workspace_Id`/`Client_Id`/`Client_Secret` — set by the setup wizard, not anything in this stack's own config. There's no documented public REST API to disconnect an already-registered workspace (only `POST /api/v1/cloud.manualRegister` to register one), so fixing an already-registered instance requires resetting it directly in MongoDB:
  ```bash
  docker exec rocketchat-mongodb mongosh --quiet --eval '
    db = db.getSiblingDB("rocketchat");
    db.rocketchat_settings.updateOne({_id: "Register_Server"}, {$set: {value: false}});
    db.rocketchat_settings.updateMany({_id: {$regex: "^Cloud_Workspace_"}}, {$set: {value: ""}});
  '
  docker restart rocketchat
  ```
  Prevented on any *future* fresh install by `OVERWRITE_SETTING_Show_Setup_Wizard: completed` in `compose.yml`, which skips the wizard (and its cloud-registration step) entirely — the admin account then needs to be created via `INITIAL_USER`/`ADMIN_*` in `.env.example`'s "Remaining Rocket.Chat env vars" block instead of the browser wizard.
- **No auth on `nats`'s monitoring port** — internal-only (`expose`, not `ports`), never reachable from outside the `homeserver` network, so this doesn't matter in practice.
- Prometheus exporters for MongoDB/NATS metrics exist in Rocket.Chat's own official compose reference but were deliberately left out here — this is a playground instance, not a production deployment needing metrics scraping.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
