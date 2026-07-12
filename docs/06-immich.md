# 06 — Immich

[← Nextcloud](05-nextcloud.md) | [Home](../setup.md) | [Next: Landing Page →](07-landing.md)

---

```bash
mkdir -p ~/homeserver/immich
cd ~/homeserver/immich
cp .env.example .env
# edit .env: set UPLOAD_LOCATION, IMMICH_SECRET, DB_PASSWORD, DB_URL
uv run homeserver.py dev up immich
```

**Cloudflare path:** open `https://immich.yourdomain.com`
**Tailscale path:** open `http://100.x.x.x:2283`

> ⚠️ Immich does not support creating the admin account via env vars — use the browser on first launch.

**Full setup detail (env var reference, ML setup, mobile app config, architecture, troubleshooting) lives in [`docs/services/immich.md`](services/immich.md)** — this page is just the walkthrough step to get it running.

---

[← Nextcloud](05-nextcloud.md) | [Home](../setup.md) | [Next: Landing Page →](07-landing.md)
