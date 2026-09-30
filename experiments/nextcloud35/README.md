# experiments/nextcloud35

A throwaway copy of the live Nextcloud (`services/nextcloud`, 34.x) running
on the **Nextcloud 35** image. It lets you try the 35 upgrade against real
data before touching the real instance.

**Not part of the real stack.** It isn't managed by `homeserver.py` and isn't on
the shared `homeserver` Docker network. It has its own isolated network, container
names (`nextcloud35*`) and volumes (`nextcloud35_nextcloud35-*`), so it can't reach
the real `nextcloud-db`/`nextcloud-redis`. The OS-ISO external storage is mounted
read-only.

## Run it

```bash
cd experiments/nextcloud35
cp ../../services/nextcloud/.env .env   # same credentials as live; gitignored
./clone.sh                              # or ./clone.sh --reset to re-clone from scratch
docker logs -f nextcloud35              # watch the 34 -> 35 upgrade
```

Open <http://localhost:8095> on the host (OnlyOffice's editor runs on :8097), or `http://10.8.0.1:8095` over
WireGuard. Log in with your normal Nextcloud account.

`clone.sh` only reads from the live instance: it runs `pg_dump` and mounts the
live volumes read-only. It never uses maintenance mode or restarts, so the live
instance keeps serving while it runs.

After the first start, two apps need their NC35 release pulled in (see findings):

```bash
docker exec -u www-data nextcloud35 php occ app:update spreed
docker exec -u www-data nextcloud35 php occ app:update quota_warning
docker exec -u www-data nextcloud35 php occ app:enable spreed quota_warning
```

Stop it with `docker compose down`, or run `docker compose down -v` to delete the sandbox's data.

## What's different from live, on purpose

- **No cron container.** Background jobs are set to cron mode and never run. So the
  Mail app doesn't sync real mailboxes, and no notifications or emails go out.
  Opening Mail in the browser *does* talk to the real IMAP server, so don't
  send mail from here.
- **`files_antivirus` is disabled,** because ClamAV lives on the real
  `homeserver` network.
- **OnlyOffice runs a separate copy inside the sandbox** (`nextcloud35-onlyoffice`,
  same 9.4.0.1 image, its own JWT secret in `.env`, editor served on port 8097).
  The live OnlyOffice isn't used, for three reasons: it won't fetch files from a
  private-IP storage URL, it's on the real network, and the cloned
  `oc_onlyoffice_filekey` rows would give the sandbox the *same* document keys as
  live. One key open on both instances would be one shared editing session.
  `clone.sh` clears that table so the sandbox gets its own keys.
  The editor URL is `http://localhost:8097/`. If you use the sandbox over WireGuard,
  set `NEXTCLOUD35_ONLYOFFICE_PUBLIC_URL=http://10.8.0.1:8097/` in `.env` and run
  `docker compose up -d nextcloud35`.
- **Whiteboard editing won't work.** Its backend is on the real network and domain.

## Findings (2026-09-30, 34.0.4 -> 35.0.1)

1. **The upgrade aborts with `HMAC does not match`.** Cause:
   `notifications.webpush_vapid_privkey` in `oc_appconfig` was encrypted with a
   different `secret` than `config.php` has now, probably from an earlier
   reinstall. The live 34 instance already logs this error on every
   notifications poll, but only NC35's upgrade treats it as fatal. The fix is to
   delete the `webpush_vapid_privkey`/`webpush_vapid_pubkey` pair so
   Notifications generates a fresh one. `oc_notifications_webpush` had 0 rows,
   so nothing is lost. `clone.sh` does this automatically; **the live instance
   needs the same fix before its real upgrade.**
2. **The upgrade disables apps it considers incompatible:** `deck`, `spreed`
   (Talk) and `quota_warning`. Deck came back on its own (1.19.0, pulled from
   the App Store during the upgrade). Talk 25.0.2 and quota_warning 1.25.0 needed
   the `app:update` + `app:enable` above.
3. After that, `occ status` reports 35.0.1.1 with `needsDbUpgrade: false`, and
   the login page and `status.php` both return 200.
