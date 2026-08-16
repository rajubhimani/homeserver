# GitLab CE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Full DevOps platform — Git, CI/CD, registry, issue tracking.
**Port:** `8085` (web), `2224` (SSH) | **Data:** `service_data/data/gitlab/` | **Requires:** ~8 GB RAM minimum per GitLab's own docs (16 GB recommended for single-node) — corrected from a previous, lower unverified figure in this doc
**Tier:** manual-only — not started by `up min`/`core`/`all`, start with `uv run homeserver.py dev up gitlab` (redundant with Forgejo, already core in this stack, at far higher memory cost)

## Setup

```bash
cp services/gitlab/.env.example services/gitlab/.env
# set GITLAB_SSH_PORT/SIGNUP_ENABLED if you want non-default values (hostname/external URL derive from the root .env's DOMAIN)
uv run homeserver.py dev up gitlab
```

GitLab takes 2–3 minutes to fully start on first launch.

## First login

Browse to `http://<ip>:8085` — set the `root` password on first login. To reset it later:

```bash
docker exec -it gitlab gitlab-rake "gitlab:password:reset[root]"
```

## Notes

- All config goes through `GITLAB_OMNIBUS_CONFIG` in compose (Ruby format)
- SSH clone port: `2224`; HTTP-only internally (`nginx['listen_https'] = false`) since Cloudflare/nginx-plain terminates TLS in front
- **Bundled Postgres/Redis** — the omnibus `gitlab-ce` image runs its own internal Postgres and Redis inside the single `gitlab` container; there's no separate `gitlab-db` container the way most other services in this stack have. Its data lives in the named volume `gitlab-data` (`/var/opt/gitlab`), which already follows the same named-volume-not-bind-mount rule as a standalone DB container, for the same reason (see the `homeserver-postgres` skill).
- **Memory cap:** `deploy.resources.limits.memory: 6G` — **this is below GitLab's own stated 8GB minimum** (see top of doc, docs.gitlab.com/install/requirements/), set here as a pragmatic tradeoff for a personal/small-scale homelab rather than GitLab's own recommended sizing, since omnibus bundles many components (Postgres, Redis, Puma, Sidekiq, Gitaly, Workhorse, its own nginx) that aren't individually tuned down the way a standalone Postgres container's `command:` flags would be — this is a backstop cap, not app-level tuning. **Measured idle usage is already 4.22GB (70% of the 6G cap) with zero users** — there is real risk of OOM-kill under actual CI/multi-user load. Raise the cap toward 8G if that happens; recreate just this container after changing it: `docker compose -f compose.yml -f compose.prod.yml up -d --no-deps gitlab`.

## Runner (optional)

```bash
uv run homeserver.py dev up gitlab --profile runner
docker exec -it gitlab-runner gitlab-runner register
```

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
