# 09 — Firewall

[← Landing Page](07-landing.md) | [Home](../setup.md)

---

## Rootless Podman — Privileged Ports

Rootless Podman cannot bind to ports below 1024. This stack handles this by remapping privileged ports to high ports on the host side, using the same pattern as nginx (80 → 8180, 443 → 8443).

Services affected and their remapped host ports:

| Service | Standard port | Host port | Protocol |
| --- | --- | --- | --- |
| nginx-plain | 80 | 8180 | HTTP |
| nginx-plain | 443 | 8443 | HTTPS |
| Stalwart SMTP | 25 | 8025 | TCP |
| Stalwart submission | 587 | 8587 | TCP |
| Stalwart SMTPS | 465 | 8465 | TCP |
| Stalwart IMAP | 143 | 8143 | TCP |
| Stalwart IMAPS | 993 | 8993 | TCP |

Port 4190 (Sieve) and all admin/UI ports bind directly — they are above 1024.

### Forwarding standard ports to remapped ports

External clients and mail servers connect to the standard ports. A firewall redirect rule on the host transparently forwards them to the remapped ports.

**Fedora / RHEL (firewalld):**
```bash
sudo firewall-cmd --permanent --add-forward-port=port=25:proto=tcp:toport=8025
sudo firewall-cmd --permanent --add-forward-port=port=587:proto=tcp:toport=8587
sudo firewall-cmd --permanent --add-forward-port=port=465:proto=tcp:toport=8465
sudo firewall-cmd --permanent --add-forward-port=port=143:proto=tcp:toport=8143
sudo firewall-cmd --permanent --add-forward-port=port=993:proto=tcp:toport=8993
sudo firewall-cmd --reload
```

**Ubuntu / Debian (iptables):**
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 25 -j REDIRECT --to-port 8025
sudo iptables -t nat -A PREROUTING -p tcp --dport 587 -j REDIRECT --to-port 8587
sudo iptables -t nat -A PREROUTING -p tcp --dport 465 -j REDIRECT --to-port 8465
sudo iptables -t nat -A PREROUTING -p tcp --dport 143 -j REDIRECT --to-port 8143
sudo iptables -t nat -A PREROUTING -p tcp --dport 993 -j REDIRECT --to-port 8993
# Make persistent across reboots
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

Verify the rules are active:
```bash
# Fedora
sudo firewall-cmd --list-forward-ports

# Ubuntu
sudo iptables -t nat -L PREROUTING -n -v
```

---

## The Docker / UFW problem

Docker writes iptables rules directly and **bypasses UFW entirely**. A `ufw deny 80` rule will not stop a container that has `ports: - "80:80"` — Docker opens that port regardless.

The correct fix is to **bind ports to a specific IP in the compose override**, not rely on UFW alone:

| Binding | Reachable from |
| --- | --- |
| `80:80` | Anywhere (`0.0.0.0`) |
| `127.0.0.1:80:80` | Localhost only |

This stack uses **compose override files** to manage port bindings per environment. The base `compose.yml` for each service has no `ports:` block. You add ports by merging an override at startup.

```text
nginx/
├── compose.yml          ← base (no ports)
├── compose.prod.yml     ← ports bound to 127.0.0.1
└── compose.dev.yml      ← ports bound to 0.0.0.0

nextcloud/
├── compose.yml          ← base (no ports)
└── compose.dev.yml      ← adds port 8081

immich/
├── compose.yml          ← base (no ports)
└── compose.dev.yml      ← adds port 2283
```

---

## Production — Cloudflare Tunnel

### How traffic flows

`cloudflared` makes an outbound connection to Cloudflare — no inbound ports are needed from the internet. NPM only needs to be reachable on `localhost` (where cloudflared connects to it).

### Start commands

```bash
# NPM — localhost-only ports via prod override
cd ~/homeserver/nginx
docker compose -f compose.yml -f compose.prod.yml up -d

# Nextcloud and Immich — no ports needed, NPM routes via Docker network
cd ~/homeserver/nextcloud && docker compose up -d
cd ~/homeserver/immich && docker compose up -d
cd ~/homeserver/landing && docker compose up -d
```

### UFW rules

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow from 192.168.0.0/16 to any port 22 comment 'SSH LAN'

sudo ufw enable
sudo ufw status verbose
```

> Adjust `192.168.0.0/16` to your actual LAN subnet (e.g. `192.168.1.0/24`).

### What's open

| Port | Binding | Access | Why |
| --- | --- | --- | --- |
| 22 | — | LAN only | SSH |
| 80 | `127.0.0.1` | localhost only | cloudflared → NPM |
| 443 | `127.0.0.1` | localhost only | cloudflared → NPM |
| 81 | `127.0.0.1` | localhost only | NPM admin |
| 8081, 2283 | not exposed | none | Docker-internal via homeserver network |

To reach NPM admin remotely without exposing port 81, use an SSH tunnel from your Mac:

```bash
ssh -L 8181:127.0.0.1:81 user@server-ip
# then open http://localhost:8181
```

---

## Testing — Tailscale

### How traffic flows

Services are accessed by Tailscale IP directly. Ports need to be reachable on that interface, so the dev overrides bind to `0.0.0.0`.

### Start commands

```bash
# NPM — all interfaces via dev override
cd ~/homeserver/nginx
docker compose -f compose.yml -f compose.dev.yml up -d

# Nextcloud — exposes 8081 via dev override
cd ~/homeserver/nextcloud
docker compose -f compose.yml -f compose.dev.yml up -d

# Immich — exposes 2283 via dev override
cd ~/homeserver/immich
docker compose -f compose.yml -f compose.dev.yml up -d

cd ~/homeserver/landing && docker compose up -d
```

### UFW rules

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH
sudo ufw allow from 192.168.0.0/16 to any port 22 comment 'SSH LAN'
sudo ufw allow from 100.64.0.0/10 to any port 22 comment 'SSH Tailscale'

# NPM
sudo ufw allow from 192.168.0.0/16 to any port 80 comment 'NPM LAN'
sudo ufw allow from 100.64.0.0/10 to any port 80 comment 'NPM Tailscale'

# NPM admin
sudo ufw allow from 192.168.0.0/16 to any port 81 comment 'NPM admin LAN'
sudo ufw allow from 100.64.0.0/10 to any port 81 comment 'NPM admin Tailscale'

# Nextcloud
sudo ufw allow from 192.168.0.0/16 to any port 8081 comment 'Nextcloud LAN'
sudo ufw allow from 100.64.0.0/10 to any port 8081 comment 'Nextcloud Tailscale'

# Immich
sudo ufw allow from 192.168.0.0/16 to any port 2283 comment 'Immich LAN'
sudo ufw allow from 100.64.0.0/10 to any port 2283 comment 'Immich Tailscale'

sudo ufw enable
sudo ufw status verbose
```

> `100.64.0.0/10` is the full Tailscale CGNAT range. Adjust `192.168.0.0/16` to your LAN subnet.

### What's open

| Port | Binding | Access | Why |
| --- | --- | --- | --- |
| 22 | — | LAN + Tailscale | SSH |
| 80 | `0.0.0.0` | LAN + Tailscale | NPM |
| 81 | `0.0.0.0` | LAN + Tailscale | NPM admin |
| 8081 | `0.0.0.0` | LAN + Tailscale | Nextcloud direct |
| 2283 | `0.0.0.0` | LAN + Tailscale | Immich direct |

---

## Verify

```bash
# show active UFW rules
sudo ufw status numbered

# confirm port binding (should show 127.0.0.1 for prod, 0.0.0.0 for dev)
sudo ss -tlnp | grep -E '80|443|81|8081|2283'

# test a port is blocked from another machine (should time out)
nc -zv server-ip 80
```

---

## Moving from testing to production

When you switch from Tailscale to Cloudflare Tunnel:

1. Complete [03a — Cloudflare Tunnel](03a-cloudflare.md)
2. Restart services with prod overrides:

```bash
cd ~/homeserver/nginx
docker compose -f compose.yml -f compose.dev.yml down
docker compose -f compose.yml -f compose.prod.yml up -d

cd ~/homeserver/nextcloud
docker compose down && docker compose up -d

cd ~/homeserver/immich
docker compose down && docker compose up -d
```

1. Reset and replace UFW rules:

```bash
sudo ufw reset
# apply production UFW rules above
```

---

[← Landing Page](07-landing.md) | [Home](../setup.md)
