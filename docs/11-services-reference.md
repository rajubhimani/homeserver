# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md) | [Next: VPN →](12-vpn.md)

---

Quick reference for all services — ports and proxy config. For setup steps, credentials, architecture, and troubleshooting per service, see [docs/services/](services/) — linked per-service below and from [10 — New Services](10-new-services.md).

---

## Service Tiers

Services are grouped into three additive tiers. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `sh homeserver.sh dev up min` | dozzle, cloudflared, nginx-plain, landing, beszel |
| `core` | `sh homeserver.sh dev up core` | min + nextcloud, vaultwarden, forgejo, firefly, immich, appflowy, plane |
| `all` | `sh homeserver.sh dev up all` | core + every extra service |

`down all` always stops everything in reverse order — no list to maintain.

**Extra services** (started with `up all` or individually):
dockge, portainer, openproject, gitlab, jellyfin, paperless, stirling-pdf-lite,
mealie, uptime-kuma, stirling-pdf, stalwart, snappymail, roundcube, syncthing, authentik, ntfy,
miniflux, audiobookshelf, conduit, wg-easy,
headscale, openvpn, invoiceshelf, guacamole, and more.

---

## Port Reference

| Service | Container | Dev port | Container port | Tier |
| --- | --- | --- | --- | --- |
| nginx-plain | `nginx-plain` | 80 / 443 | 80 / 443 | min |
| Landing Page | `landing` | 8080 | 80 | min |
| Dozzle | `dozzle` | 9999 | 8080 | min |
| Nextcloud | `nextcloud` | 8081 | 80 | core |
| Immich | `immich-server` | 2283 | 2283 | extra |
| Jellyfin | `jellyfin` | 8096 | 8096 | extra |
| Vaultwarden | `vaultwarden` | 8200 | 80 | extra |
| Paperless-ngx | `paperless` | 8010 | 8000 | extra |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | 8080 | extra |
| Stirling PDF Full | `stirling-pdf` | 8089 | 8080 | extra (manual) |
| Mealie | `mealie` | 9925 | 9000 | extra |
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | core |
| GitLab CE | `gitlab` | 8085 / 2224 (SSH) | 80 / 22 | extra |
| Uptime Kuma | `uptime-kuma` | 3001 | 3001 | extra |
| Headscale | `headscale` | 8086 | 8080 | extra (manual) |
| Syncthing | `syncthing` | 8087 | 8384 | extra |
| Authentik | `authentik-server` | 8088 | 9000 | extra |
| Stalwart Mail | `stalwart` | 8091 | 8080 | extra |
| Ntfy | `ntfy` | 8092 | 80 | extra |
| Miniflux | `miniflux` | 8093 | 8080 | extra |
| Audiobookshelf | `audiobookshelf` | 8094 | 80 | extra |
| Conduit (Matrix) | `conduit` | 8095 / 8448 (fed.) | 6167 | extra |
| Snappymail | `snappymail` | 8097 | 8888 | extra |
| Roundcube | `roundcube` | 8098 | 80 | extra |
| OpenProject | `openproject` | 8099 | 80 | extra |
| Plane | `plane-proxy` | 8100 | 80 | extra |
| InvoiceShelf | `invoiceshelf` | 8101 | 8080 | extra |
| Firefly III + Importer | `firefly` / `firefly-importer` | 8102 / 8104 | 8080 | core |
| AppFlowy | `appflowy-nginx` | 8103 | 80 | extra |
| Beszel | `beszel` | 8106 | 8090 | min |
| Guacamole | `guacamole` | 8107 | 8080 | extra |
| Nginx Proxy Manager | `nginx-proxy-manager` | 80 / 443 / 81 (admin) | same | extra (optional) |

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
> To switch: replace `nginx-plain` with `nginx` in `SERVICES_CORE` in `homeserver.sh`.

**Forward Hostname** = Docker container name (NPM resolves via `homeserver` network).
**Scheme** = `http` for all (Cloudflare handles TLS).

| Domain | Forward Hostname | Forward Port |
| --- | --- | --- |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` |
| `immich.yourdomain.com` | `immich-server` | `2283` |
| `photos.yourdomain.com` | `immich-server` | `2283` |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` |
| `paperless.yourdomain.com` | `paperless` | `8000` |
| `stirling-pdf.yourdomain.com` | `stirling-pdf-lite` | `8080` |
| `mealie.yourdomain.com` | `mealie` | `9000` |
| `forgejo.yourdomain.com` | `forgejo` | `3000` |
| `gitlab.yourdomain.com` | `gitlab` | `80` |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` |
| `status.yourdomain.com` | `uptime-kuma` | `3001` |
| `dozzle.yourdomain.com` | `dozzle` | `8080` |
| `mail.yourdomain.com` | `stalwart` | `8080` |
| `webmail.yourdomain.com` | `snappymail` | `8888` |
| `roundcube.yourdomain.com` | `roundcube` | `80` |
| `syncthing.yourdomain.com` | `syncthing` | `8384` |
| `authentik.yourdomain.com` | `authentik-server` | `9000` |
| `ntfy.yourdomain.com` | `ntfy` | `80` |
| `miniflux.yourdomain.com` | `miniflux` | `8080` |
| `audiobookshelf.yourdomain.com` | `audiobookshelf` | `80` |
| `conduit.yourdomain.com` | `conduit` | `6167` |
| `openproject.yourdomain.com` | `openproject` | `80` |
| `plane.yourdomain.com` | `plane-proxy` | `80` |
| `invoiceshelf.yourdomain.com` | `invoiceshelf` | `8080` |
| `firefly.yourdomain.com` | `firefly` | `8080` |
| `firefly-import.yourdomain.com` | `firefly-importer` | `8080` |
| `appflowy.yourdomain.com` | `appflowy-nginx` | `80` |
| `beszel.yourdomain.com` | `beszel` | `8090` |
| `guacamole.yourdomain.com` | `guacamole` | `8080` |

---

## Service Notes

Per-service setup, credentials, architecture, and troubleshooting now live under [docs/services/](services/) — one doc per service, indexed in [10 — New Services](10-new-services.md#per-service-setup-guides).

---

[← New Services](10-new-services.md) | [Home](../setup.md) | [Next: VPN →](12-vpn.md)
