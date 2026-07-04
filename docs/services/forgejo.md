# Forgejo

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Community-driven Git hosting — repos, issues, pull requests, CI/CD (Actions).
**Port:** `3002` (web), `2223` (SSH) | **Data:** `service_data/forgejo/` | **Requires:** Postgres

## Setup

```bash
cp forgejo/.env.example forgejo/.env
# set POSTGRES_PASSWORD, FORGEJO_DOMAIN, FORGEJO_ROOT_URL
sh homeserver.sh dev up forgejo
```

## Create an admin user

```bash
docker exec -it forgejo forgejo admin user create --username admin --password yourpassword --email admin@example.com --admin
```

## Notes

- Image: `codeberg.org/forgejo/forgejo:15`
- Config env vars use the `FORGEJO__` prefix
- Setup wizard is skipped via `FORGEJO__security__INSTALL_LOCK=true`
- `FORGEJO__server__ROOT_URL` must be `https://forgejo.${DOMAIN}` (not `http`) since Cloudflare always terminates TLS
- SSH clone port is `2223` on the host → `22` in the container

## Actions runner (optional)

```bash
sh homeserver.sh dev up forgejo --profile runner
docker exec -it forgejo-runner forgejo-runner register
```

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
