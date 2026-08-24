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

Router UIs vary enormously. On this homeserver's router (Sercomm AOT-4221SR, an Airtel-provided ONT/router), the only available control was a coarse **Security Level: Low/Medium/High** toggle (no granular per-port IPv6 rule option existed) — setting it to **Low** was sufficient to let the WireGuard handshake through. If your router has a proper IPv6 firewall/pinhole section, use that instead to open only the specific port rather than lowering overall security.

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
| The whole home LAN | Your LAN's subnet, e.g. `192.168.1.0/24` (check `ip route show default` on the homeserver, or your router's LAN settings, for your actual subnet) |
| Just the homeserver's Docker containers | The Docker bridge subnet, e.g. `172.18.0.0/16` (check with `docker network inspect homeserver --format '{{.IPAM.Config}}'`) |
| One specific device only (e.g. just a NAS, just one server) | That device's single IP with a `/32` suffix, e.g. `192.168.1.50/32` |
| A few specific devices/services, nothing else | List each one individually, comma-separated, each with `/32` — e.g. `192.168.1.50/32, 192.168.1.60/32` |

**In practice, for a firm/team setting**, this means you decide per-person what they should reach — e.g. an accountant might only need `192.168.1.50/32` (just the finance server), while an IT admin might get the whole LAN. There's no single "correct" scope — it's your call per client, based on what that person's role actually needs.

### The three example profiles used in this deployment

| Profile | Allowed IPs | Use case |
|---|---|---|
| `myphone` | *(left unset — defaults to)* `0.0.0.0/0, ::/0` | Routes ALL internet traffic through home — gives your home's public IP, enables content filtering, but adds latency to every request (see Performance Notes) |
| `myphone-lan` | `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 192.168.1.0/24` (VPN subnet + home LAN subnet) | Reach every homeserver service + anything else on the home network, general internet stays on the device's own fast connection |
| `myphone-docker` | `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 172.18.0.0/16` (VPN subnet + Docker bridge subnet) | Narrower — only the homeserver's own Docker containers, not other LAN devices |

**Steps per client:**
1. Admin Panel → **New Client** → name it (e.g. `myphone-lan`) → Save
2. Click the new client to edit it → find **Allowed IPs** field → set to whatever scope this person/device needs (see above) → Save
3. Click the client's **QR code** icon → scan into the WireGuard app on the target device (or download the `.conf` file directly for desktop platforms)

**Worked example — setting up `myphone-lan` and `myphone-docker`:**
1. Admin Panel → New Client → name `myphone-lan` → Save
2. Edit it → Allowed IPs → paste: `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 192.168.1.0/24` → Save
3. Repeat for `myphone-docker` with: `10.8.0.0/24, fdcc:ad94:bacf:61a4::/64, 172.18.0.0/16`
4. Get each one's QR code, scan into the WireGuard app — they appear as two additional *separate* saved tunnels alongside the original `myphone` (full-tunnel) one, so switching is just toggling which one is active

**Verifying the config took effect** (server-side check, since the Allowed IPs field here is easy to confuse with a *different* field of the same name that serves the opposite purpose — see Troubleshooting). Actual output from this deployment, confirming both were set correctly:
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
(2, 'myphone-docker', '["10.8.0.0/24","fdcc:ad94:bacf:61a4::/64","172.18.0.0/16"]', '[]')
(3, 'myphone-lan', '["10.8.0.0/24","fdcc:ad94:bacf:61a4::/64","192.168.1.0/24"]', '[]')
```
(`myphone`'s `allowed_ips` is `None` — confirms it correctly falls back to the full-tunnel default rather than being unset/broken.)

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
