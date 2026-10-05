# Handover — Kubernetes migration status (2026-10-05)

Read this first in a new session. It records where the Docker → Kubernetes
work stands, what's left, the decisions already made with the owner, and
the rules every change follows. Keep it current: update it at the end of
every working session.

Related: `CLAUDE.md` (local-only, gitignored: repo rules and index),
`docs/17-docker-to-kubernetes.md` (the guide, every command),
`research/kubernetes-compose-parity-plan.md` (local-only, gitignored: the
design), branch `feature/k8s-generated`.

---

## 0. OS reinstall: DONE (2026-10-05)

The SSD was wiped and Fedora reinstalled; the data disks are mounted at the same paths. Rebuilt the same day:
- Tools: kind, kubectl, helm (Fedora's v4.2.2; `versions.env` pins v4.3.0, nothing checks it), uv, gh (HTTPS login). inotify limits set.
- Layout as decided in §1: Docker, kind's image store (`~/k8s-data/containerd`), `fast` and `bulk` on the SSD (`chattr +C`); the backup store on the HDD through the new `backup` class (`K8S_BACKUP_PATH=/mnt/mydata/k8s-data/backup`).
- `cluster.py create`, `bootstrap --env prod` (tunnel off), then `import --from-export /mnt/mydata/k8s-data/export/20261004-185119`: all 23 services imported.
- Row counts checked on the restored databases (Immich 21,246 assets, Firefly 113 accounts / 793 transactions, Authentik 4 users, Nextcloud 691 files, Atuin 2,882 records in `store`, Forgejo 3 repos, Plausible 2 sites, Guacamole 3 connections).
- `~/.claude` was not restored; the copy is at `/mnt/mydata/claude-backup-20261004/dot-claude`.

## 1. After formatting

**The plan (2026-10-04):** wipe the whole SSD, Windows included, and install Fedora on all of it.
- **Wipe only `sda`,** the WD Green 240 GB (model `WD Green 2.5 240GB`).
- **Never touch** `sdb` (Seagate ST2000LM015 1.8 TB: all the data), `sdd` (the Passport) or `sdc` (the Ventoy installer stick).

**Mount the data disks at exactly the same paths;** the repo, every `.env` and the media mounts depend on them. Add to `/etc/fstab`, then `sudo mkdir -p /mnt/media /mnt/mydata && sudo mount -a`:

```
/dev/disk/by-uuid/F6C2F918C2F8DE35 /mnt/media auto nosuid,nodev,nofail,x-gvfs-show,x-gvfs-name=Media 0 0
/dev/disk/by-uuid/09c0e2ab-d6e1-4010-a945-ed022a666aba /mnt/mydata auto nosuid,nodev,nofail,x-gvfs-show,x-gvfs-name=MyData 0 0
```

(`sdb1` is NTFS, `/mnt/media`; `sdb2` is ext4, `/mnt/mydata`. The UUIDs don't change unless those partitions are reformatted.)

**Your user needs the same name and UID:** `raju`, 1000. File owners on `/mnt/mydata` (ext4) are stored as numbers.

**Storage layout after the reinstall (confirmed by the owner 2026-10-04: ~100 GB of the SSD for this):**

| Data | Where | `kubernetes/.env` |
|---|---|---|
| Docker itself (`/var/lib/docker`: images, containers, Docker's database volumes) | **SSD** (Fedora's default location; the kind node runs here too) | — |
| kind's image store (~35 GB, up to ~70 GB with every app) | **SSD** (this removes the bottleneck that saturated the HDD on 2026-10-04) | `K8S_IMAGES_PATH=~/k8s-data/containerd` |
| Databases, etcd, app volumes (classes `fast` and `bulk`) | **SSD** | `K8S_FAST_PATH=~/k8s-data/fast`, `K8S_BULK_PATH=~/k8s-data/bulk` |
| Backup store (MinIO: WAL archives, base backups, Velero, dumps) | **HDD**: a backup must not share a disk with its data | its PVC needs a storage class on the HDD. Add a `backup` class at `/mnt/mydata/k8s-data/backup` (generator + `cluster/base/storage.yaml` + a kind mount), then point `backup_store()`'s PVC at it. **To do before bootstrap.** |
| Exports (`cluster.py export`), archives | **HDD** | `K8S_EXPORT_PATH=/mnt/mydata/k8s-data/export` |
| Photos and media | **HDD** (`/mnt/media`), mounted as now | — |

**Cautions:**
- **Keep about 20% of the SSD free:** a DRAM-less WD Green slows down sharply when full. Remove unused images (`cluster.py rmi`; smoke tests already do).
- **Wear:** after the move, check the write rate of Prometheus, Loki and WAL (Grafana / metrics-server). If it's heavy, give those an HDD class too.
- **btrfs:** if the SSD stays btrfs (Fedora's default), run `chattr +C` on `~/k8s-data/fast` and `~/k8s-data/bulk` while they're empty. Postgres on copy-on-write fragments; this is btrfs' own advice for databases.

## 2. Where things stand

**Production right now:**
- **Kubernetes (kind, on this host) serves the stack.** Docker is down except `wg-easy` (WireGuard stays on Docker by decision).
- **The public tunnel is ON** (2026-10-05, after the import): `cloudflared` is in the running list, 4 connections registered, the public hostnames answer, and `nginx-plain` logs the visitor's real IP.
- **Prod runs** (`kubernetes/deploy/prod.yaml`): MIN, CORE, miniflux, bookstack, airflow, temporal, dagster, observability.
- **Exported services:** (adguard-home was dropped 2026-10-05: back on Docker) atuin authentik beszel clamav cloudflared docs firefly forgejo guacamole immich it-tools jellyfin landing mailpit nextcloud nginx-plain ntfy onlyoffice plausible uptime-kuma vaultwarden whiteboard.

| Phase | Status |
|---|---|
| 0 Prep, 1 Generator + MIN, 2 Databases | ✅ done |
| 3 CORE + other tiers | ✅ CORE live with real data. ✅ 36 non-core apps passed smoke tests (daily 7/7, browser 10/10, office 8/8, ollama, open-webui, n8n, paperless, bookstack, audiobookshelf, mealie, supabase). ⏳ **Deferred to the broad pass:** nocodb outline penpot documenso invoiceshelf erpnext ghostfolio openproject mattermost rocketchat zulip mail-archiver bichon orangehrm gitlab. ⏳ Airflow, temporal, dagster and observability run in prod; verify they work (§3). |
| 4 GitOps + ops tools | ✅ ArgoCD app of apps with sync waves, ESO secrets, Reloader, Headlamp, metrics-server, observability (Alloy/Prometheus on Kubernetes), Dagster via its official chart. ✅ Live since the rebuild. |
| 5 Backups | ✅ **Live and verified:** CNPG WAL archiving on all 9 Postgres clusters; a manual Barman base backup completed. ✅ Built: nightly ScheduledBackups, per-app dump CronJobs, Velero (own repository password), `cluster.py archive`, `export`/`import --from-export`. ⏳ **Velero's S3 user lacked its bucket policy** (setup job fixed in commit e2e5710; re-run it and confirm BackupStorageLocation `Available`). ❌ **`restore` not built yet** (design in §3). |
| Hardening | ✅ Secrets encrypted at rest (verified in etcd), PSS labels, per-service ingress network policies, LimitRange default requests, request = Compose limit, Velero's own key, read-only RBAC (no `nodes/proxy`). ⏳ Follow-ups in §5. |

## 3. Next steps, in order

1. ~~Backup store + Velero~~ **done 2026-10-05:** the location is `Available`; a manual Backup of one service (beszel) completed with no errors. The full nightly schedule runs at 03:30.
2. **Per-app check of the imported data (owner):** row counts already match (§0); log in to each CORE app and check it. Pods have settled except what's in §5.
3. ~~Tunnel back on~~ **done 2026-10-05** (public hostnames and real client IPs checked).
4. **`cluster.py restore`.** Design notes:
   - **Volumes:** a Velero `Restore` CR (selector `homeserver/service=<svc>`) after deleting that service's Deployments and PVCs, with ArgoCD paused (`argo_pause`).
   - **Own Postgres (point in time):** delete the Cluster and recreate it with `bootstrap.recovery` from the ObjectStore under a **new** `serverName` (CNPG refuses an archive that isn't empty), then reconcile with ArgoCD's desired spec.
   - **Shared-database apps:** `pg_restore` / `mariadb` from `dumps/<svc>/<ts>/`.
   - **Verify** with a round trip on a small service (guacamole): back up, reset, restore, data back.
5. **Measured resource requests:** read real usage (`kubectl top`, metrics-server is installed) and set per-service requests in the overrides.
6. **Broad pass:** smoke-test the 15 deferred apps (`cluster.py smoke …`, one at a time).
7. Update the docs (guide Step 7 restore, Step 8 rebuild) and this file.

### Where it stands (2026-10-05, 09:00)

**Second rebuild done, tunnel on.** A fresh export (`/mnt/mydata/k8s-data/export/20261005-012033`, 28 services) was imported into a recreated cluster; every row count matches the first rebuild (Immich 21,246 assets, Firefly 113/793, Nextcloud 691 files, Authentik 4 users, Uptime Kuma 187 monitors…). 97 pods run, the public hostnames answer and `nginx-plain` logs real client IPs. The old data folders are aside: `~/k8s-data/{fast,bulk}.pre-rebuild-20261005` and `/mnt/mydata/k8s-data/backup.pre-rebuild-20261005` (the old WAL archive, kept out of the new store on purpose: CNPG refuses a non-empty archive for the same server name). The reason for the rebuild was AdGuard's port 8123 (kind maps ports only at creation).

**Done today besides the rebuild:** AdGuard Home runs on Docker (`DNS_BIND_IP=192.168.1.7`, answers DNS over UDP and TCP; skipped in `kubernetes/scope.yaml`). `docker/host-boot-safety.sh` was run (SATA `max_performance`, `ip_nonlocal_bind=1`, mount ordering). `homeserver.py --no-wg` stops `prod up` from starting wg-easy as a side effect (docs/15). `cluster.py argocd-password` keeps one ArgoCD password across rebuilds (hash in `kubernetes/.env`, applied by bootstrap). The host's static IP is 192.168.1.7/24 on `Airtel_Roger` (a `/0` mask once cut IPv4 for an hour).

**Done while the owner was away (2026-10-05, 09:00-14:30):**
- `cluster.py verify --env prod`: one read-only health check (nodes, pods, ArgoCD, databases, backups, tunnel, public hostnames, host SATA/IO/disk). 15/15 pass. Its blind spot is the Cloudflare edge: also test from another network.
- **Backups proven:** the nightly Velero backup and all 9 CloudNativePG base backups ran on the new cluster and completed. **A Velero restore into a throwaway namespace worked end to end** (restored `beszel-data` matched the live files byte for byte; a marker written after the backup was absent). That namespace was deleted; a Released test volume `restore-test/beszel-data` (4 MB) remains under `~/k8s-data/fast/restore-test/` for the owner to remove.
- **All three restore paths proven without touching live data** (docs/17 Step 7): Velero volume restore (beszel into a throwaway namespace), a Postgres recovery cluster from Barman (Guacamole: every count equal), and a shared-DB dump restore (miniflux into a scratch database). Throwaway objects were deleted; two **Released** test volumes remain for the owner to remove: `~/k8s-data/fast/restore-test/beszel-data` and `~/k8s-data/fast/apps/guacamole-db-restore-test-1` (a few MB each; `kubectl get pv | grep Released`).
- `cluster.py restore <svc>` (volumes, from Velero) is built and tested but **only as a dry run so far**; the in-place round trip needs the owner's OK (below).
- `adguard-home.prajnatech.in` (its public admin page) is gone with the move to Docker; the admin UI is `http://127.0.0.1:8123` on this host (and `10.8.0.1:8123` over the VPN once wg-easy runs).
- Compose network aliases now get Services and routes (Supabase's `supabase-kong`); dump jobs no longer upload mc's state file.
- ArgoCD: apps now retry forever (they used to give up after 10 tries when a CRD arrived late); `ops-routes` no longer shows permanent drift (no server-side apply for plain routes); unpausing a service refreshes its app at once (`export` used to leave it stopped for minutes).
- Headlamp behind Authentik is built and off by default (`headlamp_auth` in `kubernetes/deploy/<env>.yaml`, docs/17 "Headlamp behind Authentik"): forward-auth plus a read-only service account, not real OIDC (that needs kube-apiserver flags, i.e. a control-plane change on kind).
- `homeserver.py --no-wg`, one ArgoCD password (`argocd-password`), AdGuard on Docker, boot-safety script (earlier today).

**ArgoCD health:** the 42 stopped services showed Progressing only because their volume claims are Pending by design (storage classes wait for the first consumer); a custom `PersistentVolumeClaim` health rule in `argocd-cm` fixed it (docs/17, upstream issue argo-cd #12840). 95 Healthy, 2 Suspended (bichon, plane: suspended migration Jobs).

**Watchdog (2026-10-05, validated in dry-run, then switched on):** the `cluster-watchdog` add-on (`kubernetes/watchdog/watchdog.py`, docs/17 "Watchdog") restarts `cloudflared` when Cloudflare's edge has silently dropped it (twice today: 530 / error 1033 while cloudflared reported 4 ready), probing from inside and from ~11 countries via check-host.net (nodes in filtering countries are ignored), only when `nginx-plain` is fine, at most 3 restarts an hour; and it sends ntfy alerts (`homeserver-alerts`) when a `cluster.py verify`-style check fails two rounds in a row, and when it recovers. It replaces the Uptime Kuma Docker-container monitors that fed ntfy on Docker. Permissions: read-only plus patching the `cloudflared` Deployment only (tests pin it). Switch: `watchdog: active | dry-run` in `kubernetes/deploy/prod.yaml`. Audit that found it: the Kubernetes port had skipped Docker's `cloudflared-watchdog` on the false belief that the liveness probe covers it; the other 12 skips were checked (docker-socket features gone by design; container metrics and logs verified working).

**2026-10-05 16:00, sites down again: the computer had suspended itself** (GNOME idle suspend after 15 min, even on mains: asleep 10:19-16:07; the tunnel re-registered after `kubectl -n apps rollout restart deploy/cloudflared`). Idle suspend was switched off for the owner's session with `gsettings`; **the permanent fix needs `sudo bash docker/host-boot-safety.sh`** (item 6 masks the sleep targets), and `cluster.py verify` fails until it's done. docs/08 "The host went to sleep". The earlier 530 at ~09:00 (tunnel connected locally, 1033 elsewhere, cleared by the same restart) was not a suspend; its cause is unproven.

**Waiting for the owner (nothing is blocked on Claude):**
0. **`sudo bash docker/host-boot-safety.sh`** (the host must never sleep; verify fails until then).
1. **Restore round trip, in place, on beszel** (deletes its workloads, volume claim and volume, moves the old data aside, restores from Velero): `uv run kubernetes/cluster.py restore beszel` prints the plan; add `--yes` to run it. Claude was not allowed to run it unattended (deleting a live service's volume); do it with the owner present, after `cluster.py export --env prod beszel`.
2. **Authentik steps for Headlamp** (docs/17), then `headlamp_auth: authentik`.
3. **Uptime Kuma:** `uv run services/uptime-kuma/setup-monitors.py --k8s --prune` (asks for the owner's Kuma login): the 187 Docker-socket monitors all report down.
4. **`sudo` steps:** wg-easy is stopped on purpose; to bring it back `sudo modprobe iptable_nat ip6table_nat`, persist in `/etc/modules-load.d/wg-easy.conf` (docs/services/wg-easy.md), then `uv run homeserver.py prod up wg-easy`. Any `prod up` without `--no-wg` starts it again.
5. **Router/devices:** point their DNS at 192.168.1.7 for AdGuard's dashboard to fill.
6. **Owner checks:** Cloudflare Connectors list shows only this cluster's 4 connections; a phone on mobile data reaches the sites; app logins; `argocd-password`.

**Still open (engineering):** the 15 deferred apps (Supabase's route is fixed: aliases get Services, §5); restore for databases (Postgres via Barman, shared-DB apps via their dumps: the plan is in §3); a second SSD for the cluster (the real fix for the disk limit); Headlamp token is cluster-admin until `headlamp_auth: authentik`.

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
  - How to sign in to each (commands that print the credentials): `docs/17` Step 6, "Signing in".
  - How to sign in to each (commands that print the credentials): `docs/17` Step 6, "Signing in".
  - Apps keep their Docker localhost ports through the local-access proxy.
- **Tests:** `uv run pytest`: 136 tests in ~20 s, one test per check (`conftest.each`).

## 5. Follow-ups (agreed, not started)

- **The one SSD is now the shared bottleneck** (done 2026-10-05: image store, databases and etcd all on it, replacing the HDD bottleneck). A whole-cluster start or a heavy first start (Nextcloud's rsync of its source tree) drives I/O pressure to ~50-70%, stalls the desktop and makes the API server miss leases (CNPG operator, scheduler and controller-manager restart). Options if it matters: `ionice` for etcd, a `docker update --device-write-bps` cap on the kind node, or a second SSD. Host power: `tuned-adm profile throughput-performance`, EPP `performance` and SATA `max_performance` (commands in the session notes; make them stick with `/etc/tmpfiles.d/99-maxperf.conf`).
- **Egress network policies**, Beszel's agent in its own privileged namespace (then enforce Baseline on `apps`), image scanning, Cloudflare Access/WAF, Authentik two-factor, a Docker socket proxy, and etcd `ionice`.
- ~~Compose network aliases aren't generated as Services.~~ Fixed 2026-10-05 (Supabase's `supabase-kong`); only what stays on Docker has no public route.
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

## 9. Lessons from 2026-10-05 (each fixed, each with a test or a doc note)

- **mariadb-operator's default startup probe (~50 s) kills a first start that is still initialising** on a loaded disk, leaving a corrupt datadir (zeroed `ibdata1`, root password never set). Generated `MariaDB` resources now set a 15-minute `startupProbe`. Damaged volumes: move the files aside, don't delete.
- **`import --from-export` started every exported service, the stopped tunnel included.** It now starts only the running list.
- **A probe on a container's own name goes through a Service that has no ready pod.** Temporal never became Ready; the generator now emits `tcpSocket` for that pattern.
- **Dagster's chart readiness probe is fixed to port 80;** our service port is 3000, so the probe moves with it.
- **Locally built images (`homeserver/dagster-user-code`, `homeserver/temporal-worker`) are gone after a reinstall:** run `cluster.py images <svc>` after bootstrap.
- **Cloudflare showed the tunnel healthy while no connector ran here.** Check Zero Trust, Tunnels, Connectors for a stray one before turning the tunnel on.
- **The tunnel can look healthy and still serve outside visitors `530` / `error code: 1033`** (2026-10-05, after the second rebuild). `cloudflared` logged 4 registered connections and `/ready` said `readyConnections: 4`, and requests from this host (via the Mumbai edge) returned 200, but other Cloudflare edges (Marseille) and an independent fetcher got 1033 for ~20 minutes. `kubectl -n apps rollout restart deploy/cloudflared` (a fresh registration) fixed it at once. **After any rebuild, test the public hostnames from outside this machine** (a different network or an independent fetcher), not only with `curl` from the host, and restart `cloudflared` on 1033.

