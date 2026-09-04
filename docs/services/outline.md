# Outline

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Polished self-hosted team wiki / docs app with good search.
**Port:** `8114` (host) → `3000` (container) | **Data:** `service_data/data/outline/` | **Requires:** Postgres, Redis, and an OIDC/OAuth provider (no built-in email/password login)

## Setup — Authentik OIDC required before first login

Outline has **no built-in username/password login** — it requires at least one OAuth/OIDC provider configured or nobody can sign in. This stack already runs Authentik, so use it:

1. Start Authentik first if it isn't already running: `uv run homeserver.py dev up authentik`.
2. Log into the Authentik admin interface: `https://authentik.<domain>/if/admin/`.
3. **Create the provider** — sidebar **Applications → Providers → Create**:
   - Provider type: **OAuth2/OpenID Provider** → Next
   - Name: `outline-provider` (or anything memorable)
   - Authorization flow: the default authorization flow (e.g.
     `default-provider-authorization-implicit-consent`) — fine for a
     self-hosted, single-tenant setup
   - Client type: `Confidential`
   - Client ID / Client Secret: leave auto-generated, copy them after saving
   - Redirect URIs/Origins (strict): `https://outline.<domain>/auth/oidc.callback`
   - Signing key: the default `authentik Self-signed Certificate` (or any
     available RSA cert)
   - Scopes: leave the defaults (`openid`, `email`, `profile`) — matches what
     Outline requests
   - Grant type: no extra configuration needed. Outline uses the standard
     OIDC **Authorization Code** flow (`response_type=code`), which every
     OAuth2/OpenID Provider supports out of the box — Authentik's separate
     "token exchange" grant (RFC 8693, for service-to-service
     on-behalf-of calls) is unrelated and can be ignored.
   - Logout URI: leave blank. Outline has no `OIDC_LOGOUT_*` setting — it
     just clears its own session cookie and never calls back into Authentik.
   - Save.
4. **Create the application** — sidebar **Applications → Applications →
   Create**:
   - Name: `Outline`, Slug: `outline`, Provider: `outline-provider` from
     step 3
   - Policy/Group/User Bindings: only relevant if you're restricting access
     (e.g. to one group) — the **Policy engine mode** field there controls
     how multiple bound policies combine (`any` = OR, `all` = AND). With
     zero or one binding it doesn't matter; leave it on `any`.
   - Save.
5. Back in **Applications → Providers → outline-provider**, copy the
   **Client ID** and **Client Secret** shown on its detail page.
6. Paste those into `services/outline/.env` (`OIDC_CLIENT_ID`,
   `OIDC_CLIENT_SECRET`). The authorize/token/userinfo URLs don't need to be
   copied by hand — `compose.yml` builds them as
   `https://authentik.${DOMAIN}/application/o/...` from the root `.env`'s
   `DOMAIN`, same as every other Authentik-backed service in this stack.
7. Then:

```bash
cp services/outline/.env.example services/outline/.env
# set POSTGRES_PASSWORD, SECRET_KEY, UTILS_SECRET (openssl rand -hex 32), and OIDC_CLIENT_ID/OIDC_CLIENT_SECRET from step 5-6
uv run homeserver.py dev up outline
```

Open `https://outline.<domain>/` (or `http://<host>:8114` in dev) and log in via the "Authentik" OIDC option.

**Permissions, handled automatically**: Outline's image runs as a hardcoded `nodejs` user (uid `1001`, gid `1001` — confirmed via `/etc/passwd` inside the container, distinct from the image's *other* `node` user at uid `1000`, which isn't what the app actually runs as) with no root fallback, so it could never self-heal `data/` if recreated root-owned (e.g. after a wipe/`--fresh` restart). `outline-permissions` (a one-shot `alpine` init container, same pattern as `firefly-permissions`) `chown`s it on every start, before `outline` itself starts — verified live by wiping it and confirming a clean, correctly-owned restart.

## Using it day to day

Browser-only for this deployment, by design of the app rather than a limitation here — Outline's official desktop app has no way to point at a self-hosted server domain (confirmed via Outline's own community reports, not just this stack), and there's no native mobile app, only a PWA. Use `https://outline.${DOMAIN}` directly in a browser; on mobile, the browser's own "Add to Home Screen" gives a PWA-style icon.

- **Collections → Documents** is the hierarchy — a Collection is a top-level space (e.g. "Engineering"), Documents nest inside it arbitrarily deep.
- **Search** is fast full-text across every document you have access to, including inside nested/collapsed documents.
- **Real-time collaborative editing** — multiple people editing the same document see each other's cursors/changes live, no separate "save" step.

## Notes

- `SECRET_KEY` / `UTILS_SECRET` must each be a random 32-byte hex string (`openssl rand -hex 32`) — Outline refuses to start without them set to non-default values.
- File attachments use `FILE_STORAGE=local`, stored under `service_data/data/outline/data/`. `FILE_STORAGE_UPLOAD_MAX_SIZE` caps uploads (default ~250MB).
- Health endpoint: `/_health`.
- Needs both Postgres and Redis — two extra containers (`outline-db`, `outline-redis`) beyond the app itself, heavier than most services in this stack.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
