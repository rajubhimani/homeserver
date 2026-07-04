# Portainer CE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Docker container management UI.
**Port:** `9000` (HTTP) or `9443` (HTTPS)

## Setup

```bash
cp portainer/.env.example portainer/.env
sh homeserver.sh dev up portainer
```

## First login

Create the admin account on first visit — the setup prompt times out after a few minutes, so don't leave it sitting.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
