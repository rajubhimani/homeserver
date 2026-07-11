# Stirling PDF (Lite + Full)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Two variants, run independently:

| Variant | Port | Image | Tier | RAM |
| --- | --- | --- | --- | --- |
| Lite | `8090` → `8080` | `stirlingtools/stirling-pdf:latest-ultra-lite` | `SERVICES_EXTRA`, always on | ~200MB |
| Full | `8089` → `8080` | `stirlingtools/stirling-pdf:latest` | manual-only | ~1.5GB |

## Setup — Lite (default, always on)

```bash
cp stirling-pdf-lite/.env.example stirling-pdf-lite/.env
uv run homeserver.py dev up stirling-pdf-lite
```

`STIRLING_ADMIN_USER` / `STIRLING_ADMIN_PASSWORD` in `.env` set the admin login at startup.

## Setup — Full (manual, OCR + LibreOffice conversion)

Not part of `all` — start manually when needed, stop when done to free RAM:

```bash
uv run homeserver.py dev up stirling-pdf
uv run homeserver.py dev down stirling-pdf
```

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
