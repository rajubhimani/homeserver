# Listmonk

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted newsletter and mailing list manager — single Go binary, Postgres-backed.
**Port:** `8127` (host) → `9000` (container) | **Data:** `service_data/data/listmonk/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~53MB total (app 33 + db 19)

## Setup

```bash
cp services/listmonk/.env.example services/listmonk/.env
# set POSTGRES_PASSWORD and LISTMONK_ADMIN_PASSWORD
uv run homeserver.py dev up listmonk
```

Open `https://listmonk.<domain>/` (or `http://<host>:8127` in dev) and log in with `LISTMONK_ADMIN_USER`/`LISTMONK_ADMIN_PASSWORD`.

## Registration

No public signup — the super admin account is created automatically on first start from the `LISTMONK_ADMIN_USER`/`LISTMONK_ADMIN_PASSWORD` env vars; further users are added from inside the app.

## Using it day to day

Everything below is web-UI only (`https://listmonk.<domain>/`), no client app or device to point at anything — Listmonk sends email *to* subscribers, nothing connects *to* Listmonk itself. Confirmed against Listmonk's own current docs.

- **SMTP (do this first — no campaign send works without it):** Settings → SMTP → add a server, toggle **Enabled** on, save. Listmonk ships with no SMTP server configured out of the box (see Notes below) and isn't wired to this stack's Mailpit automatically the way calcom/homebox are via env vars — wire it up yourself in the UI instead:
  - **For local testing**, point it at this stack's Mailpit container: Host `mailpit`, Port `1025`, no username/password, no TLS. Use the **Send Test E-mail** button on the same screen, then check `https://mailpit.<domain>/` for the message — confirms the whole pipeline works before touching a real provider.
  - **For real delivery**, replace those with a real SMTP provider's host/port/credentials (e.g. `smtp.gmail.com:587` with an app password, or any transactional-email provider). You can save multiple SMTP configs; only one is active at a time, so this is also how to switch providers later.
- **Create a list:** Lists → New. Choose **Public** or **Private**, and **Single** or **Double** opt-in (double sends a confirmation email before a subscriber counts as subscribed — needs working SMTP to actually land).
- **Import subscribers:** Subscribers → Import. Upload a CSV (or paste plain text) with at minimum an `email` column, assign the import to one or more lists, pick the subscription status. Existing lists can also be grown one-by-one from Subscribers → Add subscriber.
- **Create and send a campaign:** Campaigns → New Campaign. Pick the target list(s), write the content (rich-text editor, plain text, or raw HTML/Markdown), use **Send a test email** to check rendering first, then **Schedule** or **Send** to actually deliver.

## Notes

- The container's `command:` runs `--install --idempotent`, then `--upgrade`, then starts the server, every time it starts — this is the officially documented pattern (safe to repeat; install/upgrade are no-ops once already applied) rather than a one-time manual step like Wallabag needs.
- Uploaded media (campaign images etc.) lives under `service_data/data/listmonk/uploads/`.
- Health endpoint: `/` — `/api/health` returns `403 Forbidden` on a plain unauthenticated request (likely an Origin/Referer check on API routes), so the compose healthcheck and landing-page health route both just check the root page loads instead.
- SMTP isn't configured out of the box — set it up from inside the app (Settings → SMTP) before sending real campaigns.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
