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
- **Deployed from git (GitOps):** ArgoCD applies whatever the repo says, including which services run (`kubernetes/deploy/<env>.yaml`). Moving to another cluster or a managed cloud = install ArgoCD and point it at the repo. `k8s.py up/down` edit that list with `homeserver.py`'s tier meanings.

The design and its reasons are in [`research/kubernetes-compose-parity-plan.md`](../research/kubernetes-compose-parity-plan.md).

> **Status (2026-10-04): being built in phases. MIN and CORE run on kind with real data (step 8).** Each section below is filled in only once its commands are implemented and tested. Sections marked *(coming in phase N)* aren't usable yet. Docker Compose stays the system you actually run until you decide otherwise.

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
uv run kubernetes/cluster.py create                # kind cluster, Kubernetes 1.35.8 (takes ~3 min)
uv run kubernetes/cluster.py bootstrap --env test  # ArgoCD + the secret store; ArgoCD installs the rest from git (Step 6)
uv run kubernetes/cluster.py status                # pods, services, volume claims, routes
uv run kubernetes/cluster.py validate              # server-side dry run of every service; fails on errors and on deprecated APIs/fields
```

ArgoCD reads the repo from GitHub, so it deploys what is **pushed** to the branch in `kubernetes/deploy/<env>.yaml`, not your working copy.

- **The test cluster uses `DOMAIN=k8s.local`**, so apps build their links for the test hostnames, not your real domain.
- **cloudflared is prod-only:** it is never deployed with `--env test`, and its tunnel token isn't copied there, so your public sites keep pointing at Docker. To serve your real domain from the cluster instead, see Step 8 ("Serving your real domain").

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

The same `.env` files Docker uses are the only source of secrets. Nothing secret is in git, not even encrypted (the repo is public); a test fails if a value from any `.env` shows up in `kubernetes/generated/`.

**How (decided 2026-10-04):** the [External Secrets Operator](https://external-secrets.io) (ESO), with a store inside the cluster:

```bash
uv run kubernetes/cluster.py secrets                 # every ported service (bootstrap runs it once)
uv run kubernetes/cluster.py secrets miniflux        # or just some, after editing their .env
```

1. `secrets` copies each `services/<svc>/.env` into Secret `<svc>` in namespace `homeserver-secrets`: the **store**. It's built in memory and piped to `kubectl`, never written to disk. Only ESO can read that namespace, through a read-only Role; its `ClusterSecretStore` serves only the `apps` namespace.
2. Each service's generated `ExternalSecret`s (in git, holding names only) build the Secrets the app uses:

| ExternalSecret builds | From the store's `<svc>` | Used by |
|---|---|---|
| `<svc>-env` (every key) | all of `services/<svc>/.env` | the app's containers (`envFrom`) |
| `shared-postgres-superuser` (basic-auth) | `POSTGRES_USER`/`POSTGRES_PASSWORD` | CloudNativePG's admin login |
| `<svc>-db-owner` / `<svc>-db-superuser` (basic-auth) | the CORE app's own database user/password keys | its own CloudNativePG cluster |
| `<svc>-db-role` (basic-auth) | the shared-Postgres app's user/password keys (`services.json` `shared_db`) | CloudNativePG creates the app's login with it |

Plus ConfigMap `homeserver-root` (root `.env` `DOMAIN`, `TZ`; `DOMAIN=k8s.local` in test), generated into git (`envs/<env>/homeserver-config`) because neither value is secret.

**Changing a value or password:** edit the `.env` and run `secrets` again. ESO refreshes the app's Secrets within a minute. [Reloader](https://github.com/stakater/Reloader) then restarts every workload whose Secret changed; it marks the restart with an annotation, the strategy its docs give for staying in sync with ArgoCD. Database logins follow by themselves: the login Secrets carry `cnpg.io/reload`, and the MariaDB apps' `<svc>-env` carry `k8s.mariadb.com/watch`, the labels each operator needs before it re-reads a changed password.

**Why ESO, not secrets in git** (options compared 2026-10-04, ArgoCD's [secret management guide](https://argo-cd.readthedocs.io/en/stable/operator-manual/secret-management/)):

| Option | Verdict |
|---|---|
| SOPS in git | ArgoCD needs a plugin to decrypt it, which ArgoCD's docs advise against (ArgoCD would hold the secrets, and keep them in plaintext in its Redis cache). It's the homelab favourite with Flux, not ArgoCD. |
| Sealed Secrets | Simple, but tied to one cluster's key, and every secret would be public, encrypted, forever in this public repo. |
| **ESO, store in the cluster (chosen)** | Nothing secret in git. `.env` stays the one source for Docker and Kubernetes. |
| ESO, cloud store | The same manifests: moving to AWS Secrets Manager, Azure Key Vault or GCP Secret Manager changes only the `ClusterSecretStore` (`generate.py` `homeserver_config`). Apps keep reading the same Secret names. |

## Step 4 — Databases: shared and own

Same layout as Docker: apps above CORE share one Postgres and one MariaDB; CORE apps keep their own (phase 3). Two operators run them, installed by ArgoCD (Step 6):

| Docker | Kubernetes | Operator |
|---|---|---|
| `shared-postgres` container (`postgres:18.6`) | CloudNativePG `Cluster` `shared-postgres` (PostgreSQL 18.6, same settings from the Compose `command`), plus a Service named `shared-postgres` | [CloudNativePG](https://cloudnative-pg.io) 1.30 |
| `shared-mariadb` container (`mariadb:11.8`) | `MariaDB` `shared-mariadb`, the same official image and `my.cnf` settings | [mariadb-operator](https://github.com/mariadb-operator/mariadb-operator) 26.10 |
| `homeserver.py` creates each app's login and database on `up` (`provision_shared_db`) | generated `DatabaseRole` + `Database` (Postgres), or `User` + `Database` + `Grant` (MariaDB), from the same `services.json` `shared_db` entries | — |

Apps keep their `.env` unchanged: `DB_HOST=shared-postgres` / `shared-mariadb` is the Service name in Kubernetes too, and each app waits for it before starting (`wait-db`).

```bash
uv run kubernetes/k8s.py up miniflux bookstack --env test   # the shared servers start with them
git add kubernetes/deploy kubernetes/generated && git commit -m "k8s: run miniflux, bookstack" && git push
kubectl -n apps get cluster,mariadb                          # "Cluster in healthy state" / Ready True
kubectl -n apps get databaserole,databases.postgresql.cnpg.io,users,grants,databases.k8s.mariadb.com
```

Things that work differently from Docker, on purpose:

- **Isolation between apps.** Docker runs `REVOKE ALL ON DATABASE … FROM PUBLIC`; CloudNativePG doesn't manage privileges, so the generator writes `pg_hba` rules instead: each app's login may connect only to its own database(s), and is rejected everywhere else.
- **Deleting a manifest never drops data.** Roles and databases use `retain` (CloudNativePG) and `cleanupPolicy: Skip` (mariadb-operator, whose default is to drop), and ArgoCD never prunes or deletes them (Step 6). Remove a database by hand if you really mean it.
- **A stopped Postgres is hibernated** (CloudNativePG's [declarative hibernation](https://cloudnative-pg.io/docs/1.30/declarative_hibernation/)): pods gone, volumes kept. A database created stopped is initialised once and then hibernated (verified on kind, 2026-10-04).
- **A MariaDB server can't be stopped from git.** mariadb-operator has no scale-to-zero ([open request #356](https://github.com/mariadb-operator/mariadb-operator/issues/356)); its `suspend` only pauses the operator. So one is created (`suspend: false`) the first time a running app needs it and then keeps running: Uptime Kuma's own (CORE, always on anyway) and `shared-mariadb` (768 MB cap) once BookStack, InvoiceShelf or OrangeHRM has run.
- **A database outside the cluster** (RDS, Cloud SQL, Azure): point `DB_HOST` in the app's `.env.example` at it and regenerate; the generator then emits no role or database for that app, like `homeserver.py`'s `shared_db_external()`.
- **Names come from `.env.example`.** The generated output can't depend on one machine's `.env`, so a test checks your `.env` uses the same database/user names.

**Verified on this host (2026-10-03):** shared-postgres (CloudNativePG, 18.6) and shared-mariadb (11.8) run next to Docker. miniflux (14 tables created as its own role) and bookstack connect with their unchanged `.env`. The miniflux login is rejected on every other database (`pg_hba.conf rejects connection … database "postgres"`). Bookstack's grants match what `homeserver.py` creates: `ALL PRIVILEGES ON bookstack.*`, no connection cap.

**Check an app's login:**

```bash
kubectl -n apps exec shared-postgres-1 -- psql -c '\du'                  # roles
kubectl -n apps exec shared-postgres-1 -- psql -c '\l'                   # databases + owners
```

### Smoke-testing services above CORE

Every service is started once with **empty data** before you use it, to catch what the generator got wrong:

```bash
uv run kubernetes/cluster.py images temporal zulip --drop-host-copy   # locally built images (Compose build:) into kind
uv run kubernetes/cluster.py smoke excalidraw karakeep homebox        # one at a time: pull, start, wait, check, remove
uv run kubernetes/cluster.py smoke wallabag --keep                    # leave it running to inspect
uv run kubernetes/cluster.py rmi wallabag                             # free its images afterwards
```

- **Test hostnames only.** `smoke` uses `*.k8s.local`, reachable only on this machine. A fresh app often lets the first visitor create the admin account, so it must never be reachable on your real domain.
- **Login-protected apps** (behind Authentik) are checked directly at their Service, because Authentik has no provider for test hostnames and answers 404.
- **One service at a time, images pulled one by one.** Starting a whole tier at once (2026-10-04) pulled and unpacked dozens of images together: the HDD (image store) and the SSD (etcd, databases) saturated, and etcd's slow writes made the API server, scheduler and controller-manager restart repeatedly (5, 16 and 17 times). Ready services then timed out and teardowns failed. etcd is very sensitive to disk latency; on a cluster built for real use, give it a fast disk of its own, or raise its heartbeat and election timeouts (etcd's tuning guide). For kind, that's planned for the next rebuild. A side effect seen the same day: the CloudNativePG operator lost its leader election during the stall and stayed unready for 50 minutes despite three automatic restarts (its admission webhook refused every change: `failed calling webhook "mcluster.cnpg.io" ... connection refused`). `kubectl -n cnpg-system rollout restart deploy/cnpg-controller-manager` recovered it; the databases themselves kept running throughout.
- **Images are removed after each test** (`rmi`), apart from any image a running service still uses, to keep the image store's disk free.
- **ArgoCD is paused for the service under test** (its `skip-reconcile` annotation), because git says the service is stopped. Afterwards ArgoCD recreates it as git has it. `import` does the same while it copies data.

### Deprecation and currency audit (2026-10-04)

- **Kubernetes APIs and fields:** a server-side dry run of all 75 services gave **0 deprecation warnings**. `validate` now fails on any.
- **Component logs** (Traefik, CloudNativePG, mariadb-operator, local-path, kindnet, API server, controller-manager, scheduler): no deprecation notices. etcd's one notice (`--snapshot-count is deprecated in 3.6`) comes from kubeadm's default etcd setup, which kind uses, not from this repo.
- **Versions:** every pinned component (`kubernetes/versions.env`) is its project's latest release: kind, Gateway API, CloudNativePG, mariadb-operator, the Traefik chart, Argo CD, Headlamp, Velero, local-path and git-sync. Kubernetes stays on 1.35 on purpose (managed-cloud parity).

### Hardening built into every generated pod (2026-10-04)

| Setting | Why | Source |
|---|---|---|
| `automountServiceAccountToken: false` | No app here calls the Kubernetes API, so none gets API credentials | [Kubernetes: opt out of API credential automounting](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/) |
| `seccompProfile: RuntimeDefault` | The system-call filter Docker already applies to every Compose container; Kubernetes leaves it off by default | [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) |
| `allowPrivilegeEscalation: false` | A process can't gain privileges through setuid programs | Pod Security Standards, Restricted |

An app that genuinely needs an exception records it in its override: `security: {privilege_escalation: true, reason: ...}` or `security: {seccomp: Unconfined, reason: ...}`.

### Secrets encrypted at rest, and a steadier control plane

Applied by `cluster.py create` (so from the next cluster rebuild on):

- **Secrets are encrypted in etcd with `secretbox`.** The Kubernetes docs rate it "Strong"; they call `aescbc` "Weak" (padding-oracle attacks) and accept `aesgcm` only with automatic key rotation ([encrypt-data](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)). The key is generated once into `kubernetes/.env` (`K8S_SECRETS_ENCRYPTION_KEY`, mode 600, never in git). The config file goes to `K8S_ENCRYPTION_DIR`, owner-only, mounted read-only into the node. With a cloud key service (AWS KMS, Azure Key Vault, GCP KMS), `kms v2` is the stronger choice.
- **Longer leader-election leases** for the scheduler and controller-manager (60 s lease, 45 s renew, instead of 15 s/10 s). On 2026-10-04 slow etcd writes made both restart 16–17 times. A single control plane has no other instance to hand over to, so riding out a stall is better than restarting. etcd's own [tuning guide](https://etcd.io/docs/v3.6/tuning/) also recommends top disk priority for etcd (`ionice -c2 -n0`).
- **Verified on a throwaway cluster:** read raw from etcd, a new Secret starts with `k8s:enc:secretbox:v1:key1`, and its value doesn't appear in plain text; through the API it reads normally. Note: kind renders kubeadm `v1beta3`, so `extraArgs` in the template is a map, not a list.

### Pod Security Standards

Namespace `apps` warns on anything that breaks **Baseline** and audits **Restricted** (`cluster/namespaces.yaml`). It doesn't enforce yet. A dry run against the running services (`kubectl label --dry-run=server ns apps pod-security.kubernetes.io/enforce=baseline`) lists the remaining Baseline exceptions, all from deliberate features:

- **`hostPort`:** the localhost ports, matching Compose's `127.0.0.1:<port>`.
- ~~**`hostPath`:** Immich's, Jellyfin's and Nextcloud's host folders~~. Since 2026-10-04 these are **local PersistentVolumes** ([Kubernetes: local volumes](https://kubernetes.io/docs/concepts/storage/volumes/#local)): StorageClass `host` (no provisioner, `Retain`, so deleting a claim never touches the folder), one static PV per folder, bound to nodes labelled `homeserver/host-folders=true` (set by `cluster.py install` on kind; on a real cluster, label the machine that has the folders). The path and read-only flag are unchanged. Applies on their next apply.
- **Host network and capabilities:** Beszel's agent. The usual practice is a separate, privileged namespace for such agents.

**Restricted** additionally needs non-root users and all capabilities dropped, which most images here (starting as root) don't support.

### Network policies (design for phase 4)

**Why:** today any pod can open a connection to any other, including every database. Under Compose that's the same, since everything shares the `homeserver` network. For a firm this is the most valuable isolation: a compromised app shouldn't reach another app's database.

**Verified first (2026-10-04):** kind's network plugin, kindnet, enforces `NetworkPolicy` through the Kubernetes SIG project [kube-network-policies](https://kube-network-policies.sigs.k8s.io/docs/) ([kindnet docs](https://kindnet.sigs.k8s.io/docs/user/network-policies/)). A scratch test reached a pod before a deny-all ingress policy and was blocked after it.

**Design**, generated from Compose and `.env` like everything else:

1. **Default deny ingress** for every pod in `apps` ([Kubernetes: default policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/#default-policies)). Ingress only at first; egress policies come later, because they also have to allow DNS and every external API each app calls.
2. **Within a service:** its own pods may talk to each other (app ↔ its database and cache), using the `homeserver/service` label.
3. **From the router:** Traefik (namespace `infra`) and the edge may reach the ports the service's routes use.
4. **Shared servers:** `shared-postgres` and `shared-mariadb` accept connections only from the services that declare `shared_db` in `services.json`.
5. **Cross-service endpoints:** every `.env.example` `HOST`/`PORT` pair or `host:port` that names another service (e.g. `MAIL_HOST=mailpit` + 1025, Authentik for logins) becomes an allow rule, the same mapping the endpoint test already checks.
6. **Watchers:** the landing page's health checks and Uptime Kuma may reach every web port; Beszel's hub may reach its agent.
7. **Operators:** CloudNativePG and mariadb-operator may reach their database pods (status and replication ports).
8. **Localhost ports:** traffic arriving through the node (kind port mappings, `hostPort`) is allowed for the published ports only.

**Built (2026-10-04)** in `generate.py` (`network_policy`), one `networkpolicies.yaml` per service, with every rule **scoped to ports**. A service's own database pods share its label, so a rule meant for the web page must not open the database port:

| Allowed into service S from | Ports |
|---|---|
| S's own pods (app ↔ its database and cache) | all |
| Traefik, the local-access proxy, the watchers (landing, Uptime Kuma, the Browser Hub) | S's web ports: its routes plus the ports Compose publishes |
| Each service whose `.env.example` or Compose `environment` names S (`MAIL_HOST=mailpit`, `TEMPORAL_ADDRESS=temporal:7233`, …) | exactly those ports |
| Shared Postgres / MariaDB: only the apps declaring `shared_db` | 5432 / 3306 |
| The database operators (CloudNativePG, mariadb-operator) | all (status checks, replication) |
| Notification sinks (Mailpit, ntfy) from any app, since apps also configure them in their own UIs | delivery port only (1025 / 80) |
| cloudflared → the edge | 80 |

Kubelet health probes stay allowed: verified, a pod under a deny-all policy stayed ready. A test checks every service has its policy and every endpoint is allowed on its port. Writing them surfaced a hardcoded address: Airflow's example DAG called `temporal:7233` directly, against the rule that Temporal clients use Temporal's environment configuration. It now uses `TEMPORAL_ADDRESS` from `.env`. The policies take effect when each service is next applied; the per-tier smoke tests and the CORE rollout verify that nothing legitimate is blocked.

### Decisions for phase 4 (2026-10-04)

| Question | Decision | Why |
|---|---|---|
| Localhost ports | One local-access proxy | Same `localhost:<port>` URLs as Compose; apps can enforce Pod Security Baseline |
| ArgoCD's git branch | `revision` in `kubernetes/deploy/<env>.yaml`; `feature/k8s-generated` now, `develop` after the merge | No rework when the branch changes |
| What decides which services run | **Git:** the `running` list in `kubernetes/deploy/<env>.yaml`, applied by ArgoCD (Step 5) | Easy to switch clusters or clouds: everything, including what runs, comes from the repo |
| Secrets | **External Secrets Operator** with an in-cluster store filled from `.env` (Step 3) | Nothing secret in the public repo; switching to a cloud secret manager changes only the store |
| Observability | Generated from Compose; Alloy reads pod logs through the API, Prometheus the kubelets' cAdvisor (`docs/services/observability.md`) | Same setup as Compose, with Grafana's recommended log source |
| Dagster | Its official Helm chart, the code built into the image (`docs/services/dagster/dagster.md`) | Dagster's documented Kubernetes way; also Dagster+'s |
| CrowdSec | Removed from Docker and Kubernetes | The owner's call (it was detection-only, with no bouncer) |
| `down` takes a backup (Compose) | Becomes scheduled backups plus CloudNativePG's continuous WAL archive (phase 5) | A git commit can't run a backup first; WAL restores to any point in time, not only to the last `down` |
| Network policies | Ingress first; egress later | Kubernetes' documented starting point; egress has to list every app's external calls |

### Follow-ups after all phases

- **Egress network policies:** restrict outgoing traffic per app (DNS, the external APIs each app calls, mail, update checks).
- **Beszel's agent in its own privileged namespace,** so `apps` can enforce Baseline.
- **etcd disk priority** (`ionice`) and a faster, separate disk for kind's image store.
- **The remaining hardening items:** image scanning, Cloudflare Access/WAF, Authentik two-factor, Docker socket proxy.

## Step 5 — Start services by tier, like `homeserver.py`

What runs is in git, one file per environment, `kubernetes/deploy/<env>.yaml`:

```yaml
repo: https://github.com/rajubhimani/homeserver.git
revision: feature/k8s-generated   # the branch ArgoCD follows
running: [min, core]              # targets as homeserver.py takes them
stopped: []                       # services taken out of a running target
auto_sync: false                  # true: ArgoCD applies every push by itself
```

Every ported service is **deployed stopped**. Its config, volumes and databases exist (`generated/apps/<svc>`: 0 replicas, Postgres hibernated, Jobs suspended), and the environment's overlay (`generated/envs/<env>/<svc>`) switches it on when the list includes it. Shared Postgres/MariaDB are on whenever a running service uses them.

`k8s.py` edits the list with `homeserver.py`'s meanings and re-renders `generated/`:

```bash
uv run kubernetes/k8s.py up core --env test        # MIN + CORE ('up core' implies MIN)
uv run kubernetes/k8s.py down jellyfin --env test  # recorded under stopped: while core runs
uv run kubernetes/k8s.py down core --env test      # only CORE; MIN keeps running
uv run kubernetes/k8s.py status --env test         # git's list next to what the cluster runs
git add kubernetes/deploy kubernetes/generated && git commit -m "k8s: ..." && git push
```

Nothing changes in the cluster until the push. Then ArgoCD applies it: by itself with `auto_sync: true`, otherwise with **Sync** in its UI. A test checks the overlays match the list.

## Step 6 — ArgoCD and Headlamp

`cluster.py bootstrap --env <env>` is the only manual install. It:

1. installs ArgoCD from its pinned manifest;
2. fills the secret store (Step 3);
3. applies `generated/gitops/<env>`.

From then on ArgoCD installs and updates everything from git, itself included. Versions come from `kubernetes/versions.env`, and the add-on list is `kubernetes/cluster/addons.yaml`:

| ArgoCD Application | What | From |
|---|---|---|
| `root` | the folder below (app of apps) | `generated/gitops/<env>` |
| `argocd` | ArgoCD itself, its UI behind Traefik (`server.insecure`, as ArgoCD's ingress docs say for a TLS-terminating proxy) | pinned `install.yaml` |
| `gateway-api`, `cluster-base` | Gateway API CRDs; namespaces and storage classes | pinned release; `kubernetes/cluster/base` |
| `traefik`, `cloudnative-pg`, `mariadb-operator(-crds)` | router and database operators | Helm charts |
| `external-secrets`, `reloader` | secrets (Step 3) | Helm charts |
| `headlamp`, `ops-routes` | Kubernetes web UI; the two UIs' routes | Helm chart; generated |
| one per service (ApplicationSet `services`) | `generated/envs/<env>/<svc>` | generated |

**Safety built in:**
- **Two ArgoCD projects.** Services (`homeserver`) may deploy only to `apps`, `local-access` and the secret store's namespace, plus three cluster-wide kinds (Namespace, PersistentVolume, ClusterSecretStore). The project is fixed in the ApplicationSet, never templated (ArgoCD's ApplicationSet security note). Add-ons use `platform`.
- **Data is never deleted by ArgoCD.** Volumes, PersistentVolumes and database objects carry `Prune=false,Delete=false`. Deleting the ApplicationSet keeps every service's objects (`preserveResourcesOnDeletion`).
- **`auto_sync` starts off,** so the first sync is reviewed in the UI before anything changes.

**The UIs (only on this machine, never on the public domain):**
- **ArgoCD:** `http://argocd.k8s.local:18080`, user `admin`. `bootstrap` prints the command that shows the first password.
- **Headlamp:** `http://headlamp.k8s.local:18080`. Sign in with a token from `kubectl -n headlamp create token headlamp`.

Add both names to `/etc/hosts`.

**Logs (Grafana + Loki)** come with the observability port (`docs/services/observability.md`, "On Kubernetes"). CrowdSec was removed from the stack on 2026-10-04, from Docker and Kubernetes alike.

**Status (2026-10-04):** written and tested offline: generator tests, and every folder renders with `kubectl kustomize`. The first `bootstrap` happens at the next cluster rebuild, together with encryption at rest. The current cluster was installed by the old `install` command (CloudNativePG from its manifest), so a Helm-installed second copy can't be added on top of it.
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

Use `--live-db` when the newest snapshot is older than the data you want.

**Rebuilding the cluster, keeping its data** (for changes kind applies only at creation: encryption at rest, new node ports or host folders):

```bash
uv run kubernetes/cluster.py export --env prod      # every running service -> K8S_EXPORT_PATH/<timestamp>/
uv run kubernetes/k8s.py down cloudflared --env prod && git commit -am "k8s: tunnel off for the rebuild" && git push
uv run kubernetes/cluster.py delete
uv run kubernetes/cluster.py create
uv run kubernetes/cluster.py bootstrap --env prod   # ArgoCD starts the running list with empty data
uv run kubernetes/cluster.py import --env prod --from-export /mnt/mydata/k8s-data/export/<timestamp>
uv run kubernetes/k8s.py up cloudflared --env prod && git commit -am "k8s: tunnel back on" && git push
```

**The tunnel stays off until the data is back.** Between `bootstrap` and `import` the apps run empty, and a fresh app often lets its first visitor create the admin account (Authentik's initial setup, for one). Taking cloudflared out of the running list first keeps those pages unreachable from the internet.

`export` takes a `pg_dump`/`mariadb-dump` of each database the service uses (its own, or its databases on the shared servers), consistent while it runs. It also takes a tar of each data volume, with the service briefly stopped. Host folders (Immich's photos, Jellyfin's media) are left in place. `import --from-export` unpacks the volumes and restores each database as the app's own login. `export` stops, without deleting anything, if any dump fails. **Seen on 2026-10-03:** Authentik's newest snapshot came from right after a `reset`, so it held a blank Authentik; the live database had the applications and users.

**Localhost ports work like under Compose,** served by **one local-access proxy** (decided 2026-10-04) rather than a `hostPort` on every app. The proxy is a small nginx in namespace `local-access` (`generated/apps/local-access`). Its `stream` module forwards each port Compose publishes (`127.0.0.1`, plus the `10.8.0.1` VPN mirror) at the TCP level to the app's Service, so web, SSH and TLS all work, and it resolves names per connection, so services that aren't running don't stop it. Only this pod holds host ports, so namespace `apps` can meet Pod Security Baseline (which forbids `hostPort`). The proxy's ports:

- **On a cluster that runs on your machine** (k3s, kubeadm…), `localhost:8088` answers directly.
- **On kind**, the node is a container, so the generator also writes NodePort Services and `generated/host-ports.yaml`, and `cluster.py create` binds each port on `127.0.0.1` with kind's port mappings. kind adds mappings only at creation, so a newly ported service needs a rebuild for its port; its `*.<domain>` route works without one.
- **nginx-plain's** `8180`/`8443` go to Traefik, which does its job here.
- **Host-network containers** (wg-easy) listen on the node directly. A `node_ports` entry in the override forwards a port from every host address (WireGuard's UDP 51820).

Kubernetes' guidance is to avoid `hostPort` unless needed. Matching Compose's localhost ports on one machine is that need, and those Deployments use the `Recreate` strategy, because two pods can't hold the same host port at once.

**Big media folders are mounted, not copied** (`hostPath` + `env` in the override). `cluster.py create` mounts the path from the service's `.env` into the kind node; kind can only add mounts at creation, so adding one means rebuilding the cluster.

| Folder | Mounted | Why |
|---|---|---|
| Jellyfin `MEDIA_ROOT` | read-only | Compose mounts it read-only too |
| Nextcloud `OS_ISO_ROOT` | read-write in `nextcloud`, read-only in `nextcloud-cron` | Exactly Compose's mounts (the read-only flag comes from Compose's `:ro`; the node mount is writable if any container writes) |
| Immich `UPLOAD_LOCATION` | **read-write** | Immich refuses to start unless it can write its `.immich` check files |

**Immich shares your real photo folder, and Compose snapshots don't include it** (only Immich's database). Before testing Immich on Kubernetes:

- Have your own copy of the photo folder, for example on the Passport.
- Stop Compose's Immich first, so two Immichs never use the folder at once.
- Don't upload or delete photos on the Kubernetes side.

`immich-offline-remover` doesn't run on Kubernetes, so a test never removes library entries. Back on Docker, `restore immich` brings back the database. The photo folder is the same one, with at most some new thumbnails.

Logins: protected hostnames (nginx-plain's `auth_request`, e.g. `browser.`) keep the Authentik sign-in through Traefik's ForwardAuth middleware, as in [Authentik's Traefik guide](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_traefik/). The same Authentik providers work unchanged.
### Running the real-data window

How it ran on 2026-10-03/04, in this order:

1. **Fresh snapshots on Docker.** `uv run homeserver.py prod backup <svc...>` stops each service (taking a snapshot) and starts it again. Snapshots can be older than the data: check the date, or use `--live-db`.
2. **Serving your real domain from the cluster.** The Cloudflare tunnel's hostnames point at `http://nginx-plain:80` (set on Cloudflare's dashboard). On the cluster, a Service of that name points at Traefik, so the tunnel works unchanged. **Never run the tunnel in both places at once**, or Cloudflare splits traffic between them:
   ```bash
   uv run kubernetes/cluster.py secrets --env prod      # the store, with the tunnel token
   uv run homeserver.py prod down cloudflared           # Docker's tunnel off first
   uv run kubernetes/cluster.py bootstrap --env prod    # ArgoCD follows kubernetes/deploy/prod.yaml (real domain + tunnel)
   ```
3. **Stop Docker's services** that the cluster will run (`homeserver.py prod down <svc...>`, which snapshots them), so two copies never share a host folder, a host port or memory. For services you just backed up, add `--no-backup`.
4. **Bring services up in batches**, the light ones first and the heavy ones (Jellyfin, Nextcloud, Immich, OnlyOffice, ClamAV, Plausible) one at a time: `secrets`, `apply` (today: add them to the `running` list a few at a time), wait for the database and volumes, then `import`. Pulling and unpacking large images saturates an HDD, and containerd times out under that load.
5. **Before Immich starts,** count its trash: `kubectl -n apps exec immich-db-1 -c postgres -- psql -d immich -tAc 'select count(*) from asset where "deletedAt" is not null'`. With 0, the nightly trash-empty job has nothing to delete in the shared photo folder.

Things found during the window, all fixed in the generator or the services themselves:
- Nextcloud logged in as an installer-made `oc_admin` role; it now reads its database login from `.env` (`docs/services/nextcloud.md`).
- Mailpit's SMTP port wasn't declared, so mail sends timed out on Kubernetes (`docs/services/mailpit.md`).
- Images' own `HEALTHCHECK`s are ignored by Kubernetes; they're now carried as probes.
- Authentik's chart probes need their 3 s timeout.

## Step 9 — Going back to Docker

Changes made on the cluster don't flow back: Docker restarts from its own data, as it was when you stopped it.

```bash
uv run kubernetes/cluster.py delete       # frees the tunnel, the localhost ports and UDP 51820; host folders are kept
uv run homeserver.py prod up core         # starts MIN + CORE again (cloudflared, wg-easy and Jellyfin included)
uv run homeserver.py status
```

- **Delete the whole cluster, not just its tunnel.** kind holds the same `127.0.0.1` ports (and WireGuard's UDP 51820) that Docker needs.
- **Docker's databases and volumes were never touched.** `down` keeps them, and `up` starts from them, so no restore is needed.
- **Immich:** the photo folder is shared. At most it has new thumbnails from the cluster, which Docker's Immich ignores or regenerates.
- **Nextcloud:** from its next start under Docker it logs in with `.env`'s `POSTGRES_USER` (`config/db.config.php`) instead of `oc_admin`. That's intended; check `curl -s localhost:8081/status.php` after the start.
- **Want the cluster's changes on Docker?** That's a migration in the other direction (dump from CloudNativePG, `homeserver.py restore`), not part of this test.

## Real client IPs behind the Cloudflare tunnel (decision, 2026-10-04)

**The problem.** Requests reach the cluster as visitor → Cloudflare → cloudflared (a pod) → Traefik → app. Traefik sets `X-Real-IP` to whoever connected to it, which is always the cloudflared pod. A visitor's own `X-Forwarded-For` survives, with Cloudflare appending the real address *without a space* (`fake,real`). So apps reading `X-Real-IP` logged the tunnel pod, and Forgejo (which reads `X-Real-IP` first, then splits `X-Forwarded-For` only on `", "`) could be fooled by a crafted header. Under Docker, nginx-plain avoided both by **overwriting** `X-Real-IP` and `X-Forwarded-For` with `CF-Connecting-IP`.

**What the sources say** (researched 2026-10-04):

| Source | Finding |
|---|---|
| [Cloudflare: restoring visitor IPs](https://developers.cloudflare.com/support/troubleshooting/restoring-visitor-ips/restoring-original-visitor-ips/) | Restore at the origin from `CF-Connecting-IP`; for nginx use `ngx_http_realip_module` (`real_ip_header CF-Connecting-IP`) |
| [Cloudflare: request header Transform Rules](https://developers.cloudflare.com/rules/transform/request-header-modification/) | **Can't** set `x-real-ip`, `x-forwarded-for`, `true-client-ip` or `x-forwarded-proto` at the edge |
| Traefik source (`pkg/middlewares/forwardedheaders/forwarded_header.go`, v3.7) | Keeps an incoming `X-Real-Ip` only from a trusted sender, otherwise sets it to the connecting address; no option to use `CF-Connecting-IP` |
| [Traefik docs: entrypoints](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/), [forum](https://community.traefik.io/t/x-real-ip-header-wrong/28294) | Only "trust forwarded headers" (`forwardedHeaders.trustedIPs`); no built-in `CF-Connecting-IP` handling |
| Traefik plugins (GitHub, checked 2026-10-04) | BetterCorp/cloudflarewarp (98★) **archived**; Paxxs/traefik-get-real-ip 87★, 1 maintainer; PseudoResonance/cloudflarewarp 24★; jramsgz/traefik-real-ip 7★; kubitodev/traefik-cloudflared-source-ip 2★, untouched since 2023 |
| [Envoy Gateway ClientTrafficPolicy](https://gateway.envoyproxy.io/docs/tasks/traffic/client-traffic-policy/) (API: `clienttrafficpolicy_types.go`) | First-class `clientIPDetection.customHeader: CF-Connecting-IP`, but it doesn't set `X-Real-IP` for apps, and it means replacing Traefik |
| [Community issue](https://github.com/helmcode/nan/issues/114) | Anything that reaches the router directly (bypassing the tunnel) can fake `CF-Connecting-IP`; trust it only on the tunnel path |
| Forgejo (`chi-middleware/proxy`, `middleware.go`) | Reads `X-Real-IP` first; walks `X-Forwarded-For` from the right, `REVERSE_PROXY_LIMIT` hops, splitting on `", "` |
| Vaultwarden (`src/auth.rs`) | Takes the *first* entry of `IP_HEADER`, so `X-Forwarded-For` is fakeable there; `CF-Connecting-IP` isn't |

**Options considered:**

| Option | Secure | Reliable | Best practice | Verdict |
|---|---|---|---|---|
| **Edge nginx in front of Traefik**, setting `X-Real-IP` and `X-Forwarded-For` from `CF-Connecting-IP`, as nginx-plain does | Yes: overwrites the visitor's headers, and only the tunnel reaches it | High: the official nginx image | Cloudflare-documented method; identical to the Docker setup | **Chosen** |
| Traefik real-IP plugin | Yes, if it overwrites | Medium-low: small single-maintainer projects, the original archived | Community only | Rejected |
| Switch the Gateway to Envoy Gateway | Partly: no `X-Real-IP` for apps | High | Official API | Rejected: replaces the router for one feature |
| Per-app settings only | No: Forgejo stays fakeable | Medium | Each app's docs | Kept as defence in depth (Vaultwarden `CF-Connecting-IP`, Forgejo `[security]`, Nextcloud `remoteip`) |

**Result (verified 2026-10-04 on kind, a failed login or request through the tunnel with a faked `X-Forwarded-For: 6.6.6.6`):**

| Service | Records the real IP? | How |
|---|---|---|
| Authentik, Firefly, Firefly importer, Immich, Guacamole, Nextcloud (app and Apache log), Forgejo, Vaultwarden, Jellyfin, ntfy, docs, landing, IT-Tools | ✅ never the fake | edge + each app's trusted-proxy setting (`docs/services/<svc>.md`, "Real client IPs") |
| Plausible | ✅ | reads `CF-Connecting-IP` itself |
| Beszel, Uptime Kuma | ⚠️ the proxy, until set once in the app's UI | PocketBase *User IP proxy headers* = `X-Real-IP`; Uptime Kuma *Trust Proxy* = on |
| AdGuard | ✅ on kind | `trusted_proxies` + `10.0.0.0/8` (YAML) |
| Atuin | — | records no client IPs |

**Rule for the future:** check every app that records or acts on a visitor IP with a failed login through the tunnel **and** a faked `X-Forwarded-For`. It must log the real address, never the fake one or a cluster address.

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
