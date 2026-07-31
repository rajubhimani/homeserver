# IT-Tools

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** ~80 browser-only dev utilities in one place — JWT decoder, cron parser, hash/UUID/base64 generators, regex tester, and more. Replaces a dozen sketchy websites with one self-hosted page.
**Port:** `8119` (host) → `80` (container) | **Data:** none | **Requires:** nothing

## Setup

```bash
cp it-tools/.env.example it-tools/.env   # no values to fill in
uv run homeserver.py dev up it-tools
```

Open `https://it-tools.<domain>/` (or `http://<host>:8119` in dev).

## Notes

- Fully client-side — no backend, no database, nothing sent anywhere. No accounts, no registration.
- The upstream `corentinth/it-tools` image doesn't publish semver tags, only dated commit-hash tags (e.g. `2024.10.22-7ca5933`) and a `latest` that tracks the same digest — pinned here to the dated tag rather than `latest`, but expect to re-check for a newer dated tag manually rather than relying on Watchtower-style auto-update conventions used elsewhere.
- No health/status endpoint beyond `/` itself (static file serving).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
