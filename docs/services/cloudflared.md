# Cloudflared

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Cloudflare Tunnel connector — exposes `nginx-plain` to the public internet without opening any inbound ports. **Port:** none (outbound-only) | **Requires:** `nginx-plain` | **Memory:** no hard limit set; measured idle ~38MB total (cloudflared 36 + watchdog 2)

## Setup

```bash
cp services/cloudflared/.env.example services/cloudflared/.env
```

Set `TUNNEL_TOKEN` in `.env` — get it from the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com) → **Networks → Tunnels → Create a tunnel → Cloudflared** → name it → select "Docker" as the connector environment, which shows the exact token. Ingress rules (which hostname routes to `nginx-plain`) are configured on the Cloudflare dashboard side, not in this repo.

**Two dashboards can manage this now** (confirmed against Cloudflare's own Feb 2026 changelog): the Zero Trust dashboard path above still works unchanged, but tunnel management was also added to the main dashboard — `dash.cloudflare.com` → **Networking → Tunnels** — for accounts that manage tunnels alongside regular CDN/WAF/DNS settings rather than through Zero Trust. Either one edits the same tunnel; use whichever the account is already set up around.

```bash
uv run homeserver.py dev up cloudflared
```

Runs with `--protocol http2` instead of the default QUIC — this network's WiFi/router path was dropping QUIC connections repeatedly (1200+ reconnects/24h), which HTTP2-over-TCP avoids.

## Using it day to day

There's no local UI for this service — day-to-day management happens entirely on Cloudflare's side, confirmed against Cloudflare's current Zero Trust dashboard.

- **Adding a new public hostname:** [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → Networks → Tunnels → this tunnel → **Public Hostname** tab → **Add a public hostname**, pointing at `nginx-plain:80` (or another internal service) on the `homeserver` Docker network. No compose/env change needed here — nginx-plain's own vhost config is what actually routes the request once it arrives.
- **Checking tunnel health:** the same Tunnels page shows connector status and active connections at a glance; `docker logs cloudflared` (registered/dropped connections, DNS resolver errors) and `docker logs cloudflared-watchdog` (public-path check history, see below) are the local complements when the dashboard alone doesn't explain a problem.
- **Rotating the token:** the tunnel's **Configure** screen can regenerate the token — update `TUNNEL_TOKEN` in `.env` and run `up cloudflared` again afterward.

## cloudflared-watchdog

A companion container (same compose file) that guards against a specific failure mode: cloudflared's own healthcheck (`cloudflared tunnel ... ready`) only checks its *local* count of registered connections. During an incident on 2026-08-07, Cloudflare's edge silently dropped all of cloudflared's connections — the container kept reporting Docker-healthy for ~11 hours while every public request got edge error 530/1033 ("tunnel connector unreachable").

Every `WATCHDOG_CHECK_INTERVAL` (default 60s), the watchdog:

1. **With `CLOUDFLARE_API_TOKEN` set (preferred):** asks the Cloudflare API for this tunnel's status (`GET /accounts/{account}/cfd_tunnel/{tunnel}`, the edge's own view, which `cloudflared`'s local `ready` check can't give). `down` (no connections) or `degraded` is a failure, `healthy` is good. The account and tunnel IDs are decoded from `TUNNEL_TOKEN` (base64 JSON `{"a": account, "t": tunnel, "s": secret}`), so only the token is new. Create it at dash.cloudflare.com → My Profile → API Tokens → Create Custom Token with **Account → Cloudflare Tunnel → Read**.
2. **Fallback (no token, or the API gives no usable answer):** requests `https://${WATCHDOG_HOST}/` (default `immich.${DOMAIN}`) and reads only the HTTP status. **The host must be routed through the tunnel**: the apex `${DOMAIN}` (an edge 301 to `www`) and `docs.${DOMAIN}` are answered by Cloudflare itself and stayed up while every tunnelled hostname returned 1033 on 2026-10-17, which is how the earlier apex probe never fired. `530` is Cloudflare's "no live connector for this tunnel" answer (the page says Error 1033), whatever the app behind it is doing. `000` (DNS or network down on this host) is logged and ignored: restarting cloudflared doesn't fix that.
3. Each failure adds one; a good answer cancels one rather than resetting to zero, because the edge flaps between 530 and 200 while some connections are dead.
4. After `WATCHDOG_FAIL_THRESHOLD` failures (default 3, ~3 min) it restarts the `cloudflared` container via the Docker socket, then waits `WATCHDOG_RESTART_COOLDOWN` (default 120s) before resuming checks.

Also turn on **Zero Trust → Notifications → Tunnel Health Alerts** so Cloudflare tells you about outages the restart doesn't clear. Override the defaults via `CLOUDFLARE_API_TOKEN` / `WATCHDOG_HOST` / `WATCHDOG_CHECK_INTERVAL` / `WATCHDOG_FAIL_THRESHOLD` / `WATCHDOG_RESTART_COOLDOWN` in `.env` (see `.env.example`). Pick a `WATCHDOG_HOST` that is in this tunnel's public hostnames and that you keep running. Logic lives in `watchdog.sh` — it's bind-mounted read-only into a stock `curlimages/curl` container rather than baked into an image, so it's editable without a rebuild.

The watchdog needs read-write access to the Docker socket (same pattern as dozzle/portainer/dockge) to call the restart API — it only ever restarts the `cloudflared` container by name, nothing else.

## Health endpoint

`cloudflared`'s healthcheck runs `cloudflared tunnel --metrics localhost:9002 ready` — confirmed live (`docker exec cloudflared cloudflared tunnel --metrics localhost:9002 ready` exits `0`/prints nothing on success). This is a **local-only** check: it asks cloudflared's own `--metrics` HTTP server (port `9002`, not published outside the container) whether it currently has the minimum number of edge connections registered — it does **not** verify the public URL actually resolves through Cloudflare's edge, which is exactly the gap `cloudflared-watchdog` (below) exists to cover. The image ships no shell utilities (`curl`/`wget` aren't present in the container), so the `ready` subcommand is the only way to probe it from inside.

## Notes

- No ports to configure — cloudflared connects outbound only, so `compose.dev.yml`/`compose.prod.yml` are empty stubs kept for structural consistency with the three-file pattern.
- `docker logs cloudflared` is the source of truth for tunnel-level issues (registered/dropped connections, DNS resolver errors for `*.argotunnel.com`); `docker logs cloudflared-watchdog` shows the public-path check history.


## Fresh-install verification (2026-10-03)

Reset to an empty install, came up healthy, then restored from its `reset-backup-*` snapshot and came up healthy again: stateless, nothing to restore. Procedure: [16 — MIN/CORE reset runbook](../16-min-core-reset-runbook.md).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

## On Kubernetes

**Watchdog on Kubernetes.** Compose's `cloudflared-watchdog` (a curl loop on the Docker socket) is replaced by the `cluster-watchdog` add-on, not by the liveness probe: the probe only counts local connections, and on 2026-10-05 the edge dropped them silently twice. See docs/17 "Watchdog".
