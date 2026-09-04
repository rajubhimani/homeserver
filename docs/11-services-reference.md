# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports and proxy config. For setup steps, credentials, architecture, and troubleshooting per service, see [docs/services/](services/) — linked per-service below and from [10 — New Services](10-new-services.md). For which services have real per-person accounts vs. a single shared password vs. no login at all, see [13 — Auth Posture](13-auth-posture.md). For services that overlap in function (multiple chat apps, wikis, project trackers, etc.), memory cost side by side, and which is behind on updates, see [14 — Service Comparison](14-service-comparison.md).

---

## Service Tiers

Services are grouped into additive tiers, plus a manual-only group. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `uv run homeserver.py dev up min` | beszel, cloudflared, nginx-plain, portainer, docs, landing |
| `core` | `uv run homeserver.py dev up core` | min + ntfy, uptime-kuma, adguard-home, authentik, vaultwarden, firefly, immich, clamav, nextcloud, onlyoffice, whiteboard, jellyfin, forgejo, wg-easy, atuin, guacamole, it-tools, mailpit, plausible |
| `daily` | `uv run homeserver.py dev up daily` | min + core + every daily service below — **opt-in, never implied by `up core`**; turned on/off explicitly |
| `office` | `uv run homeserver.py dev up office` | min + core + daily + every office service below — **opt-in, never implied by `up daily`** |
| `automation-ai` | `uv run homeserver.py dev up automation-ai` | min + core + daily + office + every automation/AI service below — **opt-in, never implied by `up office`** |
| `all` | `uv run homeserver.py dev up all` | core + daily + office + automation-ai + every extra service (manual-only services excluded) |

**`up core`/`up daily`/`up office`/`up automation-ai` bootstrap, they don't
restart**: each checks which of its lower tier(s) are already running and
only starts what's missing — an already-running lower tier is left
untouched, not force-recreated.

**`down` is tier-scoped, not cascading**: `down core` stops only core (`min`
stays up), `down daily` stops only daily (`min`/`core` stay up), `down
office` stops only office (`min`/`core`/`daily` stay up), `down
automation-ai` stops only automation-ai (`min`/`core`/`daily`/`office` stay
up). Every `down` command stops every optional Compose-profile container for
the selected service(s), too (such as GitLab's CI runner). `down all` is the
one command that stops the entire stack, in reverse order — no list to
maintain.

**Daily services** (regular-use apps that aren't core infra — started with `up daily`/`up all` or individually):
brave, chromium, coolify, excalidraw, firefox, ungoogled-chromium,
mullvad-browser, browser, karakeep, homebox, silverbullet, syncthing, trilium,
wallabag.

**Office services** (firm/business apps — started with `up office`/`up all` or individually):
stirling-pdf-lite, stirling-pdf, vikunja, appflowy, plane, calcom, listmonk, miniflux.

**Automation & AI services** (workflow/automation/AI apps — started with `up automation-ai`/`up all` or individually):
airflow, dagster, temporal, ollama, open-webui, n8n.

**Extra services** (started with `up all` or individually):
crowdsec, dockge, dozzle,
paperless, bookstack, audiobookshelf, mealie,
supabase, nocodb, outline, penpot,
documenso, invoiceshelf, openproject, mattermost,
rocketchat, zulip, orangehrm.

**Manual-only services** (never started by any tier — start individually with `up <service>`):
gitlab (redundant with forgejo at far higher memory cost).

---

## Port Reference

| Service | Container | Dev port | Container port | Tier |
| --- | --- | --- | --- | --- |
| Beszel | `beszel` | 8106 | 8090 | min |
| nginx-plain | `nginx-plain` | 8180 / 8443 | 80 / 443 | min |
| Portainer | `portainer` | 9000 / 9445 | 9000 / 9443 | min |
| Docs | `docs` | 8144 | 80 | min |
| Landing Page | `landing` | 8080 | 80 | min |
| ntfy | `ntfy` | 8118 | 80 | core |
| AdGuard Home | `adguard-home` | 8123 (web UI) / 53 (DNS, LAN-wide) | 3000 / 53 | core |
| Authentik | `authentik-server` | 8088 / 9444 | 9000 / 9443 | core |
| Vaultwarden | `vaultwarden` | 8200 | 80 | core |
| Firefly III + Importer | `firefly` / `firefly-importer` | 8102 / 8104 | 8080 | core |
| Immich | `immich-server` | 2283 | 2283 | core |
| ClamAV | `clamav` | 8152 | 3310 | core |
| Nextcloud | `nextcloud` | 8081 | 80 | core |
| ONLYOFFICE | `onlyoffice` | 8150 | 80 | core |
| Nextcloud Whiteboard | `whiteboard` | 8151 | 3002 | core |
| Jellyfin | `jellyfin` | 8096 | 8096 | core |
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | core |
| wg-easy | `wg-easy` | 51820/UDP, 51821 (admin) | same — `network_mode: host`, no port remapping | core |
| Atuin | `atuin` | 8122 | 8888 | core |
| Guacamole | `guacamole` | 8107 | 8080 | core |
| IT-Tools | `it-tools` | 8119 | 80 | core |
| Mailpit | `mailpit` | 8140 | 8025 | core |
| Observability (Grafana) | `grafana` | 8134 | 3000 | core |
| Observability (Prometheus) | `prometheus` | 8135 | 9090 | core |
| Uptime Kuma | `uptime-kuma` | 3001 | 3001 | core |
| Plausible | `plausible` | 8130 | 8000 | core |
| Brave | `brave` | 8148 | 3000 | daily |
| Chromium | `chromium` | 8146 | 3000 | daily |
| Coolify | `coolify` | 8132 | 8080 | daily |
| Excalidraw | `excalidraw` | 8116 | 80 | daily |
| Firefox | `firefox` | 8145 | 3000 | daily |
| Ungoogled Chromium | `ungoogled-chromium` | 8147 | 3000 | daily |
| Mullvad Browser | `mullvad-browser` | 8149 | 3000 | daily |
| Karakeep | `karakeep` | 8117 | 3000 | daily |
| HomeBox | `homebox` | 8136 | 7745 | daily |
| SilverBullet | `silverbullet` | 8113 | 3000 | daily |
| Syncthing | `syncthing` | 8087 | 8384 | daily |
| Trilium Notes | `trilium` | 8112 | 8080 | daily |
| Wallabag | `wallabag` | 8121 | 80 | daily |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | 8080 | office |
| Stirling PDF Full | `stirling-pdf` | 8089 | 8080 | office |
| Vikunja | `vikunja` | 8111 | 3456 | office |
| AppFlowy | `appflowy-nginx` | 8103 | 80 | office |
| Plane | `plane-proxy` | 8100 | 80 | office |
| Cal.com | `calcom` | 8129 | 3000 | office |
| Listmonk | `listmonk` | 8127 | 9000 | office |
| Miniflux | `miniflux` | 8093 | 8080 | office |
| Airflow | `airflow-apiserver` | 8137 | 8080 | automation-ai |
| Dagster | `dagster-webserver` | 8139 | 3000 | automation-ai |
| Temporal | `temporal-ui` | 8138 | 8080 | automation-ai |
| Ollama | `ollama` | 8110 | 11434 | automation-ai |
| Open WebUI | `open-webui` | 8109 | 8080 | automation-ai |
| n8n | `n8n` | 8120 | 5678 | automation-ai |
| CrowdSec | `crowdsec` | — (no port exposed, detection-only) | 8080 (internal LAPI) | extra |
| Dockge | `dockge` | 5001 | 5001 | extra |
| Dozzle | `dozzle` | 9999 | 8080 | extra |
| Paperless-ngx | `paperless` | 8010 | 8000 | extra |
| BookStack | `bookstack` | 8115 | 80 | extra |
| Audiobookshelf | `audiobookshelf` | 8094 | 80 | extra |
| Mealie | `mealie` | 9925 | 9000 | extra |
| Supabase | `supabase-kong` | 8133 | 8000 | extra |
| NocoDB | `nocodb` | 8126 | 8080 | extra |
| Outline | `outline` | 8114 | 3000 | extra |
| Penpot | `penpot-frontend` | 8131 | 8080 | extra |
| Documenso | `documenso` | 8128 | 3000 | extra |
| InvoiceShelf | `invoiceshelf` | 8101 | 8080 | extra |
| OpenProject | `openproject` | 8099 | 80 | extra |
| Mattermost | `mattermost` | 8141 | 8065 | extra |
| Rocket.Chat | `rocketchat` | 8142 | 3000 | extra |
| Zulip | `zulip` | 8143 | 80 | extra |
| OrangeHRM | `orangehrm` | 8125 | 80 | extra |
| GitLab CE | `gitlab` | 8085 / 2224 (SSH) | 80 / 22 | manual |
| Nginx Proxy Manager | `nginx-proxy-manager` | 8180 / 8443 / 8181 (admin) | same | manual (optional) |

Observability's other four containers (`loki`, `alloy`, `cadvisor`, `node-exporter`) have no host port — they're only reached over the internal `homeserver` network (Prometheus scrapes cadvisor/node-exporter; Grafana queries Prometheus/Loki), and none of them have auth, so none get a public nginx-plain route either — only Grafana is public-facing.

**Next available ports:** web `8153`, SSH `2225`. (Coolify also uses `6001`/`6002` for its realtime websocket service — not part of the sequential web-port pool.) (Port `53` is claimed by AdGuard Home for LAN-wide DNS — not part of the sequential web-port pool, don't reassign it.) Always check this table before assigning a port to a new service — every host dev port and SSH port must be unique, even for manual-only services (they may run alongside `all`).

**In `prod` mode, every service above is also reachable at `10.8.0.1:<same port>`** over the WireGuard tunnel (whether the service is currently running or not — the binding is in `compose.prod.yml`, applied whenever it's next started) (in addition to `127.0.0.1`, not instead of it) — e.g. `10.8.0.1:2283` for Immich, `10.8.0.1:8096` for Jellyfin. See [09 — Firewall § Restoring fast direct access, safely](09-firewall.md#restoring-fast-direct-access-safely-the-10801-pattern) for why this is safe and how to add it to a new service.

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
| `ntfy.yourdomain.com` | `ntfy` | `80` | core |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` | core |
| `onlyoffice.yourdomain.com` | `onlyoffice` | `80` | core |
| `whiteboard.yourdomain.com` | `whiteboard` | `3002` | core |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` | core |
| `forgejo.yourdomain.com` | `forgejo` | `3000` | core |
| `firefly.yourdomain.com` | `firefly` | `8080` | core |
| `firefly-import.yourdomain.com` | `firefly-importer` | `8080` | core |
| `immich.yourdomain.com` | `immich-server` | `2283` | core |
| `photos.yourdomain.com` | `immich-server` | `2283` | core |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` | core |
| `guacamole.yourdomain.com` | `guacamole` | `8080` | core |
| `authentik.yourdomain.com` | `authentik-server` | `9000` | core |
| `it-tools.yourdomain.com` | `it-tools` | `80` | core |
| `mailpit.yourdomain.com` | `mailpit` | `8025` | core |
| `atuin.yourdomain.com` | `atuin` | `8888` | core |
| `plausible.yourdomain.com` | `plausible` | `8000` | core |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` | core |
| `status.yourdomain.com` | `uptime-kuma` | `3001` | core |
| `grafana.yourdomain.com` | `grafana` | `3000` | core |
| `adguard-home.yourdomain.com` | `adguard-home` | `3000` | core |
| `stirling-pdf-lite.yourdomain.com` | `stirling-pdf-lite` | `8080` | office |
| `stirling-pdf.yourdomain.com` | `stirling-pdf` | `8080` | office |
| `homebox.yourdomain.com` | `homebox` | `7745` | daily |
| `syncthing.yourdomain.com` | `syncthing` | `8384` | daily |
| `miniflux.yourdomain.com` | `miniflux` | `8080` | office |
| `plane.yourdomain.com` | `plane-proxy` | `80` | office |
| `appflowy.yourdomain.com` | `appflowy-nginx` | `80` | office |
| `open-webui.yourdomain.com` | `open-webui` | `8080` | automation-ai |
| `ollama.yourdomain.com` | `ollama` | `11434` | automation-ai |
| `vikunja.yourdomain.com` | `vikunja` | `3456` | office |
| `trilium.yourdomain.com` | `trilium` | `8080` | daily |
| `silverbullet.yourdomain.com` | `silverbullet` | `3000` | daily |
| `excalidraw.yourdomain.com` | `excalidraw` | `80` | daily |
| `karakeep.yourdomain.com` | `karakeep` | `3000` | daily |
| `browser.yourdomain.com` | *(doesn't fit this table — subpath-routed to 5 different containers behind one shared login, not a single forward host)* | *(use NPM's Advanced tab with a custom nginx snippet — see [browser-hub.md](services/browser-hub.md))* | daily |
| `n8n.yourdomain.com` | `n8n` | `5678` | automation-ai |
| `airflow.yourdomain.com` | `airflow-apiserver` | `8080` | automation-ai |
| `temporal.yourdomain.com` | `temporal-ui` | `8080` | automation-ai |
| `dagster.yourdomain.com` | `dagster-webserver` | `3000` | automation-ai |
| `wallabag.yourdomain.com` | `wallabag` | `80` | daily |
| `listmonk.yourdomain.com` | `listmonk` | `9000` | office |
| `calcom.yourdomain.com` | `calcom` | `3000` | office |
| `coolify.yourdomain.com` | `coolify` | `8080` | daily |
| `dozzle.yourdomain.com` | `dozzle` | `8080` | extra |
| `dockge.yourdomain.com` | `dockge` | `5001` | extra |
| `paperless.yourdomain.com` | `paperless` | `8000` | extra |
| `mealie.yourdomain.com` | `mealie` | `9000` | extra |
| `audiobookshelf.yourdomain.com` | `audiobookshelf` | `80` | extra |
| `openproject.yourdomain.com` | `openproject` | `80` | extra |
| `invoiceshelf.yourdomain.com` | `invoiceshelf` | `8080` | extra |
| `outline.yourdomain.com` | `outline` | `3000` | extra |
| `bookstack.yourdomain.com` | `bookstack` | `80` | extra |
| `mattermost.yourdomain.com` | `mattermost` | `8065` | extra |
| `rocketchat.yourdomain.com` | `rocketchat` | `3000` | extra |
| `zulip.yourdomain.com` | `zulip` | `80` | extra |
| `orangehrm.yourdomain.com` | `orangehrm` | `80` | extra |
| `nocodb.yourdomain.com` | `nocodb` | `8080` | extra |
| `documenso.yourdomain.com` | `documenso` | `3000` | extra |
| `penpot.yourdomain.com` | `penpot-frontend` | `8080` | extra |
| `supabase.yourdomain.com` | `supabase-kong` | `8000` | extra |
| `gitlab.yourdomain.com` | `gitlab` | `80` | manual |

---

## Service Notes

Per-service setup, credentials, architecture, and troubleshooting now live under [docs/services/](services/) — one doc per service, indexed in [10 — New Services](10-new-services.md#per-service-setup-guides).

---

[← New Services](10-new-services.md) | [Home](../setup.md)
