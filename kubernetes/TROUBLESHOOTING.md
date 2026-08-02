# kubernetes/ — troubleshooting & setup log

Every real gotcha hit while building this pilot, why it happened, and how it
was fixed — a debugging reference for future work on this same setup
(including the eventual move to a real Linux box, where some of these
Windows/Docker-Desktop-specific issues won't even apply). See
`kubernetes/README.md` for what's actually installed and how to use it; this
file is the "why does X behave this way" companion.

---

## Operational: pausing a service to reclaim resources without losing state

Since this pilot shares one Windows machine with the real Compose stack,
services get scaled down in Kubernetes (not deleted) once verified —
Compose is what's actually left running day to day, and only one *other*
(non-CORE) service should be scaled up in k8s at a time going forward to
keep resource usage sane.

**Don't just `kubectl scale --replicas=0`** — ArgoCD's `syncPolicy.automated.selfHeal: true`
notices the drift from git (which still says `replicas: 1`) and reverts it
back up within its next sync cycle. Two ways to pause correctly:

1. **For a genuinely long-term pause** (e.g. reverting to Compose as the
   real runtime, like the CORE services here): disable automated sync for
   that Application first, *then* scale:

   ```bash
   kubectl -n argocd patch application <name> --type merge \
     -p '{"spec":{"syncPolicy":{"automated":null}}}'
   kubectl scale deployment <name> -n apps --replicas=0
   kubectl scale statefulset <name>-db -n apps --replicas=0   # if it has its own DB
   ```

   Also suspend any `CronJob`s belonging to the paused service
   (`kubectl patch cronjob <name> -n apps -p '{"spec":{"suspend":true}}'`) —
   otherwise they keep firing on schedule and crash-looping against the
   now-absent app. Re-enable automated sync
   (`syncPolicy.automated: {"prune": true, "selfHeal": true}`) to resume.

2. **PVCs and Secrets are untouched by any of this** — scaling to 0 only
   stops the running pods; all data (Postgres volumes, uploaded files,
   config) stays exactly as it was for whenever the service is scaled back
   up. Nothing needs re-provisioning or re-copying (test media, etc.) on
   resume.

---

## Cluster / Docker Desktop

### Docker Desktop's multi-node Kubernetes is native now, no `kind` CLI needed

As of the 2026 Docker Desktop releases, **Settings → Kubernetes** lets you
pick `kind` as the provisioning method directly in the UI, choose the
Kubernetes version, and set the node count (1 control-plane + N workers) —
no separate `kind` binary install. This is a change from how it used to
work (single-node only); don't assume older guides/memory about
Docker-Desktop-Kubernetes still apply.

### kind's node containers have NO host filesystem passthrough

Confirmed by direct testing: a `hostPath` volume pointing at a Docker
Desktop host-mount convention path (`/run/desktop/mnt/host/d/...`) silently
created an empty directory instead of finding real data, and inspecting a
node's own mount table (`docker exec desktop-worker mount`) showed nothing
connecting to the real Windows filesystem at all. This is different from
**regular** Docker Desktop containers, which do get host path sharing via
Docker Desktop's normal bind-mount mechanism (`-v D:/path:/path` just
works for a plain `docker run`). `kind`'s nodes are themselves nested
containers that Docker Desktop does not extend that same file-sharing
integration into.

**Practical consequence:** no way to give a pod live access to a real
Windows directory (media library, uploads, etc.) without extra
infrastructure. See "Host data access" below for what was tried and why
none of it fully worked on Windows specifically.

### Docker Desktop's `LoadBalancer` Services are reachable via the real LAN IP, not just localhost

Confirmed directly: `curl http://192.168.1.3/` (the host's actual LAN IP,
not `localhost`) reached a `type: LoadBalancer` Service correctly, with zero
extra setup (no MetalLB needed). This matters for phone/other-device access
— Windows Firewall was the only remaining gate to check (a broad `Docker
Desktop Backend` inbound Allow rule already covered it here).

### Editing an existing `LoadBalancer` Service's `port:` doesn't cleanly re-provision

Changing `spec.ports[].port` on an already-applied `LoadBalancer` Service
and re-`kubectl apply`ing does **not** tear down and recreate the
underlying Docker Desktop proxy container (named `kindccm-*`) — it stays
bound to the *old* port, silently. Symptom: `curl` to the new port hangs/
refuses even though `kubectl get svc` shows the new port correctly.

**Fix:** `kubectl delete svc <name> -n <ns>` then re-`apply`, never just
edit-and-reapply a port change on a `LoadBalancer` Service.

---

## Compose → Kubernetes semantic mismatches

### `command:` means different things in Compose vs Kubernetes

Docker Compose's `command:` overrides the image's **CMD only** — the
image's own ENTRYPOINT script (e.g. Postgres's `docker-entrypoint.sh`,
which handles dropping root privileges and running init scripts) still
runs first. Kubernetes' `command:` field overrides the **ENTRYPOINT
itself**, bypassing that wrapper entirely.

**Symptom:** copying a Postgres `command: postgres -c shared_buffers=...`
line from a `compose.yml` directly into a pod spec's `command:` field
caused `guacamole-db` to crash-loop with `"root" execution of the
PostgreSQL server is not permitted` — the entrypoint script that normally
switches to the `postgres` user never ran.

**Fix:** use `args:` in Kubernetes for this, not `command:` — that's the
actual equivalent of Compose's `command:` (overrides CMD, keeps
ENTRYPOINT). The official Postgres entrypoint script auto-prepends
`postgres` when `args` starts with a flag (`-c ...`), so `args: ["-c",
"shared_buffers=128MB", ...]` with no literal `postgres` needed works
correctly.

### `.gitignore` doesn't support trailing inline comments

Unlike shell scripts, a `.gitignore` pattern with a `#` comment *after* the
pattern on the same line is **not** a comment — the `#...` text becomes
part of the literal pattern, which then matches nothing.

```gitignore
# WRONG — matches nothing, the whole line including the comment is the pattern
service_data-test/   # k8s pilot's placeholder test data

# RIGHT — comment on its own line above
# k8s pilot's placeholder test data
service_data-test/
```

Verify with `git check-ignore -v <path>` — it prints which line actually
matched (or nothing, if the pattern silently failed).

---

## kubectl gotchas (Windows-specific)

### `kubectl cp` fails on Windows drive-letter paths

`kubectl cp D:/homeserver/some/path pod:/dest` fails with `error: one of
src or dest must be a local file specification` — **not** because
anything's wrong with the pod or the path's existence, but because
`kubectl cp`'s argument parser sees the `:` in the Windows drive letter
(`D:`) and can't tell which argument is the "local" one anymore (both now
contain a colon).

**Fix:** `cd` into the source directory first and use `.` as the source, or
use Git Bash's colon-free path form (`/d/homeserver/...`) — either avoids
the colon-in-argument ambiguity. `MSYS_NO_PATHCONV=1` does **not** fix this
specific error (it addresses a different problem — MSYS auto-converting
POSIX-looking container-internal paths like `/media` into Windows paths
before they reach `docker`/`kubectl`; this cp issue is kubectl's own
argument-parsing logic, unrelated).

### Container-internal paths get mangled by Git Bash unless prefixed

Any command with a POSIX-looking path meant for *inside* a container or pod
(e.g. `kubectl exec pod -- find /media -type f`, `docker run -v
host:/nfsshare`) needs `MSYS_NO_PATHCONV=1` prefixed on Windows/Git Bash, or
Git Bash silently rewrites `/media` into something like `C:/Program
Files/Git/media` before the command ever runs. Symptom: `No such file or
directory` errors for paths that definitely exist inside the container.

---

## Application-specific gotchas

### Kubernetes auto-injects env vars that can collide with an app's own config vars

Kubernetes auto-populates every pod with legacy Docker-link-style
environment variables for **every** `Service` that already exists in the
same namespace at pod creation time — `<SERVICE_NAME>_SERVICE_HOST`,
`<SERVICE_NAME>_SERVICE_PORT`, and `<SERVICE_NAME>_PORT` (a
`tcp://<ip>:<port>` URI). This is the `enableServiceLinks` pod-spec field,
default `true`.

**Symptom:** `trilium` crash-looped with `FATAL ERROR: Invalid port value
"tcp://10.96.55.194:8080" from environment variable TRILIUM_PORT` — Trilium
itself reads an env var literally named `TRILIUM_PORT` for its own config,
and Kubernetes had already injected a same-named variable (derived from the
`trilium` Service's own name) with a completely different value format.

**Why this gets worse over time in this setup specifically:** every
service in this pilot shares one flat `apps` namespace (mirroring the
compose stack's single-network model). Every additional service added is
another `Service` name that gets auto-injected into every *other* pod's
environment — the collision risk only grows as more services are ported,
and it can hit any app with a generically-named env var (`PORT`, `HOST`,
`_PORT` suffixes are common).

**Fix:** set `enableServiceLinks: false` on every pod spec in this shared
namespace, not just the one that happened to collide first:

```yaml
spec:
  template:
    spec:
      enableServiceLinks: false   # right here, sibling to `containers:`
      containers:
        - name: ...
```

Applied retroactively to every Deployment/StatefulSet/CronJob in this repo
once found — **new services must include this from the start**, don't wait
for a collision to surface it.

### Nextcloud 400s kubelet's own health probes

Nextcloud validates every request's `Host` header against
`trusted_domains` and returns `400 Bad Request` for anything not on that
list. Compose's healthcheck (`curl http://localhost/status.php` run
*inside* the container) naturally sent `Host: localhost`, which is already
trusted by default. Kubernetes' `httpGet` probe sends the **pod IP** as the
`Host` header by default — not on the trusted list — so probes fail with
400 even though the app is actually healthy.

**Fix:** pin the probe's `Host` header explicitly:

```yaml
readinessProbe:
  httpGet:
    path: /status.php
    port: 80
    httpHeaders:
      - name: Host
        value: localhost
```

### Kubernetes' `$(VAR)` env substitution only looks *backwards* in the same list

Referencing one env var's value inside another (`$(OTHER_VAR)`) only
resolves if `OTHER_VAR` is defined **earlier** in the same container's
`env:` list. Defining it after silently fails — the literal unexpanded
string (`$(OTHER_VAR)` verbatim) becomes the value, with **no error or
warning**.

**Symptom that made this hard to diagnose:** `immich-server` crash-looped
with `Error: getaddrinfo ENOTFOUND immich-db` — a DNS resolution error that
had nothing to do with the actual bug. The literal, unsubstituted
`DB_URL` value confused Immich's Postgres client into a state where the
error surfaced as a hostname lookup failure, not an auth or "malformed
URL" error, which sent debugging in the wrong direction initially (verified
DNS resolution for `immich-db` worked fine from a separate test pod before
realizing the env var itself was the problem).

**Fix:** don't rely on in-manifest `$(VAR)` interpolation across two
separate `secretKeyRef`s. Instead, pre-compose the full value (e.g. the
whole `postgresql://user:pass@host:port/db` string) once, in
`apply-secrets.sh`, and store it as its own single secret key. No
in-manifest interpolation needed at all.

### Vendor-pinned image versions aren't "just take latest"

For Immich's Postgres image specifically (bundles pgvector/vectorchord),
neither the newest available tag on the registry (`vectorchord1.1.1`) nor
upstream's own official `docker-compose.yml` example (which pins Postgres
**14**, not 18) matched what this repo's existing, already-working
`immich/compose.yml` uses (`18-vectorchord0.5.3-pgvector0.8.1`). These
extensions are tightly coupled to the app's own migrations/schema — verify
what's *actually proven working with this exact app version in this repo*
before assuming "latest" or "upstream's example" is the safe default. This
is the opposite lesson from patch-level bumps (Postgres itself, Traefik,
ArgoCD), where taking latest stable is fine — check whether a given
component is version-sensitive to its pairing before treating "latest" as
universally safe.

---

## Host data access (media libraries, uploads) — the open problem

The actual goal: pods should see real host files live, no manual copying,
writes from the app (e.g. Immich uploads) should show up on the real disk
immediately. What was tried:

1. **`kubectl cp` into a plain PVC** — works, but is a one-time manual copy,
   not a live connection. New files added to the host afterward are
   invisible to the pod until `cp` is run again. This is the current state
   for jellyfin/immich's test media in this pilot.

2. **NFS-export a Docker-Desktop-mounted host directory directly** —
   confirmed the underlying kernel NFS server (`knfsd`) genuinely works in
   Docker Desktop's Linux VM (it started fine, `rpc.nfsd` came up
   correctly). But re-exporting a directory that itself is a **Windows
   host bind-mount** fails: `exportfs: /nfsshare does not support NFS
   export`. Docker Desktop's virtualized host-mount filesystem doesn't
   implement the export operations NFS needs — this is a confirmed,
   genuine limitation, not a flag/config issue.

3. **Sync-relay (mirror into a real Docker volume, NFS-export that
   instead)** — would work for NFS-export purposes (a real Docker volume
   is genuine Linux storage), but is **duplication with sync lag**, not a
   true live single-copy connection. Critically, a naive one-directional
   sync (host → volume) means writes originating from the pod side (e.g.
   an Immich upload) would never flow back to the real Windows folder —
   the app would work, but "where did the upload actually go on disk"
   would dead-end from the Windows side. Not pursued further given this
   pilot's actual goal was genuine bidirectional live access.

4. **SMB/CIFS share** — the option that actually matches "one copy, live,
   both directions": Windows serves the real NTFS files directly over the
   network (bypassing Docker Desktop's virtualization layer entirely), and
   the Linux side mounts that share. Not implemented in this pilot — would
   need a real Windows-side SMB share (a host-level change) and a CIFS
   mount mechanism in Kubernetes (no built-in PV type for it; the
   real-world answer is the `kubernetes-csi/csi-driver-smb` project, or a
   manual privileged pod running `mount -t cifs`).

**Root cause, stated plainly:** this is **not a Kubernetes limitation**.
`hostPath` volumes on a real Linux node work exactly like a Compose bind
mount — instant, live, both directions, zero copying, because the node IS
the real OS with direct access to its own filesystem. The problem is
specifically the stack of translation layers between the pod and the disk
on *this* setup: Windows → Docker Desktop's own virtualization → `kind`'s
node-in-container nesting. Any of the following removes the problem
entirely:

- Running the same manifests on a real Linux machine (the actual plan —
  see README's "Status" section).
- Running a self-managed Kubernetes (k3s/kubeadm) directly **inside
  WSL2** rather than through Docker Desktop's own kind integration — WSL2
  already natively mounts Windows drives at `/mnt/d/...` with real
  filesystem semantics, so a `hostPath` pointing there would just work,
  live, no bridge needed at all. Not pursued for this pilot (bigger
  infrastructure change than warranted for a config-validation exercise),
  but worth knowing as the "make it actually work on Windows" answer if
  that's ever needed before the Linux hardware arrives.

---

## ArgoCD

### Initial admin password lives in an auto-generated Secret

`admin` is ArgoCD's fixed built-in superuser (not configurable). The
initial password is randomly generated on first boot and stored in
`argocd-initial-admin-secret` (namespace `argocd`):

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

To set it to a chosen value instead (e.g. via this repo's `.env`
convention), ArgoCD requires a **bcrypt hash** in `argocd-secret`'s
`admin.password` key — it does not accept plaintext. See
`apply-secrets.sh` for how this repo automates the hashing (via `uv run
--with bcrypt`, no new project dependency).

### Migrating an existing `helm install` release into ArgoCD management

Directly pointing an ArgoCD `Application` (Helm source) at a release that
was already installed via plain `helm install` risks two different
ownership-tracking systems (Helm's own release-secret metadata vs ArgoCD's
tracking labels) conflicting over the same live resources. For a
**stateless** release (Traefik, in this case — no PVCs/data at risk), the
clean fix is: `helm uninstall` the plain release first, then let ArgoCD
create it fresh via a multi-source Application (Helm chart + a git-hosted
`values.yaml`, referenced via the `$values` ref syntax). Don't attempt this
live-migration shortcut on anything stateful without a lot more care.

### Force a sync outside the default poll interval

```bash
kubectl -n argocd patch application <name> --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

Useful after pushing a git change when you don't want to wait for ArgoCD's
default ~3-minute polling loop.

---

## Port-forward collisions (self-inflicted, twice)

Ad hoc `kubectl port-forward` ports picked without checking for collisions
caused two real outages during this pilot:

1. ArgoCD's UI port-forward (`8081`) collided with Nextcloud's own
   `lan-service` port (also `8081`, matching its `compose.dev.yml`) once
   Nextcloud was ported — whichever claimed the port second silently broke
   the other, surfacing as a browser `SSL received a record that exceeded
   the maximum permissible length` error (a classic symptom of connecting
   via HTTPS to something that's actually serving plain HTTP, or nothing at
   all).
2. The chosen replacement port (`8443`) *also* collided — with
   `nginx-plain`'s own real production HTTPS port.

**Fix applied:** moved ArgoCD's port-forward to `18081` — deliberately far
from any low port range anything else in this project uses. **Lesson:**
check a candidate port isn't already bound before committing to it:

```bash
(echo > /dev/tcp/127.0.0.1/<port>) 2>/dev/null && echo "IN USE" || echo "free"
```

---

[← kubernetes/README.md](README.md)
