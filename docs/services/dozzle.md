# Dozzle

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Real-time Docker container log viewer in the browser.
**Port:** `9999` (host) → `8080` (container) | **Requires:** — | **Memory:** no hard limit set; measured idle ~50MB

## Setup

```bash
uv run homeserver.py dev up dozzle
```

## Using it day to day

No separate client — everything happens in the web UI (`https://dozzle.${DOMAIN}/`). Confirmed against Dozzle's own current docs for the pinned `v10.7.2`:

- **Multi-container view:** the main screen already shows every container side by side; click one (or shift-click several) to follow multiple logs at once, split-screen.
- **Search/filter while streaming:** the search bar supports plain text, regex, and filtering by log level, without pausing the live stream — jump to a timestamp and it keeps following from there.
- **Resource charts:** each container's detail view has a rolling CPU/memory/network history chart alongside its logs, not just the log lines.
- **SQL queries over logs (DuckDB + WebAssembly, runs entirely in-browser):** for structured/JSON logs, Dozzle can run full SQL queries against them client-side — useful for pulling out a specific field across many lines instead of eyeballing them.

## Health endpoint

The compose healthcheck runs `/dozzle healthcheck` — the binary's own built-in subcommand, not an HTTP path (nothing to `curl` from outside the container). Confirmed present in the image via `services/dozzle/compose.yml`.

## Notes

- **Gated behind Authentik forward-auth** — Dozzle has no login of its own, so `dozzle.${DOMAIN}` requires an Authentik login at the nginx layer before any request reaches the container. See [Forward-auth for other services](authentik.md#forward-auth-for-other-services-nginx-auth_request) in `authentik.md` for the mechanism; this vhost's `auth_request` block sits alongside the existing SSE-specific directives (`proxy_buffering off` etc.) in `services/nginx-plain/templates/default.conf.template` without touching them.
- Uses SSE streaming for live logs — nginx config includes `proxy_buffering off`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
