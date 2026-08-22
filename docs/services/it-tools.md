# IT-Tools

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** ~80 browser-only dev utilities in one place — JWT decoder, cron parser, hash/UUID/base64 generators, regex tester, and more. Replaces a dozen sketchy websites with one self-hosted page.
**Port:** `8119` (host) → `80` (container) | **Data:** none | **Requires:** nothing | **Memory:** no hard limit set; measured idle ~6MB

## Setup

```bash
cp services/it-tools/.env.example services/it-tools/.env   # no values to fill in
uv run homeserver.py dev up it-tools
```

Open `https://it-tools.<domain>/` (or `http://<host>:8119` in dev).

## Health endpoint

No dedicated `/health` or `/status` route — it's a static nginx site (built from `nginx:stable-alpine` in the upstream Dockerfile, confirmed serving `Server: nginx/1.26.2` on this pinned tag). The compose `healthcheck:` just spiders the site root:

```yaml
test: ["CMD", "wget", "-q", "--spider", "http://127.0.0.1:80/"]
```

Verified live against the running container: `GET /` returns `200 OK` with the app's `index.html` (title `IT Tools - Handy online tools for developers`), and `docker inspect it-tools --format '{{.State.Health.Status}}'` reports `healthy`.

## Notes

- Fully client-side — no backend, no database, nothing sent anywhere. No accounts, no registration. Confirmed against upstream: the app is a Vue.js SPA built to static files and served by nginx with no server-side component at all — there's nothing in the image *to* phone home even if it wanted to.
- GPLv3-licensed, upstream project [CorentinTh/it-tools](https://github.com/CorentinTh/it-tools) ("Collection of handy online tools for developers, with great UX").
- The upstream `corentinth/it-tools` image doesn't publish semver tags, only dated commit-hash tags (e.g. `2024.10.22-7ca5933`, confirmed as GitHub release tag `v2024.10.22-7ca5933`) and a `latest`/`nightly` that track newer builds without a fixed version — pinned here to the dated tag rather than `latest`, but expect to re-check for a newer dated tag manually rather than relying on Watchtower-style auto-update conventions used elsewhere. `2024.10.22-7ca5933` is still the newest dated tag as of this check (~2 years old) — the project has otherwise gone quiet upstream aside from the unversioned `nightly` tag.
- No runtime environment variables exist to configure — confirmed against the upstream Dockerfile: production stage is `nginx:stable-alpine` serving a prebuilt static `dist/` with a fixed `nginx.conf`, no `ARG`/`ENV` exposed at runtime (build-stage-only `NPM_CONFIG_LOGLEVEL`/`CI` vars don't survive into the shipped image). Nothing genuinely useful to add to `.env.example` or a compose `environment:` block — this isn't an oversight, there's nothing upstream exposes to configure.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
