# 17 — Moving from Docker Compose to Kubernetes

[← MIN/CORE Reset Runbook](16-min-core-reset-runbook.md) | [Home](../setup.md)

---

A step-by-step guide, with every command, for running this stack on Kubernetes **next to** (and later instead of) Docker Compose. It's written for anyone running this repo on their own machine.

**How it works:**
- **Kubernetes is generated from Compose.** You never edit Kubernetes files by hand. `kubernetes/generate.py` turns each `services/<svc>/compose.yml` (+ `.env`, `services.json`) into Kubernetes manifests, and a test fails if they ever drift apart.
- **The same layout as Compose:**
  - shared Postgres/MariaDB for apps above CORE;
  - own databases for CORE;
  - one Valkey cache per app;
  - the same images, healthchecks and `.env` settings.
- **The same commands:** `k8s.py up/down/backup/restore` behave like `homeserver.py`.

The design and its reasons are in [`research/kubernetes-compose-parity-plan.md`](../research/kubernetes-compose-parity-plan.md).

> **Status (2026-10-03): being built in phases.** Each section below is filled in only once its commands are implemented and tested. Sections marked *(coming in phase N)* aren't usable yet. Docker Compose stays the system you actually run until you decide otherwise.

## Before you start

| Question | Answer |
|---|---|
| Does Docker have to stop? | **No.** The test cluster (kind) runs next to Docker on its own ports and its own `*.k8s.local` hostnames. |
| Does it touch my real data? | **No.** It uses copies: database dumps imported into the cluster, and sample media for apps that write to their media folders. |
| Will my public sites switch over? | **No.** The test cluster never runs cloudflared, so the Cloudflare tunnel keeps pointing at Docker. |
| How much RAM? | Start with MIN plus one CORE app. Don't run the whole stack in Kubernetes next to a live Compose stack on one machine. |

## Step 0a — Start clean (only if you ran the old pilot)

Earlier versions of this repo had a hand-written Kubernetes pilot. Its files are now in `kubernetes/legacy/`, for reference only. If you used it, remove what it left behind first:

```bash
kind get clusters                      # if "kind-cluster" is listed:
kind delete cluster --name kind-cluster
rm -f kubernetes/.env                  # old copy of service secrets; the real ones stay in services/*/.env
rm -rf ~/.kube/cache
```

Also check for an old **kubectl of a different minor version**: `kubectl version --client`. Step 0 reinstalls it at the pinned version, writing to the same `/usr/local/bin/kubectl`. Leave `containerd.service` alone; Docker uses it.

## Step 0 — Install the tools

The versions are pinned in [`kubernetes/versions.env`](../kubernetes/versions.env), which holds every cluster component in one place. **Kubernetes is 1.35**, the newest version that AWS EKS, Azure AKS and Google GKE (stable channel) all support, so what you build here can move to any of them.

You need **Docker** (kind runs Kubernetes "nodes" as Docker containers), **kind**, **kubectl** and **helm**.

```bash
cd ~/homeserver                         # the repo root
set -a; . kubernetes/versions.env; set +a

# kind
curl -fsSLo /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64"
sudo install -m 0755 /tmp/kind /usr/local/bin/kind

# kubectl (same minor as the cluster), checksum-verified
curl -fsSLo /tmp/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
curl -fsSLo /tmp/kubectl.sha256 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256"
echo "$(cat /tmp/kubectl.sha256)  /tmp/kubectl" | sha256sum --check
sudo install -m 0755 /tmp/kubectl /usr/local/bin/kubectl

# helm (official installer, pinned version)
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 | bash -s -- --version "${HELM_VERSION}"
```

### Raise the inotify limits first (required next to Docker)

Docker's containers and the kind node all use inotify, and Linux's defaults (128 instances) run out quickly. The symptom is `Too many open files`, even from `systemd`, which broadcasts `Failed to allocate manager object: Too many open files` to your terminals. Set this once:

```bash
sudo tee /etc/sysctl.d/99-inotify.conf <<'SYSCTL'
# Many containers (Docker + a kind Kubernetes node) each need inotify instances
# and watches; the defaults (128 / ~270k) run out ("Too many open files").
fs.inotify.max_user_instances = 1024
fs.inotify.max_user_watches = 524288
SYSCTL
sudo sysctl --system | grep inotify     # takes effect immediately, survives reboots
```

Check: `sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches` should print `1024` and `524288`. Details: [08 — Maintenance](08-maintenance.md#host-inotify-limits-hit-when-running-many-containers-at-once), [kind's known issues](https://kind.sigs.k8s.io/docs/user/known-issues/#pod-errors-due-to-too-many-open-files).

Check:

```bash
kind version            # kind v0.33.0 ...
kubectl version --client
helm version
```

On macOS, use the `darwin-arm64`/`darwin-amd64` downloads, or `brew install kind kubectl helm` (then check the versions match `versions.env`). On Windows, use WSL2 and follow the Linux steps.

## Step 1 — Generate the Kubernetes manifests

Kubernetes files are **generated from Compose**, never written by hand:

```bash
uv run kubernetes/generate.py           # writes kubernetes/generated/
uv run kubernetes/generate.py --check   # is generated/ up to date? (the test suite runs this)
```

- **Inputs:** each `services/<svc>/compose.yml` + `compose.prod.yml` (read through `docker compose config`, so everything resolves exactly as Docker sees it), `.env.example`, `services.json`, and nginx-plain's route template.
- **Kubernetes-only details** live in small `kubernetes/overrides/<svc>.yaml` files (e.g. "clone the docs folders with git-sync", "the agent runs on every node").
- **Which services are done:** [`kubernetes/scope.yaml`](../kubernetes/scope.yaml) lists what's ported so far, what's skipped and why.
- **Output, per service:**
  - `kubernetes/generated/apps/<svc>/`: workloads, Services, ConfigMaps, volume claims;
  - `kubernetes/generated/envs/test|prod/<svc>/`: that plus routes, with `*.k8s.local` hostnames for test and your real `DOMAIN` for prod.
- **No secrets** in any generated file. `.env` values only become `$(VAR)` references to a Secret; a test checks no secret value ever appears.

After changing a service's Compose file, re-run the generator and commit both. `uv run pytest` fails until you do.

## Step 2 — Create the test cluster

Set this machine's paths and ports (not secret):

```bash
cp kubernetes/.env.example kubernetes/.env
$EDITOR kubernetes/.env
```

| Setting | Meaning | This host |
|---|---|---|
| `K8S_HTTP_PORT` / `K8S_HTTPS_PORT` | Where the cluster's router listens (loopback only) | `18080` / `18443` |
| `K8S_FAST_PATH` | SSD folder for databases and small data (storage class `fast`) | `~/k8s-data/fast` |
| `K8S_BULK_PATH` | HDD folder for big data, backups, logs (storage class `bulk`) | `/mnt/mydata/k8s-data/bulk` |
| `K8S_IMAGES_PATH` | Where the cluster keeps its copy of every image. kind stores images a second time, so keep this off a small SSD | `/mnt/mydata/k8s-data/containerd` |

Then:

```bash
uv run kubernetes/cluster.py create     # kind cluster, Kubernetes 1.35.8 (takes ~3 min)
uv run kubernetes/cluster.py install    # Gateway API, namespaces, Traefik, storage classes fast/bulk
uv run kubernetes/cluster.py secrets    # each services/<svc>/.env -> Secret <svc>-env (piped, never written to disk)
uv run kubernetes/cluster.py apply      # every ported service (or name some: apply docs landing)
uv run kubernetes/cluster.py status     # pods, services, volume claims, routes
```

- **The test cluster uses `DOMAIN=k8s.local`**, so apps build their links for the test hostnames, not your real domain.
- **cloudflared is prod-only:** it is never deployed to the test cluster, and its tunnel token isn't copied there. Your public sites keep pointing at Docker.

**Try it:** every route answers on `127.0.0.1:18080` with its test hostname:

```bash
curl -H "Host: www.k8s.local"  http://127.0.0.1:18080/      # landing page
curl -H "Host: docs.k8s.local" http://127.0.0.1:18080/      # docs
```

For a browser, add the hostnames to `/etc/hosts` (`127.0.0.1 www.k8s.local docs.k8s.local beszel.k8s.local`) and open `http://docs.k8s.local:18080`.

**Where data lives:** volumes appear as readable folders, e.g. `~/k8s-data/fast/apps/beszel-data/`.

**Remove it all:** `uv run kubernetes/cluster.py delete` (the data folders are kept; delete them by hand if you want).

**Verified on this host (2026-10-03):** MIN (landing, docs, beszel + agent) runs next to the live Compose stack, which was unchanged (48 containers, public sites still served by Docker).

## Step 3 — Secrets from your `.env` files

The same `.env` files Docker uses are the only source of secrets. Nothing secret is in git or in `kubernetes/generated/`; a test fails if a value from any `.env` shows up there.

```bash
uv run kubernetes/cluster.py secrets                 # every ported service
uv run kubernetes/cluster.py secrets miniflux        # or just some
```

What it creates in namespace `apps` (built in memory, piped to `kubectl`, never written to disk):

| From | Secret | Used by |
|---|---|---|
| `services/<svc>/.env` | `<svc>-env` (every key) | the app's containers (`envFrom`) |
| `services/shared-postgres/.env` `POSTGRES_USER`/`POSTGRES_PASSWORD` | `shared-postgres-superuser` (basic-auth) | CloudNativePG's admin login |
| a shared-Postgres app's `.env` user/password keys (`services.json` `shared_db`) | `<svc>-db-role` (basic-auth) | CloudNativePG creates the app's login with it |
| root `.env` `DOMAIN`, `TZ` | ConfigMap `homeserver-root` (`DOMAIN=k8s.local` in test) | every app |

**Changing a value or password:** edit the `.env` and run `secrets` again. Each Secret carries a hash of its `.env`; when it changes, `secrets` restarts that service's pods so they read the new values (the kubectl form of [Helm's `checksum/config` pattern](https://helm.sh/docs/howto/charts_tips_and_tricks/#automatically-roll-deployments)). Database logins follow by themselves: the role Secrets carry the `cnpg.io/reload` label, and the MariaDB apps' `<svc>-env` Secrets carry `k8s.mariadb.com/watch`, the labels each operator needs before it re-reads a changed password.

**Later, in a cloud:** the External Secrets Operator can fill the same Secret names from AWS Secrets Manager, Azure Key Vault or GCP Secret Manager. No manifest changes.

## Step 4 — Databases: shared and own

Same layout as Docker: apps above CORE share one Postgres and one MariaDB; CORE apps keep their own (phase 3). Two operators run them, installed by `cluster.py install`:

| Docker | Kubernetes | Operator |
|---|---|---|
| `shared-postgres` container (`postgres:18.6`) | CloudNativePG `Cluster` `shared-postgres` (PostgreSQL 18.6, same settings from the Compose `command`), plus a Service named `shared-postgres` | [CloudNativePG](https://cloudnative-pg.io) 1.30 |
| `shared-mariadb` container (`mariadb:11.8`) | `MariaDB` `shared-mariadb`, the same official image and `my.cnf` settings | [mariadb-operator](https://github.com/mariadb-operator/mariadb-operator) 26.10 |
| `homeserver.py` creates each app's login and database on `up` (`provision_shared_db`) | generated `DatabaseRole` + `Database` (Postgres), or `User` + `Database` + `Grant` (MariaDB), from the same `services.json` `shared_db` entries | — |

Apps keep their `.env` unchanged: `DB_HOST=shared-postgres` / `shared-mariadb` is the Service name in Kubernetes too, and each app waits for it before starting (`wait-db`).

```bash
uv run kubernetes/cluster.py secrets shared-postgres shared-mariadb miniflux bookstack
uv run kubernetes/cluster.py apply   shared-postgres shared-mariadb       # the servers first
kubectl -n apps get cluster,mariadb                                        # wait: "Cluster in healthy state" / Ready True
uv run kubernetes/cluster.py apply   miniflux bookstack                   # then the apps
kubectl -n apps get databaserole,databases.postgresql.cnpg.io,users,grants,databases.k8s.mariadb.com
```

Things that work differently from Docker, on purpose:

- **Isolation between apps.** Docker runs `REVOKE ALL ON DATABASE … FROM PUBLIC`; CloudNativePG doesn't manage privileges, so the generator writes `pg_hba` rules instead: each app's login may connect only to its own database(s), and is rejected everywhere else.
- **Deleting a manifest never drops data.** Roles and databases use `retain` (CloudNativePG) and `cleanupPolicy: Skip` (mariadb-operator, whose default is to drop). Remove a database by hand if you really mean it.
- **A database outside the cluster** (RDS, Cloud SQL, Azure): point `DB_HOST` in the app's `.env.example` at it and regenerate; the generator then emits no role or database for that app, like `homeserver.py`'s `shared_db_external()`.
- **Names come from `.env.example`.** The generated output can't depend on one machine's `.env`, so a test checks your `.env` uses the same database/user names.

**Verified on this host (2026-10-03):** shared-postgres (CloudNativePG, 18.6) and shared-mariadb (11.8) run next to Docker. miniflux (14 tables created as its own role) and bookstack connect with their unchanged `.env`. The miniflux login is rejected on every other database (`pg_hba.conf rejects connection … database "postgres"`). Bookstack's grants match what `homeserver.py` creates: `ALL PRIVILEGES ON bookstack.*`, no connection cap.

**Check an app's login:**

```bash
kubectl -n apps exec shared-postgres-1 -- psql -c '\du'                  # roles
kubectl -n apps exec shared-postgres-1 -- psql -c '\l'                   # databases + owners
```

## Step 5 — Start services by tier, like `homeserver.py` *(coming in phase 3–4)*
## Step 6 — ArgoCD, Headlamp and logs *(coming in phase 4)*
## Step 7 — Backups: `down` backs up, `restore` brings it back *(coming in phase 5)*
## Step 8 — Testing with your real data

Data goes into the cluster as **copies**. Docker's `service_data` folders and databases are only ever read:

```bash
uv run kubernetes/cluster.py import beszel                 # newest Compose snapshot -> the service's volume
uv run kubernetes/cluster.py import authentik --live-db    # database from the running container instead
uv run kubernetes/cluster.py import nextcloud --snapshot 20261003-123208
```

What `import` does for each service:

1. Stops it on the cluster (Deployments scaled to 0).
2. Unpacks the snapshot's `service_data` tar into the service's `<svc>-data` volume. One volume per service, with each subfolder mounted as a `subPath`, like Compose's `DATA_ROOT`.
3. Copies its own Postgres database into the CloudNativePG cluster with `pg_dump`/`pg_restore`, Postgres's documented way to move data between servers:
   - **from a snapshot:** the tar is unpacked into scratch space and served by a throwaway container of the Compose image, with no network;
   - **with `--live-db`:** the dump is taken from the running Compose container. `pg_dump` reads one consistent snapshot without blocking it.
4. Unpacks other named volumes into their own volumes.
5. Starts it again.

Use `--live-db` when the newest snapshot is older than the data you want. **Seen on 2026-10-03:** Authentik's newest snapshot came from right after a `reset`, so it held a blank Authentik; the live database had the applications and users.

**Localhost ports work like under Compose.** Every port a `compose.prod.yml` publishes on a fixed address becomes the container's `hostPort` + `hostIP` (`127.0.0.1`, and the `10.8.0.1` VPN mirror), which is Kubernetes' form of `127.0.0.1:8088:9000`:

- **On a cluster that runs on your machine** (k3s, kubeadm…), `localhost:8088` answers directly.
- **On kind**, the node is a container, so the generator also writes NodePort Services and `generated/host-ports.yaml`, and `cluster.py create` binds each port on `127.0.0.1` with kind's port mappings. kind adds mappings only at creation, so a newly ported service needs a rebuild for its port; its `*.<domain>` route works without one.
- **nginx-plain's** `8180`/`8443` go to Traefik, which does its job here.
- **Host-network containers** (wg-easy) listen on the node directly. A `node_ports` entry in the override forwards a port from every host address (WireGuard's UDP 51820).

Kubernetes' guidance is to avoid `hostPort` unless needed. Matching Compose's localhost ports on one machine is that need, and those Deployments use the `Recreate` strategy, because two pods can't hold the same host port at once.

**Big media folders are mounted, not copied** (`hostPath` + `env` in the override). `cluster.py create` mounts the path from the service's `.env` into the kind node; kind can only add mounts at creation, so adding one means rebuilding the cluster.

| Folder | Mounted | Why |
|---|---|---|
| Jellyfin `MEDIA_ROOT` | read-only | Compose mounts it read-only too |
| Nextcloud `OS_ISO_ROOT` | read-only | Only read |
| Immich `UPLOAD_LOCATION` | **read-write** | Immich refuses to start unless it can write its `.immich` check files |

**Immich shares your real photo folder, and Compose snapshots don't include it** (only Immich's database). Before testing Immich on Kubernetes:

- Have your own copy of the photo folder, for example on the Passport.
- Stop Compose's Immich first, so two Immichs never use the folder at once.
- Don't upload or delete photos on the Kubernetes side.

`immich-offline-remover` doesn't run on Kubernetes, so a test never removes library entries. Back on Docker, `restore immich` brings back the database. The photo folder is the same one, with at most some new thumbnails.

Logins: protected hostnames (nginx-plain's `auth_request`, e.g. `browser.`) keep the Authentik sign-in through Traefik's ForwardAuth middleware, as in [Authentik's Traefik guide](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_traefik/). The same Authentik providers work unchanged.
## Step 9 — Going back to Docker *(written with step 8)*

## Why it's built this way (sources)

Every Kubernetes choice here follows the upstream project's documented way. Where none exists, the row says so and gives the reason. Checked 2026-10-03.

| Choice | Source / reason |
|---|---|
| Probes: readiness = the Compose healthcheck; liveness = the same check with twice the `failureThreshold`; a startup probe covers `start_period` | [Kubernetes probe guidance](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): "the same low-cost endpoint as for readiness probes, but with a higher `failureThreshold`". A short database outage takes apps out of traffic without restarting them all |
| Images with their own `HEALTHCHECK` (Compose defines none) get it copied verbatim into the override (`image_healthcheck`), then the same probe rules | Kubernetes ignores image `HEALTHCHECK`s. A test compares each copy with the image on this host, so a version bump that changes the check fails instead of drifting |
| A change to a repo file mounted from a ConfigMap rolls the pod (`homeserver/config-sha256` annotation) | Kubernetes never updates a `subPath` mount in a running pod; [Helm's `checksum/config` pattern](https://helm.sh/docs/howto/charts_tips_and_tricks/#automatically-roll-deployments) |
| `depends_on: service_healthy` becomes an init container looping on `nc -z <service> <port>` | [Kubernetes init containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) document the same `until …; sleep 2; done` loop with `nslookup`. A TCP connect is stricter: a Service only accepts connections once a pod behind it is ready, which matches Compose's "healthy" |
| Shared Postgres: CloudNativePG `Cluster`, `DatabaseRole`, `Database`; the `shared-postgres` name via `managed.services.additional` | [CloudNativePG 1.30](https://cloudnative-pg.io/docs/1.30/service_management/) |
| Per-app isolation with `pg_hba` rules instead of `REVOKE CONNECT` | CloudNativePG doesn't manage privileges. [PostgreSQL's shared-hosting guide](https://wiki.postgresql.org/wiki/Shared_Database_Hosting) recommends restricting connections in `pg_hba.conf` |
| Shared MariaDB: mariadb-operator `MariaDB`, `User`, `Database`, `Grant`; `cleanupPolicy: Skip`, `maxUserConnections: 0`, the `k8s.mariadb.com/watch` label | [mariadb-operator docs](https://github.com/mariadb-operator/mariadb-operator/tree/main/docs) and its API (`user_types.go`): the defaults are `Delete` and 10 connections, and Secret changes are only picked up with the label |
| nginx-plain's redirect-only blocks (bare domain → `www`) become an HTTPRoute with the `RequestRedirect` filter | [Gateway API HTTP redirects](https://gateway-api.sigs.k8s.io/guides/http-redirect-rewrite/): the core filter keeps path and query, like nginx's `$request_uri` |
| Traefik creates the Gateway itself (`gateway.enabled`, `namespacePolicy: All`) | The Traefik chart's own values (`helm show values traefik --version 41.6.1`) |
| Beszel agent: DaemonSet, `hostNetwork`, control-plane tolerations, `maxUnavailable: 100%` | [Beszel's Kubernetes example](https://beszel.dev/guide/advanced-deployment) |
| docs: git-sync runs once at pod start, not as a live sidecar | [git-sync](https://github.com/kubernetes/git-sync) "can pull one time". The paths are `subPath` mounts, which Kubernetes never updates after start, so a sidecar's later syncs wouldn't reach the app |
| Storage classes `fast`/`bulk` | [local-path-provisioner](https://github.com/rancher/local-path-provisioner): `nodePath` (listed in `nodePathMap`) and `pathPattern` per StorageClass |
| Restart on `.env` change | [Helm's `checksum/config` pattern](https://helm.sh/docs/howto/charts_tips_and_tricks/#automatically-roll-deployments), done with `kubectl rollout restart` when the Secret's hash changes |
| Secrets parsed with the same `.env` rules as Compose, not `kubectl --from-env-file` | **Own design:** kubectl's env-file parser keeps quotes literally, while Compose strips them. Apps must see the same values in both runtimes |
| kind node's image store on the HDD (`K8S_IMAGES_PATH` mounted at `/var/lib/containerd`) | **Own design:** [kind extraMounts](https://kind.sigs.k8s.io/docs/user/configuration/#extra-mounts) are documented, but not for containerd's store. kind keeps a second copy of every image, which the small SSD can't hold. Verified on ext4 |
| Host access through NodePort + `extraPortMappings` on `127.0.0.1` | kind's docs now recommend [cloud-provider-kind](https://github.com/kubernetes-sigs/cloud-provider-kind) (real LoadBalancer IPs). **Open:** switching is pending a decision, because it changes which address the test hostnames use |
