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

**Web Interface step — port must be `3000`, not the wizard's suggested `80`.** The wizard's `get_addresses` API defaults `web_port` to `80` (AdGuard's normal standalone-install suggestion), but this stack's `compose.dev.yml`/`compose.prod.yml` already map host `8123 → container 3000`, and `nginx-plain`'s `adguard-home.${DOMAIN}` upstream also points at `:3000`. Accepting the wizard's default `80` leaves both of those pointing at nothing once setup finishes and AdGuard switches off its temporary install-mode `:3000` listener — every request 502s (`connection refused` in `nginx-plain`'s logs) until the port is corrected. Type `3000` into the Web Interface port field explicitly; leave the DNS step's port at its default `53`.

If this is already hit — `http.address` in `service_data/data/adguard-home/conf/AdGuardHome.yaml` reads `0.0.0.0:80` instead of `0.0.0.0:3000` — fix it directly and restart, no need to redo the wizard:
```bash
sed -i 's/address: 0.0.0.0:80/address: 0.0.0.0:3000/' service_data/data/adguard-home/conf/AdGuardHome.yaml
uv run homeserver.py dev restart adguard-home
```

## Notes

- No env vars — everything (upstream resolvers, filter lists, admin credentials, client settings) is configured through the web UI and stored in `service_data/data/adguard-home/conf/AdGuardHome.yaml`.
- Ports `80`, `443`, `853` (DoH/DoT) and DHCP (`67`/`68`) from AdGuard's own docs are deliberately **not** published here — `80`/`443` would conflict with `nginx-plain`, which already owns those on this host, and DHCP/DoT weren't part of what was asked for. Revisit only if a specific need comes up.
- No health/status API endpoint requiring auth is used for the compose healthcheck — it just checks that `/` (the web UI) responds.

## Port 53 conflicts with the host's own DNS resolver — on both Windows and Linux

Binding container DNS to `0.0.0.0:53` collides with whatever DNS stub resolver the host itself already runs on port 53. This has been hit on two different hosts, with two different culprits:

**Windows (Docker Desktop):** fails with
```
Error response from daemon: ports are not available: exposing port UDP 0.0.0.0:53 -> 127.0.0.1:0: listen udp4 0.0.0.0:53: bind: Only one usage of each socket address...
```
Something else is already bound to UDP/TCP port 53 — confirmed via `Get-NetUDPEndpoint -LocalPort 53`, which pointed at an `svchost.exe` process distinct from Windows' own `Dnscache` service (so not the obvious "just stop the Windows DNS Client service" fix). Likely Docker Desktop's own internal DNS/vpnkit component, though this wasn't conclusively identified.

**Linux (systemd-resolved):** fails with
```
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint adguard-home: failed to bind host port 0.0.0.0:53/tcp: address already in use
```
`systemd-resolved`'s stub listener holds `127.0.0.53:53` (and `127.0.0.54:53`) by default (`ss -tulnp | grep :53` shows it). A wildcard `0.0.0.0:53` bind conflicts with that even though the addresses look different — Linux treats a wildcard bind as overlapping any more-specific bind already on the same port.

**Fix used here:** bind DNS to the host's actual LAN IP instead of the wildcard — set `DNS_BIND_IP` in `.env` (see `.env.example` for how to find it via `ip -4 addr`) and both `compose.dev.yml`/`compose.prod.yml` publish `${DNS_BIND_IP}:53:53` rather than `0.0.0.0:53:53`. Avoids the conflict on both platforms without touching host DNS config. Caveat: if the host's LAN IP changes (DHCP lease renewal), `DNS_BIND_IP` needs updating and the container restarting — set a DHCP reservation on your router for this host to avoid that. The web UI (port 8123/3000) is unaffected by any of this either way — it starts and passes its healthcheck regardless of the DNS port's fate.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
