# 10 — New Services

[← Firewall](09-firewall.md) | [Home](../setup.md) | [Next: Services Reference →](11-services-reference.md)

---

All services follow the same three-file compose pattern:

- `compose.yml` — base config, no ports
- `compose.dev.yml` — ports on all interfaces (direct access)
- `compose.prod.yml` — ports on `127.0.0.1` only (reverse proxy handles external)
- `.env` — secrets and paths (copy from `.env.example`)

Use `homeserver.py` to manage them (see [Maintenance](08-maintenance.md)).
New services always go into `SERVICES_EXTRA` in `homeserver.py` first.

---

## Per-service setup guides

Each service has its own consolidated doc under `docs/services/` — setup steps, default credentials, architecture, and every known gotcha in one place:

| Service | Doc |
| --- | --- |
| Beszel | [docs/services/beszel.md](services/beszel.md) |
| Portainer CE | [docs/services/portainer.md](services/portainer.md) |
| Docs | [docs/services/docs.md](services/docs.md) |
| Nextcloud | [docs/services/nextcloud.md](services/nextcloud.md) |
| ONLYOFFICE | [docs/services/onlyoffice.md](services/onlyoffice.md) |
| Nextcloud Whiteboard | [docs/services/whiteboard.md](services/whiteboard.md) |
| Immich | [docs/services/immich.md](services/immich.md) |
| Jellyfin | [docs/services/jellyfin.md](services/jellyfin.md) |
| Vaultwarden | [docs/services/vaultwarden.md](services/vaultwarden.md) |
| Forgejo | [docs/services/forgejo.md](services/forgejo.md) |
| Authentik | [docs/services/authentik.md](services/authentik.md) |
| Firefly III (+ Data Importer) | [docs/services/firefly.md](services/firefly.md) |
| Ghostfolio | [docs/services/ghostfolio.md](services/ghostfolio.md) |
| Guacamole | [docs/services/guacamole.md](services/guacamole.md) |
| IT-Tools | [docs/services/it-tools.md](services/it-tools.md) |
| Mailpit | [docs/services/mailpit.md](services/mailpit.md) |
| Atuin | [docs/services/atuin.md](services/atuin.md) |
| Plausible | [docs/services/plausible.md](services/plausible.md) |
| Observability (Grafana + Prometheus + Loki) | [docs/services/observability.md](services/observability.md) |
| Stirling PDF (Lite + Full) | [docs/services/stirling-pdf.md](services/stirling-pdf.md) |
| HomeBox | [docs/services/homebox.md](services/homebox.md) |
| Uptime Kuma | [docs/services/uptime-kuma.md](services/uptime-kuma.md) |
| Syncthing | [docs/services/syncthing.md](services/syncthing.md) |
| Miniflux | [docs/services/miniflux.md](services/miniflux.md) |
| Plane | [docs/services/plane.md](services/plane.md) |
| AppFlowy | [docs/services/appflowy.md](services/appflowy.md) |
| Browser Hub | [docs/services/browser-hub.md](services/browser-hub.md) |
| Firefox | [docs/services/firefox.md](services/firefox.md) |
| Chromium | [docs/services/chromium.md](services/chromium.md) |
| Brave | [docs/services/brave.md](services/brave.md) |
| Mullvad Browser | [docs/services/mullvad-browser.md](services/mullvad-browser.md) |
| LibreWolf | [docs/services/librewolf.md](services/librewolf.md) |
| Zen | [docs/services/zen.md](services/zen.md) |
| Helium | [docs/services/helium.md](services/helium.md) |
| Chrome | [docs/services/chrome.md](services/chrome.md) |
| Edge | [docs/services/edge.md](services/edge.md) |
| Vivaldi | [docs/services/vivaldi.md](services/vivaldi.md) |
| Open WebUI | [docs/services/open-webui.md](services/open-webui.md) |
| Ollama | [docs/services/ollama.md](services/ollama.md) |
| Vikunja | [docs/services/vikunja.md](services/vikunja.md) |
| Trilium Notes | [docs/services/trilium.md](services/trilium.md) |
| SilverBullet | [docs/services/silverbullet.md](services/silverbullet.md) |
| Excalidraw | [docs/services/excalidraw.md](services/excalidraw.md) |
| Karakeep | [docs/services/karakeep.md](services/karakeep.md) |
| n8n | [docs/services/n8n.md](services/n8n.md) |
| Airflow | [docs/services/airflow/airflow.md](services/airflow/airflow.md) |
| Temporal | [docs/services/temporal/temporal.md](services/temporal/temporal.md) |
| Dagster | [docs/services/dagster/dagster.md](services/dagster/dagster.md) |
| Wallabag | [docs/services/wallabag.md](services/wallabag.md) |
| AdGuard Home | [docs/services/adguard-home.md](services/adguard-home.md) |
| Listmonk | [docs/services/listmonk.md](services/listmonk.md) |
| Cal.com | [docs/services/calcom.md](services/calcom.md) |
| Coolify | [docs/services/coolify.md](services/coolify.md) |
| Paperless-ngx | [docs/services/paperless.md](services/paperless.md) |
| Mealie | [docs/services/mealie.md](services/mealie.md) |
| Dozzle | [docs/services/dozzle.md](services/dozzle.md) |
| Audiobookshelf | [docs/services/audiobookshelf.md](services/audiobookshelf.md) |
| OpenProject | [docs/services/openproject.md](services/openproject.md) |
| InvoiceShelf | [docs/services/invoiceshelf.md](services/invoiceshelf.md) |
| ERPNext | [docs/services/erpnext.md](services/erpnext.md) |
| Dockge | [docs/services/dockge.md](services/dockge.md) |
| Outline | [docs/services/outline.md](services/outline.md) |
| BookStack | [docs/services/bookstack.md](services/bookstack.md) |
| ntfy | [docs/services/ntfy.md](services/ntfy.md) |
| Mattermost | [docs/services/mattermost.md](services/mattermost.md) |
| Rocket.Chat | [docs/services/rocketchat.md](services/rocketchat.md) |
| Zulip | [docs/services/zulip.md](services/zulip.md) |
| Mail-Archiver | [docs/services/mail-archiver.md](services/mail-archiver.md) |
| Bichon | [docs/services/bichon.md](services/bichon.md) |
| CrowdSec | [docs/services/crowdsec.md](services/crowdsec.md) |
| ClamAV | [docs/services/clamav.md](services/clamav.md) |
| OrangeHRM | [docs/services/orangehrm.md](services/orangehrm.md) |
| NocoDB | [docs/services/nocodb.md](services/nocodb.md) |
| Documenso | [docs/services/documenso.md](services/documenso.md) |
| Penpot | [docs/services/penpot.md](services/penpot.md) |
| Supabase | [docs/services/supabase.md](services/supabase.md) |
| GitLab CE | [docs/services/gitlab.md](services/gitlab.md) |
| wg-easy | [docs/services/wg-easy.md](services/wg-easy.md) |

---

[← Firewall](09-firewall.md) | [Home](../setup.md) | [Next: Services Reference →](11-services-reference.md)

## Which version to run: LTS, always

**Every component runs its project's LTS line**: apps, databases, proxies, scanners and monitoring alike. LTS here means whatever the project calls its long-supported track: LTS, ESR, a "stable" branch next to "mainline", or a yearly major next to short rapid releases. This holds for new services, updates and audits.

- **Pin the LTS line, then take every patch inside it.** LTS doesn't mean frozen.
  | Project | LTS line in use |
  | --- | --- |
  | MariaDB | 11.8, 12.3 |
  | ClickHouse | the `.3`/`.8` lines (26.8) |
  | MongoDB | the yearly major (8.0), never rapid releases like 8.1/8.2/8.3 |
  | ClamAV | 1.4 |
  | Prometheus | 3.13 |
  | Mattermost | the ESR (11.7) |
  | Forgejo | the LTS (15) |
  | nginx | the stable branch (1.30), not mainline |
- **No LTS track at all** (Postgres, where every major gets 5 years; Redis, Valkey and RabbitMQ community; Immich, Nextcloud community, Authentik and most apps): run the newest release the project still supports for the community. RabbitMQ, for example, patches only its latest minor series.
- **Never downgrade across data migrations.** A service already past its LTS (Forgejo 16 while the LTS is 15) stays on its supported stable line until the next LTS ships, then pins it. A service holding no data can be reset onto the LTS straight away.
- **Combined with the next section:** pick the LTS line first, then the exact version inside it that upstream's compose/docs test.
- Sources: the vendors' own policies ([ClamAV](https://docs.clamav.net/faq/faq-eol.html), [Prometheus](https://prometheus.io/docs/introduction/release-cycle/), [Mattermost](https://docs.mattermost.com/product-overview/release-policy.html), [Forgejo](https://endoflife.date/forgejo), [RabbitMQ](https://www.rabbitmq.com/docs/versions), [MongoDB](https://mongodb.com/support-policy/lifecycles), [MariaDB](https://mariadb.com/resources/blog/announcing-yearly-lts-releases-for-mariadb-community-server/)).

## How fixes are chosen

The same rule applies to adding a service, fixing an issue, adding a healthcheck, or bumping a version: **research first, then change once.**

1. **Reproduce and read the real error**: container logs, the healthcheck's own output (`docker inspect <c> --format '{{json .State.Health}}'`), and not just "unhealthy" or "exited".
2. **Look up how the project does it**, in this order:
   1. Its official compose file / `.env.example` / `deploy.env`.
   2. The image's own `HEALTHCHECK`: `docker image inspect <img> --format '{{json .Config.Healthcheck}}'`, or `skopeo inspect --config` if the image isn't pulled.
   3. Its documentation.
   4. Its issue tracker, which is often where breaking changes in a new release are explained.
   5. Widely used community setups.
3. **Use the documented answer.** Only design your own when nothing upstream exists, and record that in the service's doc and in a comment next to the change, so it's clear it's a local choice.
4. **Change once, verify live, then write it down** in `docs/services/<service>.md`, in the same commit.

Things learned the hard way on 2026-10-02 (above-CORE fresh-install run):
- **Healthcheck tool order:**
  1. The app's own binary or subcommand, in exec form (`loki -health`, `dagster api grpc-health-check`, `ak healthcheck`).
  2. The app's runtime (`node -e fetch(...)`, `python3 -c urllib...`).
  3. A bundled tool (`wait-for-it` in frappe).
  4. bash `/dev/tcp`, only as a last resort.

  Don't assume `curl`/`wget` exist: images move to slim and distroless bases between releases (Penpot 2.18, Karakeep Chrome).
- **Image-provided healthchecks:** prefer the one the image already ships (Immich, Jellyfin, Vaultwarden, Uptime Kuma, …). A compose `healthcheck:` silently replaces it.
- **Fresh-install paths need their own test:** data folders recreated by Docker are root-owned (Prometheus runs as uid 65534, Loki as 10001), and new releases add required settings (AppFlowy 0.18's `APPFLOWY_S3_PRESIGNED_URL_ENDPOINT`). `reset <service>` then `up` is the way to test that path.
