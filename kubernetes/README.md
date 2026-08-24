# kubernetes/ — parallel Kubernetes experiment

A separate, parallel setup to the Docker Compose stack that makes up the rest
of this repo — not a replacement for it. The compose stack keeps running
as-is; this folder is where the same services get ported to Kubernetes
manifests, one at a time, to validate the pattern before committing to a
full migration.

## Prerequisites

Four tools, on whatever machine will run the cluster: **Docker** (or
Docker Desktop on Windows/Mac — `kind` needs a real running daemon),
**kind**, **kubectl**, and **helm**. `apply-secrets.py` needs `uv` (this
repo already requires it — see the root `CLAUDE.md`) but not a system
`openssl`: Documenso's self-signed cert is generated with Python's
`cryptography` package instead (ephemeral-installed via `uv run --with`,
same as `bcrypt_hash()`'s ArgoCD-password step) — see that script's
`generate_documenso_cert()` for why plain `openssl pkcs12` can't be used
here (Documenso needs an old PKCS12 encryption scheme OpenSSL 3.x moved
behind a "legacy" provider that isn't always installed, especially on
Windows). Pick your OS below; all four should print a version afterward
(`docker version`, `kind version`, `kubectl version --client`, `helm
version`) before moving on to "Cluster" below.

<details>
<summary><strong>Windows</strong></summary>

`winget` is built into Windows 10/11 — no extra installer needed:

```powershell
winget install Docker.DockerDesktop
winget install Kubernetes.kind
winget install Kubernetes.kubectl
winget install Helm.Helm
```

Launch Docker Desktop and wait for it to report "running" before using
`kind`. Close and reopen your terminal afterward so `PATH` picks up the
new binaries. Chocolatey works too if you already use it:
`choco install kind kubernetes-cli kubernetes-helm`.

This pilot was originally built and tested on a Windows/Docker-Desktop box
— see `kubernetes/TROUBLESHOOTING.md`'s "Cluster / Docker Desktop" section
for real gotchas already hit there (no host filesystem passthrough into
`kind` nodes, how Docker Desktop's `LoadBalancer` auto-exposure differs
from plain `kind`'s).
</details>

<details>
<summary><strong>Fedora</strong></summary>

Fedora doesn't ship `docker-ce` in its default repos — add Docker's own:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # log out/in (or `newgrp docker`) for this to take effect

# kind — check https://github.com/kubernetes-sigs/kind/releases for a newer tag
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/kubectl

# helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

This pilot's real, current target host (see "Cluster" below).
</details>

<details>
<summary><strong>Ubuntu / Debian</strong></summary>

```bash
# Docker Engine — Docker's own apt repo, not Ubuntu's bundled docker.io package
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"   # log out/in (or `newgrp docker`) for this to take effect

# kind — check https://github.com/kubernetes-sigs/kind/releases for a newer tag
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/kubectl

# helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```
</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
brew install --cask docker   # Docker Desktop for Mac
open -a Docker               # launch it, wait until it reports "running"
brew install kind kubectl helm
```
</details>

## Cluster

Originally built on a Windows/Docker-Desktop box (Settings → Kubernetes →
enable → kind provisioning). This branch has since moved to its intended
target — a real Linux (Fedora) host — using plain `kind` directly rather
than Docker Desktop's bundled integration.

**`kubernetes/bootstrap.py` runs the whole first-time setup**, one-shot,
idempotent (re-running after a partial failure only redoes what's
actually missing — same "don't re-touch what's already there" idiom
`homeserver.py`'s own `up core` has):

```bash
uv run kubernetes/bootstrap.py
# or, to run apply-secrets.py yourself later (e.g. after sync-env-from-compose.py):
uv run kubernetes/bootstrap.py --skip-secrets
```

**What it actually does, in order:**

1. Checks docker/kind/kubectl/helm are on PATH and the Docker daemon is reachable.
2. Creates the `kind-cluster` kind cluster from `kubernetes/kind-config.yaml` (1 control-plane + 3 workers) — skipped if it already exists.
3. Installs the Gateway API CRDs — **v1.6.1, standard channel** (`Gateway`/`HTTPRoute`/`GatewayClass`/`ReferenceGrant`/`BackendTLSPolicy`/`TLSRoute`/`TCPRoute`/`UDPRoute`/`GRPCRoute`; no experimental channel needed — as of v1.6.1 everything Traefik's Gateway provider watches has graduated to standard). Version matters here, not just channel: Traefik's Gateway provider needs `BackendTLSPolicy`/`TLSRoute`, and an older CRD set (this pilot was previously pinned at v1.2.1, standard channel only) doesn't have them at all — that doesn't just skip a feature, it stops Traefik's informers from ever syncing, so it never claims its `GatewayClass` and every `Gateway` sits stuck at `Programmed: Unknown, "Waiting for controller"` forever (see `kubernetes/TROUBLESHOOTING.md`'s Gateway API section).
4. Applies the namespaces (`argocd`, `apps`, `data`, `infra`, `metallb-system`) — `argocd` has to exist before ArgoCD can be installed into it.
5. Installs ArgoCD (server-side apply, its CRDs are too large for client-side), waits for it to become available.
6. Detects this machine's `kind` Docker-network subnet and rewrites `kubernetes/cluster/metallb/resources/ipaddresspool.yaml` to match it.
7. Applies the 6 cluster-level ArgoCD Applications (namespaces/gateway/traefik/metallb/postgres-shared/mariadb-shared) — ArgoCD then brings up Traefik, MetalLB, and the two shared DB servers on its own.
8. Exposes ArgoCD's UI over plain HTTP as a LoadBalancer Service on port `18081` — **not** `http://localhost:18081`, that only worked back when this pilot ran on Docker Desktop's kind integration (which auto-publishes LoadBalancer ports to real `localhost`); on plain `kind` it gets a MetalLB-assigned IP instead, same as every other service (see "LAN access" below). Find it with `kubectl get svc -n argocd argocd-server-lan` (EXTERNAL-IP column) once the restart finishes.
9. Runs `apply-secrets.py`, which creates `kubernetes/.env` from `.env.example` first if it doesn't exist yet, and auto-generates (format-aware — exact byte length, hex vs. base64, Laravel's `base64:` prefix, Fernet's padded urlsafe-base64, etc., matching each key's own `.env.example` comment) a real value for every key still holding a placeholder — persisted back into `kubernetes/.env`, so it's stable across reruns, not regenerated each time. Nothing to fill in by hand for a fresh cluster. The one exception: `TUNNEL_TOKEN` is a real Cloudflare-issued credential nothing here can invent, so it's left for you and this step fails clearly if it's still unset.
10. Applies every remaining per-service ArgoCD Application (`kubernetes/argocd-apps/*.yaml`).

**What it deliberately does *not* do:** pull any secret from the Compose
stack, scale any service up (min/core come up on their own — they're
committed at `replicas: 1`; everything else stays at `0` until you scale
it, see "Starting/stopping services" below), or copy any database data.
**Run these next**, in this order — see "Migrating data from Compose"
below for why the order matters:

```bash
uv run kubernetes/sync-env-from-compose.py     # pull real secrets from services/*/.env into kubernetes/.env
uv run kubernetes/apply-secrets.py             # push them into the cluster, auto-generating anything still unset (safe to re-run)
uv run kubernetes/k8s.py up <tier-or-service>  # scale up whatever you want running (min/core are already up)
uv run kubernetes/migrate-db.py --all          # copy each service's Postgres/MariaDB data from Compose into k8s
```

What `bootstrap.py` runs step by step, if you'd rather do any of it by
hand or are debugging a failure:

```bash
kind create cluster --config kubernetes/kind-config.yaml
kubectl config current-context   # should print: kind-kind-cluster
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml
kubectl apply -f kubernetes/cluster/namespaces.yaml
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.0/manifests/install.yaml --server-side --force-conflicts
# fix kubernetes/cluster/metallb/resources/ipaddresspool.yaml's range to match
# this Docker network (docker network inspect kind), commit it
kubectl apply -f kubernetes/argocd-apps/cluster-namespaces.yaml
kubectl apply -f kubernetes/argocd-apps/cluster-gateway.yaml
kubectl apply -f kubernetes/argocd-apps/cluster-traefik.yaml
kubectl apply -f kubernetes/argocd-apps/cluster-metallb.yaml
kubectl apply -f kubernetes/argocd-apps/cluster-postgres-shared.yaml
kubectl apply -f kubernetes/argocd-apps/cluster-mariadb-shared.yaml
kubectl patch cm argocd-cmd-params-cm -n argocd --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deployment argocd-server -n argocd
kubectl apply -f kubernetes/cluster/argocd/lan-service.yaml   # UI's real address: kubectl get svc -n argocd argocd-server-lan (NOT localhost — see "LAN access" below)
uv run kubernetes/apply-secrets.py
kubectl apply -f kubernetes/argocd-apps/   # every remaining service Application
```

Topology: 1 control-plane + 3 workers (`kubernetes/kind-config.yaml` — see
that file's own comment for why it's 1 control-plane, not 2: etcd quorum
needs an odd member count, and 2 is strictly worse than 1). `kubectl`
points at it via the `kind-kind-cluster` context.

## Migrating data from Compose

The 4-command sequence for this (`sync-env-from-compose.py` →
`apply-secrets.py` → `k8s.py up` → `migrate-db.py`) is listed under
"Cluster" above, right after what `bootstrap.py` does and doesn't cover.
This section is about *why* that order matters and exactly what
`migrate-db.py` does and doesn't move.

**Why the order matters for logins specifically:** several apps use
their own app-level secret to encrypt columns in their own database —
Firefly's `APP_KEY`, Documenso's encryption keys, Outline's
`SECRET_KEY`, NocoDB's JWT secret, and others. If `migrate-db.py` runs
before `sync-env-from-compose.py`/`apply-secrets.py`, the k8s side gets
the right *rows* encrypted with the wrong *key* — the app comes up but
can't decrypt its own data, including stored sessions/credentials. Doing
`sync-env-from-compose.py` → `apply-secrets.py` first means both sides
hold the same key before any encrypted data crosses over, so decryption
(and logins) works the same in k8s as it did in Compose. Plain password
hashes (most app login tables) aren't affected either way — they migrate
fine regardless of order — but there's no reason not to always do it in
this order.

`migrate-db.py` streams a `pg_dump`/`mariadb-dump` from the Compose
container straight into a `psql`/`mariadb` on the k8s side (via `docker
exec` piped to `kubectl exec`, nothing written to disk in between) —
into the service's dedicated StatefulSet if it has one, or the right
database on the shared Postgres/MariaDB server if it was onboarded onto
one (same detection either way: is there a `kubernetes/apps/<service>/
db-init-job.yaml`?). It's Postgres/MariaDB only: RocketChat's MongoDB
replica set needs `mongodump`/`mongorestore` by hand instead, and
**bind-mounted files are never copied** — Nextcloud's uploaded files,
Immich's photos, Jellyfin's media, wiki attachments, and so on all live
under `service_data/data/<service>/` at a different path per service,
so there's no single generic "copy this into that PVC" that's safe
across all of them; migrate those by hand per service if you need them
in k8s too (`kubectl cp` into the matching pod once its PVC is mounted).

## What's installed

| Component | Namespace | Purpose |
| --- | --- | --- |
| Traefik (Gateway API mode) | `infra` | Routes all services behind one entry point — the k8s equivalent of `nginx-plain`'s `server_name` blocks. `ingress-nginx` is deprecated (no releases/security fixes since March 2026), so this uses Gateway API (`Gateway`/`HTTPRoute`) instead of classic `Ingress` objects. |
| ArgoCD | `argocd` | GitOps — syncs cluster state to match what's in this folder on git. |
| MetalLB | `metallb-system` | Gives every `type: LoadBalancer` Service a real, reachable IP. Needed because this now runs on plain `kind`, which — unlike Docker Desktop's bundled kind — has no built-in LoadBalancer support. L2 mode, address pool carved from kind's own Docker bridge subnet. See `kubernetes/cluster/metallb/`. |
| Shared Postgres | `data` | Provisioned for services that don't need their own dedicated instance. Onboarded so far: `airflow`, `temporal`, `mattermost`, `dagster` (DB only) — each via its own `kubernetes/apps/<service>/db-init-job.yaml`, copied from `kubernetes/cluster/postgres/db-init-job.template.yaml`. Every other Postgres-backed service predates this convention and still runs its own dedicated StatefulSet (own version/extensions, e.g. Immich's pgvector and Zulip's vendor image, or just following the established older per-service pattern) — not retrofitted, see "Current status" below for why. |
| Shared MariaDB | `data` | Same story as shared Postgres above — provisioned, ArgoCD-managed, currently unused (BookStack/InvoiceShelf/OrangeHRM/etc. all run their own dedicated MariaDB instead). |
| Kubernetes Dashboard | `apps` | The Portainer-equivalent remote UI (Portainer itself is excluded, see "Not ported, deliberately" below) — start/stop/scale anything from a browser instead of `kubectl`. `cluster-admin` RBAC, gated behind the same `authentik-forward-auth` Middleware as everything else that needs one. Not a Compose service port — new to this pilot, see `kubernetes/apps/dashboard/`. |

LoadBalancer Services get their IP from MetalLB, not `localhost` — see "LAN
access" below for what that actually means for reachability.

## Layout

```
kubernetes/
  kind-config.yaml    # plain-kind cluster topology (1 control-plane + 3 workers)
  cluster/            # cluster-wide infra, not app-specific
    namespaces.yaml
    traefik/
      values.yaml      # Helm values for Traefik
      gateway.yaml      # the one shared Gateway every service's HTTPRoute attaches to
    metallb/
      values.yaml       # Helm values for MetalLB (chart defaults, mostly)
      resources/
        ipaddresspool.yaml     # address range MetalLB hands out — see its own
                                # comment for the docker-network-inspect step
                                # needed after first cluster creation
        l2advertisement.yaml
    postgres/
      statefulset.yaml
      secret.example.yaml         # template only — real Secret via apply-secrets.py
      db-init-job.template.yaml   # copy into apps/<service>/ when onboarding a
                                   # service onto the shared Postgres server
    mariadb/                      # same pattern, for MariaDB-using services
      statefulset.yaml
      secret.example.yaml
      db-init-job.template.yaml
  apps/
    <service>/
      deployment.yaml (or statefulset.yaml)
      httproute.yaml
      lan-service.yaml   # direct LAN-reachable port — see "LAN access" below
      db-init-job.yaml   # only if using the shared Postgres server
  argocd-apps/
    <service>.yaml       # ArgoCD Application manifests, one per service
  .env.example            # template — copy to .env (gitignored) and fill in
  bootstrap.py             # one-time cluster setup, idempotent — see "Cluster" above
  sync-env-from-compose.py # copies real secrets from services/*/.env into kubernetes/.env
  apply-secrets.py         # reads .env, creates/updates the matching k8s Secrets
  k8s.py                   # tier/group/service start-stop — see "Starting/stopping services"
  migrate-db.py             # copies each service's DB from Compose into k8s — see "Migrating data from Compose"
  apply-domain-routes.py    # real-domain HTTPRoute per service — see "Real-domain routing"
```

Hostnames use a `*.k8s.local` suffix (e.g. `excalidraw.k8s.local`) by
default, not the real production domain — every `httproute.yaml`
committed to git stays scoped to local testing only, on purpose (see
"Real-domain routing" below for the opt-in way to reach a service over
your actual domain instead). Test routing locally the same way
`nginx-plain` health checks are tested elsewhere in this repo:

```bash
curl -H "Host: excalidraw.k8s.local" http://localhost:80/
```

## Real-domain routing

By default nothing here is reachable over your real domain — every
`HTTPRoute` only matches `*.k8s.local`. To route your actual domain
(e.g. through the same Cloudflare Tunnel the Compose stack uses) to a
service in this pilot:

1. Add your domain to `kubernetes/.env`:
   ```
   DOMAIN=yourdomain.com
   ```
2. Run:
   ```bash
   uv run kubernetes/apply-domain-routes.py                # every service with an httproute.yaml
   uv run kubernetes/apply-domain-routes.py nextcloud immich # or just specific ones
   ```

This creates a **second** `HTTPRoute` per service (`<service>-domain`,
e.g. `nextcloud-domain`) with your real hostname (`nextcloud.yourdomain.com`),
alongside the existing `*.k8s.local` one — applied directly to the
cluster, not committed to git and not tracked by ArgoCD at all. That's
deliberate: if your domain were baked into the git-managed route
instead, ArgoCD's `selfHeal` would revert it back to `*.k8s.local` on
its next sync since the live object wouldn't match git. A separate,
ArgoCD-invisible object sidesteps that — same "real value never
committed, applied locally at runtime" pattern `apply-secrets.py`
already uses for Secrets. Re-run the script anytime you add a new
service or change your domain; it's idempotent.

**If you're reusing the same Cloudflare Tunnel as the Compose stack**
(same `TUNNEL_TOKEN`, matching that key's own comment in `.env.example`):
Cloudflare Tunnel supports multiple simultaneous connections and load-
balances across all of them, so running both this k8s pilot's
`cloudflared` and Compose's at the same time means requests randomly
land on whichever one — and each only has this cluster's or Compose's
own network reachable. Stop one before testing the other
(`uv run homeserver.py dev down cloudflared` for the Compose side), and
point the tunnel's Public Hostname origin at whichever one you're
testing: `http://cluster-traefik.infra.svc.cluster.local:80` for this
pilot's Traefik (confirm the exact Service name/port for your cluster
with `kubectl -n infra get svc`), or the Compose `nginx-plain` origin
you already had configured, for Compose.

## LAN access (phone, other devices)

Hostname routing above only works from this PC (no hosts-file trick works on
a phone, and AdGuard Home isn't set up as the network's DNS resolver yet —
revisit once it is). Until then, each service also gets a second `Service`
(`type: LoadBalancer`, see `lan-service.yaml`) exposing it on the **exact
same port its `compose.dev.yml` already uses** — same number you already
know, nothing new to learn about which port maps to which service.

**What "exposed" actually means here is different from the original
Docker-Desktop pilot.** Docker Desktop auto-published LoadBalancer Services
on literal `localhost:<port>`. Plain `kind` has no such magic — MetalLB
(see "What's installed" above) hands each Service a real IP instead, from a
pool carved out of kind's own Docker bridge network. Reachable from this
host at `<metallb-assigned-ip>:<port>`, not `localhost:<port>`:

```bash
kubectl get svc -n apps <service>-lan   # EXTERNAL-IP column has the real address
```

If you want literal `localhost:<port>` back, layer a host-side forwarder
(`socat`, or a `kubectl port-forward` run as a systemd unit) on top of the
MetalLB IP per service you actually want that for — additive, no cluster
change needed. See `kubernetes/cluster/metallb/resources/ipaddresspool.yaml`
for why the IP range itself can't be known until after the cluster exists.

**The Compose version of a service must be stopped before porting it** —
same host port, can't have both bound at once:

```bash
uv run homeserver.py dev down <service>
```

Every ported service now has a `lan-service.yaml` — see
[`docs/11-services-reference.md`](../docs/11-services-reference.md) in the
repo root for the full dev-port table (same numbers apply here 1:1). A
handful of examples:

| Service | Port | Matches |
| --- | --- | --- |
| excalidraw | 8116 | `excalidraw/compose.dev.yml` |
| guacamole | 8107 | `guacamole/compose.dev.yml` |
| vaultwarden | 8200 | `vaultwarden/compose.dev.yml` |
| forgejo | 3002 (HTTP), 2223 (SSH) | `forgejo/compose.dev.yml` |

Exceptions: `cloudflared` has no inbound port (outbound tunnel client only —
no Service/HTTPRoute/lan-service at all) and `crowdsec` exposes nothing
(detection-only, matches `docs/11-services-reference.md`'s own "no port
exposed" note).

Gotcha hit once already: editing an existing `LoadBalancer` Service's `port:`
in place does **not** cleanly re-provision the underlying proxy container —
it stays bound to the old port. If a port ever needs to change, delete and
recreate the Service (`kubectl delete svc <name>-lan -n apps` then
re-apply), don't just edit and re-apply.

## Secrets

Same convention as every other service in this repo: `.env` (gitignored,
real values) + `.env.example` (checked in, template). Run
`uv run kubernetes/apply-secrets.py` after editing `.env` to push the values into
the cluster as Secrets. ArgoCD's admin password is a special case — ArgoCD
only accepts a bcrypt hash in its Secret, so the script hashes it (via
`uv run --with bcrypt`, no new project dependency) before patching
`argocd-secret`.

## Starting/stopping services

`kubernetes/k8s.py` mirrors `homeserver.py`'s tier/group/service UX for
this pilot — same `services.json` tiers and `group:<name>` categories,
just driving `kubectl`/ArgoCD instead of Docker Compose:

```bash
uv run kubernetes/k8s.py up   min                # or core/daily/office/automation-ai/extra/manual/all
uv run kubernetes/k8s.py down group:communication # mattermost + rocketchat + zulip
uv run kubernetes/k8s.py up   mattermost          # single service, never prompts
uv run kubernetes/k8s.py status                   # tier-by-tier + group-by-group, ● up / ○ down
uv run kubernetes/k8s.py down core --dry-run       # print what would happen, change nothing
```

A tier keyword, `group:<name>`, or `all` previews the resolved service
list and asks for confirmation (skip with `--yes`/`-y`); a literal service
name never prompts. `--dry-run` resolves the target and prints every
`kubectl`/ArgoCD command it would run without executing any of them — also
how this tool gets verified before a live cluster exists (see "Current
status" below).

**Two tier baselines, self-healing in opposite directions** — `min`/`core`
are committed to git at `replicas: 1` (self-heal **up**: survive a reboot
or full ArgoCD resync on their own, same "always-on core infra" idiom
`homeserver.py`'s `core` tier already has); every other tier is committed
at `replicas: 0` (self-heals **down**: off unless deliberately started,
same "opt-in" idiom as `homeserver.py`'s daily/office/automation-ai/extra/
manual). This means `up`/`down` manage ArgoCD sync in the *opposite*
direction depending which side of that line a service is on — the
mirror-image table below, implemented as `k8s.py`'s `sync_direction()`:

| | `min`/`core` (baseline **on**) | everything else (baseline **off**) |
| --- | --- | --- |
| `up` | enable sync + scale 1 (self-heals to git's 1) | **disable** sync + scale 1 (temporary override — git says 0, so sync must go off first or `selfHeal` reverts the manual scale-up within one cycle) |
| `down` | **disable** sync first, then scale 0 (temporary override — see `TROUBLESHOOTING.md`'s "pausing a service" note for why the order matters) | scale 0 + enable sync (settles back to git's committed 0) |

**A manual override on a baseline-off service is durable, not a fluke.**
Once it's up with sync disabled, `spec.replicas` and the Application's
disabled `syncPolicy` are both persisted control-plane state in etcd, not
process memory — a node/cluster reboot doesn't reset either one. Nothing
clears it except an explicit `k8s.py down <service>` on that exact
service, or manually re-enabling its sync (which snaps it straight back
to git's baseline). `status` flags any service whose live state disagrees
with its tier baseline as `(override)`, so "this is running because
someone turned it on" is visible at a glance instead of just inferred.
PVCs and Secrets are never touched by either `up` or `down` — same "no
data loss, nothing to re-provision on restart" guarantee the manual
procedure always had.

Resources belonging to a service are found by name-prefix matching
(`<service>` or `<service>-<suffix>`) against live `kubectl get
deployment,statefulset,cronjob`, not new labels on every manifest — this
holds for all but two directories (`guacamole`'s companion `guacd`
Deployment, `observability`'s 6 unprefixed Deployments — both handled via
a small `RESOURCE_EXCEPTIONS` map in the script) and correctly
disambiguates `stirling-pdf` from `stirling-pdf-lite` via a
longest-match-wins rule. `Job` resources (one-shot DB init/schema-setup)
are never scaled — they're run-to-completion, not long-running workloads.

There's no backup/snapshot step on `down` here, unlike Compose's automatic
snapshot-on-down — this pilot has no backup mechanism of its own yet.

## Current status

This repo's Compose side was restructured after this pilot was last brought
up to date (tiers renamed/expanded to `min`/`core`/`daily`/`office`/
`automation-ai`/`extra`/`manual`, ~19 new services added — see
[`docs/11-services-reference.md`](../docs/11-services-reference.md) for the
current tier lists). Counts below are against that current tier structure,
not the older `SERVICES_CORE`/`SERVICES_EXTRA`/`SERVICES_MANUAL` naming
this section used to use.

64 of 70 Compose services are ported: `min` 4/6 (beszel, cloudflared,
landing, docs), `core` 14/14 beyond `min` (all ported, including
`mailpit`), `daily` 13/15, `office` 8/8, `automation-ai` 6/6, `extra`
17/19, `manual` 2/2 (gitlab, wg-easy). The cluster foundation (namespaces,
Traefik, the shared Gateway, MetalLB, shared Postgres/MariaDB) is
ArgoCD-managed too, see `kubernetes/argocd-apps/cluster-*.yaml`.

Every remaining gap is either deliberately excluded (below) or not a real
service — `daily`'s `browser` entry is the static browser-hub landing page
served by `nginx-plain` itself, not its own container, so there's nothing
separate to port. That's effectively full parity with everything in the
Compose stack that has a real Kubernetes equivalent.

Not ported, deliberately:

- **`nginx-plain`** — its one job, routing, is already covered by
  Traefik/Gateway API in this cluster; porting it too would just be two
  reverse proxies fighting for the same role.
- **`portainer`, `dozzle`, `dockge`, `coolify`** — removed after review,
  not just left broken. Each one's entire purpose is managing Docker
  itself via `/var/run/docker.sock` (container/stack management, live log
  tailing, deploying other containers) — there's no Kubernetes-native
  version of "manage Docker," so a manifest that starts but can never
  actually do its job isn't worth carrying. `portainer` moved into the
  `min` tier in the Compose-side reshuffle above, but the reasoning for
  excluding it here hasn't changed.
- **`dagster`'s app tier** (webserver/daemon/user-code) — all three build
  from a local Dockerfile in Compose rather than pulling a public image
  (a Dagster code location *is* your own code by definition, and there's
  no stock "just run it" webserver/daemon image either). This pilot has
  no CI/registry to build and push custom images, so only `dagster-db` is
  ported — see `kubernetes/apps/dagster/db-init-job.yaml`'s header. Same
  category of gap as `temporal`'s custom worker image (below), just
  total rather than partial.
- **`temporal`'s custom worker container** — `services/temporal/worker/`
  is a locally-built Python image (Dockerfile + bind-mounted code), same
  no-registry blocker as dagster. The core Temporal server + UI use public
  images and are ported; only the worker is left out.

**Minimizing DB instance count:** `airflow`, `temporal`, `mattermost`, and
`dagster` are onboarded onto the shared Postgres server
(`kubernetes/cluster/postgres/`, via each service's own
`db-init-job.yaml`) rather than getting a dedicated StatefulSet each —
none of them needs a specific Postgres version/extension the shared
server can't provide. `temporal` is the one adjustment to the standard
single-database onboarding template: it needs two databases (`temporal` +
`temporal_visibility`) under one role. Every other Postgres-backed service
in this pilot predates that convention and still runs its own dedicated
instance (own version/extensions, or just following the established
per-service pattern) — not retrofitted, since that would touch ~20
already-working services for no functional gain. Two exceptions stay
dedicated out of necessity, not oversight: `rocketchat`'s MongoDB (no
shared Mongo exists in this pilot) and `zulip`'s Postgres (needs the
vendor `zulip/zulip-postgresql` image, same "own extensions" category as
immich's pgvector image).

Manifests exist and are internally consistent (every Secret reference has a
matching `apply-secrets.py` entry, every YAML file parses) but **have not
been applied to a live cluster yet** — this branch just moved to its
intended real Linux hardware and the cluster itself hasn't been created
here. Next step is standing up `kind` (`kubernetes/kind-config.yaml`) and
reconciling ArgoCD against everything in git, service by service.

**Known architectural gaps, documented in-file, not oversights:**

- **Docker-socket-dependent tools still in the pilot** (beszel-agent,
  authentik-worker, crowdsec, cadvisor, alloy) mount `/var/run/docker.sock`
  via `hostPath` as currently configured — same underlying problem as the
  4 removed services above (no live socket on a containerd `kind` node),
  but these 5 differ in one important way: the Docker socket is an
  *implementation detail* of how they're wired for Compose, not their
  actual purpose. Each has a real Kubernetes-native equivalent — see
  "Making the Docker-socket-dependent services k8s-native" below for the
  per-service rework plan (in progress, not yet applied to these
  manifests).
- **`network_mode: host` → `hostNetwork: true`** (beszel-agent): needed
  `dnsPolicy: ClusterFirstWithHostNet` too, or it silently resolves via the
  node's DNS instead of the cluster's.
- **No `depends_on` equivalent.** Every multi-container service with a
  Compose `depends_on: condition: service_healthy` chain (appflowy, plane,
  penpot, karakeep, supabase, observability, ...) relies on the
  app's own connection retries + k8s's crash-loop restart instead — not a
  startup-ordering guarantee. One-shot init/migration containers
  (`appflowy-minio-setup`, `plane-migrator`) are modeled as k8s `Job`s
  (`restartPolicy: OnFailure`), matching Compose's `restart: "no"`.
- **Command vs args, an ongoing gotcha, not just a Postgres one.**
  `TROUBLESHOOTING.md` already covers this for Postgres/MariaDB images;
  it's since been hit again on `goauthentik/server` (authentik-server/
  worker), `redis:alpine` (paperless-redis), and `nginx:alpine` with a
  custom entrypoint (landing) — each image's own ENTRYPOINT determines
  whether Compose's `command:` maps to k8s `args:` (CMD override) or
  `command:` (ENTRYPOINT override); get it backwards and the container
  silently ignores your flags or crash-loops.
- **Same-node PVC risk.** Several two-pod-sharing-one-`ReadWriteOnce`-PVC
  setups (authentik server+worker, penpot backend+frontend, supabase
  storage+imgproxy, and now airflow's 5 pods — apiserver/scheduler/
  dag-processor/triggerer/init-Job — sharing one `airflow-data` PVC, the
  sharpest case yet) only work if the scheduler happens to colocate both
  pods — no `nodeAffinity` enforces it. Flagged in each manifest, not
  silently assumed away.
- **Traefik ForwardAuth ↔ Authentik is now wired up** —
  `kubernetes/apps/authentik/forward-auth-middleware.yaml` defines a
  shared `Middleware` (`authentik-forward-auth`) pointing at Authentik's
  *embedded* outpost (no separate outpost Deployment needed). Any
  HTTPRoute in the `apps` namespace gates itself behind it with an
  `ExtensionRef` filter — see that file's header for the exact snippet.
  Applied to every host Compose gates the same way (cross-checked against
  `services/nginx-plain/templates/default.conf.template`'s
  `auth_request /outpost.goauthentik.io/auth/nginx` blocks): `firefox`,
  `chromium`, `ungoogled-chromium`, `brave`, `mullvad-browser` (Compose
  gates these as subpaths under one `browser.${DOMAIN}` hub; this pilot
  gates each on its own hostname instead — functionally equivalent, wider
  namespace footprint), `excalidraw`, `temporal`, `mailpit`, `ollama`.
  Not applied (not ported, or ported without an app tier to gate): `dagster`
  (app tier isn't ported), `dozzle` (excluded entirely), `wg-easy`/wg-admin
  (not ported at all yet).
  **Still missing:** the Authentik-side half — a Proxy Provider (forward
  auth mode) + Application, created via Authentik's own UI/API once it's
  actually running; that's live cluster state, not something git can
  express as a manifest, same category as ArgoCD's admin password. Until
  that exists, the outpost endpoint the Middleware calls won't resolve
  correctly. Each gated service's `lan-service.yaml` (LoadBalancer,
  routes straight to the pod) still fully bypasses this Middleware —
  flagged with a security-note comment in each one, not silently assumed
  safe.
  Same 5 browser services also still drop Compose's static
  per-container Docker-bridge IP (used for a LAN-isolation firewall
  rule) — k8s has no direct equivalent; a `NetworkPolicy` would be the
  real fix, not yet written.
- **Vendor Postgres images, a growing list.** immich (pgvector/
  vectorchord) and zulip (`zulip/zulip-postgresql`) both need their own
  Postgres build, not the shared server and not even a stock `postgres:`
  dedicated instance — same category, different vendor image each time.
- **supabase** is the single most complex service here (~15 containers).
  db/auth/rest/storage/kong got full attention; realtime needed a real fix
  (its Compose container name, `realtime-dev.supabase-realtime`, isn't a
  legal k8s Service name — renamed, kong.yml's routes rewritten to match);
  imgproxy/meta/functions/studio/pooler got a lighter, best-effort pass.
- Two gaps found auditing pre-existing (older) manifests while doing this
  pass: `nextcloud`'s Postgres StatefulSet was missing the
  `postgres-init` ConfigMap its own `compose.yml` mounts (schema-ownership
  script — now fixed), and 12 already-ported services had no
  `lan-service.yaml` at all (audiobookshelf, bookstack, it-tools, mealie,
  miniflux, ntfy, openproject, outline, silverbullet, trilium, uptime-kuma,
  vikunja — now added). Worth a periodic `find kubernetes/apps -maxdepth 1
  -mindepth 1 -type d` sweep against `docs/11-services-reference.md` if
  services keep getting added ad hoc.

See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for every real bug/gotcha
hit while building this out, and why each one happened.
