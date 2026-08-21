# Authentik

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Identity provider — SSO, OAuth2, OIDC, SAML for all your other services.
**Port:** `8088` (host) → `9000` (container, `authentik-server`, HTTP) and `9444` (host) → `9443` (container, HTTPS) | **Data:** `service_data/data/authentik/` | **Requires:** Postgres (no Redis in this compose.yml — this doc previously claimed one that doesn't exist here) | **Memory:** DB capped 384M in compose.yml; server/worker: no hard limit set; measured idle ~244MB total (server 143 + worker 49 + db 52). Authentik's own docs state a 2GB/2-core minimum for the whole stack — comfortable headroom for personal-scale use, though their GitHub issue #21413 notes real deployments at ~1400 users saw the worker alone peak past 7GB

## Setup

```bash
cp services/authentik/.env.example services/authentik/.env
# generate: openssl rand -base64 60 → AUTHENTIK_SECRET_KEY
# set POSTGRES_PASSWORD
uv run homeserver.py dev up authentik
```

`AUTHENTIK_SECRET_KEY` must be set **before** first start.

## First login

Browse to `http://<ip>:8088/if/admin/` — set the password for the default admin account `akadmin`.

## Real client IP in user/event logs

By default Authentik logs the wrong IP for every user session and event — confirmed live, not theoretical: its `trusted_proxy_cidrs` default is `127.0.0.0/8` and `10.0.0.0/8` only, which doesn't cover this stack's `homeserver` Docker network (`172.18.0.0/16`, inside the `172.16.0.0/12` block Docker actually uses). Since nginx-plain isn't a trusted proxy from Authentik's point of view, it ignores the `X-Forwarded-For`/`X-Real-IP` headers nginx sends and just uses the raw TCP connection IP — nginx-plain's own container IP — for everything. `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS=127.0.0.0/8,10.0.0.0/8,172.16.0.0/12` in `services/authentik/.env` fixes this (already set — see `.env.example`'s comment for why the `/12` rather than the exact `/16`, which could change if the network gets recreated).

This is one half of the fix — the other half (nginx-plain not forwarding the real client IP at all, always showing `cloudflared`'s own container IP) is a stack-wide issue documented in [`docs/04-nginx.md`](../04-nginx.md#real-client-ip-not-cloudflareds-own-ip), not specific to Authentik. Both were needed together.

## Forward-auth for other services (nginx `auth_request`)

Some services in this stack have no login of their own at all (Dozzle, Mailpit, Excalidraw, Dagster, Temporal — see [13 — Auth Posture](../13-auth-posture.md)'s bucket A). Rather than giving each one its own OIDC integration (the [Outline](outline.md) pattern — real work, and most of these apps don't even support OIDC natively), Authentik can front the whole vhost at the nginx layer instead: nginx asks Authentik "is this request authenticated?" before it ever reaches the container, and redirects to a login page if not.

**One provider covers every service, not one per app.** Using Authentik's **Forward auth (domain level)** mode instead of "single application" mode means the login cookie is scoped to the whole `${DOMAIN}`, not one subdomain — log into any protected service once, and you're authenticated on all the others too. Adding a *new* service to this protection later needs zero Authentik-side changes, only the nginx snippet below on that service's vhost.

This uses Authentik's **embedded outpost** (built into `authentik-server`, already running — no extra container to deploy) rather than a separately-deployed outpost.

### 1. Create the provider

Sidebar **Applications → Providers → Create**:

- Provider type: **Proxy Provider** → Next
- Proxy type: **Forward auth (domain level)**
- Name: `forward-auth-domain` (or anything memorable — only one of these should exist)
- Authorization flow: the default (`default-provider-authorization-implicit-consent`) — same as every other provider in this stack
- Cookie domain: `${DOMAIN}` (e.g. `prajnatech.in` — no leading dot, no subdomain)
- Everything else: leave at its default
- Save

### 2. Add it to the embedded outpost

Sidebar **Applications → Outposts** → open **authentik Embedded Outpost** → **Edit** → under **Applications**, check the provider created in step 1 → **Update**.

### 3. Create the application

Sidebar **Applications → Applications → Create**:

- Name: `Internal Tools` (or anything — this is just the launcher tile, not tied to any one service)
- Slug: `internal-tools`
- Provider: `forward-auth-domain` from step 1
- Save

No client ID/secret to copy anywhere — unlike OIDC, forward-auth doesn't hand the protected app any credentials. Nothing in `services/<app>/.env` changes for any of the five services below.

### 4. Protect a vhost

Add this to a service's `server { }` block in `services/nginx-plain/templates/default.conf.template`, inside the existing `location / { }` (alongside its current `proxy_set_header` lines, not replacing them), plus two new top-level locations in the same server block:

```nginx
    location / {
        # ...existing proxy_set_header lines stay...
        auth_request /outpost.goauthentik.io/auth/nginx;
        error_page 401 = @goauthentik_proxy_signin;
        auth_request_set $auth_cookie $upstream_http_set_cookie;
        add_header Set-Cookie $auth_cookie;
    }

    location /outpost.goauthentik.io {
        internal;
        set $authentik_upstream http://authentik-server:9000;
        proxy_pass $authentik_upstream$uri;
        proxy_set_header Host $host;
        proxy_set_header X-Original-URL https://$http_host$request_uri;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        auth_request_set $auth_cookie $upstream_http_set_cookie;
        add_header Set-Cookie $auth_cookie;
    }

    location @goauthentik_proxy_signin {
        internal;
        add_header Set-Cookie $auth_cookie;
        return 302 https://authentik.${DOMAIN}/outpost.goauthentik.io/start?rd=https://$http_host$request_uri;
    }
```

The `auth_request` subrequest talks to `authentik-server` directly over the internal `homeserver` Docker network (fast, no public hop); the `return 302` sent to the browser on an unauthenticated request has to be a real public HTTPS URL since it's a client-side redirect through Cloudflare Tunnel, not a server-side proxy.

**Two nginx variable gotchas hit getting this working, both confirmed live:**

- **Never reuse the same `set $variable` name across a vhost's app location and its outpost location.** Confirmed live: both used `$upstream` (matching this file's own established indirection convention), and since `auth_request`'s subrequest runs *before* the main location's `proxy_pass` phase evaluates its variable, the subrequest's `set $upstream http://authentik-server:9000;` clobbered the shared variable slot — so after a successful (200) auth check, the actual app request got silently proxied to `authentik-server` instead of the real app, producing a redirect loop that looked like an auth failure but wasn't. Fixed by giving the outpost location its own distinct name (`$authentik_upstream`), matching what's in the snippet above.
- **`$request_uri` in the `proxy_pass` line is wrong — use `$uri` instead.** `$request_uri` always reflects the *original* client request's URI, even inside an `auth_request` subrequest — it does not update to the subrequest's own URI (`/outpost.goauthentik.io/auth/nginx`). Since `proxy_pass` targets a variable (`$upstream`), nginx's automatic prefix-rewriting is also disabled, so getting this wrong sends the *outer* page's path to Authentik instead of the actual auth-check path, and every request 404s at the outpost. `$uri` is subrequest-aware and already contains the full path — don't re-append `/outpost.goauthentik.io` to it.
- **`$scheme` always evaluates to `http` here, even for real HTTPS requests** — same root cause as the `X-Forwarded-Proto` gotcha in the [reverse-proxy skill](../../.claude/skills/homeserver-reverse-proxy/SKILL.md): Cloudflare terminates TLS, so nginx only ever sees plain HTTP internally. Used dynamically in the `rd=` redirect target or `X-Original-URL`, this sends Authentik an `http://` URL for something the browser actually loaded over HTTPS. Hardcode `https://` instead, same as everywhere else in this file.

**Currently applied to:** Dozzle, Mailpit, Excalidraw, Dagster, Temporal — see each service's own doc for any app-specific caveats (Dozzle's SSE headers, in particular, needed care not to conflict with the added blocks).

**Known tradeoff — fail-closed on Authentik itself.** If `authentik-server` isn't running, the `auth_request` subrequest fails and every protected vhost 502s, even though the protected container itself is perfectly healthy. This is why Mailpit and Plausible were moved from `min` into `core` alongside this change — `min` is meant to work standalone without `core`, and Authentik is core-tier.

## Creating team member accounts (invitation-based enrollment)

For a team/firm, always prefer inviting people over creating their accounts yourself — you never see or handle anyone's password, they self-serve their own signup via a one-time link, and revoking an unused invitation is cleaner than resetting a password you handed out. Manually creating a user (**Directory → Users → Create**, leave **"Is superuser" off**, then set a password yourself) should only be a fallback for one-off edge cases.

There's no ready-made "invite someone, they set a password" flow out of the box — the only enrollment flow present by default (`default-source-enrollment`) is for post-OAuth-login enrollment, not standalone invitations. Authentik ships an official example blueprint for exactly this case instead of hand-building flow/stage objects:

### 1. Import the blueprint

Sidebar **Customization → Blueprints → Create**:

- Name: `Team Enrollment` (or anything memorable)
- Path: **Local path** → `example/flows-invitation-enrollment-minimal.yaml`
- Context (JSON field):

  ```json
  {"flow_name": "Team Enrollment", "user_type": "internal"}
  ```

- Enabled: on → Create

This creates one enrollment flow with the full stage chain already wired together (invitation check → username/password prompts → name/email prompts → user-write → auto-login) — no manual flow-building needed.

**Gotcha, confirmed live: creating the blueprint instance does not apply it.** It's saved with `status: unknown` and zero apply tasks recorded — the underlying flow/stage objects are never actually created until something explicitly triggers an apply. The periodic discovery/sync task doesn't pick up a just-created instance immediately. Fix: back in the Blueprints list, find the row, open its **⋮** (kebab) menu → **Apply**. Confirm the status icon turns green ("successful") before moving on — if there's no direct Apply action visible, toggling **Enabled** off then back on (Update each time) also re-triggers it. Only after this will the new flow actually show up in the Invitations flow dropdown.

### 2. Create the invitation

Sidebar **Directory → Invitations → Create**:

- Name: whatever identifies this batch (e.g. `team-aug-2026`)
- Flow: **Team Enrollment** (the one from step 1)
- Expires: set a reasonable window if you want it to auto-expire
- Save

Open the invitation you just created — it shows the enrollment link with a token baked in. **Send that link directly to the person yourself** (Slack/WhatsApp/etc.) rather than relying on Authentik to email it — outgoing email is wired to Mailpit for testing only (see `services/authentik/.env`), so nothing it sends actually leaves this server.

They open the link, pick their own username, set their own password, fill in name/email, and land in Authentik as a real `internal` user (not superuser).

### Access is open by default

None of the five forward-auth apps above, nor Outline's OIDC application, have any group/policy restrictions configured — every application has zero bindings, which in Authentik means *any* authenticated user can reach it. A freshly-enrolled account gets access to everything immediately, no per-app step needed. The flip side: those five apps have no internal user/role system of their own, so anyone you invite gets full access to all of them (e.g. can read every captured email in Mailpit, see all Docker logs in Dozzle). Restricting *which* people can reach *which* app would need group-based policy bindings added per-application — not set up today.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
