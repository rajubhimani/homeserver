# Service comparison: overlapping apps, memory cost, what to prune

[← Services Reference](11-services-reference.md) | [Home](../setup.md)

---

This stack runs several services that solve the *same* job — three team-chat apps, four notes/wiki apps, three project trackers, four workflow-orchestration engines. This doc groups those clusters together (scroll through one job at a time) with memory cost and version currency side by side, so a decision about which one(s) to actually keep has real numbers behind it instead of a gut feeling.

**How to read the Memory column:** a plain number (e.g. `~630MB`) is an independently measured idle figure, sourced from that service's own `docs/services/<slug>.md`. `(live)` means it was read from a `docker stats` snapshot taken while writing this doc, not a settled long-term measurement. `not measured` means neither exists — bring the service up, let it sit idle a few minutes, then `docker stats --no-stream` before deciding based on memory alone. Container counts are given as a lightweight complexity proxy even where no MB figure exists — more containers is usually (not always) more RAM.

**Version currency** was checked against each project's own release feed on 2026-08-21 — see `research/version-audit.md` (gitignored scratch notes, not this doc) for sources and the couple of inconclusive ones. Only two real findings came out of it: **Temporal is one version behind on a security fix**, and **Forgejo is one patch behind**. Everything else in this stack is already current.

---

## Team chat — Slack alternatives

| Our Service | Status | Tier | Containers | Memory | Version |
| --- | --- | --- | --- | --- | --- |
| **Mattermost** | ○ down | extra | 2 (db + app) | not measured — architecturally the lightest of the three | 11.10.0 — current |
| **Rocket.Chat** | ○ down | extra | ~5 (mongo replica set + nats + app) | **~630MB** steady-state (documented, was OOM-crashing at 1024M, fixed at 2048M cap) | 8.7.0 — current, just added phishing-resistant MFA, PKCE OAuth, XMPP federation (licensed) |
| **Zulip** | ○ down | extra | 5 (db, memcached, rabbitmq, redis, app) | not measured — architecturally the heaviest of the three, plus a one-time migration step on bring-up | 12.2-0 — current |

**Notes:** Zulip's topic-threaded model is a genuinely different UX from the other two (Mattermost/Rocket.Chat are both flat-channel Slack clones). Rocket.Chat has the most features (video calls, omnichannel/livechat, federation) but also the roughest setup history in this stack — two real crashes hit during initial bring-up (missing mail config, then an undersized memory cap). If resource footprint is the deciding factor, Mattermost's 2-container architecture is hard to beat; if topic-threading matters more than footprint, Zulip.

## Notes / wiki / knowledge base

| Our Service | Status | Tier | Containers | Memory | Version |
| --- | --- | --- | --- | --- | --- |
| **Trilium Notes** | ● up | extra | **1** | **~119MB** (live, this session) | v0.104.1 — current |
| **SilverBullet** | ● up | extra | **1** | **~2.4MB** (live, this session) | 2.10.0 — unconfirmed, check github.com/silverbulletmd/silverbullet/releases directly |
| **Outline** | ○ down | extra | 3 (db, redis, app) | not measured | 1.9.2 — current |
| **BookStack** | ○ down | extra | 2 (db, app) | not measured | v26.05.3 — current, and already has an OIDC/SAML2/LDAP security fix |
| **AppFlowy** | ● up | daily | 8 | **~509MB** total (appflowy-cloud alone ~218MB) | appflowy_cloud 0.16.5 — unconfirmed (search only surfaced the separate desktop-client versioning) |

**Notes:** Trilium and SilverBullet are both single-container (cheapest to run by far) but serve different styles — Trilium is a hierarchical personal wiki with scripting/attributes, SilverBullet is flatter Markdown-plus-query-language, closer to Obsidian. Now measured: Trilium ~119MB and SilverBullet ~2.4MB (live, this session) confirm both are far cheaper than the multi-container Outline/BookStack/AppFlowy tier — SilverBullet's Deno-based server barely registers at idle. Outline and BookStack are both more "team wiki" oriented (Notion/Confluence-shaped) with real multi-container architecture. AppFlowy is the heaviest by container count (8) and the most Notion-like (databases, kanban, AI writing) but has the least mature self-hosted deployment story of the five (unpinned upstream `latest` tags, no official RAM figure). Given `karakeep` (bookmark manager) and `excalidraw` (whiteboard) also live in this stack's "notes" subcategory but solve different jobs entirely, they're covered separately below rather than lumped in here.

## Project / task management

| Our Service | Status | Tier | Containers | Memory | Version |
| --- | --- | --- | --- | --- | --- |
| **OpenProject** | ○ down | extra | 1 (bundled Postgres inside) | **~1.94GB** idle (65% of its 3G cap — already below OpenProject's own stated 4GB minimum) | 17.7.2 — current |
| **Plane** | ● up | extra | 11 | **~709MB** total (`plane-worker` alone ~205MB) | v1.4.1 — current (verified via Docker Hub directly, not just search) |
| **Vikunja** | ● up | extra | 2 (db, app) | **~48MB** (live, this session — app ~30MB + db ~18MB) | 2.5.0 — current |

**Notes:** OpenProject is the most Jira/Asana-like (biggest feature surface: Gantt, time tracking, budgets, wiki) but also the heaviest per-container and already running close to its memory cap with zero users — real OOM risk under actual load, and it's still the one of these three not brought up this session. Plane is lighter overall despite 11 containers (microservice split, most are small) and closer to Linear's UX. Vikunja, now measured, confirms it as the lightest of the three by a wide margin (~48MB total, 2 containers) — worth weighing ahead of OpenProject/Plane on footprint alone if project tracking is the deciding factor.

## Container / stack management UI

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Portainer** | ● up | **min** | **~38MB** | 2.44.0 — likely current (search index looked stale, showed a lower number than our own pin) |
| **Dockge** | ○ down | extra | **~132MB** (documented) | 1.5.0 — current |

**Notes:** Portainer is already in `SERVICES_MIN` (always-on) and is ~7x cheaper than Dockge for materially the same job (start/stop/inspect containers and compose stacks) — genuinely hard to justify running both continuously. Dockge's edge is a nicer compose-file-editing UX; Portainer covers more ground (Kubernetes too, if that's ever relevant here).

## System / resource monitoring

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Beszel** | ● up | **min** | **~42MB** (hub + agent) | 0.18.8 — current |
| **Uptime Kuma** | ● up | extra | **~56MB** app + Postgres cap 384M | 2.5.0 — current |
| **Observability** (Grafana+Prometheus+Loki+Alloy+cAdvisor+node-exporter) | ● up | **core** | **~2.09GB** live total this session (Prometheus alone ~877MB — grown with retention/cardinality now that it's scraping ~110 containers; cAdvisor ~217MB after a `--docker_only=true` fix applied this session dropped it from ~3.9GB, where it had been walking the entire host cgroup tree instead of just container cgroups) | prometheus v3.14.0 / loki 3.7.6 / alloy v1.18.1 — current (bumped this session) |

**Notes:** these three aren't strict competitors — Beszel is a lightweight always-on host/container overview (~42MB, cheapest possible "is something on fire" check), Uptime Kuma is external uptime/ping monitoring (a different job — "is this URL reachable from outside," not resource usage), and Observability is the heavyweight full metrics+logs stack (~50x Beszel's footprint) for actual dashboards and history. Keeping Beszel always-on and only bringing Observability up when doing a deeper investigation is a reasonable middle ground if ~2GB feels like a lot for something that's mostly idle — and cAdvisor's `--docker_only=true` fix this session already cut Observability's own footprint by ~3.7GB, so it's worth checking Prometheus's retention/cardinality settings next if it keeps growing.

## Read-later / bookmarking

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Wallabag** | ● up | extra | **~50MB** (live, this session — app ~32MB + db ~18MB) | 2.6.14 — current |
| **Karakeep** | ● up | extra | **~263MB** (live, this session — app ~236MB + meilisearch ~8MB + headless chrome ~19MB) | `:release` floating tag — always current by construction (recently added semantic search) |

**Notes:** functionally similar (save-and-read-later) but Karakeep leans more toward AI-assisted bookmark organizing (auto-tagging, full-text + semantic search) while Wallabag is the more "classic Pocket clone" — simpler, no AI features, but also no separate search-index/browser containers to run. Now measured: Wallabag's ~50MB is roughly a fifth of Karakeep's ~263MB — the extra headless-Chrome and Meilisearch containers are the real cost of Karakeep's auto-tagging/semantic-search features, not the base app itself.

## Workflow / data orchestration

See [`docs/12-orchestration.md`](12-orchestration.md) for what each of these is actually *for* — they're not interchangeable despite all living in the same "automation" bucket; this table is only the resource/version side.

| Our Service | Status | Tier | Containers | Memory | Version |
| --- | --- | --- | --- | --- | --- |
| **n8n** | ● up | extra | 2 (db, app) | **~322MB** (live, this session — app ~298MB + db ~24MB) | 2.36.2 — likely current or ahead (n8n ships ~weekly, exact latest hard to pin from search) |
| **Airflow** | ● up | extra | 6 (5 long-running + `airflow-init` one-shot) | **~925MB** (live, this session) | 3.3.1 — current |
| **Temporal** | ● up | extra | ~6 (5 long-running + 2 one-shot setup jobs) | **~267MB** (live, this session) | **1.29.1 pinned — 1.30.4 available, fixes CVE-2026-5724 (medium severity)** |
| **Dagster** | ● up | extra | 4 | **~274MB** (live, this session — daemon ~126MB + user-code ~116MB + webserver ~13MB + db ~19MB) | 1.13.18 — current |

**Notes:** Temporal is the one real actionable item in this whole audit — worth bumping `TEMPORAL_VERSION` in `services/temporal/.env` for the CVE fix even if you don't use it often. All four are live this session, giving a real footprint comparison: n8n (~322MB, 2 containers) is lightest and closest to a no-code Zapier-style tool; Dagster (~274MB, 4) and Temporal (~267MB, ~6) land in the middle; Airflow (~925MB, 6) is by far the heaviest, consistent with it being the most mature/heaviest general-purpose scheduler of the four. Airflow/Dagster/Temporal are genuinely different engines (see the linked doc) rather than redundant with each other, so footprint alone shouldn't decide between them.

## Git hosting

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Forgejo** | ● up | **core** | **~96MB** total (app 76 + db 20) | 16.0.2 pinned — **16.0.3 available (patch)** |
| **GitLab** | ○ down | manual-only | **~4.22GB** idle (70% of its 6G cap, already below GitLab's own 8GB minimum) | 19.2.4-ce.0 — current on the 19.2 minor |

**Notes:** already effectively decided in this repo — GitLab is explicitly `SERVICES_MANUAL` because it's ~44x Forgejo's memory for largely overlapping functionality (git hosting + CI). Forgejo is core-tier and always up; GitLab exists only for the rare case something specifically needs GitLab's feature set. GitLab also has an unresolved incident on record (`SERVICE_ROLLOUT.md`): a 6G cap OOM-killed it for 5 hours straight once and needs its memory limit raised before it's started again.

## Cloud storage / file sync

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Nextcloud** | ● up | **core** | **~181MB** total (app 122 + db 21 + redis 6 + cron 31) | 34.0.3 — current |
| **Syncthing** | ● up | extra | **~25MB** | v2.1.3 — current |

**Notes:** different mechanisms more than direct competitors — Nextcloud is a hosted cloud drive with a web UI, calendar/contacts, and apps ecosystem (closer to Google Drive); Syncthing is pure peer-to-peer folder sync with no server-side web UI or storage of its own (closer to a private Dropbox-sync-only mode). Syncthing is ~7x cheaper if all you actually need is "keep folders in sync across my own devices," not a hosted drive with sharing/collaboration features.

## PDF tools

| Our Service | Status | Tier | Memory | Version |
| --- | --- | --- | --- | --- |
| **Stirling PDF (lite)** | ● up | extra | **~274MB** (live, this session) | 2.14.3 — current |
| **Stirling PDF (full)** | ● up | extra | **~501MB** (live, this session) | 2.14.3 — current |

**Notes:** the "lite"/"ultra-lite" naming previously looked misleading based on a "nearly identical idle RAM" claim — but now measured live, full (~501MB) is actually ~83% heavier than lite (~274MB), a real difference, not "nearly identical." Both are still JVM/Spring Boot apps with a large baseline heap, so this could shift with longer settle time or different load; worth treating the "nearly identical" claim as unconfirmed until re-checked rather than assuming either figure is final. The one certain functional difference is the full variant supports login (`SECURITY_ENABLELOGIN`); the lite image's build has no security module at all — if login doesn't matter, lite is both simpler and, per this session's numbers, lighter too.

---

## Everything else — no direct competitor in this stack

Single-purpose services with nothing else in this stack doing the same job. Listed for completeness since the point of this doc is seeing the whole picture, not just the redundant parts.

| Our Service | Mainstream equivalent | Status | Tier | Memory |
| --- | --- | --- | --- | --- |
| Nextcloud | Google Drive | ● up | core | ~181MB |
| Vaultwarden | 1Password / LastPass | ● up | core | ~14MB |
| Forgejo | GitHub | ● up | core | ~96MB |
| Firefly III | YNAB / Mint | ● up | core | ~141MB |
| Immich | Google Photos | ● up | core | ~531MB (ML container idle, no model loaded) |
| Jellyfin | Netflix / Plex | ● up | core | ~65MB — RAM isn't the constraint here — CPU/GPU for transcoding is |
| Guacamole | TeamViewer / AnyDesk | ● up | core | ~217MB |
| IT-Tools | assorted sketchy websites | ● up | core | ~5MB (live) |
| Authentik | Okta / Auth0 | ● up | core | ~244MB |
| Atuin | plain bash/zsh history file | ● up | core | ~27MB (live) |
| Beszel | Netdata / Datadog | ● up | min | ~42MB |
| Plausible | Google Analytics | ● up | min | ~265MB (live, this session, 3 containers) |
| Mailpit | Mailtrap | ● up | min | ~35MB (live) |
| Dozzle | — (log viewer) | ○ down | extra | ~50MB |
| Uptime Kuma | Pingdom | ● up | extra | ~56MB |
| Paperless | Scansnap cloud | ○ down | extra | ~582MB (spikes 1.5-2GB during OCR) |
| Mealie | recipe apps | ○ down | extra | ~329MB |
| Audiobookshelf | Audible | ○ down | extra | ~36MB |
| Invoiceshelf | FreshBooks | ○ down | extra | ~172MB |
| Open WebUI | ChatGPT | ● up | daily | ~662MB (live, this session — includes the downloaded embedding model) |
| Ollama | — (AI backend, pairs with Open WebUI) | ● up | daily | ~18MB idle, one small model pulled (`qwen2.5:0.5b`, live) |
| Excalidraw | draw.io / Miro | ● up | extra | ~10MB (live) |
| ntfy | Pushover / Pushbullet | ○ down | extra | not measured |
| Firefox / Chromium / Ungoogled Chromium / Brave / Mullvad Browser | — (isolated remote browsers via Browser Hub) | ● up | extra | 207-442MB each (live, this session) — still well under docs' "~1GB each" estimate, though noticeably higher than a prior session's 91-252MB range; real session-to-session variance, worth eventually settling the individual browser docs to a real range instead of the old ~1GB placeholder |
| Crowdsec | Fail2ban / Cloudflare WAF | ● up | extra | ~80MB (live) |
| AdGuard Home | Pi-hole | ● up | extra | ~57MB (live) |
| OrangeHRM | BambooHR / Workday | ○ down | extra | not measured |
| NocoDB | Airtable | ○ down | extra | not measured |
| Listmonk | Mailchimp | ● up | extra | ~53MB (live, this session — app ~33MB + db ~19MB) |
| Documenso | DocuSign | ○ down | extra | not measured |
| Cal.com | Calendly | ● up | extra | ~850MB (live, this session — app ~827MB + db ~22MB) — the heaviest single-purpose service measured this session |
| Penpot | Figma | ○ down | extra | not measured |
| Coolify | Vercel / Heroku | ● up | extra | ~479MB (live, this session, 6 containers: app 326 + realtime 57 + redis 8 + proxy 28 + sentinel 34 + db 26) |
| Supabase | Firebase | ○ down | extra | not measured, but 11 containers — doc explicitly warns "expect noticeably higher than anything else in this stack" |
| HomeBox | Sortly | ● up | extra | ~26MB (live) |
| Miniflux | Feedly | ● up | extra | ~29MB (app 13 + db 16) |

---

*Data behind this doc — raw search results, sources, and the memory-figure sourcing breakdown — lives in `research/` at the repo root (not checked in, working notes only). Live figures marked "(live, this session)" were taken 2026-08-21 with essentially the whole stack (min+core+daily tiers, plus most of extra) running simultaneously — see `research/memory-audit.md` for the full snapshot.*
