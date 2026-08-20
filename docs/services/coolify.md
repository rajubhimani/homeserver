# Coolify

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted PaaS — deploy and manage *other* projects/services with a Vercel/Heroku-style workflow (git push to deploy, one-click databases, etc.).
**Port:** `8132` (host) → `8080` (container); realtime websocket on `6001`/`6002` | **Data:** `service_data/data/coolify/` | **Requires:** Postgres, Redis

## Conceptual overlap worth naming

Coolify's whole purpose is deploying and managing *other* Docker projects on this machine — conceptually it overlaps with what `homeserver.py` already does by hand for this stack. It's included here anyway because it's genuinely useful for deploying separate, unrelated projects (not this repo's own services) through a proper UI/git-push workflow — not to replace `homeserver.py` for managing this stack.

## ⚠ Never use Coolify's own in-app "Upgrade" button

Coolify's dashboard shows an "Upgrade available" banner and a one-click
upgrade action once a newer release exists. **Don't click it in this
stack.** It runs `https://cdn.coollabs.io/coolify/upgrade.sh`, which:

1. Downloads a **fresh `docker-compose.yml`, `docker-compose.prod.yml`,
   and `.env.production` from Coolify's own CDN** into `/data/coolify/`
   — a completely separate file set from this repo's
   `services/coolify/compose.yml`.
2. Stops and removes `coolify`, `coolify-db`, `coolify-redis`,
   `coolify-realtime`.
3. Recreates them from that downloaded compose file, with whatever image
   versions *it* pins — not this repo's.

Running it would fork Coolify out of this stack's "one
`services/<name>/compose.yml` per service, managed via `homeserver.py`"
model: future `homeserver.py dev update coolify` runs would no longer
reflect what's actually running, and any version bumps made here (e.g.
`coolify-db`'s Postgres tag) would likely get silently overwritten.

**To upgrade Coolify in this stack instead:** bump the pinned tag in
`services/coolify/compose.yml` yourself (check
[Docker Hub](https://hub.docker.com/r/coollabsio/coolify/tags) — search
by tag *name*, e.g. `?name=.`, not by "most recently updated"; the
default recency sort buries numbered releases behind constantly-rebuilt
`edge`/`next`/sha tags and made this repo wrongly conclude for a while
that no stable tag existed at all), then
`uv run homeserver.py dev update coolify`. The banner itself may keep
appearing between bumps — that's just Coolify comparing its own
baked-in version string against the latest tagged release, harmless.

Currently pinned to `coollabsio/coolify:4.3.9` (real semver tag,
confirmed compatible — Coolify's own upgrade-path check treats
`4.3.0 → 4.3.9` as a valid forward upgrade, not a downgrade, and this
image previously ran as `edge` self-reporting version `4.3.0`).

## Setup

```bash
cp services/coolify/.env.example services/coolify/.env
# generate ALL secrets before first start (see comments in .env.example) —
# changing any of them later can break the installation
uv run homeserver.py dev up coolify
```

Open `https://coolify.<domain>/` (or `http://<host>:8132` in dev) and complete the first-run setup wizard.

## Connecting the "localhost" server — required before deploying anything

Coolify auto-registers a `localhost` server pointing at the mounted Docker socket, but — non-obviously — Coolify manages **every** server, including its own host, over **SSH**, not just the Docker socket. Without that, the server shows as unavailable in the UI, and `docker logs coolify` shows:

```text
No SSH key found for the Coolify host machine (localhost).
Please read the following documentation (point 3) to fix it: https://coolify.io/docs/knowledge-base/server/openssh/
Your localhost connection won't work until then.
```

with `App\Jobs\CoolifyTask`, `App\Actions\Proxy\StartProxy`, and `App\Jobs\CheckAndStartSentinelJob` all failing in the logs as a result. Fix, once, before first use:

**1. Enable sshd on the host** (not in any container — this is the actual machine Docker runs on):

```bash
sudo systemctl enable --now sshd
```

This opens port 22 on the host to your LAN — not the internet, since this stack has no port-forwarding, only the outbound-only `cloudflared` tunnel for HTTP(S). Acceptable for a trusted home network; scope it further with a firewall rule if you want to restrict it to just the Docker bridge subnet.

**2. Generate a dedicated keypair** for Coolify — this can be done from anywhere, no host `sudo` needed, since `service_data/data/coolify/ssh/` is already bind-mounted into the container at `/data/coolify/ssh/`:

```bash
mkdir -p service_data/data/coolify/ssh/keys
ssh-keygen -t ed25519 -a 100 \
  -f "service_data/data/coolify/ssh/keys/id.root@localhost" \
  -q -N "" -C root@coolify
```

**3. Authorize that key for root login on the host**:

```bash
sudo mkdir -p /root/.ssh
sudo sh -c 'cat "service_data/data/coolify/ssh/keys/id.root@localhost.pub" >> /root/.ssh/authorized_keys'
sudo chmod 700 /root/.ssh
sudo chmod 600 /root/.ssh/authorized_keys
```

**4. In the Coolify dashboard**: Settings → Private Keys → Add, paste the contents of `service_data/data/coolify/ssh/keys/id.root@localhost` (the private key, not `.pub`). Then Servers → `localhost` → Private Key tab, select the key you just added, and click **Validate Server & Install Docker Engine** — a green "Proxy Running" status confirms it worked.

Verify the SSH path itself works before touching the UI, if something still seems off:

```bash
docker exec coolify sh -c 'ssh -o StrictHostKeyChecking=no -i /data/coolify/ssh/keys/id.root@localhost root@host.docker.internal echo SSH_OK'
```

(`host.docker.internal` resolves via the `extra_hosts: host-gateway` entry already in `compose.yml` — this is how the container reaches back out to the real host, not `localhost` inside its own network namespace.)

## After connecting the server: run `fix-proxy-sentinel.sh`

Coolify's database hardcodes two host-networking assumptions that don't
match this stack, and — because they live in Coolify's own database, not
this repo's `compose.yml` — they come back every time that database
starts fresh (a new install, or after wiping `coolify-postgres-alpine`):

1. **`coolify-proxy` gets stuck on "starting" forever.** Once the
   `localhost` server is connected, Coolify tries to start its own
   Traefik reverse-proxy (`coolify-proxy` — separate from this stack's
   `nginx-plain`, used only for apps deployed *through* Coolify). Its
   default generated config binds host ports `80`, `443`, and `8080`
   (Traefik's dashboard). Port `8080` is already used by `landing` in
   this stack, so the proxy fails silently — `docker ps` shows no
   `coolify-proxy` container at all, and nothing useful lands in
   `docker logs coolify` about it.
2. **Sentinel never reports metrics ("Sentinel is out of sync").**
   Coolify hardcodes `http://host.docker.internal:8000` as the URL
   Sentinel pushes metrics to for the `localhost` server — its own
   standard install publishes the app on host port `8000`. This stack
   publishes `coolify` on a different host port instead (`8132` in dev,
   same in prod — see the top of this doc), so every push gets
   `connection refused`, `sentinel_updated_at` never advances, and the
   UI shows a permanent "out of sync" warning.

Neither has a config/env-var fix — both are hardcoded in Coolify's own
PHP (`bootstrap/helpers/proxy.php`'s `generateDefaultProxyConfiguration()`
and `ServerSetting::generateSentinelUrl()`). Run this once the
`localhost` server shows connected (after the SSH steps above):

```bash
sh services/coolify/fix-proxy-sentinel.sh
```

It drops Traefik's optional dashboard (not required — Coolify's own
[firewall docs](https://coolify.io/docs/knowledge-base/server/firewall)
never list port 8080, only `80`/`443` for the proxy and
`8000`/`6001`/`6002` for the dashboard/realtime/terminal) and points
Sentinel at whatever host port `coolify` is actually published on
(read live from the running container via `docker port`, so it's
correct in both dev and prod). Both applied through Coolify's own
`SaveProxyConfiguration`/`StartProxy` actions and the `ServerSetting`
model — the same code paths the UI itself uses — so they persist across
restarts. Safe to re-run any time either symptom reappears.

## Registration — a real action item, not just informational

Coolify has no env var for this — public self-registration is **on by default** and stays on until manually disabled in the UI (Settings → Configuration) after your first login. Do this immediately: anyone who finds the URL can otherwise create their own account. Everything else about Coolify's behavior is likewise UI/database-managed, not env-var-driven — there's nothing further to add to `.env` beyond the one-time bootstrap secrets.

## Architecture — 4 containers

- `coolify-db` (Postgres) — app metadata.
- `coolify-redis` — caching/queues.
- `coolify-realtime` (`coollabsio/coolify-realtime`, a maintained Soketi fork) — websocket server for live deploy logs/status in the UI. Listens on `6001` (WS + HTTP API) and `9601` (metrics/`/usage`, used for its own healthcheck — there's no dedicated `/health` path documented).
- `coolify` — the main app; needs the Docker socket mounted (`${DOCKER_SOCKET}`) since its entire job is creating/managing containers on this host for deployed projects, plus several bind-mounted subdirectories (`data`, `ssh`, `applications`, `databases`, `backups`, `services`) that Coolify itself populates.

## Notes

- `APP_ID`/`APP_KEY`/`DB_PASSWORD`/`REDIS_PASSWORD`/`PUSHER_*` are all one-time secrets — generate them once, keep them, never rotate casually (documented upstream behavior: changing them later can break the installation).
- Health endpoint: `/api/health`.
- Since Coolify mounts the Docker socket, treat it with the same trust level as `portainer`/`dockge` in this stack — anything with socket access can affect any other container on the host.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
