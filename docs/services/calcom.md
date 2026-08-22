# Cal.com

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted scheduling and booking pages (Calendly alternative).
**Port:** `8129` (host) → `3000` (container) | **Data:** none beyond Postgres — the app itself is stateless | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~852MB total (app 830 + db 22)

## Setup

```bash
cp services/calcom/.env.example services/calcom/.env
# set POSTGRES_PASSWORD, NEXTAUTH_SECRET (openssl rand -base64 32),
# CALENDSO_ENCRYPTION_KEY (openssl rand -base64 24)
uv run homeserver.py dev up calcom
```

Open `https://calcom.<domain>/` (or `http://<host>:8129` in dev) and create the first account.

## Registration

Self-registration is on by default through the UI.

## Connecting a calendar and sharing a booking link

1. **Settings → Calendars** — connect Google Calendar, Outlook, or iCloud (OAuth flow for Google/Outlook). Once connected, Cal.com reads existing events from it to avoid double-booking, and can write new bookings back to it.
2. **Availability** — set a schedule (working hours, days) that determines what's actually bookable; this merges with the connected calendar's existing busy times.
3. **Event Types** — create one (e.g. "30 Minute Meeting") with its own duration/location/questions, then share its booking page URL (`https://calcom.${DOMAIN}/<your-username>/<event-type-slug>`) — this is the actual link people use to book time, embeddable on a website or dropped in an email signature.

## Notes

- `CALENDSO_ENCRYPTION_KEY` encrypts every stored integration credential (Google OAuth tokens, calendar connections). **Never change it after first run** — doing so permanently corrupts everything it encrypted.
- SMTP (`EMAIL_*` vars) is already wired to this stack's Mailpit container (`mailpit:1025`, no auth) for testing booking confirmation/reminder emails — see [mailpit.md](mailpit.md) to view them. Point it at a real SMTP provider instead for bookings to actually reach anyone's inbox.
- The official upstream `docker-compose.yaml` also wires up a separate API v2 container, Redis, and an optional Prisma Studio service (for building from source / advanced API use) — deliberately left out here to keep this a normal single-app-plus-DB service like everything else in this stack. Revisit only if the v2 API is specifically needed.
- Health endpoint: `/auth/login` — `/api/health` doesn't exist on this version (404); the root `/` redirects (307) to `/auth/login` for unauthenticated requests, so the compose healthcheck and landing-page health route both hit that page directly instead.
- The app logs a repeating `Match of WEBAPP_URL with ALLOWED_HOSTNAMES failed` warning (an organization-domain feature check) — harmless, and deliberately left unset here. Cal.com expects `ALLOWED_HOSTNAMES` as an already-JSON-quoted value (e.g. `"calcom.example.com"`, not a bare string) since it wraps it in `[...]` and parses the result as JSON; a plain unquoted value causes a hard `SyntaxError` crash (confirmed while testing this setup), which is worse than the warning it was meant to silence. Not set here for that reason — revisit only with the exact quoting the app expects if the warning becomes a real problem.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
