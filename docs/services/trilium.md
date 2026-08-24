# Trilium Notes

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Hierarchical, scriptable notes app with a proper attribute/relation system — a personal wiki + database hybrid, not a pile of markdown files.
**Port:** `8112` (host) → `8080` (container) | **Data:** `service_data/data/trilium/` | **Requires:** nothing (bundled SQLite, no external DB) | **Memory:** no hard limit set; measured idle ~118MB

## Setup

```bash
cp services/trilium/.env.example services/trilium/.env
uv run homeserver.py dev up trilium
```

Open `https://trilium.<domain>/` (or `http://<host>:8112` in dev) and follow the first-run setup wizard to set the login password.

## Registration

None — Trilium is single-user by design, no signup toggle applies.

## Connecting desktop and mobile clients (sync)

This container is the **sync server**; the web UI above is only one way to reach it. For daily use, the desktop app is the more common driver — it works offline and syncs to this server in the background:

1. Download the build for your OS from [TriliumNext/Trilium releases](https://github.com/TriliumNext/Trilium/releases/latest) (Windows/Mac/Linux — unzip and run, no installer).
2. On first launch, the setup wizard offers a choice of what to do — pick **"I have a server instance already, and I want to set up sync with it."**
3. Enter the server address (`https://trilium.<domain>/`) and the same username/password set on the server's own first-run wizard above.
4. Click **Test sync** — on success the client and server exchange data (the first sync can take a while against an existing note tree; you can keep working while it runs). After that, sync is automatic and continuous — no manual "sync now" step needed day to day.

Two prerequisites that cause silent failures if missed: client and server clocks must be within 5 minutes of each other, and the server must be reached over HTTPS with a valid cert — both already true here via the Cloudflare tunnel.

**Mobile:** there's no official Trilium mobile app — the same server automatically serves a touch-friendly mobile UI when `https://trilium.<domain>/` is opened from a phone's browser, no separate URL or setup. Unofficial third-party native clients exist if wanted (TriliumDroid and Pocket Trilium for Android, Trinote for iOS) but aren't required and haven't been verified against this stack.

**Web Clipper (optional):** to save web pages into Trilium directly from the browser, install "Trilium Web Clipper" (Firefox: [addons.mozilla.org](https://addons.mozilla.org/en-US/firefox/addon/trilium-notes-web-clipper/)) or "Trilium Web Clipper Plus" (the Manifest V3 fork on the Chrome Web Store, since Google delisted the original Chrome build) and point it at the same server address.

## Notes

- Data (notes DB + attachments) lives entirely under `service_data/data/trilium/trilium-data/` — no Postgres/MariaDB container needed.
- Health endpoint: `/api/health-check`.
- Scripting (JS) and the attribute/relation system are the main differentiator vs. a plain markdown notes app — see Trilium's own docs for the query/scripting API once running.
- UI is dated compared to Obsidian/Notion; community is small. Chosen here for structure (attributes/relations) over polish.
- `TRILIUM_NETWORK_TRUSTEDREVERSEPROXY` must be left **empty**, not `false` — setting it to the literal string `false` crashes the app entirely (`TypeError: invalid IP address: false`, confirmed while re-verifying this setup after adding it as a documented default). This var expects an IP/CIDR value or nothing, not a boolean-style string.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
