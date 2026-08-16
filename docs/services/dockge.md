# Dockge

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Docker Compose stack manager UI.
**Port:** `5001` | **Data:** `service_data/data/dockge/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~132MB

## Setup

```bash
cp services/dockge/.env.example services/dockge/.env
# set DOCKGE_STACKS_DIR to an absolute path and mkdir -p it before starting
uv run homeserver.py dev up dockge
```

## Notes

- `DOCKGE_STACKS_DIR` must be an absolute path — relative paths silently break stack management
- Only manages stacks it created itself; use Portainer to manage existing running containers it didn't create

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
