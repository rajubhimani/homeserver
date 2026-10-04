# Handover — Kubernetes migration status (2026-10-04)

Read this first in a new session. It records where the Docker → Kubernetes
work stands, what's left, the decisions already made with the owner, and
the rules every change follows. Keep it current: update it at the end of
every working session.

Related: `CLAUDE.md` (local-only, gitignored: repo rules and index),
`docs/17-docker-to-kubernetes.md` (the guide, every command),
`research/kubernetes-compose-parity-plan.md` (local-only, gitignored: the
design), branch `feature/k8s-generated`.

---

## 0. Before formatting the OS (the owner is about to)

**What's on which disk** (checked 2026-10-04):

| Disk | Holds | On format |
|---|---|---|
| `sda6` (SSD, btrfs: `/` and `/home`) | `/var/lib/docker` (**every Docker named volume: all Docker databases**), `~/k8s-data/fast` (Kubernetes databases and fast volumes), `~/k8s-data/encryption`, `~/.claude`, the kind cluster | **lost** |
| `sdb2` (HDD, `/mnt/mydata`) | this repo, every `.env`, `kubernetes/.env` (all keys), `service_data/` (Docker data folders **and snapshots**), `/mnt/mydata/k8s-data/` (export, backup store, image store), `/mnt/mydata/claude-backup-20261004/` | safe |
| `sdb1` (HDD, `/mnt/media`) | photos (Immich), media (Jellyfin), OS ISOs | safe |
| Passport (`/run/media/raju/My Passport`) | archives | safe |

**Checked before the format:**
- **Docker:** all 52 named volumes are in snapshots under `service_data/backup/` (2026-10-02/03, taken when Docker stopped; nothing newer exists). The 106 anonymous volumes hold no data (kind's node `/var`, tool installs).
- **Kubernetes:** export `/mnt/mydata/k8s-data/export/20261004-185119` (23 services, 9 database dumps, 25 volume archives). **If the cluster was used after 18:51 on 2026-10-04, take a fresh export first:** `uv run kubernetes/cluster.py export --env prod <services>` (the list is in §2).
- **`~/.claude`:** copied to `/mnt/mydata/claude-backup-20261004/dot-claude` (memories, global `CLAUDE.md`, session history).
- **Optional extra copy:** `uv run homeserver.py archive "/run/media/raju/My Passport/homeserver"`, plus `kubernetes/.env` to the Passport.

## 1. After formatting

1. **Tools:** Docker, git, `gh`, uv, then kind, kubectl and helm at the versions in `kubernetes/versions.env`. Raise the inotify limits (docs/17 "Step 0").
2. **Restore Claude's files:** `cp -a /mnt/mydata/claude-backup-20261004/dot-claude/. ~/.claude/`. That brings back the memories (`projects/-mnt-mydata-homeserver/memory/`) and the global rule file `~/.claude/CLAUDE.md`.
3. **Docker databases: restore explicitly, never just `up`.** `up` auto-restores only when a service's volumes **and** its `service_data/data/<svc>` folder are both missing. After a format the folders exist and the volumes don't, so `up` would start apps on empty databases, and some (Authentik) offer their first-visitor admin setup. For each service with named volumes: `uv run homeserver.py prod restore <svc>`, then `up`.
4. **`service_data` symlink:** the repo's `service_data` points at `/mnt/mydata/service_data`. Check it with `readlink -f service_data`.
5. **Kubernetes:** `~/k8s-data/fast` and the encryption folder are gone; `kubernetes/.env` keeps every key.
   1. `uv run kubernetes/cluster.py create` (it rewrites the encryption config from the key in `kubernetes/.env`).
   2. Before bootstrap, set cloudflared to stopped in git (see §4).
   3. `bootstrap --env prod`.
   4. `images temporal dagster --drop-host-copy`.
   5. `import --env prod --from-export <newest export>`.
   6. Turn the tunnel back on in git.

   The image store (`/mnt/mydata/k8s-data/containerd`) survives, which saves the downloads. If containerd complains about its state, move it aside and let it re-pull.
6. **The Cloudflare tunnel must never run in two places.** Docker's cloudflared and the cluster's cloudflared share one token.

## 2. Where things stand

**Production right now:**
- **Kubernetes (kind, on this host) serves the stack.** Docker is down except `wg-easy` (WireGuard stays on Docker by decision).
- **The public tunnel is OFF:** `cloudflared` is under `stopped:` in `kubernetes/deploy/prod.yaml`, held off during the 2026-10-04 rebuild until the data check (§3).
- **Prod runs** (`kubernetes/deploy/prod.yaml`): MIN, CORE, miniflux, bookstack, airflow, temporal, dagster, observability.
- **Exported services:** adguard-home atuin authentik beszel clamav cloudflared docs firefly forgejo guacamole immich it-tools jellyfin landing mailpit nextcloud nginx-plain ntfy onlyoffice plausible uptime-kuma vaultwarden whiteboard.

| Phase | Status |
|---|---|
| 0 Prep, 1 Generator + MIN, 2 Databases | ✅ done |
| 3 CORE + other tiers | ✅ CORE live with real data. ✅ 36 non-core apps passed smoke tests (daily 7/7, browser 10/10, office 8/8, ollama, open-webui, n8n, paperless, bookstack, audiobookshelf, mealie, supabase). ⏳ **Deferred to the broad pass:** nocodb outline penpot documenso invoiceshelf erpnext ghostfolio openproject mattermost rocketchat zulip mail-archiver bichon orangehrm gitlab. ⏳ Airflow, temporal, dagster and observability run in prod; verify they work (§3). |
| 4 GitOps + ops tools | ✅ ArgoCD app of apps with sync waves, ESO secrets, Reloader, Headlamp, metrics-server, observability (Alloy/Prometheus on Kubernetes), Dagster via its official chart. ✅ Live since the rebuild. |
| 5 Backups | ✅ **Live and verified:** CNPG WAL archiving on all 9 Postgres clusters; a manual Barman base backup completed. ✅ Built: nightly ScheduledBackups, per-app dump CronJobs, Velero (own repository password), `cluster.py archive`, `export`/`import --from-export`. ⏳ **Velero's S3 user lacked its bucket policy** (setup job fixed in commit e2e5710; re-run it and confirm BackupStorageLocation `Available`). ❌ **`restore` not built yet** (design in §3). |
| Hardening | ✅ Secrets encrypted at rest (verified in etcd), PSS labels, per-service ingress network policies, LimitRange default requests, request = Compose limit, Velero's own key, read-only RBAC (no `nodes/proxy`). ⏳ Follow-ups in §5. |

## 3. Next steps, in order

1. **Re-run the backup store setup** (ArgoCD app `backup-store`; its PostSync job) and check Velero: `kubectl -n velero get backupstoragelocation default` → `Available`. Then run a manual Velero backup and check it completes.
2. **Per-app check of the imported data:** log in to each CORE app, check the data is there, and confirm the CrashLoop/Init pods have settled.
3. **Tunnel back on:** `uv run kubernetes/k8s.py up cloudflared --env prod`, commit, push. Then check the public hostnames and real client IPs (`docs/17` "Real client IPs").
4. **`cluster.py restore`.** Design notes:
   - **Volumes:** a Velero `Restore` CR (selector `homeserver/service=<svc>`) after deleting that service's Deployments and PVCs, with ArgoCD paused (`argo_pause`).
   - **Own Postgres (point in time):** delete the Cluster and recreate it with `bootstrap.recovery` from the ObjectStore under a **new** `serverName` (CNPG refuses an archive that isn't empty), then reconcile with ArgoCD's desired spec.
   - **Shared-database apps:** `pg_restore` / `mariadb` from `dumps/<svc>/<ts>/`.
   - **Verify** with a round trip on a small service (guacamole): back up, reset, restore, data back.
5. **Measured resource requests:** read real usage (`kubectl top`, metrics-server is installed) and set per-service requests in the overrides.
6. **Broad pass:** smoke-test the 15 deferred apps (`cluster.py smoke …`, one at a time).
7. Update the docs (guide Step 7 restore, Step 8 rebuild) and this file.

## 4. How things work (short)

- **Generated, never hand-edited:** `kubernetes/generate.py` turns Compose + `.env.example` + `kubernetes/overrides/<svc>.yaml` into `kubernetes/generated/`. A test fails if it's stale, so run `uv run kubernetes/generate.py` after any change.
- **What runs = git:** `kubernetes/deploy/<env>.yaml` (`running`, `stopped`, `backup`, `auto_sync`).
  - `uv run kubernetes/k8s.py up|down <target> --env prod` edits that file. Commit and push, and ArgoCD applies it.
  - Services are generated stopped; the env overlay switches the listed ones on.
- **Secrets:** `cluster.py secrets` copies each `.env` into namespace `homeserver-secrets` (plus `kubernetes/.env`'s backup keys as `kubernetes`). ExternalSecrets build the app Secrets, and Reloader restarts pods when they change.
- **Add-ons:** `kubernetes/cluster/addons.yaml` (with sync waves); versions in `kubernetes/versions.env`.
- **Scripts only for what git can't do:**
  - `cluster.py create`, `bootstrap`, `secrets`, `import`, `export`, `archive`, `images`, `smoke`, `rmi`, `validate`.
  - `argo_pause` (ArgoCD's skip-reconcile) for imports and smoke tests.
- **Ops UIs** (only on this machine; add them to `/etc/hosts` as `127.0.0.1`):
  - `argocd.k8s.local:18080`, `headlamp.k8s.local:18080`, `grafana.k8s.local:18080`, `backup.k8s.local:18080`.
  - Apps keep their Docker localhost ports through the local-access proxy.
- **Tests:** `uv run pytest`: 136 tests in ~20 s, one test per check (`conftest.each`).

## 5. Follow-ups (agreed, not started)

- **A separate SSD for kind's image store.** It's on the HDD, and starting ~90 pods saturated it for over an hour (100% busy at ~130 IOPS) and made probes kill slow starters. This is the main performance limit.
- **Egress network policies**, Beszel's agent in its own privileged namespace (then enforce Baseline on `apps`), image scanning, Cloudflare Access/WAF, Authentik two-factor, a Docker socket proxy, and etcd `ionice`.
- **Headlamp's token is cluster-admin** (the chart's default): add a read-only role, or put it behind Authentik.
- **mariadb-operator can't scale to 0** (upstream #356): a MariaDB server runs once created.
- **Pending Docker-side check:** Dagster's code is now built into the image on Compose too (`DAGSTER_EXECUTOR=docker`). Rebuild and test it when Docker is used again.

## 6. Decisions made with the owner (don't re-litigate)

**Platform and deployment:**
- Kubernetes mirrors Compose; it's generated.
- Production on kind on this host (switched during the real-data window).
- wg-easy stays on Docker.

**GitOps:**
- Deploy from GitHub with ArgoCD. What runs lives in git (a running list per environment).
- Secrets go through hybrid ESO (in-cluster store filled from `.env`; a cloud store later by changing the ClusterSecretStore).
- Branch: `feature/k8s-generated` now, `develop` after the merge.

**Routing and access:**
- One local-access proxy for localhost ports.
- Real client IPs through the edge nginx (docs/17).
- Network policies: ingress first, egress later.

**Components:**
- Observability is generated from Compose.
- Dagster: its official Helm chart, with the code built into the image.
- CrowdSec: removed from Docker and Kubernetes.

**Backups:**
- Option A: Barman Cloud plugin + Velero + dumps + MinIO (`pgsty`, the maintained fork) + an archive to the Passport.
- Docker's "`down` takes a backup" becomes nightly backups + continuous WAL.

**Rebuild and data:**
- Rebuild: accept the outage, carry over the Kubernetes data (export/import). Old data folders renamed aside, never deleted.
- Immich mounts the real photo folder (the owner backed it up first). Jellyfin's is read-only.

**Testing:**
- Smoke tests run one at a time and remove their images afterwards.
- Finish all phases on CORE + a test set first, then the broad testing.

## 7. Rules (also in `CLAUDE.md`, local-only, and Claude's memories)

**Research and choices:**
- **Research first, fix second:** the project's own compose, docs, issues and community; reproduce and read the real error. No trial and error.
- **The bar:** secure, reliable, best practice. For design choices, show an options table with sources and ask when it means rework.
- **Only actively maintained components:** a release within ~6 months, not archived; prefer the maintained fork. **Confirm the exact image tag exists in the registry**: GitHub releases can run ahead of images.
- **LTS always**, and managed-cloud parity (Postgres/Valkey/S3 only at versions AWS/Azure/GCP run). Orchestrators stay movable to their clouds.

**Repo discipline:**
- **Twelve-factor:** everything per-deployment lives in `.env`.
- Change `.env`/compose together with `.env.example` and `docs/services/<svc>.md` in the same pass.
- Run tests after every change.
- Commit and push routinely on the branch. **No Claude attribution** in commits or PRs.

**Safety:**
- Never print `.env` secrets.
- Never delete under `service_data/data/`; move aside, don't delete.
- Never run the tunnel token twice.
- Fresh, empty apps only on test hostnames (first-visitor admin risk).
- Ask before outward or irreversible actions; don't work around permission denials.

**Host and updates:**
- The weak SSD holds databases and etcd; no image store there.
- Update one service at a time with a backup first; remove superseded images afterwards (never `prune -a`).
- "Update" means the upstream-tested versions.

## 8. Lessons from 2026-10-04 (each fixed, most with a test)

**Generator bugs, found in smoke tests:**
- Init steps got no environment, so airflow-init migrated a throwaway SQLite file and temporal-schema-setup got empty arguments.
- `${VAR:-default}` host ports were skipped.
- local-access took Traefik's node port.
- Readiness and liveness exec probes ran concurrently and OOM-killed the airflow triggerer; containers without ports now get liveness only.

**The rebuild:**
- The kind config put mounts after the kubeadm patches.
- ArgoCD's namespace isn't created by its own manifest.
- The Dagster chart fetches its schema at render time.
- An image shared by two containers was loaded twice.
- The import waited on the Cluster's Ready, which includes WAL archiving.
- A store setup job silenced its errors, and the `mc` image has no `grep`.
- A MinIO tag existed on GitHub but not on Docker Hub.

**Load:** starting everything at once saturated the HDD; sync waves fix the ordering, and a dedicated SSD would fix the capacity.
