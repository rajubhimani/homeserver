# Auth posture: which services have real accounts, and which don't

[← Services Reference](11-services-reference.md) | [Home](../setup.md)

---

Every service in this stack has *some* barrier at its own login screen, but "has a login screen" and "has user management" are different claims. This doc audits all 58 services with a user-facing UI against four buckets, then looks at which of the weakest ones are realistic candidates to put behind [Authentik](services/authentik.md) forward-auth instead of (or in addition to) their own login.

**Excluded from the audit** (no login-facing UI at all): `cloudflared`, `nginx-plain`, `landing`, `crowdsec`, `ollama`.

## The four buckets

| Bucket | Meaning | Example in this stack |
| --- | --- | --- |
| **A** | No authentication at all | Dozzle — reaches the container, no gate |
| **B** | One shared credential for everyone, no distinct identities | Supabase Studio — single Kong basic-auth login (see the [Supabase doc](services/supabase.md)) |
| **C** | Real per-person accounts, but no role/permission tiering | Firefly III — each person signs up, but there's nothing like admin-vs-viewer |
| **D** | Per-person accounts **and** role-based permissions | Airflow — Admin/Op/Viewer/Public roles, `airflow users create` |

A and B are the ones worth acting on — nobody using them is individually identifiable, and in B's case a single leaked password (or a former housemate/collaborator who should've been removed) grants full access to everyone who ever had it.

## Bucket A — no authentication at all (7)

| Service | Category | Notes |
| --- | --- | --- |
| Docs | System | Static Docsify site — setup guides, this doc included. Low sensitivity (no secrets, but does map out internal topology). |
| Dozzle | System | Live container log viewer — logs can leak env vars, tokens, stack traces. **Higher sensitivity than it looks.** |
| IT-Tools | Dev | Client-side-only browser utilities (JWT decode, hash/UUID gen). Nothing server-side to protect. |
| Mailpit | Dev | SMTP catcher — shows every captured email body (password resets, invite links) sent by any service in the stack. |
| Temporal | Dev | Workflow UI. RBAC is a Temporal Cloud / paid-tier feature, not available in the OSS build running here. |
| Dagster | Dev | Asset/pipeline UI. Same story — RBAC is Dagster+ (paid) only. |
| Excalidraw | Productivity | Whiteboard — [its own doc](services/excalidraw.md) notes it's local-only by default, nothing persisted server-side. |

## Bucket B — single shared credential (11)

| Service | Category | Notes |
| --- | --- | --- |
| Dockge | System | Stack manager — can start/stop/edit any compose stack. Shared password, high blast radius if leaked. |
| Uptime Kuma | System | Has a public-status-page feature that's *meant* to be unauthenticated — only the admin dashboard needs gating. |
| AdGuard Home | System | Admin UI only (port 3000); DNS itself (port 53) is LAN-only and unaffected by any of this. |
| Syncthing | Storage | GUI password only — the actual device-to-device sync protocol uses separate device IDs/certs, untouched by anything here. |
| Stirling PDF Lite | Productivity | Exposes an API for programmatic PDF conversion in addition to its UI. |
| Stirling PDF (Full) | Productivity | Manual-tier duplicate of the above; same caveat. |
| Trilium | Productivity | Single-space notes app. Also supports desktop/mobile sync clients speaking their own protocol, not just the browser. |
| SilverBullet | Productivity | Single-space markdown notes, pure browser PWA, no separate client protocol. |
| Supabase | Dev | Studio dashboard behind Kong basic-auth (`DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`) — see [supabase.md](services/supabase.md). |
| Plausible | Dev | Dashboard is shared-login, but its `/api/event` tracking-beacon endpoint is *meant* to be public — anonymous visitor browsers POST to it. |
| Browser Hub | System | HTTP basic-auth gate at the nginx-plain level protects all 5 remote-browser containers (Firefox/Chromium/Ungoogled Chromium/Brave/Mullvad Browser) behind one shared login — see [browser-hub.md](services/browser-hub.md). Each container also keeps its own basic-auth gate as defense-in-depth against direct dev-port access. |

## Reference — bucket C, multi-user but no roles (9)

Firefly III, Mealie, Miniflux, Wallabag, HomeBox, Karakeep, n8n (CE: owner + members, no granular roles), Atuin (per-person history, no sharing/permission model to have roles over), Beszel.

## Reference — bucket D, real RBAC (31)

Nextcloud, Vaultwarden, Forgejo, Immich, Jellyfin, Guacamole, Portainer, OpenProject, Paperless-ngx, Authentik, AppFlowy, Plane, Open WebUI, Vikunja, Outline, BookStack, Mattermost, Rocket.Chat, Zulip, ntfy, Airflow, GitLab, Grafana (Observability), InvoiceShelf, OrangeHRM, NocoDB, Listmonk, Documenso, Cal.com, Penpot, Coolify.

---

## Putting bucket A/B behind Authentik forward-auth — feasibility

**Not implemented yet** — this stack doesn't have an nginx `auth_request` → Authentik outpost pattern wired up anywhere; Authentik itself is only documented as a standalone IdP today, per [authentik.md](services/authentik.md). This section is a feasibility read, not a setup guide — treat it as the input to a future "add forward-auth" pass, one service at a time.

Forward-auth puts a cookie/redirect-based login screen in front of the *whole vhost* at the nginx layer, before the request ever reaches the container. That's a clean fit for a pure browser UI reached by one person at a time. It breaks down wherever something other than "a human in a browser" needs to reach the service directly.

### Clean candidates — no nuance

Pure browser UI, single vhost, nothing else depends on hitting it directly.

| Service | Why it's clean |
| --- | --- |
| Docs | Static site, browser-only. |
| Dozzle | Browser-only log viewer — this closes its biggest current gap. |
| IT-Tools | Browser-only, low stakes either way. |
| Temporal | Browser UI; the gRPC/worker ports it needs aren't proxied publicly. |
| Dagster | Same — webserver UI only, not the internal gRPC ports. |
| Excalidraw | Browser-only, nothing server-side at stake regardless. |
| Dockge | Browser-only stack manager. |
| AdGuard Home | Admin UI is browser-only; DNS port 53 is separate and unaffected. |
| Syncthing | GUI is browser-only; sync protocol runs on its own port, untouched. |
| SilverBullet | Browser-only PWA, no competing client protocol. |
| Supabase | Studio dashboard is browser-only — a clean upgrade from the shared Kong credential. |

### Needs path-scoping — don't blanket-protect the whole vhost

The service has one path that must stay reachable *without* Authentik's login, alongside dashboard paths that should require it.

| Service | What has to stay open | Why |
| --- | --- | --- |
| **Plausible** | `/api/event` (and any other tracking-beacon path) | Anonymous visitor browsers on *your other sites* POST here directly — this is the one where blanket-protecting the vhost breaks analytics collection entirely, not just your own access. |
| **Uptime Kuma** | `/status/*` public status pages | Those are meant to be shared with people who have no login at all; only `/dashboard` and admin paths should be gated. |
| Mailpit | Its REST API, *if* anything scripts/CI reads captured mail programmatically | Fine to fully gate if only ever used interactively in a browser — check first. |
| Stirling PDF Lite / Full | The conversion API, *if* anything calls it programmatically | Same caveat as Mailpit — audit actual usage before gating the whole vhost. |
| Trilium | N/A for the web UI, but check before gating if you use Trilium's desktop/mobile sync clients against this server | Those speak Trilium's own sync protocol, not a browser session — forward-auth wouldn't cover them. |

---

[← Services Reference](11-services-reference.md) | [Home](../setup.md)
