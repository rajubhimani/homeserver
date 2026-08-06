# AdGuard Home

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Network-wide DNS-level ad/tracker blocking for every device on the LAN.
**Port:** `8123` (web UI, host) → `3000` (container); `53` (DNS, LAN-wide, both tcp+udp) | **Data:** `service_data/data/adguard-home/` | **Requires:** nothing

## Different from every other service in this stack: DNS is LAN-only, can't go through the tunnel

Every other service here is reachable at `https://<service>.<domain>` through the Cloudflare tunnel. AdGuard Home's **DNS function (port 53) cannot work that way** — DNS is a raw TCP/UDP protocol on port 53, not HTTP(S), so:

- Port `53` is published directly on the host (`0.0.0.0:53:53/tcp` and `/udp`) — reachable only from your LAN, not from the internet.
- Point each device's DNS settings (or your router's DHCP-assigned DNS) at this host's LAN IP to actually use it for ad-blocking.
- The **web admin panel** (port 3000) is a normal HTTPS app and does get the usual tunnel + `adguard-home.<domain>` treatment — that part works like every other service.

### A platform correction worth remembering

The original plan was `network_mode: host` for a "just works" LAN binding. That's wrong on this host: **Docker Desktop for Windows does not actually expose `network_mode: host` containers to the LAN** — the container stays isolated inside the WSL2 VM even in "host" mode, a documented Docker Desktop limitation (unlike native Linux Docker, where host networking works as expected). The fix used here instead is standard bridge networking with explicit `0.0.0.0:53:53` port publishing in `compose.dev.yml`/`compose.prod.yml`, which Docker Desktop's port-forwarding *does* handle correctly.

## Setup

```bash
cp services/adguard-home/.env.example services/adguard-home/.env
uv run homeserver.py dev up adguard-home
```

Open `http://<host-lan-ip>:8123/` (or `https://adguard-home.<domain>/` once DNS/tunnel routing is set up) and complete the first-run setup wizard — admin password, upstream DNS resolvers, which network interfaces to bind. Then point your router or individual devices' DNS at this host's LAN IP on port 53.

## Notes

- No env vars — everything (upstream resolvers, filter lists, admin credentials, client settings) is configured through the web UI and stored in `service_data/data/adguard-home/conf/AdGuardHome.yaml`.
- Ports `80`, `443`, `853` (DoH/DoT) and DHCP (`67`/`68`) from AdGuard's own docs are deliberately **not** published here — `80`/`443` would conflict with `nginx-plain`, which already owns those on this host, and DHCP/DoT weren't part of what was asked for. Revisit only if a specific need comes up.
- No health/status API endpoint requiring auth is used for the compose healthcheck — it just checks that `/` (the web UI) responds.

## Known issue on this host: port 53 already in use

On the machine this was verified on, starting the container fails with:

```
Error response from daemon: ports are not available: exposing port UDP 0.0.0.0:53 -> 127.0.0.1:0: listen udp4 0.0.0.0:53: bind: Only one usage of each socket address...
```

Something else is already bound to UDP/TCP port 53 — confirmed via `Get-NetUDPEndpoint -LocalPort 53`, which pointed at an `svchost.exe` process distinct from Windows' own `Dnscache` service (so not the obvious "just stop the Windows DNS Client service" fix). Likely Docker Desktop's own internal DNS/vpnkit component, though this wasn't conclusively identified. **The web UI (port 8123/3000) starts and passes its healthcheck fine on its own** — only the port 53 DNS binding is blocked. Before actually using this service for LAN-wide DNS, whoever runs it will need to identify and stop whatever currently holds port 53 on the host (check `Get-NetUDPEndpoint -LocalPort 53` → `Get-Process -Id <pid>`), or accept DNS-blocking won't function until that's resolved.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
