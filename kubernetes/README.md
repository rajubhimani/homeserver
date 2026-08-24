# kubernetes/ — parallel Kubernetes experiment

A separate, parallel setup to the Docker Compose stack that makes up the rest
of this repo — not a replacement for it. The compose stack keeps running
as-is; this folder is where the same services get ported to Kubernetes
manifests, one at a time, to validate the pattern before committing to a
full migration.

## Cluster

Originally built on a Windows/Docker-Desktop box (Settings → Kubernetes →
enable → kind provisioning). This branch has since moved to its intended
target — a real Linux (Fedora) host — using plain `kind` directly rather
than Docker Desktop's bundled integration:

```bash
kind create cluster --config kubernetes/kind-config.yaml
```

Topology: 1 control-plane + 3 workers (`kubernetes/kind-config.yaml` — see
that file's own comment for why it's 1 control-plane, not 2: etcd quorum
needs an odd member count, and 2 is strictly worse than 1). `kubectl`
points at it via the `kind-kind-cluster` context.

## What's installed

| Component | Namespace | Purpose |
| --- | --- | --- |
| Traefik (Gateway API mode) | `infra` | Routes all services behind one entry point — the k8s equivalent of `nginx-plain`'s `server_name` blocks. `ingress-nginx` is deprecated (no releases/security fixes since March 2026), so this uses Gateway API (`Gateway`/`HTTPRoute`) instead of classic `Ingress` objects. |
| ArgoCD | `argocd` | GitOps — syncs cluster state to match what's in this folder on git. |
| MetalLB | `metallb-system` | Gives every `type: LoadBalancer` Service a real, reachable IP. Needed because this now runs on plain `kind`, which — unlike Docker Desktop's bundled kind — has no built-in LoadBalancer support. L2 mode, address pool carved from kind's own Docker bridge subnet. See `kubernetes/cluster/metallb/`. |
| Shared Postgres | `data` | Provisioned for services that don't need their own dedicated instance — but as of this writing every ported service actually has its own dedicated Postgres/MariaDB StatefulSet instead (own version/extensions, e.g. Immich's pgvector, or just following the established per-service pattern). This shared server exists and is ArgoCD-managed, but nothing is onboarded onto it yet — `kubernetes/cluster/postgres/db-init-job.template.yaml` is ready for the first service that actually wants it. |
| Shared MariaDB | `data` | Same story as shared Postgres above — provisioned, ArgoCD-managed, currently unused (BookStack/InvoiceShelf/OrangeHRM/etc. all run their own dedicated MariaDB instead). |

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
      lan-service.yaml   # direct LAN-reachable port — see "LAN access" below
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
`./kubernetes/apply-secrets.sh` after editing `.env` to push the values into
the cluster as Secrets. ArgoCD's admin password is a special case — ArgoCD
only accepts a bcrypt hash in its Secret, so the script hashes it (via
`uv run --with bcrypt`, no new project dependency) before patching
`argocd-secret`.

## Current status

This repo's Compose side was restructured after this pilot was last brought
up to date (tiers renamed/expanded to `min`/`core`/`daily`/`office`/
`automation-ai`/`extra`/`manual`, ~19 new services added — see
[`docs/11-services-reference.md`](../docs/11-services-reference.md) for the
current tier lists). Counts below are against that current tier structure,
not the older `SERVICES_CORE`/`SERVICES_EXTRA`/`SERVICES_MANUAL` naming
this section used to use.

49 of 70 Compose services are ported: `min` 3/6 (beszel, cloudflared,
landing), `core` 20/20 beyond `min` (all ported except `mailpit`, which is
still missing), `daily` 7/15, `office` 8/8, `automation-ai` 3/6, `extra`
14/19, `manual` 1/1 (gitlab). The cluster foundation (namespaces, Traefik,
the shared Gateway, MetalLB, shared Postgres/MariaDB) is ArgoCD-managed
too, see `kubernetes/argocd-apps/cluster-*.yaml`.

Missing but portable, no known blocker (not yet done, just not gotten to):
`docs`, `mailpit`, the 6 remote-browser services (firefox, chromium,
ungoogled-chromium, brave, mullvad-browser, browser-hub), `homebox`, and
the 6 heavier multi-container platforms — `airflow`, `temporal`,
`dagster`, `mattermost`, `rocketchat`, `zulip` — each needs its own
Postgres/Mongo/Redis-backed StatefulSet(s), same pattern as `supabase`
below but not yet done.

Not ported, deliberately — same reasoning as before, unaffected by the
tier rename:

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

Manifests exist and are internally consistent (every Secret reference has a
matching `apply-secrets.sh` entry, every YAML file parses) but **have not
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
  storage+imgproxy) only work if the scheduler happens to colocate both
  pods — no `nodeAffinity` enforces it. Flagged in each manifest, not
  silently assumed away.
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
