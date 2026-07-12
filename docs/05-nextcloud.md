# 05 — Nextcloud

[← Reverse Proxy](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)

---

```bash
mkdir -p ~/homeserver/nextcloud
cd ~/homeserver/nextcloud
cp .env.example .env
# edit .env: set DATA_ROOT, USER_DATA_ROOT, POSTGRES_PASSWORD, NEXTCLOUD_ADMIN_PASSWORD
uv run homeserver.py dev up nextcloud
```

**Cloudflare path:** open `https://nextcloud.yourdomain.com`
**Tailscale path:** open `http://100.x.x.x:8081`

Login with your admin credentials.

**Full setup detail (env var reference, external storage, family accounts, architecture, troubleshooting) lives in [`docs/services/nextcloud.md`](services/nextcloud.md)** — this page is just the walkthrough step to get it running.

---

[← Reverse Proxy](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)
