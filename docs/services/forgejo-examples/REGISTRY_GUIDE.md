# Forgejo Package & Container Registry Guide

[← Forgejo](../forgejo.md) | [Home](../../../setup.md)

---

Reference for pulling/pushing container images and Python packages against
this Forgejo instance. Both registries are enabled by default (no extra
config needed) and store their contents under `service_data/data/forgejo/`
alongside the rest of Forgejo's data.

## 1. Container Registry (Docker/Podman)

```bash
docker login forgejo.prajnatech.in
docker pull forgejo.prajnatech.in/<owner>/<image>:latest
docker push forgejo.prajnatech.in/<owner>/<image>:latest
```

`<owner>` is the Forgejo username or org the image belongs to — the registry
namespace is owner/image, it doesn't require a repository name in the path.
See `build-and-push.yml` in this directory for a CI workflow that logs in
and pushes automatically using Forgejo's own repo-scoped Actions token
(no manual credential setup needed for same-instance pushes).

## 2. Python Package Registry (pip)

### Public packages (no auth)

```bash
pip install --index-url https://forgejo.prajnatech.in/api/packages/<owner>/pypi/simple/ <package-name>
```

### Private packages (auth required)

1. In Forgejo: **Settings → Applications → Generate New Token**, scope it to
   `read:package` (or `write:package` if you're also publishing).
2. Install with the token embedded:

```bash
pip install --index-url https://<username>:<token>@forgejo.prajnatech.in/api/packages/<owner>/pypi/simple/ <package-name>
```

### Publishing a package

```bash
pip install twine
python -m build
twine upload --repository-url https://forgejo.prajnatech.in/api/packages/<owner>/pypi/ \
  -u <username> -p <token> dist/*
```

## Notes

- Visibility (public vs. private) follows the *owning repository's* visibility
  setting in Forgejo, not a separate registry-level toggle — check
  **Repository → Settings → Visibility** if a package isn't pulling
  anonymously as expected.
- These endpoints require `https://forgejo.prajnatech.in` (matching
  `FORGEJO__server__ROOT_URL` in `services/forgejo/compose.yml`) — Cloudflare
  terminates TLS in front of this instance, so plain `http://` will not work
  from outside the Docker network.

---

[← Forgejo](../forgejo.md) | [Home](../../../setup.md)
