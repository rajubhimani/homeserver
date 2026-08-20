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

## Setup — full checklist, in order

This is the complete, verified sequence — including the fresh-install
gotchas documented in detail further down this page. Every step matters;
skipping the SSH-volume init step in particular will make the very first
boot fail (see "Persistent storage" below for why).

**1. Configure secrets:**

```bash
cp services/coolify/.env.example services/coolify/.env
# generate ALL secrets before first start (see comments in .env.example) —
# changing any of them later can break the installation
```

Optionally also fill in the commented `ROOT_USERNAME`/`ROOT_USER_EMAIL`/
`ROOT_USER_PASSWORD` block in the same file to seed your real admin
account directly (fresh install only) instead of registering through the
UI afterward.

**2. Initialize the SSH-keys volume — before the first boot:**

```bash
sh services/coolify/init-ssh-volume.sh
```

Required every time `coolify-ssh-keys` is freshly created (a genuine
first install, or after wiping it) — a brand-new Docker volume is owned
by `root:root`, and Coolify's own image can't write into it and doesn't
self-heal that itself the way official database images do. See
"Persistent storage" below for the full explanation.

**3. Start it:**

```bash
uv run homeserver.py dev up coolify
```

**4. Enable sshd on the host** (not in any container — this is the
actual machine Docker runs on; Coolify manages every server, including
its own host, over SSH, not just the Docker socket):

```bash
sudo systemctl enable --now sshd
```

This opens port 22 on the host to your LAN — not the internet, since
this stack has no port-forwarding, only the outbound-only `cloudflared`
tunnel for HTTP(S). Acceptable for a trusted home network; scope it
further with a firewall rule if you want to restrict it to just the
Docker bridge subnet.

**5. Open `https://coolify.<domain>/` (or `http://<host>:8132` in dev)**
and log in with the `ROOT_USER_*` credentials from step 1, or complete
the first-run registration if you skipped that.

**6. Go through Coolify's own onboarding wizard.** It offers to
generate an SSH key for the `localhost` server — **pick ED25519, not
RSA** (smaller, faster, and what this stack's own scripts use
elsewhere): Ed25519 is a modern elliptic-curve algorithm with better
performance and much smaller keys than RSA for equivalent security; RSA
is the older, more universally-compatible standard but needs 3072–4096
bit keys to match it. This is the real official flow — confirmed against
`app/Livewire/Boarding/Index.php`, which calls the same
`generateSSHKey()`/`PrivateKey::createAndStore()` functions either way.

**7. Copy the public key the wizard shows you, and authorize it on the
host:**

```bash
sudo mkdir -p /root/.ssh && sudo chmod 700 /root/.ssh
echo "PASTE_THE_PUBLIC_KEY_HERE" | sudo tee -a /root/.ssh/authorized_keys
sudo chmod 600 /root/.ssh/authorized_keys
```

**8. Back in the wizard, click Validate/Continue.** A green "Proxy
Running" status confirms the SSH connection worked.

Verify the SSH path itself works directly, if something still seems off:

```bash
docker exec coolify sh -c 'ssh -o StrictHostKeyChecking=no -i /var/www/html/storage/app/ssh/keys/<key-file-name> root@host.docker.internal echo SSH_OK'
```

(`host.docker.internal` resolves via the `extra_hosts: host-gateway`
entry in `compose.yml`, present on both `coolify` and `coolify-realtime`
— this is how each container reaches back out to the real host, not
`localhost` inside its own network namespace.)

**9. Once the server shows connected, run the fix script** — needed
after every fresh install, since it fixes two things that live in
Coolify's own database, not this repo's `compose.yml`:

```bash
sh services/coolify/fix-proxy-sentinel.sh
```

See "run `fix-proxy-sentinel.sh`" below for what it actually fixes.

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

## Terminal / live deploy logs — "websocket connection lost, reconnecting"

Coolify's terminal, live deploy logs, and other real-time UI features
connect over a WebSocket using config baked directly into every page
(`resources/views/layouts/base.blade.php`):

```js
wsHost: "{{ config('constants.pusher.host') }}",  // PUSHER_HOST
wsPort: "{{ getRealtime() }}",                     // PUSHER_PORT
```

By default `PUSHER_HOST` is the Docker-internal container name
`coolify-realtime` — rendered straight into the page your browser loads,
which has no way to resolve it, so every connection attempt fails
immediately.

Unlike the proxy/Sentinel issues above, this **is** fixed permanently
via `compose.yml` — Coolify already splits frontend vs. backend config
(`config/broadcasting.php` uses separate `PUSHER_BACKEND_HOST`/
`PUSHER_BACKEND_PORT` for the Laravel-to-`coolify-realtime` server-side
connection, defaulting to the same internal values). `PUSHER_HOST`/
`PUSHER_PORT` are set to `coolify.${DOMAIN}`/`443` — routed through a
`/app/` location added to `nginx-plain`'s `coolify.${DOMAIN}` vhost
(`default.conf.template`, WebSocket-upgrade headers, proxying to
`coolify-realtime:6001`) — so the browser connects back through the same
public domain everything else uses, working identically on LAN and via
`cloudflared`, instead of needing `coolify-realtime` exposed on its own
port.

**The terminal specifically needs three more fixes on top of the above**
(same symptom, different cause — it's a *separate* WebSocket process,
not the Pusher/Soketi one):

1. **A second nginx-plain route.** The terminal connects to a different
   listener inside `coolify-realtime` — port `6002` (a plain Node
   process), not `6001` (Soketi). Frontend JS default (from the compiled
   bundle, when `TERMINAL_HOST`/`PORT`/`PROTOCOL` are unset): connect to
   `wss://<current host>/terminal/ws`, auto-derived from the page's own
   URL — no env vars needed, just a `location /terminal/ws` route in
   `nginx-plain` proxying to `coolify-realtime:6002` (added alongside
   `/app/`).
2. **`extra_hosts` on `coolify-realtime`.** It SSHes into whatever
   host/IP the target server is configured with (`host.docker.internal`
   in this stack's setup) to actually spawn the shell. Only `coolify`
   itself had the `host.docker.internal:host-gateway` entry — missing it
   on `coolify-realtime` caused `Could not resolve hostname
   host.docker.internal` *inside* terminal sessions, even once the
   WebSocket connection itself was working.
3. **The SSH private key needs to be a named volume, not a
   `service_data/` bind mount.** `coolify-realtime` also needs the same
   ssh-keys directory `coolify` uses (confirmed against upstream's own
   `docker-compose.prod.yml`) to read the private key file directly. But
   OpenSSH refuses to load a key unless its file mode is exactly `0600`
   — and `service_data/` on this host sits on an NTFS drive
   (`fuseblk`/`ntfs-3g`, confirmed with `df -T`), which **cannot store
   Unix permissions or ownership at all**: `chmod`/`chown` against it
   silently succeed and do nothing, forever, no matter how many times
   you retry. So the key stayed stuck at whatever permissive mode got
   written (`0777`), and SSH rejected it every time with `Permissions
   ... are too open`. Fixed by mounting a **named volume**
   (`coolify-ssh-keys`, lives in Docker's own storage — `btrfs` on this
   host, confirmed with `df -T /var/lib/docker`) instead — same
   reasoning as this stack's database-data-as-named-volume rule, see the
   `homeserver-postgres` skill. A fresh named volume is owned by
   `root:root` by default, which the container's `www-data` (uid `9999`)
   can't write into either — fix once with:
   ```bash
   docker run --rm -v coolify_coolify-ssh-keys:/data alpine chown -R 9999:9999 /data
   ```

## Persistent storage was silently broken — fixed, but know the history

Every bind mount in `compose.yml` (`ssh`/`applications`/`databases`/
`services`/`backups`) used to point at `/data/coolify/...` inside the
container — a path this image doesn't use for anything (verified: it
exists on disk but nothing reads or writes it). The real Laravel storage
root is `/var/www/html/storage/app/...` (confirmed against upstream's
own `docker-compose.prod.yml`), and an `images` mount (avatars/project
icons) was missing entirely. Practical effect: every SSH private key,
deployed-application config, one-click database, backup, and one-click
service was **silently ephemeral** — wiped on every container
recreation, not persisted at all, for as long as this compose file
existed. All six are fixed now (five real `service_data/` bind mounts +
`ssh` as a named volume, per the terminal section above) — nothing
further to do, just worth knowing why a `coolify` container recreation
used to lose things that looked like they should have survived it.

## Registration — a real action item, not just informational

Coolify has no env var for the registration toggle itself — public self-registration is **on by default** and stays on until manually disabled in the UI (Settings → Configuration) after your first login. Do this immediately: anyone who finds the URL can otherwise create their own account.

There **is** an env-var path for the root user account itself (fresh installs only, same caveat as everywhere else on this page — skipped if a user with id 0 already exists): `ROOT_USERNAME`/`ROOT_USER_EMAIL`/`ROOT_USER_PASSWORD` in `.env.example` (commented). Login is by email, not a fixed username; password needs 8+ chars, mixed case, a number, and a symbol, and is checked against HaveIBeenPwned.

## Architecture — 6 containers, 2 of them self-managed by Coolify itself

Four are defined in `compose.yml` like any other service:

- `coolify-db` (Postgres) — app metadata.
- `coolify-redis` — caching/queues.
- `coolify-realtime` (`coollabsio/coolify-realtime`, a maintained Soketi fork) — websocket server for live deploy logs/status (port `6001`) *and* the terminal (port `6002`, a separate Node process), plus `9601` (metrics/`/usage`, used for its own healthcheck — there's no dedicated `/health` path documented).
- `coolify` — the main app; needs the Docker socket mounted (`${DOCKER_SOCKET}`) since its entire job is creating/managing containers on this host for deployed projects, plus five bind-mounted `service_data/` subdirectories and the `coolify-ssh-keys` named volume (see "Persistent storage" above) that Coolify itself populates.

The other two **aren't in `compose.yml` at all** — `coolify` creates and
manages them itself via the mounted Docker socket, once the `localhost`
server is connected:

- `coolify-proxy` — Coolify's own Traefik reverse-proxy, for apps
  deployed *through* Coolify (separate from this stack's `nginx-plain`).
  See "run `fix-proxy-sentinel.sh`" above.
- `coolify-sentinel` — the monitoring agent behind the CPU/RAM/disk
  graphs on the server dashboard. Same section above.

Both regenerate from Coolify's own database on every `up`/restart — `docker ps -a` showing neither of them existing yet, right after starting `coolify`, is expected while the server connects, not broken.

**Stopping them:** `uv run homeserver.py dev down coolify` doesn't touch
either one, since neither is declared in `compose.yml`. Stop them
afterward with:

```bash
uv run homeserver.py dev down coolify
sh services/coolify/stop-self-managed.sh
```

Run it only *after* `coolify` itself is stopped, not before — while the
main app is running, its `ServerManagerJob` reconciles server state
every minute and will just recreate them if it sees them missing while
the database still says they should exist.

## Migrating to a different machine

Standard flow applies (see the `homeserver-backups` skill: `backup all`
→ copy `service_data/backup/` → clone repo → `restore all`) — no
Coolify-specific extra steps needed for data:

- The three named volumes (`coolify-postgres-alpine`,
  `coolify-redis-alpine`, `coolify-ssh-keys`) are captured via real
  `docker volume` tar/untar, so there's no NTFS-related risk even if
  the new machine's filesystem differs from this one.
- Today's proxy/Sentinel fixes carry over automatically — both live
  inside the Postgres database itself (`servers.proxy`,
  `server_settings.sentinel_custom_url`), captured in the
  `coolify-postgres-alpine` backup. No need to rerun
  `fix-proxy-sentinel.sh` on the new machine, provided it uses the same
  port scheme (it will, if it's this same repo).

As with every service in this stack, `services/coolify/.env` isn't part
of `backup`/`restore` (gitignored, lives outside `service_data/`) — copy
it to the new machine yourself. This matters more for Coolify than most
services: `APP_KEY` *encrypts* sensitive database columns (SSH private
keys, OAuth secrets). Restoring the database with a different `.env`
means those columns are permanently undecryptable, not just
"needs reconfiguring" — see the "generate ALL secrets before first
start" note in Setup above.

## Notes

- `APP_ID`/`APP_KEY`/`DB_PASSWORD`/`REDIS_PASSWORD`/`PUSHER_*` are all one-time secrets — generate them once, keep them, never rotate casually (documented upstream behavior: changing them later can break the installation).
- Health endpoint: `/api/health`.
- Since Coolify mounts the Docker socket, treat it with the same trust level as `portainer`/`dockge` in this stack — anything with socket access can affect any other container on the host.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
