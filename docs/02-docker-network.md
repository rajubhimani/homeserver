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

Every `compose.yml` in this stack references it as:

```yaml
networks:
  homeserver:
    external: true
```

> If you ever get `network homeserver not found`, re-run `docker network create homeserver`.

---

[← Data Drive](01-data-drive.md) | [Home](../setup.md) | [Next: Access Setup →](03-access.md)
