# Dozzle

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Real-time Docker container log viewer in the browser.
**Port:** `9999` (host) → `8080` (container)

## Setup

```bash
sh homeserver.sh dev up dozzle
```

## Notes

- No login by default — restrict via nginx access control if exposed publicly
- Uses SSE streaming for live logs — nginx config includes `proxy_buffering off`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
