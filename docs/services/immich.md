# Immich

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Photo management, replaces Google Photos.
**Port:** `2283` (host) → `2283` (container, `immich-server`)

## Setup

```bash
cp immich/.env.example immich/.env
sh homeserver.sh dev up immich
```

## First login

Admin account is created on first browser visit — no env var needed.

## Notes

- Mobile app: connect to `https://immich.yourdomain.com` or `https://photos.yourdomain.com`
- ML (face recognition) is opt-in: `sh homeserver.sh dev up immich --profile ml`
- Uses a custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`) — see the Postgres tuning section in `CLAUDE.md` for why its `command:` override must keep `-c config_file=/etc/postgresql/postgresql.conf` as the first flag

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
