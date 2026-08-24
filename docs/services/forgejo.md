# Forgejo

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Community-driven Git hosting — repos, issues, pull requests, CI/CD (Actions).
**Port:** `3002` (web), `2223` (SSH) | **Data:** `service_data/data/forgejo/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~96MB total (app 76 + db 20)

## Setup

```bash
cp services/forgejo/.env.example services/forgejo/.env
# set POSTGRES_PASSWORD (DOMAIN/ROOT_URL are derived from the root .env's DOMAIN, not set here)
uv run homeserver.py dev up forgejo
```

## Create an admin user

```bash
docker exec -it forgejo forgejo admin user create --username admin --password yourpassword --email admin@example.com --admin
```

## Connecting your git client

The web UI alone doesn't let you actually push code — a real git client needs to be pointed at this server first, over SSH or HTTPS. Confirmed against Forgejo's own current user documentation, not assumed from memory.

- **SSH (recommended for regular use):** generate a key locally if you don't already have one — `ssh-keygen -t ed25519 -C "you@example.com"` — then in Forgejo go to your avatar → **Settings → SSH / GPG Keys → Add Key** and paste the public key (`~/.ssh/id_ed25519.pub`). Because this stack publishes SSH on the non-standard port `2223` (not `22`), either clone with the full `ssh://` form that embeds the port — `ssh://git@forgejo.${DOMAIN}:2223/<owner>/<repo>.git` — or add an entry to `~/.ssh/config` once so plain `git@forgejo.${DOMAIN}:<owner>/<repo>.git` URLs work too:

  ```text
  Host forgejo.yourdomain.com
    Port 2223
  ```

- **HTTPS:** clone/push at `https://forgejo.${DOMAIN}/<owner>/<repo>.git` — git prompts for username/password on the first push (or a **personal access token** instead of a password, generated under Settings → Applications → Generate New Token, needed anyway if the account has 2FA enabled).
- **Verify the connection works** before relying on it: `ssh -T -p 2223 git@forgejo.${DOMAIN}` should return a Forgejo greeting (not a connection error) if the SSH key was added correctly.

## Using it day to day

Confirmed against Forgejo's own current user documentation, not assumed from memory.

- **Creating a repo:** top-right **+** → **New Repository** — pick owner, name, visibility, optionally a README/`.gitignore`/license (the license picker surfaces the `PREFERRED_LICENSES` IDs from `.env` first — see Notes below). Clone/push it using whichever connection method was set up above.
- **Issues:** each repo's **Issues** tab — title/description, labels, assignees, milestones. Reference or auto-close one from a commit message or PR description with `Fixes #12` / `Closes #12` (closes on merge).
- **Pull requests:** push a branch (or fork the repo) then **Pull Requests → New Pull Request** against the target branch. Reviewers can approve, request changes, or leave inline comments; merge strategy (merge commit / rebase / squash) is configurable per-repo under repo **Settings → Merge Options**.
- **Actions/CI:** once the optional runner (below) is up, any workflow committed to `.forgejo/workflows/*.yml` runs automatically on push/PR/etc. — same syntax as GitHub Actions, so an existing `runs-on: ubuntu-latest` workflow usually just works unmodified (see the `RUNNER_LABELS` note below for why). Runs and logs show up under the repo's own **Actions** tab.
- **Webhooks:** repo **Settings → Webhooks → Add Webhook** — pick a target type (Forgejo/Gitea, Slack, Discord, generic JSON, etc.), set the payload URL and optional secret, and choose which events fire it (push, PR, issue, release, ...). Useful for notifying something external without needing Actions/CI at all.

## Notes

- Image: `codeberg.org/forgejo/forgejo:16.0.3`
- Config env vars use the `FORGEJO__` prefix
- Setup wizard is skipped via `FORGEJO__security__INSTALL_LOCK=true`
- `FORGEJO__server__ROOT_URL` must be `https://forgejo.${DOMAIN}` (not `http`) since Cloudflare always terminates TLS
- SSH clone port is `2223` on the host → `22` in the container
- Forgejo bundles 776 SPDX license templates, covering GitHub's documented license chooser list. Apache License 2.0 (`Apache-2.0`), GNU GPL v3.0-only (`GPL-3.0-only`), and MIT (`MIT`) are pinned to the top of the picker via `PREFERRED_LICENSES`; change the comma-separated IDs in `.env` to reorder them. Use `GPL-3.0-or-later` instead if repositories should permit later GPL versions.

## Migrated: `forgejo-db` from `postgres:18.4` to `postgres:18.4-alpine`

Done as a trial of moving other services' Postgres containers to the smaller Alpine-based image (~150MB smaller than the Debian-based default) — forgejo was picked as the safe/low-stakes service to validate the process on before touching anything with real production data.

**Why this can't be a simple image-tag swap:** Postgres bakes the OS's collation library into the data directory at `initdb` time. Alpine uses musl libc, the default image uses glibc — switching the image tag on an *already-initialized* volume silently leaves indexes sorted under a collation version that no longer matches the running library, which can corrupt sorted/text indexes without any obvious error at switch time. This is a well-documented footgun (see [docker-library/postgres#327](https://github.com/docker-library/postgres/issues/327)); the only safe path is a **logical migration** (`pg_dump`/`pg_restore`) into a freshly-initialized cluster, never reusing the old volume's on-disk files directly.

**Process used** — `homeserver.py` has this built in as two commands, `dump` and `migrate` (originally validated manually on forgejo first; now the standard tool for any service):

```bash
# 1. Dump the running DB — pg_dump (custom format) + pg_dumpall --roles-only,
#    saved to service_data/db_dump/forgejo/<timestamp>/
uv run homeserver.py dev dump forgejo

# 2. Migrate — stops forgejo, swaps compose.yml's image tag to postgres:18.4-alpine
#    and renames the volume (forgejo-postgres -> forgejo-postgres-alpine, so the
#    new image gets a genuinely fresh initdb rather than touching the old volume),
#    starts ONLY the DB on that fresh volume, applies the roles dump, restores
#    the main dump, then brings the rest of the service back up
uv run homeserver.py dev migrate forgejo

# 3. Verify before trusting it — compare row/table counts against a baseline
#    taken before step 1, and check a real API response (not just a DB ping)
#    actually reflects the old data:
docker exec forgejo curl -s http://localhost:3000/api/v1/users/search

# 4. Only after verification passes — migrate prints the exact command:
docker volume rm forgejo_forgejo-postgres
```

Confirmed working: user count, table count, and a real `/api/v1/users/search` response all matched pre-migration state exactly; no migration/collation errors in `forgejo` app logs on first boot against the restored DB.

**Two gotchas found migrating other services this same way** (both now handled automatically by `dump`/`migrate`, not manual steps):

- **`pg_restore` erroring on `CREATE TYPE`/`CREATE TABLE` colliding with objects that already exist** — e.g. an image whose `docker-entrypoint-initdb.d/` script bootstraps its own schema (guacamole's `01-schema.sql`) before the restore ever runs. Fixed with `--clean --if-exists --no-owner` on the restore (safe here specifically because the target is always a container created fresh for this migration).
- **An app authenticating as a DB role other than `POSTGRES_USER`** — Nextcloud creates its own `oc_admin` role during initial setup and points `config.php` at it; a per-database `pg_dump` never captures that (roles are cluster-wide, not database-scoped), so the role silently didn't exist after restore and Nextcloud crash-looped on auth failure. Fixed by also running `pg_dumpall --roles-only` at dump time and applying it *before* the main restore — and deliberately keeping (not stripping) the restore's `GRANT` statements, since those are exactly what a secondary role like `oc_admin` needs on the restored tables. An earlier attempt added `--no-privileges` to sidestep the ordering problem instead of fixing the ordering — that broke `oc_admin`'s actual table access (login worked, every query returned `permission denied`) and has since been removed; see `docs/services/nextcloud.md` for the full incident.

**Not every Postgres image has an Alpine variant.** `migrate <service>` only auto-infers `-alpine` for the plain official `postgres:<tag>` image (no registry prefix). A custom/extended image (e.g. `immich`'s `ghcr.io/immich-app/postgres` with vectorchord/pgvector baked in) requires an explicit target: `migrate <service> --image <repo:tag>` — there's no way to know whether that specific fork even publishes an alpine (or any other) variant, so it's never guessed.

## Actions runner

1. In Forgejo, go to **Site Administration → Actions → Runners → Create new Runner** and copy the token.
2. Set `RUNNER_REGISTRATION_TOKEN` (and optionally `RUNNER_NAME`/`RUNNER_LABELS`) in `services/forgejo/.env`.
3. `uv run homeserver.py dev up forgejo`

The container registers itself on first boot (writing `${FORGEJO_RUNNER_DATA_ROOT}/.runner`) and then runs `forgejo-runner daemon`; on later boots it finds `.runner` already there and skips straight to `daemon`. If `RUNNER_REGISTRATION_TOKEN` is unset and no `.runner` file exists yet, the container logs an error and exits instead of crash-looping silently — check `docker logs forgejo-runner`.

The image's own default command (`forgejo-runner` with no subcommand) just prints help text and exits 0, which `restart: unless-stopped` loops forever without ever registering — this is why `compose.yml` overrides `command:` with the register-then-daemon script above instead of relying on the image default.

`RUNNER_LABELS` defaults to `docker`, `ubuntu-latest`, `ubuntu-24.04`, and `ubuntu-22.04`, all mapped to `catthehacker/ubuntu` images (`act-latest`/`act-24.04`/`act-22.04`) — the standard community image built to emulate GitHub's runner environment for act/Forgejo/Gitea. A workflow written for GitHub can be copied into `.forgejo/workflows/` unmodified and its `runs-on: ubuntu-latest` will already match, instead of everyone having to know to rewrite it as `runs-on: docker`. Plain `node:20-bookworm` (an earlier attempt at a lighter default) is not a safe substitute — its Node ABI is too old for `actions/checkout@v7`'s post-run cache step (`webidl.util.markAsUncloneable is not a function`), which fails the job.

**Labels only take effect at registration time.** Changing `RUNNER_LABELS` in `.env` after the runner has already registered has no effect until you force it to re-register: `docker exec forgejo-runner rm -f /data/.runner` then `uv run homeserver.py dev up forgejo`.

**A workflow step running `docker build`/`docker push` uses an isolated `forgejo-docker` sidecar, not this host's real Docker.** Each CI job runs in its own separate sibling container, which needs *some* Docker daemon reachable inside it for `docker build`/`push` to work. Rather than automounting this host's own `docker.sock` (`container.docker_host: automount` — the simpler option, but it hands every CI job root-equivalent access to the host engine, and every image layer it builds lands on the OS drive under `/var/lib/docker`), `compose.yml` runs a dedicated `docker:28-dind` container (`forgejo-docker`) and points the runner's generated `config.yaml` at it over the internal network: `docker_host: "tcp://forgejo-docker:2375"`. This is unconditional — active whenever Forgejo is up, no toggle, no config.

**A `tcp://` `docker_host` is not auto-wired into job containers the way `automount` is — a workflow using the `docker` CLI needs `DOCKER_HOST` set, or it silently defaults to a nonexistent local socket and fails with `no such file or directory`.** `automount`'s whole purpose is bind-mounting a real `/var/run/docker.sock` into every job container automatically; the runner's own `generate-config` output documents that behavior only for `unix://` socket URLs, not `tcp://`. Rather than requiring every repo's workflow to set `DOCKER_HOST` itself (easy to forget, breaks silently the same way for the next repo added to this instance), `config.yaml`'s `runner.envs` injects it into every job container instance-wide:

```yaml
runner:
  envs:
    DOCKER_HOST: tcp://forgejo-docker:2375
```

No per-repo workflow changes needed for this — any `.forgejo/workflows/*.yml` using plain `docker build`/`push`/`login` just works, the same as it would against `automount`.

```mermaid
flowchart LR
    subgraph unchanged["Unchanged — this host's own Docker"]
        direction TB
        WS["Your workstation<br/>docker build / docker pull"] -->|"local docker.sock"| HD["Host Docker daemon<br/>(what 'docker ps' shows you)"]
        HD -->|"writes images, containers,<br/>volumes, build cache"| OSD[("OS drive<br/>/var/lib/docker")]
    end

    subgraph isolated["Forgejo's own isolated daemon"]
        direction TB
        CI["forgejo-runner<br/>runs each CI job"] -->|"tcp://forgejo-docker:2375<br/>(internal homeserver network)"| FD["forgejo-docker<br/>dind sidecar, privileged: true"]
        FD -->|"writes CI's images and<br/>build cache only"| SEC[("FORGEJO_DOCKER_DATA_ROOT<br/>native fs, fast disk")]
        CI -->|"registration + actions/checkout cache"| RD[("FORGEJO_RUNNER_DATA_ROOT<br/>native fs, fast disk")]
    end

    CI -.->|"✕ docker.sock — not mounted"| HD

    classDef unchangedStyle fill:#eef2f6,stroke:#7a94a8,color:#1c2b36,stroke-width:1px;
    classDef isolatedStyle fill:#fdecdf,stroke:#c1571b,color:#5c2a0c,stroke-width:1.5px;
    classDef diskStyle stroke-width:1.5px;
    class WS,HD unchangedStyle;
    class CI,FD isolatedStyle;
    class OSD unchangedStyle,diskStyle;
    class SEC,RD isolatedStyle,diskStyle;
```

Consequences:

- This host's own Docker (whatever runs `docker ps` when you SSH in) is never touched by a CI job — completely separate daemon, separate storage.
- `forgejo-docker`'s storage lives at `${FORGEJO_DOCKER_DATA_ROOT}` and the runner's own registration/cache at `${FORGEJO_RUNNER_DATA_ROOT}` — both absolute paths set in `services/forgejo/.env`, **deliberately not the usual `${DATA_ROOT}` convention** (see the filesystem requirement below for why).
- `forgejo-docker` needs `privileged: true` (a dind requirement) and has no TLS (`DOCKER_TLS_CERTDIR: ""`) — safe here specifically because it's reachable only over the internal `homeserver` bridge network, never published to a host port.
- Nothing about this is workflow-controllable — it's set once in `compose.yml`/the runner's generated `config.yaml`, not something a `.forgejo/workflows/*.yml` file can override.
- Both directories are pure CI cache, not real service data — not part of a normal Forgejo restore, safe to delete entirely any time (`docker compose down` first) to reclaim space or force a clean re-pull/re-clone.

**`FORGEJO_DOCKER_DATA_ROOT`/`FORGEJO_RUNNER_DATA_ROOT` must point at a native Linux filesystem (ext4/xfs/btrfs) on a fast disk — a FUSE-mounted disk (NTFS/exFAT via `ntfs-3g` etc.) breaks CI in two separate, confirmed ways, not just "slower":**

1. **Docker's `overlay2` storage driver cannot mount on a FUSE filesystem at all** — `forgejo-docker`'s own dockerd log shows `failed to mount overlay: invalid argument` and silently falls back to the `vfs` driver, which copies every image layer in full for every container instead of overlay2's copy-on-write. This isn't a modest slowdown: on this host it took the `catthehacker/ubuntu:act-latest` image (1.63GB) from a few seconds to several minutes per container, and in practice caused CI jobs to hang indefinitely with zero visible activity (no container ever created) rather than just run slow — confirmed by pointing the exact same runner at the host's own Docker (`overlay2` on an SSD) and watching the same job that had been stuck for 6+ minutes complete in 3 seconds.
2. **A FUSE mount reports every file as owned by whichever UID the mount itself was configured with (commonly root), regardless of which process actually wrote it.** This separately broke `forgejo-runner`'s persistent `actions/checkout` cache under `FORGEJO_RUNNER_DATA_ROOT`/.cache/act/ — Git's "detected dubious ownership" safety check saw the runner (uid 1000) writing into what looked like a root-owned repo and refused to fetch, failing every job at the checkout step (`fatal: detected dubious ownership in repository at '/data/.cache/act/...'`). Clearing the cache did *not* fix this — a freshly-written cache entry hit the exact same error immediately, because the ownership mismatch comes from the mount itself, not stale state. Only relocating off the FUSE mount fixed it permanently.

Before setting either variable, verify the target path is genuinely native, not just fast:

```bash
lsblk -d -o NAME,ROTA,MODEL,TRAN   # ROTA=0 -> SSD/NVMe (necessary but not sufficient)
findmnt -T <path>                  # fstype must NOT be fuseblk/ntfs/exfat
```

**Also considered and rejected: automounting the host's real `docker.sock`** (`container.docker_host: automount`, this repo's pre-`forgejo-docker` setup) as a way to sidestep the FUSE problem entirely. It does work — confirmed by testing it live, jobs ran and completed in seconds — but gives every CI job root-equivalent access to this host's real Docker engine and dumps build layers on the OS drive, which is exactly the isolation `forgejo-docker` exists to prevent. Once `FORGEJO_DOCKER_DATA_ROOT` pointed at a native-filesystem fast disk instead, the isolated sidecar performed identically to the host socket, so there was no remaining reason to give up the isolation.

See `docker/README.md`'s "Two independent knobs" section for how this compares to `docker/docker-limits.py relocate-data-root` (a separate, whole-host, opt-in tool — not needed here) and for the same FUSE/`overlay2` warning stated more generally.

See `docs/services/forgejo-examples/` for a matching CI workflow template and registry usage guide.

**Mirrored repos**: Forgejo Actions only triggers on `.forgejo/workflows/` (or `.gitea/workflows/` for compat) — never `.github/workflows/`. If the repo is a pull mirror (`is_mirror` in Forgejo's DB), you also can't add that file directly in Forgejo — mirror syncs force-reset tracked branches to match the upstream exactly (and prune anything else), so a locally-added file gets silently wiped at the next sync. Add `.forgejo/workflows/` to the *source* repo instead (e.g. on GitHub, if that's what's being mirrored) so it comes down with the next sync.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
