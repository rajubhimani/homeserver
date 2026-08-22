# AdGuard Home

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Network-wide DNS-level ad/tracker blocking for every device on the LAN.
**Port:** `8123` (web UI, host) → `3000` (container); `53` (DNS, LAN-wide, both tcp+udp) | **Data:** `service_data/data/adguard-home/` | **Requires:** nothing | **Memory:** no hard limit set; measured idle ~57MB

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

## Making devices actually use it

Running the container doesn't route anyone's DNS through it — every device still needs to be pointed at `${DNS_BIND_IP}` (this host's LAN IP, e.g. `192.168.1.7`) as its DNS server. Two ways, in order of effort saved:

**Router-level (recommended) — every device gets it automatically, including new ones later:** in the router's admin page, find the DHCP/LAN DNS setting (varies by router — often "DNS Server" or "Primary DNS" under LAN/DHCP settings) and set it to `${DNS_BIND_IP}`. Existing devices pick it up on their next DHCP lease renewal (or reconnect/reboot to force it).

**Per-device, if you can't touch the router or want to override just one device:**

- **Mac:** System Settings → Network → select the active connection → Details → DNS → add `${DNS_BIND_IP}` (put it first, or remove the others).
- **iPhone/iPad:** Settings → Wi-Fi → tap the ⓘ next to the network → Configure DNS → Manual → remove existing entries, add `${DNS_BIND_IP}`.
- **Android:** Wi-Fi settings → long-press the network → Modify → Advanced options → IP settings → Static → set DNS 1 to `${DNS_BIND_IP}`.

**Caveat that catches people:** port 53 is LAN-only (see "Different from every other service" above) — none of this works once a device leaves the home Wi-Fi (cellular data, another network's Wi-Fi). Those per-device settings just get silently ignored there; there's no VPN/Tailscale in this stack to extend coverage off-network.

**How to confirm it's actually being used**, after pointing a device at it: open the Query Log (see below) and watch for requests from that device's IP within a minute or two of it reconnecting. If nothing shows up, the device is still using some other DNS server — double check the setting actually saved, and that the device reconnected to Wi-Fi (not just toggled airplane mode, which doesn't always force a DHCP renewal).

## Using it day to day

Everything below happens in the web UI (`https://adguard-home.${DOMAIN}/`, own login — separate from Authentik), not env vars or compose changes. Confirmed against AdGuard's own current Knowledge Base, not assumed from memory.

- **Blocklists (Filters → DNS blocklists):** toggle any of the built-in community lists on/off, or add your own by URL. This stack ships with the AdGuard DNS filter (list ID 1) enabled by default; the AdAway Default Blocklist (ID 2) is present but off — a reasonable second list to turn on if the default alone lets too much through. More lists = more coverage but a slightly larger blocked-domain database in memory.
- **Query Log (left nav):** every DNS request from every device, with the result (allowed/blocked/rewritten) and which rule matched. This is the first place to look when something's unexpectedly blocked or a device seems to bypass filtering entirely (check it's actually querying this server, not falling back to its own DNS).
- **Unblocking a false positive:** find the request in the Query Log and use its own "Unblock" action, or add a rule directly under **Filters → Custom filtering rules**: `@@||example.com^` allows a domain despite a blocklist match. The base blocking syntax is `||example.com^` (blocks the domain and subdomains) if you want to add your own blocks the same way.
- **Per-client settings (Clients tab):** identify a device by IP/MAC and give it its own blocklists, upstream servers, or "Blocked services" (YouTube, TikTok, etc. by name, no manual domain lists needed) — client-level settings take priority over the global ones above. Useful for e.g. stricter filtering on one device without affecting the rest of the LAN.
- **DNS rewrites (Filters → DNS rewrites):** force a specific domain to resolve to a chosen IP — handles local hostnames or overriding a public record for this network only.

## DNS-over-HTTPS (DoH) — usable off the home network too

Unlike plain DNS (port 53, LAN-only — see "Different from every other service" above), DoH rides over HTTPS through the existing Cloudflare Tunnel + `nginx-plain` path — the same one the admin UI already uses — so it works from anywhere, not just the LAN.

**Endpoint:** `https://adguard-home.${DOMAIN}/dns-query` (RFC 8484, GET and POST; `/dns-query/{ClientID}` variants also work, for per-client filtering rules to apply to DoH queries too).

**How this was enabled** (already done on this host, documented here for reference/redeploy): AdGuard Home has a `http.doh.insecure_enabled` flag in `AdGuardHome.yaml` that serves DoH on its existing plain-HTTP port instead of requiring its own separate TLS certificate/listener. Since the DoH routes already live on the same port (`3000`) `nginx-plain`'s existing catch-all proxy already forwards, flipping this to `true` needed **zero nginx/compose changes** — confirmed live: decoded a real DoH response (NOERROR, valid answer records) through the public domain, not just a 200 status.

```bash
sed -i 's/insecure_enabled: false/insecure_enabled: true/' service_data/data/adguard-home/conf/AdGuardHome.yaml
uv run homeserver.py dev restart adguard-home
```

**Also needed:** `dns.trusted_proxies` in the same file only trusted `127.0.0.0/8`/`::1/128` by default — not the Docker bridge `nginx-plain` actually connects from, so DoH client IPs would've been misattributed to nginx-plain's own container IP (same class of gap already fixed for Authentik elsewhere in this stack). Added `172.16.0.0/12` (the block Docker's default bridge networks live in) to that list.

**Setting it up on a device:** this is a different setting from the plain-DNS steps above — look for "DNS over HTTPS" / "Encrypted DNS" specifically, not just a DNS server field:

- **Firefox:** Settings → Privacy & Security → DNS over HTTPS → Custom → `https://adguard-home.${DOMAIN}/dns-query`.
- **Windows 11 / recent Edge/Chrome:** OS-level "Encrypted DNS" settings and Chrome's own DoH setting both accept a custom DoH URL the same way as Firefox.
- **Android — no built-in support for a DoH URL, use Intra instead:** Android 9+'s native Private DNS setting only accepts a DoT hostname, not a DoH URL, and this stack hasn't enabled DoT (see Notes below — DoH's `insecure_enabled` escape hatch has no DoT equivalent). Use [Intra](https://getintra.org/) (Google Play or [F-Droid](https://f-droid.org/en/packages/app.intra/)) instead — it runs as a local VPN (Android's `VpnService`) that tunnels DNS queries to a custom DoH endpoint:
  1. Open Intra, tap the current server name/selector.
  2. Choose the custom-server option and enter `https://adguard-home.${DOMAIN}/dns-query`.
  3. Grant the VPN permission prompt (this is what lets Intra intercept system DNS — expected, not a red flag) and enable protection.
  4. Confirm menu wording against the app's own current UI if it's changed since — the exact labels weren't independently verifiable from Intra's own docs at time of writing, just the general flow.
- **AdGuard for Mac (the standalone Mac app, not this AdGuard Home server) — see its own subsection below, it needs more than just pasting a URL.**
- **Linux (Fedora or Ubuntu, systemd-resolved) — no built-in DoH support, needs `dnscrypt-proxy` as a local forwarder:** `systemd-resolved` (the default resolver on both, Ubuntu since 18.04+) supports DNS-over-TLS natively, but **not** DNS-over-HTTPS — and this server only has DoH enabled (see Notes below), not DoT, so the native path doesn't apply here. `dnscrypt-proxy` fills the gap: it runs locally, speaks DoH to this server, and `systemd-resolved` is pointed at it instead of a real upstream. Same package name and mechanism on both distros, just a different package manager:

  1. `sudo dnf install dnscrypt-proxy` (Fedora) or `sudo apt install dnscrypt-proxy` (Ubuntu)
  2. Generate a DNS "stamp" for this server (dnscrypt-proxy's config format encodes the server as a stamp, not a raw URL) at [dnscrypt.info/stamps](https://dnscrypt.info/stamps/) — protocol: DoH, hostname: `adguard-home.${DOMAIN}`, path: `/dns-query`. Copy the resulting `sdns://...` string.
  3. Edit `/etc/dnscrypt-proxy/dnscrypt-proxy.toml`:

     ```toml
     server_names = ['home-adguard']
     listen_addresses = ['127.0.0.1:53']

     [static]
       [static.'home-adguard']
       stamp = 'sdns://...'   # paste the generated stamp here
     ```

  4. Point `systemd-resolved` at it instead of a real upstream:

     ```bash
     sudo mkdir -p /etc/systemd/resolved.conf.d
     printf '[Resolve]\nDNS=127.0.0.1\nDomains=~.\n' | sudo tee /etc/systemd/resolved.conf.d/dnscrypt.conf
     sudo systemctl enable --now dnscrypt-proxy.service
     sudo systemctl restart systemd-resolved.service
     ```

  5. Verify: `resolvectl status` should show `127.0.0.1` as the DNS server; `resolvectl query example.com` should resolve, and the query should show up in AdGuard's Query Log.

### AdGuard for Mac — full setup, including the certificate gotcha hit live

AdGuard for Mac is a separate product from AdGuard Home (the server this doc is about) — a system-wide ad-blocker/DNS client app. Confirmed live on this stack:

1. AdGuard for Mac → **Settings** (gear icon) → **DNS** → **Providers** → **+** (add custom server).
2. Name it (e.g. "Home AdGuard"), address: `https://adguard-home.${DOMAIN}/dns-query`. The `https://` prefix is enough for it to auto-detect DoH — no separate protocol dropdown.
3. Select it from the Providers list to make it active, then enable **Protection** (main toggle).

**If this breaks system-wide internet the moment Protection is turned on:** almost always a macOS permission problem, not a config problem — AdGuard's DNS interception runs through a Network Extension that needs explicit OS approval. Check **System Settings → Privacy & Security** (or **General → Login Items & Extensions → Network Extensions** on newer macOS) for an AdGuard entry and make sure it's allowed; a reboot is sometimes needed after first approving it for the extension to actually start intercepting traffic instead of silently blackholing every query.

**If Firefox specifically shows "Software is preventing Firefox from safely connecting to this site"** (other browsers unaffected): this is AdGuard's separate **HTTPS filtering** feature (full TLS interception for in-page ad-blocking, distinct from DNS protection) needing its own root certificate trusted — and Firefox keeps its own certificate store instead of using macOS's system one, so a system-wide-trusted cert still isn't enough for Firefox specifically. Two ways to fix, pick one:

- **Simplest — turn off HTTPS filtering, keep DNS protection:** if all you actually want is DNS routed through your own server (not full HTTPS content-level ad blocking), disable **HTTPS filtering** in AdGuard for Mac's settings and leave DNS protection on. Firefox stops erroring immediately since AdGuard no longer tries to intercept its TLS traffic at all.
- **To keep HTTPS filtering too — import AdGuard's cert into Firefox specifically** (confirmed working live):
  1. Firefox → Settings → **Privacy & Security** → scroll to **Certificates** → **View Certificates**.
  2. **Authorities** tab → **Import**.
  3. Navigate to `/Library/Application Support/AdGuard Software/com.adguard.mac.adguard/AdguardCore/Adguard Personal CA.cer` and import it.
  4. Trust it for identifying websites when prompted.

## Notes

- No env vars for most settings — upstream resolvers, filter lists, admin credentials, and client settings are configured through the web UI and stored in `service_data/data/adguard-home/conf/AdGuardHome.yaml`. Two exceptions, made directly in that YAML rather than the UI (see "DNS-over-HTTPS" above): `http.doh.insecure_enabled` and `dns.trusted_proxies`.
- Ports `80`, `443`, `853` (DoT/DoQ) and DHCP (`67`/`68`) from AdGuard's own docs are deliberately **not** published here — `80`/`443` would conflict with `nginx-plain`, which already owns those on this host; DoT/DoQ would need AdGuard's own TLS certificate configured (unlike DoH's `insecure_enabled` escape hatch, there's no equivalent for DoT/DoQ), and DHCP wasn't part of what was asked for. Revisit only if a specific need comes up.
- No health/status API endpoint requiring auth is used for the compose healthcheck — it just checks that `/` (the web UI) responds.

## Port 53 conflicts with the host's own DNS resolver — on both Windows and Linux

Binding container DNS to `0.0.0.0:53` collides with whatever DNS stub resolver the host itself already runs on port 53. This has been hit on two different hosts, with two different culprits:

**Windows (Docker Desktop):** fails with

```text
Error response from daemon: ports are not available: exposing port UDP 0.0.0.0:53 -> 127.0.0.1:0: listen udp4 0.0.0.0:53: bind: Only one usage of each socket address...
```

Something else is already bound to UDP/TCP port 53 — confirmed via `Get-NetUDPEndpoint -LocalPort 53`, which pointed at an `svchost.exe` process distinct from Windows' own `Dnscache` service (so not the obvious "just stop the Windows DNS Client service" fix). Likely Docker Desktop's own internal DNS/vpnkit component, though this wasn't conclusively identified.

**Linux (systemd-resolved):** fails with

```text
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint adguard-home: failed to bind host port 0.0.0.0:53/tcp: address already in use
```

`systemd-resolved`'s stub listener holds `127.0.0.53:53` (and `127.0.0.54:53`) by default (`ss -tulnp | grep :53` shows it). A wildcard `0.0.0.0:53` bind conflicts with that even though the addresses look different — Linux treats a wildcard bind as overlapping any more-specific bind already on the same port.

**Fix used here:** bind DNS to the host's actual LAN IP instead of the wildcard — set `DNS_BIND_IP` in `.env` (see `.env.example` for how to find it via `ip -4 addr`) and both `compose.dev.yml`/`compose.prod.yml` publish `${DNS_BIND_IP}:53:53` rather than `0.0.0.0:53:53`. Avoids the conflict on both platforms without touching host DNS config. Caveat: if the host's LAN IP changes (DHCP lease renewal), `DNS_BIND_IP` needs updating and the container restarting — set a DHCP reservation on your router for this host to avoid that. The web UI (port 8123/3000) is unaffected by any of this either way — it starts and passes its healthcheck regardless of the DNS port's fate.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
