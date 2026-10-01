# Shared MariaDB

One MariaDB 11.8 (LTS) server (`shared-mariadb`) for the services **above CORE** that declare `"shared_db": {"engine": "mariadb", ...}` in `services.json`. It works exactly like [shared-postgres](shared-postgres.md): same reference-counted lifecycle, same `shared_db` field, same snapshot/restore behaviour. Only the MariaDB-specific parts are listed here.

**Port:** none published (`shared-mariadb:3306` on the `homeserver` network) | **Data:** named volume `shared-mariadb_shared-mariadb-data` | **Memory:** capped 768M; `innodb-buffer-pool-size=256M`, `max-connections=100`

## Setup

```bash
cp services/shared-mariadb/.env.example services/shared-mariadb/.env
# set MARIADB_ROOT_PASSWORD (admin only — never given to any app)
```

## Why 11.8

It's the one version every intended user accepts. OrangeHRM's installer requires MariaDB below 12; BookStack and InvoiceShelf only set minimums. ERPNext also wants 11.8, but keeps its own `erpnext-db`, because Frappe needs root to create its sites and it holds real business data. `MARIADB_AUTO_UPGRADE=1` runs `mariadb-upgrade` after any image bump.

## MariaDB specifics

- **Provisioning** runs as root: `CREATE USER IF NOT EXISTS '<user>'@'%'`, then `ALTER USER` (password from the app's `.env`). After that it runs `CREATE DATABASE IF NOT EXISTS` (utf8mb4 / utf8mb4_unicode_ci) and `GRANT ALL ON <db>.*` to that user only.
- **Snapshots** include `<app>_shareddb_<db>_<ts>.sql` from `mariadb-dump --single-transaction --routines --triggers`. **Restore** drops the database, re-provisions it, and loads the SQL.
- The root password reaches the container via `docker exec -e MYSQL_PWD` taken from the environment, never as a command-line argument.

## Status

Created 2026-10-01. BookStack is the first user and was converted as the pilot, verified live: auto-start, provisioning (user granted on its own database only), snapshot `.sql` dump, backup → drop → restore round trip, and auto-stop when it went down. InvoiceShelf and OrangeHRM follow.
