# Beszel

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Lightweight server monitoring — CPU, memory, disk, network, and Docker container stats with alerts.
**Port:** `8106` (host) → `8090` (container) | **Data:** `service_data/data/beszel/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~42MB (hub + agent combined)

## Setup

```bash
cp services/beszel/.env.example services/beszel/.env
uv run homeserver.py dev up beszel
```

Two containers start: `beszel` (hub, web UI + storage) and `beszel-agent` (monitors this Docker host). The agent **crash-loops** until it has a token/key pair from the hub — this is expected (`restart: unless-stopped` just keeps retrying) and stops once you pair it below.

## Connecting an agent (the step that actually makes monitoring work)

Running `up beszel` alone gets you an empty hub — a system only shows up once its agent has a paired token/key. This is the concrete, one-time step per system; skipping it is why the bundled agent crash-loops on first start.

**This host (the bundled `beszel-agent` container, already in `compose.yml`):**

1. Browse to `http://<ip>:8106` — create the admin account on first launch.
2. Hub UI → **Add System** (top right) → give it a name/host, or use **Settings → Tokens** for a universal token → copy the token + public key it shows you.
3. Set them in `services/beszel/.env`:

   ```bash
   BESZEL_AGENT_TOKEN=<token from hub>
   BESZEL_AGENT_KEY=<public key from hub>
   ```

4. Restart: `uv run homeserver.py dev up beszel`

The system indicator in the hub UI turns green once the agent connects.

**Monitoring another machine (any server outside this Docker host):** Beszel's whole point is a single hub watching a fleet, so this is the normal way it gets used beyond just this host. Hub UI → **Add System** → fill in the new system's name/host, and the dialog hands you a ready-to-run install command plus a `docker-compose.yml` snippet, both pre-filled with that system's token/key — copy whichever fits the target machine and run it there, pointed at this hub's reachable address (LAN IP or `beszel.${DOMAIN}` if it's off-LAN and the tunnel route is set up). Once the agent's running on the remote machine, click **Add System** again in the hub to confirm — the new system appears in the table, green once connected, red if the agent can't reach the hub.

Per-OS install, confirmed against Beszel's current agent-installation docs (all pull the same underlying script, just per-platform packaging):

- **Ubuntu / Fedora (Linux, native):** `curl -sL https://get.beszel.dev -o /tmp/install-agent.sh && chmod +x /tmp/install-agent.sh && /tmp/install-agent.sh` (needs root; accepts `-k` key, `-t` token, `-url` hub-url flags so it can run fully unattended, or just answer its prompts) — installs a systemd service.
- **Mac (Homebrew):** `curl -sL https://get.beszel.dev/brew -o /tmp/install-agent.sh && chmod +x /tmp/install-agent.sh && /tmp/install-agent.sh` — config lands in `~/.config/beszel/beszel-agent.env`, logs in `~/.cache/beszel/beszel-agent.log`.
- **Windows (PowerShell):** `& iwr -useb https://get.beszel.dev -OutFile "$env:TEMP\install-agent.ps1"; & Powershell -ExecutionPolicy Bypass -File "$env:TEMP\install-agent.ps1"` — installs NSSM to run the agent as a Windows service; reconfigure later with `nssm edit beszel-agent`.
- **Android:** no native agent — Beszel monitors hosts (Linux/Mac/Windows/Docker), not individual phones; not applicable here.
- **Any Docker host (alternative to the native installers above):** paste the hub's generated `docker-compose.yml` snippet and `docker compose up -d` it — same mechanism this repo's own bundled `beszel-agent` container uses.

## Using it day to day

Everything happens in the hub web UI (`http://<ip>:8106`), confirmed against Beszel's own current README/site.

- **Dashboard (home page):** every connected system as a grid of cards with live CPU/memory/disk/network at a glance — the place to spot which system is under load right now across the whole fleet.
- **System page:** click into any system for its historical charts — CPU, memory (incl. swap/ZFS ARC), disk usage and I/O per partition, network, load average, temperature/fan sensors, and (since this stack's agent also reads the Docker socket) per-container CPU/memory/network history.
- **Alerts:** configurable per system for CPU, memory, disk, bandwidth, temperature, fan speed, load average, and status (system unreachable) — threshold-based, so setting e.g. "CPU > 90%" notifies once a system crosses it.
- **Notification Settings (separate settings page):** where alert triggers actually get delivered — email, webhook, and a range of third-party integrations. Configure this once; alerts set on individual systems route through whatever's enabled here.
- **Multi-user:** each user manages their own systems by default; an admin can share a system with other users if more than one person needs to see the same fleet.

## Health endpoint

Both containers' healthchecks were confirmed live on this host:

- **Hub** (`beszel` container): `/beszel health --url http://localhost:8090` — the hub binary's own subcommand, not a raw HTTP probe. It calls the hub's `/api/health` endpoint internally; confirmed directly too — `curl http://localhost:8106/api/health` returns `{"message":"API is healthy.","code":200,"data":{}}`.
- **Agent** (`beszel-agent` container): `/agent health` — the agent binary's own subcommand (checks it's listening on its configured socket/port), prints `ok` on success. No HTTP endpoint of its own to curl — it only exists to serve the hub over the shared socket.

## Additional env knobs available but not previously exposed

The image supports more configuration than this stack previously wired up. Added to `compose.yml` at their defaults (no behavior change) since this repo threads beszel's config through plain env vars, not a mounted YAML file like some other services:

- **Hub — `HEARTBEAT_URL`:** if set, the hub pings this URL on an interval (see also `HEARTBEAT_INTERVAL`/`HEARTBEAT_METHOD`, image defaults, not added here) — a natural fit for this stack's own uptime-kuma Push monitor type, letting uptime-kuma alert if the hub itself goes dark. Blank/unset (current state) disables it entirely.
- **Agent — `FILESYSTEM`:** overrides which device the agent reports as "root" for disk usage/IO; blank auto-detects (picks the device with the most reads), which is normally fine but can pick the wrong device on unusual disk layouts.
- **Agent — `EXTRA_FILESYSTEMS`:** comma-separated extra mountpoints/devices to track alongside root — useful if this host has additional data disks worth graphing separately. Blank tracks root only.
- **Agent — `EXCLUDE_CONTAINERS`:** comma-separated name/ID patterns to hide from per-container stats — useful to cut noise from containers you don't care to chart. Blank reports every container.

Other hub knobs exist (`DISABLE_PASSWORD_AUTH`, `USER_CREATION` for OIDC, `MFA_OTP`, `TRUSTED_AUTH_HEADER`, `CSP`) but weren't added — they only matter if OAuth/SSO or a reverse-proxy auth header gets wired up for beszel specifically, which this stack doesn't currently do (beszel has its own login, separate from Authentik).

## Architecture notes

`beszel-agent` runs with `network_mode: host` instead of joining the `homeserver` bridge network — it's the only service that does. This is required for it to report real host-level network throughput; on the bridge network it would only see its own virtual interface. It talks to the hub over a shared local Unix socket (`${DATA_ROOT}/socket`), not the Docker network, so it has no need to resolve other containers by name.

Because of the host-network mode, the agent's `HUB_URL` must point at the hub's **published host port** (`http://localhost:8106`), not its container port (`8090`) — update it if the hub's port mapping ever changes.

`TOKEN`/`KEY` are blank on first start — the agent refuses to run without them and crash-loops (`Failed to load public keys: no key provided`) until paired as above. The crash-loop is expected/harmless (`restart: unless-stopped`), not a bug.

It also reports per-container Docker stats via the mounted `${DOCKER_SOCKET}` (read-only).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
