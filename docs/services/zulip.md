# Zulip

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Topic-threaded team chat, good for organized async discussion — the third of this stack's chat playground trio (alongside Mattermost and Rocket.Chat). Backing services: Postgres, RabbitMQ, Redis, Memcached. Uses Docker Compose **secrets** for its credentials, sourced from `.env` values (not files) — the only service in this stack that does, since Zulip's own official compose reference is built around secrets rather than plain environment variables.

## Setup

First-time setup is two steps, not just `up` — Zulip's own official procedure, not a shortcut:

```bash
cp services/zulip/.env.example services/zulip/.env
# generate real values for the ZULIP__* secrets in .env (see the file's own comments)

cd services/zulip
docker compose --env-file .env -f compose.yml -f compose.dev.yml up -d zulip-db zulip-memcached zulip-rabbitmq zulip-redis
DOMAIN=<your-domain> docker compose --env-file .env -f compose.yml -f compose.dev.yml run --rm zulip app:init
cd ../..

uv run homeserver.py dev up zulip
```

`app:init` runs Zulip's database migrations and secret provisioning once — `homeserver.py` doesn't know about this step (it's Zulip-specific, not part of the normal up/down lifecycle), so it has to be run directly via `docker compose` the first time, with `DOMAIN` exported manually since `homeserver.py` isn't the one invoking it here.

Then create the first organization. By default (`ZULIP_OPEN_REALM_CREATION=True` in `.env`), just visit `https://zulip.<domain>/new/` directly — no token needed, and the homepage footer gets a "Create new organization" link too.

**`ZULIP_OPEN_REALM_CREATION`** — Zulip ships with this **off** upstream: without it, `/new/` alone 404s with "Organization creation link required," and creating an org needs an admin-generated single-use link instead:

```bash
docker exec zulip su zulip -c "/home/zulip/deployments/current/manage.py generate_realm_creation_link"
```

Defaults to **on** here (`SETTING_OPEN_REALM_CREATION` in `compose.yml`, sourced from `.env`) since this is a single-user homelab playground behind Cloudflare Tunnel, not a public multi-tenant server — the tradeoff being real either way: on, anyone who can reach `zulip.<domain>` (not just you) could create an org; off, you're back to generating a link yourself each time. Set `ZULIP_OPEN_REALM_CREATION=False` in `.env` and restart to go back to the safer default.

## Architecture

Five containers: `zulip-db` (Zulip's own `zulip/zulip-postgresql` image — bakes in extensions Zulip specifically needs, not this stack's usual `postgres:18.4-alpine`), `zulip-memcached`, `zulip-rabbitmq`, `zulip-redis`, and `zulip` itself.

**Secrets sourced from environment variables, not files** — `compose.yml`'s top-level `secrets:` block uses Compose's `environment:` source (`zulip__postgres_password: {environment: "ZULIP__POSTGRES_PASSWORD"}`), so credentials still live in this service's own `.env` like everywhere else in this stack, while the `zulip`/`zulip-db`/etc. containers each see them mounted as real files under `/run/secrets/` at runtime — no separate secrets directory, nothing extra to gitignore.

**`LOADBALANCER_IPS`, not `TRUST_GATEWAY_IP`** — a real gotcha hit building this: Zulip needs to trust the IP of whatever proxies to it before it trusts `X-Forwarded-Proto`/`X-Forwarded-For`. `TRUST_GATEWAY_IP: True` only trusts connections from the Docker network's gateway address specifically — but `nginx-plain`/`landing` connect to `zulip` as sibling containers on the shared `homeserver` bridge network (their own container IP), not routed through the gateway, so every proxied request 500'd until this was `LOADBALANCER_IPS: 172.16.0.0/12` instead (Docker's entire default bridge-network range, deliberately broad for portability across different hosts rather than hardcoding this specific deployment's actual subnet).

**Health check needs a real `Host` header** — Zulip validates `Host` strictly against its configured `EXTERNAL_HOST`; a bare `proxy_pass` (which forwards the container name, `zulip`, as `Host`) gets a permanent 400. `services/landing/nginx.conf`'s `/health/zulip` location sets `proxy_set_header Host zulip.DOMAIN_PLACEHOLDER` — and since `landing`'s `nginx.conf` previously had no domain-templating mechanism (only `index.html` did), this required extending `entrypoint.sh` to template `nginx.conf` through the same `DOMAIN_PLACEHOLDER` substitution, so the real domain is never hardcoded into a git-tracked file.

## Notes

- **Resource usage**: heaviest bring-up procedure of the three chat apps (5 containers + a one-time migration step) — bring it up when you want it, down when you don't (`uv run homeserver.py dev down zulip`) rather than leaving it running idle. `down` snapshots all 4 named volumes automatically first.
- **The bare root path (`/`) shows a "No organization found" page until an organization exists** — expected Zulip behavior for a zero-realm deployment, not a bug: the real entry point is always the realm-creation link (or an existing organization's own subdomain/URL), not the bare domain.
- **Outgoing email routed through the shared [Mailpit](mailpit.md) catcher by default** (`SETTING_EMAIL_HOST=mailpit` in `compose.yml`) — invite/notification emails genuinely send, nothing ever leaves this host. `ZULIP__EMAIL_PASSWORD` stays an unused placeholder since Mailpit needs no auth; point `SETTING_EMAIL_HOST`/etc. at a real relay instead in `.env` if you want actual delivery.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
