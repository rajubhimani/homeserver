# SilverBullet

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Markdown notes with a query language over your own space — lightweight, no plugin sprawl.
**Port:** `8113` (host) → `3000` (container) | **Data:** `service_data/data/silverbullet/` | **Requires:** nothing (plain markdown files on disk, no DB)

## Setup

```bash
cp services/silverbullet/.env.example services/silverbullet/.env
# set SB_USER to username:password
uv run homeserver.py dev up silverbullet
```

Open `https://silverbullet.<domain>/` (or `http://<host>:8113` in dev) and log in with the `SB_USER` credentials.

## Registration

None — single space, single basic-auth login set via `SB_USER` in `.env` (format `username:password`). No public signup exists to toggle.

## Notes

- Notes are plain markdown files under `service_data/data/silverbullet/space/` — greppable, syncable, versionable like any other file tree.
- Health endpoint: `/.ping`.
- The built-in query language (`query` blocks over frontmatter/tags) is the main differentiator vs. a plain markdown folder — see SilverBullet's own docs for query syntax once running.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
