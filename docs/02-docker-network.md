# 02 — Docker + Shared Network

[← Data Drive](01-data-drive.md) | [Home](../setup.md) | [Next: Access Setup →](03-access.md)

---

## Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh

sudo usermod -aG docker $USER
# log out and back in, then verify
docker --version
docker compose version

sudo systemctl enable docker
```

## Create shared network

All services communicate via a single external Docker network. Create it once before starting any compose file.

```bash
docker network create --subnet "$(grep ^HOMESERVER_SUBNET .env | cut -d= -f2)" homeserver
```

> `homeserver.py` auto-creates the network if missing, with this same pinned subnet — you only need to run this manually on a fresh machine before the first `up`.
>
> **The subnet is pinned on purpose, in one place: `HOMESERVER_SUBNET` in the root `.env`** (default `172.19.0.0/16`, see `.env.example`). `homeserver.py` creates the network with it and derives the Browser Hub's fixed IPs from it (`BROWSER_NET`, the subnet's `x.y.255` block; each browser's `compose.yml` says `ipv4_address: ${BROWSER_NET}.<n>`, `.240`–`.250`). `services/nginx-plain/browser-lan-block.sh` reads the live network, so nothing repeats the subnet. When the network was recreated without `--subnet` (2026-10-05), Docker picked `172.19.0.0/16` instead of the old `172.18.0.0/16` and every browser failed to create with `no configured subnet contains IP address 172.18.255.x`. `homeserver.py` warns at start when the live network is on a different subnet, and `tests/test_repo_invariants.py` fails if a compose file hard-codes a fixed IP.

### Which subnet is Docker using?

```bash
docker network inspect homeserver --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'   # this stack's network
docker network ls -q | xargs docker network inspect --format '{{.Name}}  {{range .IPAM.Config}}{{.Subnet}}{{end}}' | sort -k2   # every network
ip -4 -br addr | grep -E 'docker0|br-'                                                  # the same, as the host sees it
grep HOMESERVER_SUBNET .env                                                             # what the stack expects
```

The first command and the `.env` line must agree. If they don't, `homeserver.py` warns on every start. Every Compose project that has no `external` network also gets its own `<project>_default` network from the same `172.17`–`172.31` pool, in creation order, so which subnet a *new* network gets depends on what already exists. That is why this one is pinned instead of left to Docker.

**Changing the subnet on a running host:** set `HOMESERVER_SUBNET` in `.env`, then `uv run homeserver.py prod down all`, `docker network rm homeserver`, `uv run homeserver.py prod up core` (or your tiers). Choose a `/16` no other network above uses, then re-run `sudo bash services/nginx-plain/browser-lan-block.sh undo` (before) and `apply` (after) so the browsers' LAN-isolation rules follow the new IPs.

Every `compose.yml` in this stack references it as:

```yaml
networks:
  homeserver:
    external: true
```

## Network commands reference

```bash
# List all networks
docker network ls

# Inspect the homeserver network (shows connected containers)
docker network inspect homeserver

# Create the network (if missing)
docker network create homeserver

# Delete the network (all containers must be stopped first)
docker network rm homeserver
```

---

[← Data Drive](01-data-drive.md) | [Home](../setup.md) | [Next: Access Setup →](03-access.md)
