# GitLab CE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Full DevOps platform — Git, CI/CD, registry, issue tracking.
**Port:** `8085` (web), `2224` (SSH) | **Data:** `service_data/gitlab/` | **Requires:** ~4 GB RAM minimum

## Setup

```bash
cp gitlab/.env.example gitlab/.env
# set GITLAB_HOSTNAME, GITLAB_EXTERNAL_URL
sh homeserver.sh dev up gitlab
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

## Runner (optional)

```bash
sh homeserver.sh dev up gitlab --profile runner
docker exec -it gitlab-runner gitlab-runner register
```

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
