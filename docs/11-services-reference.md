# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports and proxy config. For setup steps, credentials, architecture, and troubleshooting per service, see [docs/services/](services/) — linked per-service below and from [10 — New Services](10-new-services.md).

---

## Service Tiers

Services are grouped into additive tiers, plus a manual-only group. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `uv run homeserver.py dev up min` | dozzle, beszel, cloudflared, nginx-plain, landing |
| `core` | `uv run homeserver.py dev up core` | min + nextcloud, vaultwarden, forgejo, firefly, immich, jellyfin, guacamole |
| `all` | `uv run homeserver.py dev up all` | core + every extra service (manual-only services excluded) |

`down all` always stops everything in reverse order — no list to maintain.

**Extra services** (started with `up all` or individually):
dockge, portainer, uptime-kuma, openproject, paperless, stirling-pdf-lite,
mealie, syncthing, authentik,
miniflux, audiobookshelf, invoiceshelf, appflowy, plane.

**Manual-only services** (never started by any tier — start individually with `up <service>`):
gitlab (redundant with forgejo at far higher memory cost), stirling-pdf full (redundant with stirling-pdf-lite at ~2x the memory).

---

## Port Reference

| Service | Container | Dev port | Container port | Tier |
| --- | --- | --- | --- | --- |
| Dozzle | `dozzle` | 9999 | 8080 | min |
| Beszel | `beszel` | 8106 | 8090 | min |
| nginx-plain | `nginx-plain` | 80 / 443 | 80 / 443 | min |
| Landing Page | `landing` | 8080 | 80 | min |
| Nextcloud | `nextcloud` | 8081 | 80 | core |
| Vaultwarden | `vaultwarden` | 8200 | 80 | core |
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | core |
| Firefly III + Importer | `firefly` / `firefly-importer` | 8102 / 8104 | 8080 | core |
| Immich | `immich-server` | 2283 | 2283 | core |
| Jellyfin | `jellyfin` | 8096 | 8096 | core |
| Guacamole | `guacamole` | 8107 | 8080 | core |
| Dockge | `dockge` | 5001 | 5001 | extra |
| Portainer | `portainer` | 9000 / 9443 | 9000 / 9443 | extra |
| Uptime Kuma | `uptime-kuma` | 3001 | 3001 | extra |
| OpenProject | `openproject` | 8099 | 80 | extra |
| Paperless-ngx | `paperless` | 8010 | 8000 | extra |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | 8080 | extra |
| Mealie | `mealie` | 9925 | 9000 | extra |
| Syncthing | `syncthing` | 8087 | 8384 | extra |
| Authentik | `authentik-server` | 8088 / 9444 | 9000 / 9443 | extra |
| Miniflux | `miniflux` | 8093 | 8080 | extra |
| Audiobookshelf | `audiobookshelf` | 8094 | 80 | extra |
| InvoiceShelf | `invoiceshelf` | 8101 | 8080 | extra |
| AppFlowy | `appflowy-nginx` | 8103 | 80 | extra |
| Plane | `plane-proxy` | 8100 | 80 | extra |
| GitLab CE | `gitlab` | 8085 / 2224 (SSH) | 80 / 22 | extra (manual) |
| Stirling PDF Full | `stirling-pdf` | 8089 | 8080 | extra (manual) |
| Jellyfin Postgres test | `jellyfin-pgsql-test` | 8097 | 8096 | extra (manual) |
| Nginx Proxy Manager | `nginx-proxy-manager` | 80 / 443 / 81 (admin) | same | extra (optional) |

**Next available ports:** web `8109`, SSH `2225`. Always check this table before assigning a port to a new service — every host dev port and SSH port must be unique, even for manual-only services (they may run alongside `all`).

---

## Reverse Proxy Config

### nginx-plain (default)

Config lives in `nginx-plain/templates/default.conf.template`.
Domain is injected from `DOMAIN` in root `.env` at container start.

Each service gets a `server_name <service>.<DOMAIN>` block pointing to its container name.
No UI — edit the template file and recreate the container to reload.

### Nginx Proxy Manager (optional)

UI at `http://<server>:81`. Add proxy hosts manually through the web interface.

> Run only one proxy at a time — both bind to ports 80/443.
> To switch: replace `nginx-plain` with `nginx` in `SERVICES_MIN` in `homeserver.py`.

**Forward Hostname** = Docker container name (NPM resolves via `homeserver` network).
**Scheme** = `http` for all (Cloudflare handles TLS).

| Domain | Forward Hostname | Forward Port | Tier |
| --- | --- | --- | --- |
| `dozzle.yourdomain.com` | `dozzle` | `8080` | min |
| `beszel.yourdomain.com` | `beszel` | `8090` | min |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` | core |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` | core |
| `forgejo.yourdomain.com` | `forgejo` | `3000` | core |
| `firefly.yourdomain.com` | `firefly` | `8080` | core |
| `firefly-import.yourdomain.com` | `firefly-importer` | `8080` | core |
| `immich.yourdomain.com` | `immich-server` | `2283` | core |
| `photos.yourdomain.com` | `immich-server` | `2283` | core |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` | core |
| `guacamole.yourdomain.com` | `guacamole` | `8080` | core |
| `paperless.yourdomain.com` | `paperless` | `8000` | extra |
| `stirling-pdf.yourdomain.com` | `stirling-pdf-lite` | `8080` | extra |
| `mealie.yourdomain.com` | `mealie` | `9000` | extra |
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
| `gitlab.yourdomain.com` | `gitlab` | `80` | extra (manual) |
| `jellyfin-test.yourdomain.com` | `jellyfin-pgsql-test` | `8096` | extra (manual) |

---

## Service Notes

Per-service setup, credentials, architecture, and troubleshooting now live under [docs/services/](services/) — one doc per service, indexed in [10 — New Services](10-new-services.md#per-service-setup-guides).

---

[← New Services](10-new-services.md) | [Home](../setup.md)
