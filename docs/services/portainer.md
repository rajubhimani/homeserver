# Portainer CE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Docker container management UI.
**Port:** `9000` (HTTP) or `9445` (HTTPS, host-mapped off the image's default `9443` — that port is claimed locally by the `kind` k8s-pilot cluster's ingress) | **Requires:** — | **Memory:** no hard limit set; measured idle ~17.5MB

## Setup

```bash
cp services/portainer/.env.example services/portainer/.env
uv run homeserver.py dev up portainer
```

## First login

Create the admin account on first visit — the setup prompt times out after a few minutes, so don't leave it sitting.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
