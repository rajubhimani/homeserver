# OrangeHRM

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source HR management — employee records, leave, time tracking, recruitment.
**Port:** `8125` (host) → `80` (container) | **Data:** ⚠ none persisted yet, see below | **Requires:** MariaDB

## ⚠ Best-effort setup — OrangeHRM's Docker packaging is weaker than every other service in this stack

Two official-ish Docker paths exist for OrangeHRM, and neither is in great shape:

- **Bitnami's image** (`bitnami/orangehrm`) has proper env-var-driven DB wiring (matches this stack's usual pattern) but is **deprecated and archived** (`bitnami/orangehrm-archived`), stuck on an old PHP version with no further security patches. Not used here for that reason.
- **The actual official `orangehrm/orangehrm` image** (used here) has sparse, dated documentation: the upstream wiki's own install instructions still describe finding the container's IP via `docker inspect` and connecting the database through the web installer UI rather than any documented env-var scheme. There's no confirmed `ORANGEHRM_DATABASE_*`-style env var support in the current image.

This `compose.yml` uses standard container-name networking (`orangehrm-db` on the shared `homeserver` network) instead of the wiki's manual IP-lookup approach, which should work the same way every other multi-container service here does — but **the DB connection step still has to be completed through OrangeHRM's own web installer on first visit**, pointing it at host `orangehrm-db`, port `3306`, and the credentials from `.env`. This is not fully pre-wired like every other service in this stack.

### No persistent data volume — needs follow-up before real use

Verified by inspecting a running container: the app root is `/var/www/html` (not `/var/www/html/orangehrm` — an earlier guess in this doc was wrong and has been corrected). Config/upload paths that would need persisting (`src/config`, `web/images`, etc.) aren't populated until the web installer actually runs, and blind-mounting a host directory over any of those paths risks **silently overlaying and losing the baked-in app files that ship inside the image** (bind mounts replace, they don't merge). Rather than guess again, `compose.yml` currently mounts nothing for the app container — **all app state lives only inside the container and is lost if it's recreated.**

To fix this properly: run the web installer once, then inspect the container (`docker exec -it orangehrm find /var/www/html -newer /var/www/html/index.php -maxdepth 3`) to see exactly which paths the installer wrote to, and add bind mounts for those specific subdirectories only — never the app root.

## Setup

```bash
cp services/orangehrm/.env.example services/orangehrm/.env
# set MYSQL_ROOT_PASSWORD and MYSQL_PASSWORD
uv run homeserver.py dev up orangehrm
```

Open `https://orangehrm.<domain>/` (or `http://<host>:8125` in dev) and complete the web installer's database step. `services/orangehrm/.env`'s `MYSQL_DATABASE`/`MYSQL_USER` already exist and are pre-granted full privileges on that database by the time you reach this screen (the official MariaDB image creates both automatically from those env vars on first boot) — so pick **"Existing Empty Database"**, not "New Database":

### Select Database to Use → Existing Empty Database

| Field | Value |
| --- | --- |
| Database Host Name | `orangehrm-db` |
| Database Host Port | `3306` |
| Database Name | `MYSQL_DATABASE` from `.env` |
| OrangeHRM Database Username | `MYSQL_USER` from `.env` |
| OrangeHRM Database User Password | `MYSQL_PASSWORD` from `.env` |
| Enable Data Encryption | Recommended if this will ever hold real employee PII — not otherwise verified against this stack's backup/restore tooling, so treat encrypted DB dumps as something to test-restore once before relying on it |

Click Next to continue.

### If you ever use "New Database" instead (not this stack's default path)

Only relevant if the database doesn't already exist yet — e.g. you're pointing the installer at a fresh MariaDB instance that hasn't run the container's own `MYSQL_DATABASE` auto-create. The installer creates the database and (optionally) the app user itself, so it needs root, not the scoped app user:

| Field | Value |
| --- | --- |
| Database Host Name | `orangehrm-db` |
| Database Host Port | `3306` |
| Database Name | `MYSQL_DATABASE` from `.env` (or any new name) |
| Use the same Database User for OrangeHRM | Leave unchecked — don't run the app as `root` day-to-day |
| Privileged Database Username | `root` |
| Privileged Database User Password | `MYSQL_ROOT_PASSWORD` from `.env` |
| OrangeHRM Database Username | `MYSQL_USER` from `.env` |
| OrangeHRM Database User Password | `MYSQL_PASSWORD` from `.env` |
| Enable Data Encryption | Same recommendation as above |

## Connecting the Android app

Official **OrangeHRM Open Source** app ([Google Play](https://play.google.com/store/apps/details?id=com.orangehrm.opensource)) — needs Web Version `5.4+`; this stack pins `5.9` (`orangehrm/orangehrm:5.9`), so it clears that. On first launch, enter the instance URL `https://orangehrm.${DOMAIN}` and log in with an employee account. Requires a valid SSL certificate on the URL (Cloudflare Tunnel already provides this) — covers leave requests, attendance, and performance from the app.

## Registration

None — HR admin creates employee accounts from inside the app after setup. No public signup, no env var toggle applies.

## Notes

- `orangehrm-db` uses `mariadb:11.4`, **not** the stack-wide `mariadb:12.3.3` default every other MariaDB-backed service uses — confirmed via the web installer's own compatibility check, OrangeHRM requires MariaDB `>5` and `<12`. Don't bump this one to match the stack-wide default without re-checking that requirement first.
- No confirmed health/status endpoint — both the compose healthcheck and the landing-page health route just check that `/` responds.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
