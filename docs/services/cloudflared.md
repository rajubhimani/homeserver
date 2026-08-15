# Cloudflared

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Cloudflare Tunnel connector — exposes `nginx-plain` to the public internet without opening any inbound ports. **Port:** none (outbound-only) | **Requires:** `nginx-plain` | **Memory:** no hard limit set

## Setup

```bash
uv run homeserver.py dev up cloudflared
```

Requires `TUNNEL_TOKEN` in `.env` — get it from the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com) → Networks → Tunnels → Create tunnel → select "Docker" as the connector type. Ingress rules (which hostname routes to `nginx-plain`) are configured on the Cloudflare dashboard side, not in this repo.

Runs with `--protocol http2` instead of the default QUIC — this network's WiFi/router path was dropping QUIC connections repeatedly (1200+ reconnects/24h), which HTTP2-over-TCP avoids.

## cloudflared-watchdog

A companion container (same compose file) that guards against a specific failure mode: cloudflared's own healthcheck (`cloudflared tunnel ... ready`) only checks its *local* count of registered connections. During an incident on 2026-08-07, Cloudflare's edge silently dropped all of cloudflared's connections — the container kept reporting Docker-healthy for ~11 hours while every public request got edge error 530/1033 ("tunnel connector unreachable").

Every `WATCHDOG_CHECK_INTERVAL` (default 60s), the watchdog:

1. Curls `https://${DOMAIN}/` — the real public path through Cloudflare's edge.
2. On failure, curls `nginx-plain:80` directly on the Docker network with the right `Host` header, to check whether the origin itself is the problem.
3. If the origin is reachable but the public path isn't, that's a stale tunnel: after `WATCHDOG_FAIL_THRESHOLD` consecutive failures (default 3, ~3 min), it restarts the `cloudflared` container via the Docker socket, then waits `WATCHDOG_RESTART_COOLDOWN` (default 120s) before resuming checks.
4. If the origin is also unreachable, it skips the restart and just logs — restarting cloudflared won't fix a broken `nginx-plain` or a wider network outage, so it doesn't flap.

Override the defaults via `WATCHDOG_CHECK_INTERVAL` / `WATCHDOG_FAIL_THRESHOLD` / `WATCHDOG_RESTART_COOLDOWN` in `.env` (see `.env.example`). Logic lives in `watchdog.sh` — it's bind-mounted read-only into a stock `curlimages/curl` container rather than baked into an image, so it's editable without a rebuild.

The watchdog needs read-write access to the Docker socket (same pattern as dozzle/portainer/dockge) to call the restart API — it only ever restarts the `cloudflared` container by name, nothing else.

## Notes

- No ports to configure — cloudflared connects outbound only, so `compose.dev.yml`/`compose.prod.yml` are empty stubs kept for structural consistency with the three-file pattern.
- `docker logs cloudflared` is the source of truth for tunnel-level issues (registered/dropped connections, DNS resolver errors for `*.argotunnel.com`); `docker logs cloudflared-watchdog` shows the public-path check history.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
