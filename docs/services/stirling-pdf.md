# Stirling PDF (Lite + Full)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Two variants, run independently:

| Variant | Port | Image | Tier | Measured idle RAM |
| --- | --- | --- | --- | --- |
| Lite | `8090` → `8080` | `stirlingtools/stirling-pdf:latest-ultra-lite` | `SERVICES_EXTRA`, always on | **1.13 GiB** |
| Full | `8089` → `8080` | `stirlingtools/stirling-pdf:latest` | manual-only | **1.19 GiB** |

**Requires:** — | **Memory:** no hard limit set in compose.yml. Both variants are JVM (Spring Boot) apps with a large baseline heap — despite the "lite"/"ultra-lite" naming, idle RAM is nearly identical between the two and much higher than the name suggests. This is a correction of a previous, unverified estimate in this doc (~200MB/~1.5GB) — the numbers above were independently measured via `docker stats` on a freshly-settled container.

## Setup — Lite (default, always on)

```bash
cp services/stirling-pdf-lite/.env.example services/stirling-pdf-lite/.env
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
