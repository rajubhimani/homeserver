# kubernetes/ — parallel Kubernetes experiment

A separate, parallel setup to the Docker Compose stack that makes up the rest
of this repo — not a replacement for it. The compose stack keeps running
as-is; this folder is where the same services get ported to Kubernetes
manifests, one at a time, to validate the pattern before committing to a
full migration.

## Cluster

Docker Desktop's built-in Kubernetes, provisioned via `kind` (Settings →
Kubernetes → enable → kind provisioning → 4 nodes: 1 control-plane + 3
workers). No separate `kind` CLI install needed — Docker Desktop handles
cluster creation itself. `kubectl` (bundled with Docker Desktop) already
points at it via the `docker-desktop` context.

## What's installed

| Component | Namespace | Purpose |
| --- | --- | --- |
| Traefik (Gateway API mode) | `infra` | Routes all services behind one entry point — the k8s equivalent of `nginx-plain`'s `server_name` blocks. `ingress-nginx` is deprecated (no releases/security fixes since March 2026), so this uses Gateway API (`Gateway`/`HTTPRoute`) instead of classic `Ingress` objects. |
| ArgoCD | `argocd` | GitOps — syncs cluster state to match what's in this folder on git. |
| Shared Postgres | `data` | One Postgres server, separate database + role per service that doesn't need its own dedicated instance. Services needing a dedicated Postgres (own version/extensions, e.g. Immich's pgvector) get their own separate StatefulSet instead. |
| Shared MariaDB | `data` | Same pattern, for the MariaDB-using services (BookStack, InvoiceShelf, OrangeHRM) — one server, separate database + user per service via `GRANT`, no cross-service visibility. |

Docker Desktop auto-exposes `type: LoadBalancer` Services on `localhost` —
no MetalLB or extra setup needed.

## Layout

```
kubernetes/
  cluster/            # cluster-wide infra, not app-specific
    namespaces.yaml
    traefik/
      values.yaml      # Helm values for Traefik
      gateway.yaml      # the one shared Gateway every service's HTTPRoute attaches to
    postgres/
      statefulset.yaml
      secret.example.yaml         # template only — real Secret via apply-secrets.sh
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
      lan-service.yaml   # direct LAN-reachable port, kept for real-hardware
                          # use later — see "Current status" below for why
                          # it's not live-applied on this Windows pilot box
      db-init-job.yaml   # only if using the shared Postgres server
  argocd-apps/
    <service>.yaml       # ArgoCD Application manifests, one per service
  .env.example            # template — copy to .env (gitignored) and fill in
  apply-secrets.sh         # reads .env, creates/updates the matching k8s Secrets
```

Hostnames use a `*.k8s.local` suffix (e.g. `excalidraw.k8s.local`), not the
real production domain — this is a parallel experiment, not production
traffic. Test routing locally the same way `nginx-plain` health checks are
tested elsewhere in this repo:

```bash
curl -H "Host: excalidraw.k8s.local" http://localhost:80/
```

## LAN access (phone, other devices)

Hostname routing above only works from this PC (no hosts-file trick works on
a phone, and AdGuard Home isn't set up as the network's DNS resolver yet —
revisit once it is). Until then, each service also gets a second `Service`
(`type: LoadBalancer`, see `lan-service.yaml`) exposing it directly on the
**exact same port its `compose.dev.yml` already uses** — same number you
already know, nothing new to learn. Docker Desktop's LoadBalancer support
auto-exposes these on both `localhost` and the host's real LAN IP with no
extra setup.

**The Compose version of a service must be stopped before porting it** —
same host port, can't have both bound at once:

```bash
uv run homeserver.py dev down <service>
```

| Service | Port | Matches |
| --- | --- | --- |
| excalidraw | 8116 | `excalidraw/compose.dev.yml` |
| guacamole | 8107 | `guacamole/compose.dev.yml` |
| vaultwarden | 8200 | `vaultwarden/compose.dev.yml` |
| forgejo | 3002 (HTTP), 2223 (SSH) | `forgejo/compose.dev.yml` |

Gotcha hit once already: editing an existing `LoadBalancer` Service's `port:`
in place does **not** cleanly re-provision the underlying proxy container
(Docker Desktop's `kindccm-*` containers) — it stays bound to the old port.
If a port ever needs to change, delete and recreate the Service
(`kubectl delete svc <name>-lan -n apps` then re-apply), don't just edit and
re-apply.

**Not currently live-applied on this Windows pilot box** — the whole point
of matching Compose's exact ports means the k8s and Compose versions of a
service can never run at the same time on this one machine (same port,
can't both bind it). Since the real Compose stack is what's actually in use
day to day right now, these `lan-service.yaml` files stay in git (so
they're ready to use once this moves to real Linux hardware, where there's
no competing Compose stack to collide with) but aren't part of what's
currently `kubectl apply`'d/ArgoCD-synced. See "Current status" below.

## Secrets

Same convention as every other service in this repo: `.env` (gitignored,
real values) + `.env.example` (checked in, template). Run
`./kubernetes/apply-secrets.sh` after editing `.env` to push the values into
the cluster as Secrets. ArgoCD's admin password is a special case — ArgoCD
only accepts a bcrypt hash in its Secret, so the script hashes it (via
`uv run --with bcrypt`, no new project dependency) before patching
`argocd-secret`.

## Current status

All 7 `SERVICES_CORE` services are ported and validated: guacamole,
vaultwarden, forgejo, firefly, nextcloud, jellyfin, immich — each with a
dedicated or shared Postgres as appropriate, routed through Traefik/Gateway
API, and ArgoCD-managed (`Synced`/`Healthy`). Plus the cluster foundation
(namespaces, Traefik itself, the shared Gateway, shared Postgres) — also
ArgoCD-managed, see `kubernetes/argocd-apps/cluster-*.yaml`.

**This pilot's actual purpose, going forward:** validate that these
manifests are correct and deployable — not to run this cluster as a
day-to-day replacement for the real Compose stack on this Windows machine.
The real Compose stack is what's actually in production use here; this
`kind`-on-Docker-Desktop cluster is a config-validation exercise. The plan
is to bring this exact `feature/k8s-pilot` branch to real Linux hardware
(Fedora) once available, where `hostPath` volumes work natively (no
Windows/Docker-Desktop/kind virtualization stack in the way — see
`TROUBLESHOOTING.md`'s "Host data access" section for why that specifically
doesn't work well on this Windows setup) and there's no competing Compose
stack to collide with on ports.

See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for every real bug/gotcha
hit while building this out, and why each one happened.
