# Homeserver

A self-hosted personal cloud on your own hardware, run with Docker Compose. It replaces Google Drive and Photos, Netflix, password managers, Slack and dozens more, with individual logins for the family. Over 60 services live in one repo, each in its own folder under `services/`, and one script manages all of them.

> The full guide, with the whole service list, is **[setup.md](setup.md)**. Every service has its own page under [`docs/services/`](docs/services/).

## Quick start

You need Docker (or Podman), git and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rajubhimani/homeserver.git && cd homeserver
uv sync                                   # once
cp .env.example .env                      # set DOMAIN and RUNTIME
cp services/nextcloud/.env.example services/nextcloud/.env   # per service you start

uv run homeserver.py dev up min           # infrastructure: proxy, tunnel, docs, landing page
uv run homeserver.py dev up core          # always-on apps
uv run homeserver.py dev up open-webui    # or any single service
uv run homeserver.py dev logs open-webui
uv run homeserver.py prod up all          # prod binds ports to 127.0.0.1 only
```

`homeserver.py` is the only entrypoint (Python standard library only). Every start and stop command, and what each does automatically: [docs/15-starting-services.md](docs/15-starting-services.md). Follow the numbered guides in [setup.md](setup.md#setup-path) for the first install: data drive, Docker network, Cloudflare Tunnel or Tailscale, reverse proxy.

## How it is organised

| Tier | Contents | Start with |
| --- | --- | --- |
| min | proxy, Cloudflare tunnel, certificates, Portainer, docs site, landing page | `up min` |
| core | Nextcloud, Immich, Jellyfin, Forgejo, Vaultwarden, Authentik, AdGuard Home, WireGuard and more | `up core` |
| monitoring | ntfy, Uptime Kuma, Grafana/Prometheus/Loki, Dozzle | `up monitoring` |
| daily | notes, bookmarks, inventory, code-server, Syncthing and similar | `up daily` |
| browser | remote browsers behind one login | `up browser` |
| office | PDF tools, tasks, calendar, newsletters, RSS, project tools | `up office` |
| automation-ai | Airflow, Dagster, Temporal, Ollama, Open WebUI with a code sandbox, n8n | `up automation-ai` |
| extra | documents, chat, ERP, finance, and other opt-in apps | `up extra` |

Tiers add up: `up core` also starts `min`. `up all` starts everything, and `down` snapshots running services before stopping them. [`services.json`](services.json) is the source of truth for tiers, categories and the landing page.

- **Traffic:** Cloudflare terminates TLS and reaches the server through an outbound tunnel, so no inbound port is opened. nginx routes by hostname to containers on the `homeserver` Docker network.
- **Data:** everything persistent lives under `service_data/` (gitignored): `data/` for config and state, `media/` for irreplaceable content, `cache/` for re-creatable files, `backup/` for snapshots. Databases use named Docker volumes.
- **Config:** all per-deployment settings live in each service's `.env`, with `.env.example` as the template. Nothing is hardcoded in compose files.
- **Versions:** every component runs its project's LTS line, or the newest supported release where none exists.

## Layout

```text
homeserver.py          the manager (up / down / restart / update / backup / restore / reset)
services.json          service registry: tiers, groups, landing-page cards
services/<name>/       compose.yml + compose.dev.yml + compose.prod.yml + .env(.example)
docs/                  numbered guides, plus docs/services/<name>.md for every service
tests/                 behaviour tests on a fake Docker backend, plus repo-consistency checks
kubernetes/            retired 2026-10-05, kept as a reference (see docs/17-docker-to-kubernetes.md)
```

## Tests

```bash
uv run pytest
```

Run them after any change to `homeserver.py`, `services.json`, compose files, `.env.example` or the docs. They check ports, env templates, docs coverage and tier lists against each other. Details: [docs/08-maintenance.md](docs/08-maintenance.md#tests-homeserverpy-and-repo-consistency).

## Docs

- [setup.md](setup.md): the guide and the full service list
- [Services reference](docs/11-services-reference.md): ports, proxy hosts, tiers
- [Adding a service](docs/10-new-services.md)
- [Maintenance and troubleshooting](docs/08-maintenance.md)
- [CLAUDE.md](CLAUDE.md): conventions for working in this repo with Claude Code
- A searchable copy of all of this runs as the `docs` service (Docsify) on your own server.
