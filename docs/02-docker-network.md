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
docker network create homeserver
```

> `homeserver.sh` auto-creates the network if missing — you only need to run this manually on a fresh machine before the first `up`.

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
