# Stirling PDF (Lite + Full)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Two variants, run independently:

| Variant | Port | Image | Tier | Measured idle RAM |
| --- | --- | --- | --- | --- |
| Lite | `8090` → `8080` | `stirlingtools/stirling-pdf:2.14.2-ultra-lite` | `SERVICES_EXTRA`, always on | **1.13 GiB** |
| Full | `8089` → `8080` | `stirlingtools/stirling-pdf:2.14.2` | manual-only | **1.19 GiB** |

**Requires:** — | **Memory:** no hard limit set in compose.yml. Both variants are JVM (Spring Boot) apps with a large baseline heap — despite the "lite"/"ultra-lite" naming, idle RAM is nearly identical between the two and much higher than the name suggests. This is a correction of a previous, unverified estimate in this doc (~200MB/~1.5GB) — the numbers above were independently measured via `docker stats` on a freshly-settled container.

## Setup — Lite (default, always on)

```bash
cp services/stirling-pdf-lite/.env.example services/stirling-pdf-lite/.env
uv run homeserver.py dev up stirling-pdf-lite
```

**No login on Lite, by design of the image, not this config:** the `ultra-lite` tag is built without Stirling-PDF's security module — its startup logs never show a `security` Spring profile active, unlike Full. `STIRLING_ADMIN_USER` / `STIRLING_ADMIN_PASSWORD` in `.env` and `SECURITY_ENABLELOGIN=true` in `compose.yml` are set but have no effect on this image; `GET /` returns `200` straight into the app instead of the `401` Full gives unauthenticated. There's no "lite with login" tag upstream — only plain, `-fat`, and `-ultra-lite` exist. Left open deliberately (same posture as mailpit etc. — relies on the Cloudflare Tunnel being the only way in); switching to a login-capable image means dropping to the plain/`-fat` tag, which is functionally redundant with the Full variant already running below.

## Setup — Full (manual, OCR + LibreOffice conversion)

Not part of `all` — start manually when needed, stop when done to free RAM:

```bash
uv run homeserver.py dev up stirling-pdf
uv run homeserver.py dev down stirling-pdf
```

`SECURITY_INITIALLOGIN_USERNAME` / `SECURITY_INITIALLOGIN_PASSWORD` in `.env` set the admin login at startup (same mechanism as Lite, just under the raw Stirling-PDF property names since Full's `.env` passes through unmapped).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
