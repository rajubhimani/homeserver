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
