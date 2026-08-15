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
| Nextcloud | [docs/services/nextcloud.md](services/nextcloud.md) |
| Immich | [docs/services/immich.md](services/immich.md) |
| Jellyfin | [docs/services/jellyfin.md](services/jellyfin.md) |
| Vaultwarden | [docs/services/vaultwarden.md](services/vaultwarden.md) |
| Paperless-ngx | [docs/services/paperless.md](services/paperless.md) |
| Stirling PDF (Lite + Full) | [docs/services/stirling-pdf.md](services/stirling-pdf.md) |
| Mealie | [docs/services/mealie.md](services/mealie.md) |
| HomeBox | [docs/services/homebox.md](services/homebox.md) |
| Forgejo | [docs/services/forgejo.md](services/forgejo.md) |
| GitLab CE | [docs/services/gitlab.md](services/gitlab.md) |
| Uptime Kuma | [docs/services/uptime-kuma.md](services/uptime-kuma.md) |
| Dozzle | [docs/services/dozzle.md](services/dozzle.md) |
| Syncthing | [docs/services/syncthing.md](services/syncthing.md) |
| Authentik | [docs/services/authentik.md](services/authentik.md) |
| Miniflux | [docs/services/miniflux.md](services/miniflux.md) |
| Audiobookshelf | [docs/services/audiobookshelf.md](services/audiobookshelf.md) |
| OpenProject | [docs/services/openproject.md](services/openproject.md) |
| Plane | [docs/services/plane.md](services/plane.md) |
| InvoiceShelf | [docs/services/invoiceshelf.md](services/invoiceshelf.md) |
| AppFlowy | [docs/services/appflowy.md](services/appflowy.md) |
| Firefly III (+ Data Importer) | [docs/services/firefly.md](services/firefly.md) |
| Beszel | [docs/services/beszel.md](services/beszel.md) |
| Guacamole | [docs/services/guacamole.md](services/guacamole.md) |
| Portainer CE | [docs/services/portainer.md](services/portainer.md) |
| Dockge | [docs/services/dockge.md](services/dockge.md) |
| Ollama + Open WebUI | [docs/services/open-webui.md](services/open-webui.md) |
| Vikunja | [docs/services/vikunja.md](services/vikunja.md) |
| Trilium Notes | [docs/services/trilium.md](services/trilium.md) |
| SilverBullet | [docs/services/silverbullet.md](services/silverbullet.md) |
| Outline | [docs/services/outline.md](services/outline.md) |
| BookStack | [docs/services/bookstack.md](services/bookstack.md) |
| Excalidraw | [docs/services/excalidraw.md](services/excalidraw.md) |
| Karakeep | [docs/services/karakeep.md](services/karakeep.md) |
| ntfy | [docs/services/ntfy.md](services/ntfy.md) |
| IT-Tools | [docs/services/it-tools.md](services/it-tools.md) |
| n8n | [docs/services/n8n.md](services/n8n.md) |
| Airflow | [docs/services/airflow.md](services/airflow.md) |
| Temporal | [docs/services/temporal.md](services/temporal.md) |
| Dagster | [docs/services/dagster.md](services/dagster.md) |
| CrowdSec | [docs/services/crowdsec.md](services/crowdsec.md) |
| Wallabag | [docs/services/wallabag.md](services/wallabag.md) |
| Atuin | [docs/services/atuin.md](services/atuin.md) |
| AdGuard Home | [docs/services/adguard-home.md](services/adguard-home.md) |
| PhotoPrism | [docs/services/photoprism.md](services/photoprism.md) |
| OrangeHRM | [docs/services/orangehrm.md](services/orangehrm.md) |
| NocoDB | [docs/services/nocodb.md](services/nocodb.md) |
| Listmonk | [docs/services/listmonk.md](services/listmonk.md) |
| Documenso | [docs/services/documenso.md](services/documenso.md) |
| Cal.com | [docs/services/calcom.md](services/calcom.md) |
| Plausible | [docs/services/plausible.md](services/plausible.md) |
| Penpot | [docs/services/penpot.md](services/penpot.md) |
| Coolify | [docs/services/coolify.md](services/coolify.md) |
| Supabase | [docs/services/supabase.md](services/supabase.md) |
| Observability (Grafana + Prometheus + Loki) | [docs/services/observability.md](services/observability.md) |

---

[← Firewall](09-firewall.md) | [Home](../setup.md) | [Next: Services Reference →](11-services-reference.md)
