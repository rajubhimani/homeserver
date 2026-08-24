# Stirling PDF (Lite + Full)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Two variants, run independently:

| Variant | Port | Image | Tier | Measured idle RAM |
| --- | --- | --- | --- | --- |
| Lite | `8090` → `8080` | `stirlingtools/stirling-pdf:2.14.2-ultra-lite` | `SERVICES_EXTRA`, always on | **274MB** |
| Full | `8089` → `8080` | `stirlingtools/stirling-pdf:2.14.2` | manual-only | **505MB** |

**Requires:** — | **Memory:** no hard limit set in compose.yml. Both variants are JVM (Spring Boot) apps with a large baseline heap — despite the "lite"/"ultra-lite" naming, idle RAM is much higher than the name suggests. This is a correction of a previous, unverified estimate in this doc (~200MB/~1.5GB) — the numbers above were independently measured via `docker stats` on a freshly-settled container.

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

## Using it day to day

Both variants share the same web UI shape — a tool grid/sidebar at their respective port, pick a tool, upload a PDF, download the result. Everyday structural tools work on **both**: merge, split, rotate/reorder pages, compress, add/remove/change passwords, add watermarks, add page numbers, flatten, redact, sign.

**OCR and format conversion (PDF ↔ Word/PowerPoint/images via LibreOffice) only exist on Full** — the `ultra-lite` image is built without Tesseract or LibreOffice at all, so those tool cards either don't appear or fail on Lite. Reach for Full (`up stirling-pdf`) specifically for those, then `down stirling-pdf` again afterward to free the RAM.

### API access (Full only — Lite has no login, see above)

Full exposes a REST API for every tool it has a UI for, useful for scripting instead of clicking through the browser (n8n, cron jobs, batch processing):

1. Log in, then **Account Settings** (gear icon, top right) to find/generate an API key.
2. Call any endpoint under `/api/v1/<category>/<operation>` (categories include `security`, `general`, `misc`, `convert`) with the key in the `X-API-KEY` header:

   ```bash
   curl -X POST "http://<host>:8089/api/v1/security/add-watermark" \
        -H "X-API-KEY: your-api-key-here" \
        -F "fileInput=@/path/to/file.pdf" \
        -F "watermarkType=text" \
        -F "watermarkText=CONFIDENTIAL"
   ```

3. Full interactive reference for every endpoint/parameter: `http://<host>:8089/swagger-ui/index.html`.

Upstream also supports `SECURITY_CUSTOMGLOBALAPIKEY` (one shared key for every request instead of per-user keys) — not currently set in this stack's `.env.example`, add it there if a single static key is preferred over per-user ones. Lite has no login and therefore no API key concept at all — its endpoints are open to anyone who can reach port `8090`, same posture as the rest of its UI.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
