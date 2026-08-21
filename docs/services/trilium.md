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

## Notes

- Data (notes DB + attachments) lives entirely under `service_data/data/trilium/trilium-data/` — no Postgres/MariaDB container needed.
- Health endpoint: `/api/health-check`.
- Scripting (JS) and the attribute/relation system are the main differentiator vs. a plain markdown notes app — see Trilium's own docs for the query/scripting API once running.
- UI is dated compared to Obsidian/Notion; community is small. Chosen here for structure (attributes/relations) over polish.
- `TRILIUM_NETWORK_TRUSTEDREVERSEPROXY` must be left **empty**, not `false` — setting it to the literal string `false` crashes the app entirely (`TypeError: invalid IP address: false`, confirmed while re-verifying this setup after adding it as a documented default). This var expects an IP/CIDR value or nothing, not a boolean-style string.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
