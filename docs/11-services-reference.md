# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports and proxy config. For setup steps, credentials, architecture, and troubleshooting per service, see [docs/services/](services/) — linked per-service below and from [10 — New Services](10-new-services.md). For which services have real per-person accounts vs. a single shared password vs. no login at all, see [13 — Auth Posture](13-auth-posture.md).

---

## Service Tiers

Services are grouped into additive tiers, plus a manual-only group. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `uv run homeserver.py dev up min` | beszel, cloudflared, nginx-plain, landing, docs, portainer |
| `core` | `uv run homeserver.py dev up core` | min + nextcloud, vaultwarden, forgejo, firefly, immich, jellyfin, guacamole, it-tools, authentik, atuin, observability |
| `all` | `uv run homeserver.py dev up all` | core + every extra service (manual-only services excluded) |

`down all` always stops everything in reverse order — no list to maintain.

**Extra services** (started with `up all` or individually):
dozzle, dockge, uptime-kuma, openproject, paperless, stirling-pdf-lite,
mealie, homebox, syncthing,
miniflux, audiobookshelf, invoiceshelf, appflowy, plane, ollama, open-webui, vikunja,
trilium, silverbullet, outline, bookstack, excalidraw, karakeep, ntfy, browser,
firefox, chromium, ungoogled-chromium, brave, mullvad-browser,
n8n, airflow, temporal, dagster, mailpit, mattermost, rocketchat, zulip,
crowdsec, wallabag, adguard-home, orangehrm, nocodb, listmonk,
documenso, calcom, plausible, penpot, coolify, supabase.

**Manual-only services** (never started by any tier — start individually with `up <service>`):
gitlab (redundant with forgejo at far higher memory cost), stirling-pdf full (redundant with stirling-pdf-lite at ~2x the memory).

---

## Port Reference

| Service | Container | Dev port | Container port | Tier |
| --- | --- | --- | --- | --- |
| Beszel | `beszel` | 8106 | 8090 | min |
| nginx-plain | `nginx-plain` | 8180 / 8443 | 80 / 443 | min |
| Landing Page | `landing` | 8080 | 80 | min |
| Portainer | `portainer` | 9000 / 9445 | 9000 / 9443 | min |
| Nextcloud | `nextcloud` | 8081 | 80 | core |
| Vaultwarden | `vaultwarden` | 8200 | 80 | core |
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | core |
| Firefly III + Importer | `firefly` / `firefly-importer` | 8102 / 8104 | 8080 | core |
| Immich | `immich-server` | 2283 | 2283 | core |
| Jellyfin | `jellyfin` | 8096 | 8096 | core |
| Guacamole | `guacamole` | 8107 | 8080 | core |
| Dozzle | `dozzle` | 9999 | 8080 | extra |
| Dockge | `dockge` | 5001 | 5001 | extra |
| Uptime Kuma | `uptime-kuma` | 3001 | 3001 | extra |
| OpenProject | `openproject` | 8099 | 80 | extra |
| Paperless-ngx | `paperless` | 8010 | 8000 | extra |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | 8080 | extra |
| Mealie | `mealie` | 9925 | 9000 | extra |
| HomeBox | `homebox` | 8136 | 7745 | extra |
| Syncthing | `syncthing` | 8087 | 8384 | extra |
| Authentik | `authentik-server` | 8088 / 9444 | 9000 / 9443 | extra |
| Miniflux | `miniflux` | 8093 | 8080 | extra |
| Audiobookshelf | `audiobookshelf` | 8094 | 80 | extra |
| InvoiceShelf | `invoiceshelf` | 8101 | 8080 | extra |
| AppFlowy | `appflowy-nginx` | 8103 | 80 | extra |
| Plane | `plane-proxy` | 8100 | 80 | extra |
| Ollama | `ollama` | 8110 | 11434 | extra (`--profile docker-ollama`) |
| Open WebUI | `open-webui` | 8109 | 8080 | extra |
| Vikunja | `vikunja` | 8111 | 3456 | extra |
| Trilium Notes | `trilium` | 8112 | 8080 | extra |
| SilverBullet | `silverbullet` | 8113 | 3000 | extra |
| Outline | `outline` | 8114 | 3000 | extra |
| BookStack | `bookstack` | 8115 | 80 | extra |
| Excalidraw | `excalidraw` | 8116 | 80 | extra |
| Karakeep | `karakeep` | 8117 | 3000 | extra |
| ntfy | `ntfy` | 8118 | 80 | extra |
| Firefox | `firefox` | 8145 | 3000 | extra |
| Chromium | `chromium` | 8146 | 3000 | extra |
| Ungoogled Chromium | `ungoogled-chromium` | 8147 | 3000 | extra |
| Brave | `brave` | 8148 | 3000 | extra |
| Mullvad Browser | `mullvad-browser` | 8149 | 3000 | extra |
| IT-Tools | `it-tools` | 8119 | 80 | core |
| n8n | `n8n` | 8120 | 5678 | extra |
| Airflow | `airflow-apiserver` | 8137 | 8080 | extra |
| Temporal | `temporal-ui` | 8138 | 8080 | extra |
| Dagster | `dagster-webserver` | 8139 | 3000 | extra |
| Mailpit | `mailpit` | 8140 | 8025 | extra |
| Mattermost | `mattermost` | 8141 | 8065 | extra |
| Rocket.Chat | `rocketchat` | 8142 | 3000 | extra |
| Zulip | `zulip` | 8143 | 80 | extra |
| Docs | `docs` | 8144 | 80 | min |
| CrowdSec | `crowdsec` | — (no port exposed, detection-only) | 8080 (internal LAPI) | extra |
| Wallabag | `wallabag` | 8121 | 80 | extra |
| Atuin | `atuin` | 8122 | 8888 | extra |
| AdGuard Home | `adguard-home` | 8123 (web UI) / 53 (DNS, LAN-wide) | 3000 / 53 | extra |
| GitLab CE | `gitlab` | 8085 / 2224 (SSH) | 80 / 22 | extra (manual) |
| OrangeHRM | `orangehrm` | 8125 | 80 | extra |
| NocoDB | `nocodb` | 8126 | 8080 | extra |
| Listmonk | `listmonk` | 8127 | 9000 | extra |
| Documenso | `documenso` | 8128 | 3000 | extra |
| Cal.com | `calcom` | 8129 | 3000 | extra |
| Plausible | `plausible` | 8130 | 8000 | extra |
| Penpot | `penpot-frontend` | 8131 | 8080 | extra |
| Coolify | `coolify` | 8132 | 8080 | extra |
| Supabase | `supabase-kong` | 8133 | 8000 | extra |
| Observability (Grafana) | `grafana` | 8134 | 3000 | core |
| Observability (Prometheus) | `prometheus` | 8135 | 9090 | core |
| Stirling PDF Full | `stirling-pdf` | 8089 | 8080 | extra (manual) |
| Nginx Proxy Manager | `nginx-proxy-manager` | 8180 / 8443 / 8181 (admin) | same | manual (optional) |

Observability's other four containers (`loki`, `alloy`, `cadvisor`, `node-exporter`) have no host port — they're only reached over the internal `homeserver` network (Prometheus scrapes cadvisor/node-exporter; Grafana queries Prometheus/Loki), and none of them have auth, so none get a public nginx-plain route either — only Grafana is public-facing.

**Next available ports:** web `8150`, SSH `2225`. (Coolify also uses `6001`/`6002` for its realtime websocket service — not part of the sequential web-port pool.) (Port `53` is claimed by AdGuard Home for LAN-wide DNS — not part of the sequential web-port pool, don't reassign it.) Always check this table before assigning a port to a new service — every host dev port and SSH port must be unique, even for manual-only services (they may run alongside `all`).

---

## Reverse Proxy Config

### nginx-plain (default)

Config lives in `nginx-plain/templates/default.conf.template`.
Domain is injected from `DOMAIN` in root `.env` at container start.

Each service gets a `server_name <service>.<DOMAIN>` block pointing to its container name.
No UI — edit the template file and recreate the container to reload.

### Nginx Proxy Manager (optional)

UI at `http://<server>:8181`. Add proxy hosts manually through the web interface.

> Run only one proxy at a time — both bind to ports 80/443 inside the container.
> To switch: `uv run homeserver.py dev up nginx` (or `up nginx-plain`) — `homeserver.py` detects the conflict and automatically stops the other proxy.

**Forward Hostname** = Docker container name (NPM resolves via `homeserver` network).
**Scheme** = `http` for all (Cloudflare handles TLS).

| Domain | Forward Hostname | Forward Port | Tier |
| --- | --- | --- | --- |
| `beszel.yourdomain.com` | `beszel` | `8090` | min |
| `portainer.yourdomain.com` | `portainer` | `9000` | min |
| `docs.yourdomain.com` | `docs` | `80` | min |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` | core |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` | core |
| `forgejo.yourdomain.com` | `forgejo` | `3000` | core |
| `firefly.yourdomain.com` | `firefly` | `8080` | core |
| `firefly-import.yourdomain.com` | `firefly-importer` | `8080` | core |
| `immich.yourdomain.com` | `immich-server` | `2283` | core |
| `photos.yourdomain.com` | `immich-server` | `2283` | core |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` | core |
| `guacamole.yourdomain.com` | `guacamole` | `8080` | core |
| `dozzle.yourdomain.com` | `dozzle` | `8080` | extra |
| `dockge.yourdomain.com` | `dockge` | `5001` | extra |
| `paperless.yourdomain.com` | `paperless` | `8000` | extra |
| `stirling-pdf-lite.yourdomain.com` | `stirling-pdf-lite` | `8080` | extra |
| `stirling-pdf.yourdomain.com` | `stirling-pdf` | `8080` | extra (manual) |
| `mealie.yourdomain.com` | `mealie` | `9000` | extra |
| `homebox.yourdomain.com` | `homebox` | `7745` | extra |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` | extra |
| `status.yourdomain.com` | `uptime-kuma` | `3001` | extra |
| `syncthing.yourdomain.com` | `syncthing` | `8384` | extra |
| `authentik.yourdomain.com` | `authentik-server` | `9000` | extra |
| `miniflux.yourdomain.com` | `miniflux` | `8080` | extra |
| `audiobookshelf.yourdomain.com` | `audiobookshelf` | `80` | extra |
| `openproject.yourdomain.com` | `openproject` | `80` | extra |
| `plane.yourdomain.com` | `plane-proxy` | `80` | extra |
| `invoiceshelf.yourdomain.com` | `invoiceshelf` | `8080` | extra |
| `appflowy.yourdomain.com` | `appflowy-nginx` | `80` | extra |
| `open-webui.yourdomain.com` | `open-webui` | `8080` | extra |
| `vikunja.yourdomain.com` | `vikunja` | `3456` | extra |
| `trilium.yourdomain.com` | `trilium` | `8080` | extra |
| `silverbullet.yourdomain.com` | `silverbullet` | `3000` | extra |
| `outline.yourdomain.com` | `outline` | `3000` | extra |
| `bookstack.yourdomain.com` | `bookstack` | `80` | extra |
| `excalidraw.yourdomain.com` | `excalidraw` | `80` | extra |
| `karakeep.yourdomain.com` | `karakeep` | `3000` | extra |
| `ntfy.yourdomain.com` | `ntfy` | `80` | extra |
| `browser.yourdomain.com` | *(doesn't fit this table — subpath-routed to 5 different containers behind one shared login, not a single forward host)* | *(use NPM's Advanced tab with a custom nginx snippet — see [browser-hub.md](services/browser-hub.md))* | extra |
| `it-tools.yourdomain.com` | `it-tools` | `80` | core |
| `n8n.yourdomain.com` | `n8n` | `5678` | extra |
| `airflow.yourdomain.com` | `airflow-apiserver` | `8080` | extra |
| `temporal.yourdomain.com` | `temporal-ui` | `8080` | extra |
| `dagster.yourdomain.com` | `dagster-webserver` | `3000` | extra |
| `mailpit.yourdomain.com` | `mailpit` | `8025` | extra |
| `mattermost.yourdomain.com` | `mattermost` | `8065` | extra |
| `rocketchat.yourdomain.com` | `rocketchat` | `3000` | extra |
| `zulip.yourdomain.com` | `zulip` | `80` | extra |
| `wallabag.yourdomain.com` | `wallabag` | `80` | extra |
| `atuin.yourdomain.com` | `atuin` | `8888` | extra |
| `adguard-home.yourdomain.com` | `adguard-home` | `3000` | extra |
| `gitlab.yourdomain.com` | `gitlab` | `80` | extra (manual) |
| `orangehrm.yourdomain.com` | `orangehrm` | `80` | extra |
| `nocodb.yourdomain.com` | `nocodb` | `8080` | extra |
| `listmonk.yourdomain.com` | `listmonk` | `9000` | extra |
| `documenso.yourdomain.com` | `documenso` | `3000` | extra |
| `calcom.yourdomain.com` | `calcom` | `3000` | extra |
| `plausible.yourdomain.com` | `plausible` | `8000` | extra |
| `penpot.yourdomain.com` | `penpot-frontend` | `8080` | extra |
| `coolify.yourdomain.com` | `coolify` | `8080` | extra |
| `supabase.yourdomain.com` | `supabase-kong` | `8000` | extra |
| `grafana.yourdomain.com` | `grafana` | `3000` | core |

---

## Service Notes

Per-service setup, credentials, architecture, and troubleshooting now live under [docs/services/](services/) — one doc per service, indexed in [10 — New Services](10-new-services.md#per-service-setup-guides).

---

[← New Services](10-new-services.md) | [Home](../setup.md)
