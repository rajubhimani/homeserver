# 09 — Firewall

[← Maintenance](08-maintenance.md) | [Home](../setup.md) | [Next: New Services →](10-new-services.md)

---

## The one rule that matters

**Default-deny inbound. Explicitly allow only the ports something actually needs open, from only the sources that need them.** Everything else in this doc is detail in service of that one rule.

This matters more than most guides admit, because of one fact people don't internalize until it bites them: **a NAT'd IPv4 connection accidentally protects you even with a sloppy host firewall — a real, routable IPv6 address does not.** Behind IPv4 CGNAT, nothing from the internet can reach your box directly no matter what your host firewall allows, because there's no public IPv4 address pointing at it at all. The moment your host has a real, globally-routable IPv6 address (which most modern ISPs now hand out, mobile carriers especially), that accidental protection is gone — every port your host firewall allows inbound is now genuinely reachable from anywhere on the internet, on that address, regardless of what your router does. Most people never notice this transition happened.

---

## Case study: how this stack's own host got exposed (2026-09-04)

This isn't hypothetical — it happened on this exact deployment, caught by a routine security review, not by an incident. Recorded here so the mistake doesn't get repeated on a rebuild.

**Setup:** [wg-easy](services/wg-easy.md) needs to accept inbound WireGuard connections from the internet. This host is behind Airtel CGNAT on IPv4 (no public IPv4 to port-forward to at all), but has a real, routable IPv6 `/64` — so wg-easy binds WireGuard's UDP port directly to the host's real IPv6 address, sidestepping CGNAT entirely (see wg-easy's doc for the full reasoning).

**What went wrong:** the home router had no granular per-port IPv6 firewall rule — only a blunt `Security Level: Low/Medium/High` toggle — so `Low` had to be set globally just to let the WireGuard handshake through. That alone would have been a contained, acceptable trade-off. The actual damage came from a *second*, unrelated fact discovered only once IPv6 traffic could reach the host at all: **this host's own firewalld default zone had `1025-65535/tcp` and `1025-65535/udp` wide open** — a leftover from some past, forgotten need, harmless for years because IPv4 CGNAT made it moot. Combined with a real public IPv6 address, that single overly-broad rule meant almost every high port on the host was directly reachable from the internet:

- **GNOME Remote Desktop's RDP server** (port 3389) — one of the most heavily brute-forced protocols that exists, wide open with credential auth as the only gate.
- **Every dev-mode Docker service port** — this stack's `compose.dev.yml` files bind `0.0.0.0:<port>` for LAN convenience (see "The Docker / IPv6 blind spot" below for why that also means IPv6). Portainer's admin UI (9000), Immich (2283), Authentik's own HTTPS port (9444), and dozens more were all reachable directly, completely bypassing the Cloudflare Tunnel + nginx-plain + Authentik forward-auth this whole stack is built around.

None of this was WireGuard's fault — WireGuard's protocol is specifically designed to be safely exposed directly to the internet (it never responds to an unauthenticated packet, so it's invisible to internet-wide scanners; no banner, no handshake reply). The exposure came entirely from an unrelated, pre-existing permissive firewall rule that had simply never mattered before.

**The fix, in order:**
1. Switched the running stack from `dev` mode to `prod` mode (`compose.prod.yml` binds every container port to `127.0.0.1` only — see "Compose file pattern" in the root `CLAUDE.md`). This alone closed every Docker-published port.
2. Disabled GNOME Remote Desktop's RDP entirely where it wasn't actively used, and where it *was* used (a Guacamole connection gatewaying into this same host), left it running but relying on the Docker-bridge-only reachability rather than the WAN interface (see "Guacamole-style gateways" below).
3. Replaced the host's `1025-65535/tcp`+`udp` blanket allow with an explicit allow of only the one port that genuinely needs to be reachable from the internet: WireGuard's `51820/udp`.

---

## Checking your own exposure

Run this on any host before assuming your firewall is fine — takes under a minute, no special tools beyond `ip`/`ss`/`firewall-cmd` (all present on any modern Linux distro). Every output block below is **real output captured on this host** while diagnosing the incident in the case study above, not a mockup — so you can compare your own output line-by-line against what a genuinely exposed host looks like.

**Step 1 — do you have a real, routable IPv6 address?**

```bash
ip -6 addr show scope global
```
```
3: wlp13s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP qlen 1000
    inet6 2401:4900:1f3f:17d9:b655:9552:2586:33e5/64 scope global dynamic noprefixroute
       valid_lft 86150sec preferred_lft 86150sec
29: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1280 state UNKNOWN qlen 1000
    inet6 fdcc:ad94:bacf:61a4::cafe:1/112 scope global
       valid_lft forever preferred_lft forever
```
**Reading this:** the `wlp13s0` line is the real interface — `scope global` means this address is genuinely routable from the public internet, not a `fe80::...` link-local address that only works on the LAN. That's your actual attack surface. The `wg0` line is WireGuard's own internal VPN subnet (`fdcc:...`) — a different, unrelated address, not something the internet can route to on its own. If your only `scope global` line were on a `wg0`/`tun0`/`tailscale0`-style interface instead of your real NIC, you would not have this problem at all.

**Step 2 — what's actually listening on IPv6, right now?**

```bash
ss -tln6   # TCP
ss -uln6   # UDP
```
```
State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0      4096           [::1]:631          [::]:*
LISTEN 0      4096            [::]:5355         [::]:*
LISTEN 0      5                  *:3389            *:*
```
```
State  Recv-Q Send-Q                      Local Address:Port  Peer Address:Port
UNCONN 0      0                                   [::1]:323           [::]:*
UNCONN 0      0      [fe80::7378:8322:7ed:9113]%wlp13s0:546           [::]:*
UNCONN 0      0                                    [::]:51820         [::]:*
UNCONN 0      0                                    [::]:5353          [::]:*
UNCONN 0      0                                    [::]:5355          [::]:*
```
**Reading this:** go line by line and ask "should this be reachable from the raw internet?"
- `[::1]:631` — CUPS printing, bound to `::1` (loopback only). Not reachable from outside no matter what your firewall does. Safe.
- `[::]:5355`, `[::]:5353` — LLMNR/mDNS, local name resolution. Low-value to an attacker, standard on any desktop.
- **`*:3389`** — this is the line that mattered here. `*` means every interface, IPv4 and IPv6 both, including the real address from Step 1. This turned out to be GNOME Remote Desktop's RDP server — one of the most heavily brute-forced protocols on the internet.
- `[::]:51820` (UDP) — WireGuard. This one is *supposed* to be reachable from the internet — its protocol design never replies to an unauthenticated packet, so it's invisible to internet-wide scanners.

**Step 3 — what does your host firewall actually allow inbound?**

```bash
firewall-cmd --list-all              # Fedora/RHEL (firewalld) — no sudo needed to read
```
```
FedoraWorkstation (default, active)
  target: default
  interfaces: wlp13s0
  sources:
  services: dhcpv6-client samba-client ssh
  ports: 1025-65535/udp 1025-65535/tcp
  ...
```
**Reading this:** the `ports:` line is the smoking gun — `1025-65535/udp 1025-65535/tcp` allows **every port from 1025 to 65535** in from the internet on `wlp13s0` (the real interface from Step 1). Combined with Step 2's `*:3389`, that's the whole bug in one line: nothing about WireGuard required this, it was an unrelated, long-forgotten rule that only became dangerous once a real IPv6 address made it internet-facing. The `services:` line lists named, pre-defined allow rules (`ssh`, etc.) — separate from the broad port range, and fine to leave as-is (check `systemctl is-active sshd` first — if it's `inactive`, that particular allow rule isn't even load-bearing).

If your Step 2 shows more than you expected — an admin panel, a database port, a remote-desktop protocol, anything you didn't deliberately decide to expose — and your Step 3 shows a similarly broad allow range, you have the exact same bug. The fix is below.

## The Docker / IPv6 blind spot

Most people assume `docker run -p 8080:8080` or a compose `ports: ["8080:8080"]` only publishes on IPv4, because that's the common mental model from years of NAT'd IPv4-only hosting. **On a host with IPv6 enabled, Docker publishes to the IPv6 wildcard (`[::]`) too, automatically, with zero extra configuration.** This is exactly what turned "convenient LAN-only dev binding" into "every dev port on the public internet" in the case study above. If your host has a real IPv6 address, treat every `0.0.0.0`-bound container port as if it were bound to your public IP directly — because on IPv6, it is.

This stack's answer is the dev/prod compose split described in the root `CLAUDE.md` ("Compose file pattern"): `compose.dev.yml` binds `0.0.0.0` for LAN convenience, `compose.prod.yml` binds `127.0.0.1` only. **Once a host has a real public IPv6 address, running in `dev` mode day-to-day is no longer just a LAN convenience — it's a public exposure**, and `prod` mode should be the default, with `dev` mode used only for short, deliberate local-testing sessions.

## Guacamole-style gateways: firewall by network path, not just by port

If you use [Guacamole](services/guacamole.md) (or any similar browser-based remote-desktop gateway) to reach a VNC/RDP/SSH service running on the *same host* the gateway itself runs on, that target service still needs to be listening — but it does **not** need to be reachable from the WAN interface. Guacamole's `guacd` container reaches the host over the internal Docker bridge network, not through the host's real network interface at all. That means you can (and should) firewall the WAN-facing interface to reject that port entirely, while the Guacamole path keeps working untouched — the two are on genuinely different network paths, not just different "logical" access methods. Don't reason about this as "the port needs to be open because Guacamole needs it" — it needs to be open on the Docker bridge, not on the interface facing the internet.

## Default-deny inbound: concrete commands

### Fedora / RHEL (firewalld) — this host's setup, real before/after

```bash
firewall-cmd --get-active-zones
```
```
FedoraWorkstation (default)
  interfaces: wlp13s0
```
This tells you which zone actually governs your real interface — `<your-zone>` in every command below is `FedoraWorkstation` on this host; yours may be named `public`, `home`, `FedoraServer`, etc.

```bash
# Remove the overly wide range (same shape as the case study's bug)
sudo firewall-cmd --zone=FedoraWorkstation --remove-port=1025-65535/udp --permanent
sudo firewall-cmd --zone=FedoraWorkstation --remove-port=1025-65535/tcp --permanent

# Add back only the specific port something genuinely needs from the internet
sudo firewall-cmd --zone=FedoraWorkstation --add-port=51820/udp --permanent

sudo firewall-cmd --reload
firewall-cmd --zone=FedoraWorkstation --list-all
```
```
FedoraWorkstation (default, active)
  target: default
  interfaces: wlp13s0
  sources:
  services: dhcpv6-client samba-client ssh
  ports: 51820/udp
  ...
```
**Reading this:** compare the `ports:` line to Step 3 above — `1025-65535/udp 1025-65535/tcp` is gone, replaced with exactly `51820/udp`. The `services:` line (`ssh`, etc.) is untouched, since `--remove-port`/`--add-port` only ever touches the explicit port-range allow, not named-service allows. Re-running `ss -tln6`/`ss -uln6` afterward will still show the same sockets *bound* (a program can always bind a port on its own machine) — what changes is that nothing from the internet can reach them anymore except `51820/udp`. Socket state and firewall reachability are two different layers; don't expect `ss` output to change from this step, `firewall-cmd --list-all`'s `ports:` line is the thing to check.

Check `systemctl is-active sshd` before assuming SSH access is load-bearing — if it prints `inactive`, that named `ssh` allow rule isn't doing anything right now either way.

### Debian / Ubuntu (ufw)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
```
```
Default incoming policy changed to 'deny'
(be sure to update your rules accordingly)
Default outgoing policy changed to 'allow'
(be sure to update your rules accordingly)
```
This is the actual default-deny switch — from this point on, nothing gets in unless a rule below explicitly allows it.

```bash
# Only what genuinely needs to be reachable from the internet
sudo ufw allow 51820/udp comment 'WireGuard'
```
```
Rule added
Rule added (v6)
```
Ubuntu's `ufw` adds matching IPv4 *and* IPv6 rules for a bare port like this — the `(v6)` line is exactly the IPv6-reachability half that this whole doc is about; don't mistake the two-line output for an error or a duplicate.

```bash
# LAN-only services — scope by source, not just by port
sudo ufw allow from 192.168.1.0/24 to any port 22 comment 'SSH LAN only'

sudo ufw enable
sudo ufw status verbose
```
```
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
51820/udp                  ALLOW IN    Anywhere
51820/udp (v6)             ALLOW IN    Anywhere (v6)
22/tcp                     ALLOW IN    192.168.1.0/24             # SSH LAN only
```
**Reading this:** `Default: deny (incoming)` at the top confirms the switch took; every line under `To / Action / From` is now the complete allow-list — if a port you care about isn't listed here, it's blocked, full stop. `Anywhere (v6)` on the WireGuard line is intentional (it needs to accept connections from any internet client); the SSH line's `192.168.1.0/24` (not `Anywhere`) is what actually scopes it to your LAN instead of the whole internet.

> Adjust the LAN subnet and any service-specific ports to your own setup — the point isn't to copy this list, it's to end up with a short, explicit, reasoned allow-list instead of a wide default-open range.
>
> Sources: [UFW Firewall Commands with Examples on Ubuntu](https://computingforgeeks.com/common-ufw-firewall-commands-with-examples/), [UFW — Official Ubuntu Documentation](https://help.ubuntu.com/community/UFW)

### Windows (Windows Defender Firewall)

Same principle, PowerShell instead of a Linux CLI — run these from an elevated (Administrator) PowerShell prompt.

```powershell
# Check the current default inbound action per profile first
Get-NetFirewallProfile | Select-Object Name, DefaultInboundAction, DefaultOutboundAction
```
```
Name    DefaultInboundAction DefaultOutboundAction
----    -------------------- ---------------------
Domain                 Allow                 Allow
Private                Allow                 Allow
Public                 Allow                 Allow
```
If any profile shows `Allow` for `DefaultInboundAction`, that profile has no default-deny at all — anything without an explicit *block* rule gets in. This is Windows' out-of-the-box posture on most consumer installs.

```powershell
# Switch to default-deny inbound on every profile
Set-NetFirewallProfile -DefaultInboundAction Block -DefaultOutboundAction Allow

# Add back only the specific port something genuinely needs from the internet
New-NetFirewallRule -DisplayName "WireGuard" -Direction Inbound -Protocol UDP -LocalPort 51820 -Action Allow -Profile Any
```
```
Name                  : {a1b2c3d4-...}
DisplayName           : WireGuard
Description           :
DisplayGroup          :
Group                 :
Enabled               : True
Profile               : Any
Direction             : Inbound
Action                : Allow
```
**Reading this:** re-run the `Get-NetFirewallProfile` check above — `DefaultInboundAction` should now read `Block` for every profile. The `New-NetFirewallRule` output confirms one specific rule now exists as an exception to that block; `Enabled: True` and `Action: Allow` are the two fields that matter, everything else is metadata. Verify the full rule set anytime with `Get-NetFirewallRule -Direction Inbound -Action Allow | Select-Object DisplayName, Enabled`.
>
> Sources: [Manage Windows Firewall With the Command Line — Microsoft Learn](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure-with-command-line), [New-NetFirewallRule — Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)

## SSH hardening — key-only auth

Applies regardless of which firewall rules are active — the firewall controls *where* port 22 is reachable from, this controls *how* anyone at those addresses can authenticate once they reach it.

```bash
sudo grep -i '^PasswordAuthentication' /etc/ssh/sshd_config   # should read: PasswordAuthentication no
sudo systemctl reload sshd                                    # after editing
```

**Root logging in over SSH from a `172.x.0.0/16`-range address is expected, not a compromise** if you run [Coolify](services/coolify.md) — it SSHes into the Docker host as root (key-only, same key every time) to orchestrate deployments outside the Docker socket. See `docs/services/coolify.md`'s SSH setup steps for why. Any root SSH session from an address *outside* your Docker bridge subnets, or any password-based auth attempt at all, is not this and is worth investigating (`journalctl -u sshd`, `last -a`).

## Verify

```bash
# Confirm no container port is bound wider than intended
docker ps --format '{{.Names}} -> {{.Ports}}' | grep -E '0\.0\.0\.0|:::'
```
```
(no output)
```
Empty output is the pass condition here — it means every published container port is loopback-only (i.e. `prod` mode). Any line printed is a container still reachable beyond `127.0.0.1`.

```bash
firewall-cmd --zone=FedoraWorkstation --list-all   # or your platform's equivalent from above
```
```
FedoraWorkstation (default, active)
  target: default
  interfaces: wlp13s0
  sources:
  services: dhcpv6-client samba-client ssh
  ports: 51820/udp
  ...
```
This is the actual real `ports:` line captured on this host right after applying the fix — confirm yours reads as a short, explicit list too, not a range.

```bash
# Re-run the IPv6 listening check from "Checking your own exposure" above.
# Note: sockets that were already bound (like RDP's) will still show here —
# ss reports what's *bound*, not what's *reachable*. The firewall list above
# is what actually determines reachability now, not this output.
ss -tln6
ss -uln6

# From OUTSIDE your own network (e.g. phone on mobile data, not your WiFi) —
# only ever scan hosts/addresses you own — confirm a port you closed is now
# genuinely unreachable rather than just unreachable from inside your LAN:
nc -zv -w3 <your-public-ip-or-hostname> <port>   # should time out / refuse
```

---

## Moving from `dev` to `prod` mode

This stack's own dev/prod split (see root `CLAUDE.md`) already does most of the port-binding work for you — the remaining job is the host firewall itself.

```bash
# Stop whatever's running in dev mode (auto-snapshots everything first)
uv run homeserver.py dev down all

# Bring it back with loopback-only bindings
uv run homeserver.py prod up all      # or 'up core', 'up <tier>', etc.
```

After switching, re-run the "Verify" checks above — `dev` mode's LAN convenience is fine for short, deliberate local testing, but shouldn't be how a host with a real public IPv6 address runs day-to-day.

---

## Restoring fast direct access, safely: the `10.8.0.1` pattern

Locking every service to `127.0.0.1` closes the exposure above, but it also kills a legitimate convenience: reaching a service directly by IP:port (fast, no reverse-proxy hop) instead of always going through the public hostname. That convenience doesn't have to be sacrificed — it can be restored scoped to *only* VPN-authenticated traffic, with no new internet exposure at all.

**The pattern:** every service's `compose.prod.yml` in this stack binds each port **twice** — once to `127.0.0.1` (unchanged) and once to `10.8.0.1`, [wg-easy](services/wg-easy.md)'s own tunnel-side WireGuard address:

```yaml
services:
  jellyfin:
    ports:
      - "127.0.0.1:8096:8096"
      - "10.8.0.1:8096:8096"
```

**Why this is safe, unlike the original `1025-65535` exposure:** `10.8.0.1` lives inside `10.8.0.0/24`, WireGuard's own private tunnel subnet — there is no internet route to it at all, from anywhere, full stop. The only way a packet ever arrives addressed to `10.8.0.1` is by first completing a real WireGuard handshake (public-key authenticated) to this server. Compare that to the case study's bug, where the exposed address (`wlp13s0`'s real IPv6) genuinely is reachable by anyone on the internet with no authentication step at all — the two are not the same class of risk, even though both involve "a port besides 51820 being reachable from *some* remote client."

**What it gets you:** once connected over WireGuard (any client profile works — `10.8.0.0/24` is mandatory in every profile, see [wg-easy's Allowed IPs section](services/wg-easy.md#what-allowed-ips-actually-controls)), every service is reachable directly — `http://10.8.0.1:8096` for Jellyfin, `http://10.8.0.1:2283` for Immich, etc. (full port list: [11 — Services Reference](11-services-reference.md#port-reference)) — no Cloudflare hop, no reverse-proxy Host-header routing needed, because you're hitting the container's own port directly rather than asking nginx-plain to route by hostname. Applies whether the service is currently running or not (this is a `compose.prod.yml` binding, not a runtime toggle) — the two intentional exceptions are `cloudflared` and `crowdsec`, neither of which publishes any host port at all by design.

**Verified gotcha — this pattern needs `wg0` explicitly zoned, or it silently fails:** WireGuard's own `wg0` interface isn't automatically assigned to a firewalld zone (`firewall-cmd --get-zone-of-interface=wg0` prints `no zone` on a fresh setup). Left that way, decapsulated tunnel traffic destined for a locally-bound address like `10.8.0.1:8096` can fall through to whatever your default zone's restrictive policy is (e.g. the `51820/udp`-only rule from the case study above) and get silently dropped — the service itself will test fine from the host (`curl http://10.8.0.1:8096` succeeds locally) while a real connected client gets nothing, which looks identical to a client-side connectivity problem. Fix it once, explicitly:

```bash
sudo firewall-cmd --zone=trusted --add-interface=wg0 --permanent
sudo firewall-cmd --reload
firewall-cmd --get-zone-of-interface=wg0   # should now print: trusted
```

This is safe specifically because nothing can ever reach `wg0` without first passing WireGuard's own authentication — trusting the interface fully doesn't trust arbitrary traffic, only traffic that already proved itself. **To actually diagnose "client shows connected but nothing loads"** rather than guess: check `docker exec wg-easy wg show wg0 dump` for the peer's endpoint/handshake activity, and `ip -s link show wg0` for its RX packet counter, both before and after a retry. If neither moves at all, the packet never reached this host — that's a client/network-path problem (stale session, or an upstream firewall like the router's own IPv6 filter — see the "Confirmed on this router" note in [wg-easy's doc](services/wg-easy.md)), not this zone issue. If the counters do move but the request still fails, that's when the zone assignment above is the fix.

**Applying it to a service that doesn't have it yet:** add a second `ports:` line to that service's `compose.prod.yml`, same host port, `10.8.0.1` instead of `127.0.0.1`, then recreate it (`uv run homeserver.py prod up <service>`) — port bindings only take effect on container recreation, not a plain restart.

---

## Optional: restoring LAN-direct access (skipping the VPN entirely)

**This host's default, as configured by this doc, is that LAN devices cannot reach a service by its raw IP:port even in `dev` mode** — the WAN-interface lockdown above (`ports: 51820/udp` only) applies to *all* traffic on that interface regardless of source, LAN included, since the interface carries both your LAN traffic and your public IPv6 address and firewalld doesn't distinguish between them by default. This is intentional here — the `10.8.0.1` VPN pattern above already covers "fast direct access" safely, so there's no `dev`-mode/router-IP path left open by default.

If you specifically want LAN devices to reach `dev`-mode ports directly again (e.g. a device that can't run WireGuard, or you just don't want the VPN in the loop for local testing), the fix is a **source-scoped firewalld zone** — traffic matched by source IP takes priority over the interface-based zone, so LAN-originating requests get a more permissive zone while internet-originating requests on that same interface stay locked to just WireGuard:

```bash
sudo firewall-cmd --permanent --new-zone=lan       # skip if you already have a zone for this
sudo firewall-cmd --permanent --zone=lan --add-source=192.168.1.0/24   # your actual LAN subnet
sudo firewall-cmd --permanent --zone=lan --set-target=ACCEPT
sudo firewall-cmd --reload

firewall-cmd --get-zone-of-interface=wlp13s0   # unaffected — still your locked-down zone
firewall-cmd --list-all --zone=lan             # confirm: source-matched, target ACCEPT
```

Only do this if you've decided you actually want it — it re-widens the attack surface back to "anything on your LAN can reach dev-mode ports," which is a real trade-off, not free. Nothing about the `10.8.0.1` VPN pattern or the WAN lockdown needs this; it's purely for restoring the old router-IP:port convenience on purpose.

---

[← Maintenance](08-maintenance.md) | [Home](../setup.md) | [Next: New Services →](10-new-services.md)
