# Docs

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

A searchable site over every markdown doc in this repo — `setup.md` plus the whole `docs/` tree — rendered with [Docsify](https://docsify.js.org/). No build step, no static-site generator, no copy of the content: the container bind-mounts the repo's own `setup.md` and `docs/` directly, and Docsify renders `.md` files client-side on request. Edit a doc on the host, refresh the browser, see the change — nothing to rebuild or redeploy.

## Setup

```bash
cp services/docs/.env.example services/docs/.env
uv run homeserver.py dev up docs
```

Open `https://docs.<domain>/` (or `http://<host>:8144` in dev).

## Architecture

One container: `nginx:1.28.0-alpine` with a custom `entrypoint.sh` (same `DOMAIN_PLACEHOLDER`-style templating pattern as [landing](../07-landing.md), here just templating `SITE_TITLE` into `index.html`) serving:

- `setup.md` and `docs/` — bind-mounted **read-only** straight from the repo root, at the exact same relative paths they already live at (`../../setup.md` → `/usr/share/nginx/html/setup.md`, `../../docs` → `/usr/share/nginx/html/docs`). Every existing relative link in this doc set (`[Home](../../setup.md)`, `[← Services Reference](../11-services-reference.md)`, etc.) resolves correctly with zero rewriting, because the served directory structure mirrors the repo's own.
- `vendor/` — Docsify core, the search/copy-code/sidebar-collapse plugins, Mermaid + the `docsify-mermaid` plugin (renders ` ```mermaid ` fences as diagrams instead of plain code blocks — see any of this repo's own docs for examples, e.g. `setup.md`'s traffic-flow diagram), and Prism (with `bash`/`yaml`/`json`/`python`/`nginx`/`docker` language components) — all vendored into `services/docs/vendor/` and checked into git, rather than loaded from a CDN at runtime. Keeps the page fully self-hosted and working even with no outbound internet access from the container.

**No hand-maintained sidebar/nav file.** `setup.md` (Docsify's configured `homepage`) already functions as a full index — the "What's in the stack" table links every per-service doc, and the "Setup path" table links every numbered `docs/NN-*.md` guide — so there's no second nav list to keep in sync as docs are added (`_sidebar.md` would be exactly that problem). The vendored search plugin covers full-text lookup across every doc for anything not directly linked from the homepage.

**Cache-Control is split by content type** (`nginx.conf`): `.md` files and `index.html` are `no-store` — they're fetched live by Docsify's client-side router on every navigation, and a cached stale response would mean an edited doc doesn't show up until a hard refresh. `vendor/` gets a real `max-age=604800` instead — it's a fixed set of library files (`mermaid.min.js` alone is ~3.5MB) that only change when this repo's own vendored copies are updated, so re-fetching them on every page navigation would be pure waste.

## Notes

- **If `setup.md` (or anything under `docs/`) ever 404s or serves stale content after an edit, recreate the container** — `uv run homeserver.py dev restart docs` does a full recreate, not a bare restart, which fixes it. Root cause: `setup.md` is bind-mounted as a single file (`../../setup.md:/usr/share/nginx/html/setup.md:ro`), and Docker's file bind mounts track a specific inode, not a path. An editor that saves via write-temp-then-rename (common for atomic writes) replaces that inode — the running container's mount keeps pointing at the now-unlinked old one, and the file appears to vanish inside the container even though `docker inspect` still lists the mount. Hit repeatedly in practice while iterating on `setup.md` in the same session this service was built. **`docs/` itself is a directory bind mount and is not affected** — Docker mounts the directory entry, so file replacement inside it is transparent; only single-file mounts (`setup.md` here, `services.json` in [landing](../07-landing.md)) have this failure mode.
- **No persistent data, no `.env` beyond `SITE_TITLE`** — this service holds no state of its own; everything it serves already lives elsewhere in the repo (bind-mounted read-only, so a container compromise can't modify source).
- **`CLAUDE.md` and `TODO.md` are deliberately not served** — only `setup.md` and `docs/` are mounted. `CLAUDE.md` is AI-agent instructions, not user-facing reference material; `TODO.md` is a private working list, not linked from `setup.md`'s own doc tree.
- If a doc you expect to find isn't reachable from the homepage or search, check whether it's actually linked from `setup.md` — `docs/00-services-overview.md` is a known example that predates this site and isn't linked from anywhere; it's still reachable directly by URL, just not discoverable via browsing.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
