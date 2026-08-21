# Dozzle

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Real-time Docker container log viewer in the browser.
**Port:** `9999` (host) → `8080` (container) | **Requires:** — | **Memory:** no hard limit set; measured idle ~50MB

## Setup

```bash
uv run homeserver.py dev up dozzle
```

## Notes

- **Gated behind Authentik forward-auth** — Dozzle has no login of its own, so `dozzle.${DOMAIN}` requires an Authentik login at the nginx layer before any request reaches the container. See [Forward-auth for other services](authentik.md#forward-auth-for-other-services-nginx-auth_request) in `authentik.md` for the mechanism; this vhost's `auth_request` block sits alongside the existing SSE-specific directives (`proxy_buffering off` etc.) in `services/nginx-plain/templates/default.conf.template` without touching them.
- Uses SSE streaming for live logs — nginx config includes `proxy_buffering off`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
