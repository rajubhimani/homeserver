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

- `setup.md`, `docs/`, and `_sidebar.md` — bind-mounted **read-only** straight from the repo root, at the exact same relative paths they already live at (`../../setup.md` → `/usr/share/nginx/html/setup.md`, `../../docs` → `/usr/share/nginx/html/docs`, `../../_sidebar.md` → `/usr/share/nginx/html/_sidebar.md`). Every existing relative link in this doc set (`[Home](../../setup.md)`, `[← Services Reference](../11-services-reference.md)`, etc.) resolves correctly with zero rewriting, because the served directory structure mirrors the repo's own.
- `vendor/` — Docsify core, the search/copy-code/sidebar-collapse plugins, Mermaid + the `docsify-mermaid` plugin (renders ` ```mermaid ` fences as diagrams instead of plain code blocks — see any of this repo's own docs for examples, e.g. `setup.md`'s traffic-flow diagram), and Prism (with `bash`/`yaml`/`json`/`python`/`nginx`/`docker` language components) — all vendored into `services/docs/vendor/` and checked into git, rather than loaded from a CDN at runtime. Keeps the page fully self-hosted and working even with no outbound internet access from the container.

**Persistent sidebar (`_sidebar.md`, `loadSidebar: true` in `index.html`).** An earlier version of this doc argued against a hand-maintained sidebar/nav file, on the grounds that `setup.md`'s own tables already worked as an index and a second nav list would just be one more thing to keep in sync. That held up until the doc tree grew deep enough (per-service docs with their own `##`/`###` sections) that landing on a leaf page left no way back up to sibling sections without returning Home first. `_sidebar.md` (repo root) now mirrors the same category/subcategory grouping used in `setup.md`'s "What's in the stack" section and on the landing page, nested by category → subcategory → service. `sidebarDisplayLevel: 1` keeps only the top-level groups (Setup Guide, Services) expanded on load — everything deeper stays collapsed via the vendored `docsify-sidebar-collapse` plugin until you're actually on a page in that branch, at which point its ancestor chain auto-expands and highlights. `subMaxLevel: 3` additionally appends the *current page's own* `##`/`###` headings under its sidebar entry (e.g. Services → System → Uptime Kuma → Setup → First login), so the in-page outline and the site-wide tree share one control instead of two. **Maintenance cost:** adding a service now means updating `_sidebar.md` alongside `setup.md` and `services.json` — see the `homeserver-add-service` skill's index-files step. The vendored search plugin still covers full-text lookup across every doc for anything you'd rather not click down to.

**Cache-Control is split by content type** (`nginx.conf`): `.md` files and `index.html` are `no-store` — they're fetched live by Docsify's client-side router on every navigation, and a cached stale response would mean an edited doc doesn't show up until a hard refresh. `vendor/` gets a real `max-age=604800` instead — it's a fixed set of library files (`mermaid.min.js` alone is ~3.5MB) that only change when this repo's own vendored copies are updated, so re-fetching them on every page navigation would be pure waste.

## Notes

- **If `setup.md`, `_sidebar.md` (or anything under `docs/`) ever 404s or serves stale content after an edit, recreate the container** — `uv run homeserver.py dev restart docs` does a full recreate, not a bare restart, which fixes it. Root cause: `setup.md` and `_sidebar.md` are bind-mounted as single files, and Docker's file bind mounts track a specific inode, not a path. An editor that saves via write-temp-then-rename (common for atomic writes) replaces that inode — the running container's mount keeps pointing at the now-unlinked old one, and the file appears to vanish inside the container even though `docker inspect` still lists the mount. Hit repeatedly in practice while iterating on `setup.md` in the same session this service was built. **`docs/` itself is a directory bind mount and is not affected** — Docker mounts the directory entry, so file replacement inside it is transparent; only single-file mounts (`setup.md`, `_sidebar.md` here, `services.json` in [landing](../07-landing.md)) have this failure mode.
- **Every link in `_sidebar.md` must be root-absolute (`/docs/...`), never bare (`docs/...`)** — `relativePath: true` in `index.html` makes Docsify resolve *all* relative links, including the sidebar's, against the currently open page rather than the site root. A bare `docs/01-data-drive.md` sidebar link works fine from the homepage but 404s as `docs/services/<whatever-page-you're-on>/01-data-drive` once you're anywhere deeper in the tree — hit this immediately after adding the sidebar. Content-page links (`[Home](../../setup.md)` etc.) are fine as relative because they're hand-written per page to match that page's own depth; `_sidebar.md` is one file rendered from every depth at once, so it doesn't have that luxury.
- **No persistent data, no `.env` beyond `SITE_TITLE`** — this service holds no state of its own; everything it serves already lives elsewhere in the repo (bind-mounted read-only, so a container compromise can't modify source).
- **`CLAUDE.md` and `TODO.md` are deliberately not served** — only `setup.md` and `docs/` are mounted. `CLAUDE.md` is AI-agent instructions, not user-facing reference material; `TODO.md` is a private working list, not linked from `setup.md`'s own doc tree.
- If a doc you expect to find isn't reachable from the homepage or search, check whether it's actually linked from `setup.md` and `_sidebar.md` — an unlinked doc is still reachable directly by URL, just not discoverable via browsing. (`docs/00-services-overview.md` was exactly this case — stale and unlinked — and was deleted rather than fixed, since `setup.md`'s "What's in the stack" section already covered the same ground accurately.)

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
