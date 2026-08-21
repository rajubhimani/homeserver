# CrowdSec

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Collaborative fail2ban replacement — parses logs for attack patterns and builds ban decisions from a shared community threat feed.
**Port:** none exposed (see below) | **Data:** `service_data/data/crowdsec/config/` | **Requires:** Docker socket read access (to read nginx-plain's logs via the Docker log API) | **Memory:** no hard limit set; measured idle ~80MB

## ⚠ Detection-only in this setup — nothing is actually blocked yet

CrowdSec's normal blocking mechanism is a "bouncer" that manipulates the host's `iptables`/`nftables` rules. **This host is Windows (Docker Desktop/WSL2), which has no native iptables to manipulate that way** — the standard bouncer doesn't apply here. The alternative (the official nginx Lua bouncer module) would require rebuilding `nginx-plain` on OpenResty instead of stock `nginx:alpine`, which is a bigger change than adding a new service.

So this pass deploys **detection only**: the CrowdSec engine reads `nginx-plain`'s logs, correlates them against the `crowdsecurity/nginx` collection's attack scenarios, and records decisions — but no bouncer is wired up to act on them. See the deferred item in [`TODO.md`](../../TODO.md) at the repo root for the two options to revisit this.

## Setup

```bash
cp services/crowdsec/.env.example services/crowdsec/.env
uv run homeserver.py dev up crowdsec
```

No web UI ships with open-source CrowdSec — inspect it via `cscli` instead:

```bash
docker exec -it crowdsec cscli decisions list   # current ban decisions
docker exec -it crowdsec cscli metrics          # what's being parsed/detected
docker exec -it crowdsec cscli collections list # installed detection scenarios
```

## Architecture — reads logs without touching nginx-plain's logging config

Rather than mounting nginx's log files (which the standard official `nginx` image symlinks to `/dev/stdout`, making file-based acquisition unreliable in Docker), this setup uses CrowdSec's **Docker log acquisition source** (`services/crowdsec/acquis.yaml`, `source: docker` + `use_container_labels: true`): CrowdSec reads container logs directly via the Docker API for any container labeled `crowdsec.enable: "true"`, and takes the parser/collection to apply from that same container's `crowdsec.labels.type` label. `services/nginx-plain/compose.yml` carries both labels — see the `labels:` block there.

This requires read access to the Docker socket (`${DOCKER_SOCKET}` mounted read-only) — the same socket-access pattern already used by `dozzle`, `portainer`, `dockge`, `forgejo`, and `guacamole` in this stack.

## Notes

- No landing-page card and no public reverse-proxy route — there's no user-facing web UI to link to (unlike every other service in this stack), and the LAPI isn't meant to be publicly exposed.
- `COLLECTIONS=crowdsecurity/nginx` in `compose.yml` installs the nginx-specific detection scenarios on first start. Add more space-separated collection names there if other log sources are wired up later (e.g. `crowdsecurity/sshd` if SSH is ever exposed).
- Since CrowdSec 1.7.0, `/var/lib/crowdsec/data` (the decisions/bans database) must be a persisted volume — it's the named volume `crowdsec-data` here, not under `service_data/data/` (it's derived/rebuildable state, not source config).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
