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

Check:

```bash
kind version            # kind v0.33.0 ...
kubectl version --client
helm version
```

On macOS, use the `darwin-arm64`/`darwin-amd64` downloads, or `brew install kind kubectl helm` (then check the versions match `versions.env`). On Windows, use WSL2 and follow the Linux steps.

## Step 1 — Generate the Kubernetes manifests *(coming in phase 1)*
## Step 2 — Create the test cluster *(coming in phase 1)*
## Step 3 — Secrets from your `.env` files *(coming in phase 2)*
## Step 4 — Databases: shared and own *(coming in phase 2)*
## Step 5 — Start services by tier, like `homeserver.py` *(coming in phase 3–4)*
## Step 6 — ArgoCD, Headlamp and logs *(coming in phase 4)*
## Step 7 — Backups: `down` backs up, `restore` brings it back *(coming in phase 5)*
## Step 8 — Testing with your real data (planned window) *(after phase 3)*
## Step 9 — Going back to Docker *(written with step 8)*
