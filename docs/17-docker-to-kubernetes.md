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

## Step 3 — Secrets from your `.env` files *(coming in phase 2)*
## Step 4 — Databases: shared and own *(coming in phase 2)*
## Step 5 — Start services by tier, like `homeserver.py` *(coming in phase 3–4)*
## Step 6 — ArgoCD, Headlamp and logs *(coming in phase 4)*
## Step 7 — Backups: `down` backs up, `restore` brings it back *(coming in phase 5)*
## Step 8 — Testing with your real data (planned window) *(after phase 3)*
## Step 9 — Going back to Docker *(written with step 8)*
