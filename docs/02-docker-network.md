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
docker network create --subnet 172.19.0.0/16 homeserver
```

> `homeserver.py` auto-creates the network if missing, with this same pinned subnet (`HOMESERVER_SUBNET` in `homeserver.py`) — you only need to run this manually on a fresh machine before the first `up`.
>
> **The subnet is pinned on purpose.** The Browser Hub's containers have fixed IPs inside it (`172.19.255.240`–`.250`, `ipv4_address` in each browser's `compose.yml`, mirrored in `services/nginx-plain/browser-lan-block.sh`). When the network was recreated without `--subnet` (2026-10-05), Docker picked `172.19.0.0/16` instead of the old `172.18.0.0/16`, and every browser then failed to create with `no configured subnet contains IP address 172.18.255.x`. If you ever change the subnet, change `HOMESERVER_SUBNET`, the browsers' IPs and the script together; `tests/test_repo_invariants.py` checks they agree. `homeserver.py` warns at start if the live network is on a different subnet.

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
