# 12 — Kubernetes Pilot (experimental, parallel to Compose)

[← Services Reference](11-services-reference.md) | [Home](../setup.md)

---

**This is not part of the setup path above and nothing here is required.**
The `kubernetes/` directory is a separate, parallel experiment that ports
services from this repo's Docker Compose stack to Kubernetes manifests, one
at a time, to validate the pattern before ever committing to a full
migration. The Compose stack (everything in the numbered docs 01–11) is
what actually runs day to day and keeps running exactly as-is regardless of
what happens here.

## What it is

A `kind` cluster (1 control-plane + 3 workers) with Traefik (Gateway API
mode — the k8s equivalent of `nginx-plain`'s routing), ArgoCD for GitOps,
and MetalLB for `LoadBalancer` IPs. Each ported service gets a
`kubernetes/apps/<service>/` directory with its Kubernetes manifests
(Deployment/StatefulSet, Service, HTTPRoute, and a LAN-reachable
LoadBalancer Service on the same port you already know from
`compose.dev.yml`) plus a matching `kubernetes/argocd-apps/<service>.yaml`
Application manifest.

## Where the actual detail lives

This file is intentionally short — it's an index entry, not a rewrite.
Everything else lives in `kubernetes/`, checked into this same repo:

| Topic | Where |
| --- | --- |
| What's installed, cluster layout, LAN access, secrets, current port status (which services are ported, which are deliberately excluded and why) | [`kubernetes/README.md`](../kubernetes/README.md) |
| Every real gotcha hit building this out — kind quirks, `command` vs `args` traps, same-node PVC risk, disk-full recovery, ArgoCD bootstrap issues | [`kubernetes/TROUBLESHOOTING.md`](../kubernetes/TROUBLESHOOTING.md) |

## Status at a glance

63 of 70 Compose services are ported — effectively full parity with
everything that has a real Kubernetes equivalent. Deliberately not
ported: `nginx-plain` (Traefik already covers its one job — routing),
`portainer`/`dozzle`/`dockge`/`coolify` (their entire purpose is managing
the Docker socket, which has no Kubernetes-native equivalent), and the
app tier of `dagster` plus `temporal`'s worker container (both build
custom images locally in Compose; this pilot has no CI/registry to build
and push them). See `kubernetes/README.md`'s "Current status" section for
the live count and the full reasoning — that section is the source of
truth, not this page.

## Trying it

```bash
kind create cluster --config kubernetes/kind-config.yaml
# then follow kubernetes/README.md for Traefik/ArgoCD/MetalLB setup and
# ./kubernetes/apply-secrets.sh for secrets
```

Manifests are validated (YAML parses, every Secret reference has a matching
`apply-secrets.sh` entry) but this is a pilot, not a production deployment
path — don't point real traffic or real data at it.

---

[← Services Reference](11-services-reference.md) | [Home](../setup.md)
