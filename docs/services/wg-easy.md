# wg-easy — Self-Hosted WireGuard VPN with Web UI

wg-easy is a self-hosted WireGuard VPN server with a web-based admin panel for managing clients (each gets a QR code / config file). Standard, mature WireGuard technology — this is what powers this stack's VPN, giving remote devices access to the homeserver's LAN/services, and optionally routing all internet traffic through home (an "exit node" style full tunnel).

## Why This Exists (and Why NetBird/Cloudflare Tunnel Don't Work Here)

This service was built after extensive investigation ruled out every zero-port-forward option that goes through Cloudflare Tunnel:

- **Cloudflare's own Terms of Service explicitly prohibit proxying VPN traffic through their network** (updated Dec 2024) — this rules out NetBird, Headscale/Tailscale, or any VPN routed through `cloudflared`/nginx-plain, since that risks the *entire* Cloudflare account being flagged, taking down every other self-hosted service in this stack.
- **Headscale's own docs explicitly say Cloudflare Tunnel is unsupported** (WebSocket POST requirement Cloudflare doesn't support).
- **This homeserver's ISP (Airtel personal broadband) uses CGNAT for IPv4** — no real public IPv4 address exists to port-forward to, confirmed by comparing the router's WAN IP against an external "what's my IP" check (they don't match).

**The solution: this homeserver has a real, publicly-routable IPv6 `/64` prefix** (no CGNAT on IPv6 — IPv6 doesn't need NAT at all). wg-easy runs with `network_mode: host`, listens on WireGuard's UDP port directly on the host's real IPv6 address, and is reached via a plain DNS-only (non-Cloudflare-proxied) hostname. This sidesteps both the ToS risk (Cloudflare never carries this traffic) and the CGNAT problem (IPv6 bypasses it entirely).

**Trade-off:** any client connecting must itself have IPv6 connectivity. This is very common in India — Jio and Airtel both have large-scale IPv6 deployments on mobile data — but isn't universal. If a client's network is IPv4-only, it cannot reach this server as currently configured.

## Architecture

- **`wg-easy`** — single container, `network_mode: host`, binds WireGuard's UDP port (default `51820`) and the admin web UI (`51821`) directly to the host's real network interfaces.
- **VPN tunnel traffic (UDP 51820)**: reached via a plain DNS-only (grey-clouded, non-proxied) `AAAA` record pointing at the homeserver's real IPv6 address — e.g. `wg.yourdomain.com`. This is safe to host on Cloudflare's DNS because it's DNS-only: no traffic is proxied through Cloudflare's network, it's just a name-to-address lookup, same as any other DNS provider. **This record must never be proxied (orange cloud)** — see the ToS note above.
- **Admin web UI (port 51821)**: unlike the VPN tunnel itself, this is just a plain HTTP/REST web dashboard — no WireGuard/VPN protocol traffic involved. It's safe to expose normally through nginx-plain + Cloudflare (regular orange-cloud proxying), since Cloudflare's VPN-proxying ToS restriction is about actual VPN/tunnel traffic, not a web app that happens to manage one. This stack exposes it at a separate hostname (e.g. `wg-admin.yourdomain.com`) behind **Authentik forward-auth** (defense-in-depth on top of wg-easy's own login, matching the pattern used for other sensitive admin panels like Dozzle/Ollama in this stack — see `docs/services/authentik.md`).
  - Since wg-easy uses `network_mode: host`, it isn't on the same Docker network as nginx-plain — nginx-plain reaches it via the `homeserver` Docker network's own bridge gateway IP (`172.18.0.1` in this deployment; check `docker network inspect homeserver --format '{{.IPAM.Config}}'` if rebuilding, this can differ), which is just another host interface wg-easy's host networking already binds to.
  - `INSECURE: "true"` is still needed in the container's environment even with this HTTPS-fronted public route — the *internal* hop from nginx-plain to wg-easy is still plain HTTP (same pattern as every other proxied service in this stack; Cloudflare/nginx-plain terminate TLS, internal traffic is HTTP).

## Prerequisites Discovered During Setup (All Required)

Getting this working end-to-end required fixing several host-level issues that aren't obvious from wg-easy's own docs. All of these are **one-time, host-level** configuration (not container config) — write them down before rebuilding this host.

### 1. Confirm you're behind CGNAT (or not) for IPv4

Compare your router's own reported WAN IP against what an external site reports:
1. Router admin page → WAN/Status → note the IPv4 address shown
2. From a device on that network, visit `https://whatismyipaddress.com` → note the IPv4 shown
3. **If they differ**, you're behind CGNAT — this whole IPv6-direct approach is necessary. If they match, you have a real public IPv4 and could use IPv4 directly instead (simpler, but not this homeserver's situation).

Also check the router's **IPv6** WAN info — you want a real `/64` (or similar) prefix, not just a link-local address, and it should also match what the external site reports for IPv6 (confirming no IPv6 NAT either, which is normal — IPv6 essentially never uses NAT).

### 2. Host sysctls (IPv6 forwarding)

`network_mode: host` means sysctls **cannot** be set via the container's `sysctls:` block — Docker refuses ("not allowed in host network namespace"). Set on the host directly:

```bash
sudo sysctl -w net.ipv6.conf.all.forwarding=1 net.ipv6.conf.default.forwarding=1
```

**To persist across reboots**, add to `/etc/sysctl.d/99-wg-easy.conf`:
```
net.ipv6.conf.all.forwarding=1
net.ipv6.conf.default.forwarding=1
```

### 3. Kernel NAT modules

The container needs `iptable_nat` and `ip6table_nat` kernel modules loaded on the host — without them, `wg-quick up` fails with `can't initialize iptables table 'nat': Table does not exist`.

```bash
sudo modprobe iptable_nat ip6table_nat
```

**To persist across reboots**, add both module names (one per line) to `/etc/modules-load.d/wg-easy.conf`.

### 4. firewalld masquerade (if using firewalld — Fedora/RHEL default)

This is the least obvious gotcha: even with correct WireGuard config and NAT rules, traffic silently failed to route (client received data, but return traffic never left the server) because **firewalld's zone for the WiFi/ethernet interface had masquerading explicitly disabled**, overriding wg-easy's own iptables MASQUERADE rules at a layer `iptables -L` doesn't show.

Check your active zone and whether masquerade is on:
```bash
firewall-cmd --get-active-zones
firewall-cmd --zone=<your-zone> --list-all   # look for "masquerade: no"
```

If disabled:
```bash
sudo firewall-cmd --zone=<your-zone> --add-masquerade --permanent
sudo firewall-cmd --reload
```

(If you don't use firewalld — e.g. Ubuntu with ufw or ufw disabled — this step doesn't apply, but check whatever firewall manager you do have for an equivalent "masquerade"/NAT toggle.)

### 5. Router IPv6 firewall

Your router needs to allow inbound UDP on the WireGuard port over IPv6. Unlike IPv4 port-forwarding (NAT translation), this is just a firewall **allow rule** — IPv6 doesn't need NAT since addresses are already globally routable.

Router UIs vary enormously. On this homeserver's router (Sercomm AOT-4221SR, an Airtel-provided ONT/router), the only available control was a coarse **Security Level: Low/Medium/High** toggle (no granular per-port IPv6 rule option existed). If your router has a proper IPv6 firewall/pinhole section, use that instead to open only the specific port rather than lowering overall security.

**Confirmed on this router: `High` silently blocks new WireGuard handshakes, `Medium` does not.** This was non-obvious to diagnose — an existing connection kept working for a while after switching to `High` (state from before the change, or a brief propagation window), which looked like success, but any *new* handshake attempt after that (phone reconnecting, a stale session needing to re-negotiate) was dropped with zero packets ever reaching the server — confirmed via `wg show wg0 dump` showing no endpoint activity and `ip -s link show wg0` showing an unchanged RX counter across multiple retries. Switching back to `Medium` fixed it immediately (fresh handshake within seconds, `wg0`'s RX counter jumped from 135 to 1861 packets on the first real page load). If you hit "VPN was working, now nothing connects, no error either side" after touching this toggle, suspect the toggle itself before anything else — check `docker exec wg-easy wg show wg0 dump` for peer endpoint/handshake activity and `ip -s link show wg0` for RX counter movement across a retry; if neither moves at all despite a client-side reconnect, it's the router silently dropping the handshake, not this host.

**This coarse router toggle is only half the picture — your host's own firewall matters just as much, if not more.** A real, routable IPv6 address (which this whole setup depends on) means anything your *host* firewall allows inbound is now reachable from the internet too, regardless of the router. This exact combination (router set to Low + an unrelated, overly-broad host firewall rule) once exposed RDP and several admin panels on this deployment — see [09 — Firewall](../09-firewall.md) for the full incident and the default-deny host firewall setup every IPv6-reachable host should have, VPN or not.

## Exact Commands Run On This Host (Copy-Paste Reference)

Every host-level command actually executed to get this working, in order. The Prerequisites section above explains *why* each is needed — this is the condensed "just run these" version for rebuilding this exact host. Adjust the zone name (`FedoraWorkstation`) and interface name (`wlp13s0`) if your host differs — check with `firewall-cmd --get-active-zones` and `ip route show default` respectively.

```bash
# 1. Enable IPv6 forwarding (persists only for this boot — see Prerequisites
#    step 2 above for the /etc/sysctl.d/ file to make it survive a reboot)
sudo sysctl -w net.ipv6.conf.all.forwarding=1 net.ipv6.conf.default.forwarding=1

# 2. Load NAT kernel modules (persists only for this boot — see Prerequisites
#    step 3 above for the /etc/modules-load.d/ file to make it survive a reboot)
sudo modprobe iptable_nat
sudo modprobe ip6table_nat

# 3. Enable masquerade on firewalld's zone (Fedora/RHEL default firewall —
#    skip if you use a different firewall manager, but find its equivalent
#    NAT/masquerade toggle)
sudo firewall-cmd --zone=FedoraWorkstation --add-masquerade --permanent
sudo firewall-cmd --reload

# 4. One-time cleanup: remove leftover routing state from an unrelated prior
#    WireGuard-based experiment on this host (only needed if you've run
#    another WireGuard/NetBird-style tool on this same host before — check
#    `ip link show` and `ip -6 rule show` first to see if anything unexpected
#    is present; skip this on a genuinely fresh host)
sudo ip link delete wt0
sudo ip -6 rule del not from all fwmark 0x1bd00 lookup 7120
```

After steps 1-3 (or anytime config changes in the Admin Panel need to take effect — e.g. after changing Interface → Device or MTU), do a full container recreate, not just a restart:

```bash
docker rm -f wg-easy
uv run homeserver.py dev up wg-easy
```

(A plain `docker restart` is not reliable here — `wg-quick`'s `PostUp` script, which sets up the NAT/firewall rules, only re-runs when the WireGuard interface comes up fresh.)

## Setup Steps

### 1. Create a DNS-only hostname

In Cloudflare (or whatever DNS provider you use) — **not proxied**:
- Type: `AAAA`
- Name: `wg` (or whatever subdomain)
- Value: the homeserver's real global IPv6 address (`ip -6 addr show <interface>` on the host, the `scope global` one — note it may be marked `dynamic`; if your ISP rotates this address, disable IPv6 privacy extensions/temporary addresses on that interface, or plan on updating the DNS record when it changes)
- Proxy status: **DNS only** (grey cloud) — critical, must never be proxied through Cloudflare

### 2. Start the container

```bash
uv run homeserver.py dev up wg-easy
```

(This service is `manual` tier — never auto-started by `up all`/`up core`/etc., only by explicitly naming it.)

### 3. Complete the first-run setup wizard

Open `http://<homeserver-lan-ip>:51821` in a browser **on your local network** (not the public hostname — the admin UI isn't exposed publicly).

- **Host / public address**: the DNS hostname from step 1 (e.g. `wg.yourdomain.com`)
- **Port**: `51820` (default)
- Set an admin username/password

### 4. Fix the MASQUERADE interface (Admin Panel → Interface → Device)

wg-easy defaults to interface name `eth0` (correct for most cloud VPS, wrong for anything else — e.g. a WiFi adapter like `wlp13s0`, or a differently-named ethernet interface). Without this fix, client traffic reaches the server but is never NAT'd out to the real internet (confirmed via `iptables -t nat -L POSTROUTING -n -v` showing 0 packets matched on the `eth0` rule).

1. Admin Panel (gear/settings icon) → **Interface**
2. Find **Device**, change from `eth0` to your host's actual default-route interface name (check with `ip route show default` on the host)
3. Save — this regenerates `wg0.conf`, but only takes effect on the **next** container restart (`PostUp` only runs when the interface comes up)
4. Restart: `docker rm -f wg-easy && uv run homeserver.py dev up wg-easy` (a plain `docker restart` isn't reliably enough — do a full recreate)

Also set **MTU** to `1280` here while you're at it (see Performance Notes below for why).

## Creating Clients (Full-Tunnel vs Split-Tunnel vs Custom Access)

wg-easy doesn't have a single "split tunnel" toggle — instead, create **separate client profiles**, each with a different `Allowed IPs` value, and load multiple profiles into the WireGuard app on your device. Switching between modes is just toggling which saved tunnel is active.

### What "Allowed IPs" actually controls

This one field is what decides **what a client can reach through the tunnel** — think of it as the permission grant. It's a comma-separated list of IP ranges (CIDR notation). When the client connects, only traffic destined for one of these ranges gets routed through the VPN; everything else uses the device's own normal connection.

**Always include the VPN's own subnet** (`10.8.0.0/24, fdcc:ad94:bacf:61a4::/64` in this deployment — check **Admin Panel → Interface** for the exact values if rebuilding) in every profile, full-tunnel or not — without it, the client can't even reach the server itself or other peers.

**Then add whatever else that specific person/device should be able to reach:**

| Want to grant access to... | Add this to Allowed IPs |
|---|---|
| Everything (full-tunnel/exit-node) | `0.0.0.0/0, ::/0` (or just leave the field empty — this is wg-easy's default) |
| The whole home LAN (other, non-Docker devices — NAS, printers, other PCs) | Your LAN's subnet, e.g. `192.168.1.0/24` (check `ip route show default` on the homeserver, or your router's LAN settings, for your actual subnet) |
| One specific device only (e.g. just a NAS, just one server) | That device's single IP with a `/32` suffix, e.g. `192.168.1.50/32` |
| A few specific devices/services, nothing else | List each one individually, comma-separated, each with `/32` — e.g. `192.168.1.50/32, 192.168.1.60/32` |

**In practice, for a firm/team setting**, this means you decide per-person what they should reach — e.g. an accountant might only need `192.168.1.50/32` (just the finance server), while an IT admin might get the whole LAN. There's no single "correct" scope — it's your call per client, based on what that person's role actually needs.

> **Reaching the homeserver's own containerized services (Immich, Jellyfin, Nextcloud, etc.) no longer needs its own Allowed IPs entry at all.** Every service's `compose.prod.yml` in this stack binds to `10.8.0.1` (WireGuard's own tunnel-side address) in addition to `127.0.0.1` — see [09 — Firewall](../09-firewall.md#restoring-fast-direct-access-safely-the-10801-pattern) for the full pattern and why it's safe. Since `10.8.0.0/24` (the VPN subnet itself) is already mandatory in *every* profile, this means **any connected client can already reach every service directly** — e.g. `http://10.8.0.1:8096` for Jellyfin, `http://10.8.0.1:2283` for Immich — full port list in [11 — Services Reference](../11-services-reference.md#port-reference). This is what retired the old `myphone-docker` profile below: it existed only to route to the Docker bridge subnet (`172.18.0.0/16`) for direct container access, which is now unnecessary — the same access comes for free from the VPN subnet already in every profile.

### The two client profiles used in this deployment

Down from three — `myphone-docker` (see box above) is retired; its whole purpose is now covered automatically by every profile's mandatory VPN-subnet entry.

| Profile | Allowed IPs | Use case |
|---|---|---|
| `myphone` | *(left unset — defaults to)* `0.0.0.0/0, ::/0` | Routes ALL internet traffic through home — gives your home's public IP, enables content filtering, but adds latency to every request (see Performance Notes). Also reaches every service directly via `10.8.0.1` (see box above), same as any profile. |
| `myphone-lan` | `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 192.168.1.0/24` (VPN subnet + home LAN subnet) | Reach every homeserver service (via `10.8.0.1`) **and** other LAN devices that aren't part of the Docker stack (NAS, printers, other PCs, or this host's own LAN-bound things like GNOME Remote Desktop at `192.168.1.7:3389`) — general internet stays on the device's own fast connection |

**Steps per client:**
1. Admin Panel → **New Client** → name it (e.g. `myphone-lan`) → Save
2. Click the new client to edit it → find **Allowed IPs** field → set to whatever scope this person/device needs (see above) → Save
3. Click the client's **QR code** icon → scan into the WireGuard app on the target device (or download the `.conf` file directly for desktop platforms)

**Worked example — setting up `myphone-lan`:**
1. Admin Panel → New Client → name `myphone-lan` → Save
2. Edit it → Allowed IPs → paste: `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 192.168.1.0/24` → Save
3. Get its QR code, scan into the WireGuard app — it appears as a second saved tunnel alongside the original `myphone` (full-tunnel) one, so switching is just toggling which one is active

**Verifying the config took effect** (server-side check, since the Allowed IPs field here is easy to confuse with a *different* field of the same name that serves the opposite purpose — see Troubleshooting). Actual output from this deployment, confirming both were set correctly (from when `myphone-docker` still existed — the shape of the check is unchanged, just one fewer row today):
```bash
docker cp wg-easy:/etc/wireguard/wg-easy.db /tmp/check.db
python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/check.db')
c = conn.cursor()
c.execute('SELECT id, name, allowed_ips, server_allowed_ips FROM clients_table')
for row in c.fetchall(): print(row)
"
```
```
(1, 'myphone', None, '[]')
(3, 'myphone-lan', '["10.8.0.0/24","fdcc:ad94:bacf:61a4::/64","192.168.1.0/24"]', '[]')
```
(`myphone`'s `allowed_ips` is `None` — confirms it correctly falls back to the full-tunnel default rather than being unset/broken. If you still have an old `myphone-docker` client from before this change, it's safe to delete from the Admin Panel — nothing depends on it anymore.)

## Platform Support

wg-easy generates standard WireGuard client configs — the actual VPN app is the official **WireGuard** app, available on:
- **Windows / macOS / Linux** — from wireguard.com or your platform's package manager/app store; import the downloaded `.conf` file directly (no camera for QR scanning on most desktops)
- **Android** — Google Play Store; scan the QR code from the wg-easy dashboard
- **iOS** — App Store; scan the QR code

Same underlying protocol and config format across all platforms — only the import method (QR scan vs file import) differs.

## Performance Notes (Why Full-Tunnel Feels Slower for Some Traffic)

Full-tunnel routing adds a real, unavoidable extra hop: `device ↔ mobile/other network ↔ homeserver ↔ internet`. Two effects observed in practice:

1. **Bandwidth ceiling**: the homeserver's own connection speed becomes the ceiling for everything routed through it. Test with:
   ```bash
   curl -o /dev/null -s -w "%{speed_download} bytes/sec\n" https://speed.cloudflare.com/__down?bytes=25000000
   ```
   If this is slower than the connecting device's own normal connection, full-tunnel browsing will feel slower than going direct — this is inherent, not a misconfiguration.

2. **Latency compounds for many-small-request workloads**: the extra hop adds real round-trip latency (measured ~35-100ms extra on this setup, checked via `docker exec wg-easy ping -c 4 <client-tunnel-ip>`). This barely affects continuous-stream workloads (video/audio — buffers ahead, latency-tolerant), but compounds heavily for pages making many small sequential requests (search results, ad/tracker-heavy websites — each of dozens of requests pays the extra latency tax). This is why, e.g., YouTube can feel fine over full-tunnel while Google search feels noticeably slower — it's a latency effect, not a bandwidth one.

**MTU 1280**: set conservatively (down from the 1420 default) as a precaution against fragmentation issues common when the connecting device is on a mobile network with its own encapsulation overhead. In this setup it turned out not to be the actual bottleneck (latency was), but it's a safe, standard value to use regardless (1280 is IPv6's guaranteed minimum MTU — works everywhere).

## Troubleshooting (Gotchas Actually Hit Setting This Up)

**`sysctl "net.ipv4.conf.all.src_valid_mark" not allowed in host network namespace`**
`network_mode: host` containers cannot set sysctls via Docker's `sysctls:` compose key — that key applies to the container's own network namespace, which with host networking *is* the host's namespace, and Docker refuses to let a container mutate host sysctls this way. Set them on the host directly (see Prerequisites above) and remove `sysctls:` from the compose file entirely.

**`iptables v1.8.13 (legacy): can't initialize iptables table 'nat': Table does not exist (do you need to insmod?)`**
The `iptable_nat` (and separately, `ip6table_nat`) kernel modules aren't loaded on the host. `modprobe` them (see Prerequisites above) — note these are two *separate* modules; loading one doesn't load the other.

**Admin UI client list is empty / stuck loading, with no obvious error visible in the UI itself**
This is a *downstream symptom* of the NAT-module gotcha above, not a separate bug — but it's easy to miss the connection because the error you actually see (in the browser network tab or `docker logs wg-easy`) doesn't mention NAT or iptables at all:

```
[request error] [unhandled] [GET] .../api/client?sort=asc
 H3Error: Command failed: wg show wg0 dump
Unable to access interface: No such device
```

This just means the `wg0` interface doesn't exist, so every API call that shells out to `wg show wg0 ...` 500s — including the one that populates the client list. It doesn't say *why* `wg0` is missing. **Debug it in this order:**

1. Confirm the interface really is missing: `ip link show wg0` on the host (not inside the container — with `network_mode: host` they share one network namespace, so either works, but checking the host directly rules out a container-vs-host confusion). `Device "wg0" does not exist` confirms it.
2. Don't just look at the tail of `docker logs wg-easy` — the "Unable to access interface" lines repeat forever (once per API poll) and will bury the one-time startup error above them. Look further back, at the container's actual *start* (`docker logs wg-easy --since <container start time>`, from `docker inspect wg-easy --format '{{.State.StartedAt}}'`), for the real `wg-quick up wg0` failure — e.g. the NAT-table error above, or something else entirely (a stale interface left by another tool, per the "no IP address at all" entry below).
3. Once you see *why* `wg-quick up` failed at startup, that's your actual root cause — fix that (NAT modules, stale interface, etc.), then recreate the container so it retries bringing `wg0` up cleanly.
4. Confirm the fix: `docker exec wg-easy wg show wg0 dump` should print one line per configured peer (their public key, IP, handshake stats) instead of erroring — at that point the admin UI's client list will populate correctly on next load.

**Why this can happen on a host that already "has NAT working"**: a Fedora (or other nftables-default) host doesn't need `iptable_nat`/`ip6table_nat` loaded for its own `iptables` command — `iptables` there is actually `iptables-nft` (check with `update-alternatives --display iptables`), a compatibility shim over the nftables backend, which uses different kernel modules (`nft_chain_nat`, etc.) that may already be loaded for unrelated reasons (Docker itself, firewalld). wg-easy's container ships the **legacy** `iptables`/`ip6tables` binaries internally (note the `(legacy)` in its error output), which specifically require the older `iptable_nat`/`ip6table_nat` modules — loaded independently of whatever the host's own `iptables` command uses. Loading one does not imply the other is loaded; check both explicitly with `lsmod | grep -w iptable_nat` and `lsmod | grep -w ip6table_nat`.

**`You can't log in with an insecure connection. Use HTTPS.`**
wg-easy v15 refuses admin login over plain HTTP by default. Since this admin UI is intentionally LAN-only (never exposed via HTTPS/Cloudflare), set `INSECURE: "true"` in the container's environment to allow HTTP login.

**Client traffic reaches the server (handshake succeeds, `wg show` reports data received) but zero/near-zero data ever gets sent back, and `iptables -t nat -L POSTROUTING -n -v` shows 0 packets matched on the MASQUERADE rule**
The MASQUERADE rule targets a hardcoded `eth0`, which doesn't exist on this host (real interface has a different name, e.g. `wlp13s0`). The `WG_DEVICE` environment variable does **not** fix this in v15 despite some online guides suggesting it — it must be changed via **Admin Panel → Interface → Device** in the web UI. Confirm the fix by checking `PostUp` in the generated config no longer says `eth0`, then do a full container recreate (not just `docker restart`) since `PostUp` only re-runs when the interface comes up fresh.

**Even after the Device fix, traffic still doesn't route (or intermittently large downloads/pages hang)**
Check for **firewalld** (or your distro's firewall manager) blocking masquerade at a layer separate from wg-easy's own iptables rules — see Prerequisites step 4. This was the single most non-obvious gotcha hit building this: everything *looked* correctly configured in `iptables -L`, but firewalld's own nftables-based zone policy silently dropped the NAT'd traffic anyway.

**Interface has no IP address at all (`ip addr show wg0` shows no `inet`/`inet6` lines), despite `wg-quick up` logs showing the `ip address add` command running successfully, causing 100% packet loss even for a direct ping to another peer's tunnel IP**
Caused here by a stale, orphaned interface + policy routing rule left behind from an *unrelated* prior WireGuard-based tool (a different VPN experiment on the same host, cleaned up abruptly without graceful teardown). Check for leftover interfaces and `ip rule` entries referencing fwmarks you don't recognize:
```bash
ip link show   # look for unexpected WireGuard-style interfaces (wt0, wg1, etc.)
ip -6 rule show   # look for rules referencing an fwmark not from this service
```
Remove any found: `sudo ip link delete <iface>` and `sudo ip -6 rule del <the exact rule text>`. This is why a genuinely clean host matters when running multiple WireGuard-based tools over time — always fully tear down (not just `docker rm -f`) an old VPN experiment before starting a new one on the same host.

**Confusing the client-side `allowed_ips` with the server-side `server_allowed_ips` field**
wg-easy's database has *two* similarly-named fields per client: `allowed_ips` (what the **client** routes into the tunnel — this is what you want for split-tunnel setups) and `server_allowed_ips` (what source IPs the **server** accepts from that peer — a different, narrower-purpose field, normally left as its default). The web UI's "Allowed IPs" edit field maps to the client-side one; if a change doesn't seem to affect routing behavior, verify which field actually changed via the database query shown in "Creating Clients" above.

## Data Paths

| Path | Purpose | Backed Up |
|------|---------|-----------|
| `service_data/data/wg-easy/wg0.conf` | Generated WireGuard server config (do not edit directly — overwritten on every start) | Yes — `down` auto-snapshots |
| `service_data/data/wg-easy/wg-easy.db` | SQLite database — all client definitions, admin credentials, interface settings | Yes — `down` auto-snapshots |

## See Also

- [wg-easy official docs](https://wg-easy.github.io/wg-easy/latest/)
- [WireGuard official site](https://www.wireguard.com/) (client app downloads)
