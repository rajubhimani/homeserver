# Portainer CE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Docker container management UI.
**Port:** `9000` (HTTP) or `9445` (HTTPS, host-mapped off the image's default `9443` — that port is claimed locally by the `kind` k8s-pilot cluster's ingress) | **Data:** `service_data/data/portainer/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~38MB

## Setup

```bash
cp services/portainer/.env.example services/portainer/.env
uv run homeserver.py dev up portainer
```

## First login

Create the admin account on first visit — the setup prompt times out after a few minutes, so don't leave it sitting.

This container already manages **this** host out of the box — it mounts `${DOCKER_SOCKET}` directly, so the `local` environment is there with nothing further to connect.

## Connecting another Docker host

Only needed if you want this same Portainer to manage a *second* machine's containers — this stack's own services (all on this one host) need nothing here. Confirmed against Portainer CE's own current docs.

1. On the target machine, run the agent Portainer gives you (**Environments** → **Add environment** → **Docker Standalone** → **Start Wizard** → **More options** → **Agent**) — it shows the exact `docker run` command for that OS, publishing the Portainer Agent on port `9001` and mounting that host's Docker socket (plus `/:/host` for host-level features).
2. Back in this Portainer, finish the wizard: give the environment a **Name**, and for **Environment URL** enter the remote host's DNS name/IP plus `:9001` (the agent's default port).
3. Click **Connect**. The new environment then shows up in the environment switcher, with its own Containers/Images/Volumes/Stacks views, independent of this host's.

## Using it day to day

Everything happens in the Portainer web UI, confirmed against Portainer CE's own current docs.

- **Containers** (left nav): the main list of every container on this host — including ones started outside Portainer entirely, like this whole stack via `homeserver.py`. Start/stop/restart, view logs, open a console/exec session, and check per-container CPU/memory stats, all without dropping to the CLI.
- **Images:** shows whether each running container's image is up to date against its registry (green check / orange cross / grey dash) — pull a newer image or remove an unused one from here.
- **Volumes:** browse and remove Docker volumes directly — useful for spotting orphaned volumes left behind by a container that was torn down manually instead of through `homeserver.py down`.
- **Stacks:** Portainer's own compose-deployment feature (web editor, file upload, or a Git repo). This repo's services aren't managed as Portainer stacks — `homeserver.py` is the entrypoint for those — but Stacks is there for one-off compose experiments independent of this repo's tooling.
- In short: the fastest way to answer "what's actually running and how much RAM is it using right now" without `docker ps`/`docker stats` on the host itself.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
