# Bichon

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Lightweight email archiver: pulls mail from any IMAP account (password or OAuth2) and gives you very fast full-text search, tags, conversation threads, an attachment browser and a contacts view. Single Rust binary, no database container.
**Port:** `8154` (host) → `15630` (container) | **Data:** `bichon-data` named volume (index + compressed mail + metadata) | **Requires:** nothing | **Memory:** no hard limit set; upstream recommends 2GB+ RAM for 10+ accounts / 200GB+ of mail; measured idle with an empty archive ~22MB

Upstream: [github.com/rustmailer/bichon](https://github.com/rustmailer/bichon).

Not an email client: it archives, searches and restores, but can't compose/reply/send. Compared with [Mail-Archiver](mail-archiver.md) (also in this stack): Bichon is lighter and has the nicer search/browsing, but it only speaks IMAP (no Microsoft Graph), and it has no built-in "copy this mailbox into a different provider" feature. Its restore puts mail back into the *original* account.

## Setup

```bash
cp services/bichon/.env.example services/bichon/.env
# set BICHON_ENCRYPT_PASSWORD (openssl rand -hex 32) — and save a copy of it somewhere safe
uv run homeserver.py dev up bichon
```

Open `https://bichon.<domain>/` (or `http://<host>:8154` in dev).

## Admin account

Created automatically on first start: username `admin`, password `admin@bichon` (confirmed on first bring-up). **Change it immediately:** Settings → Profile. There's no env var to set it up front.

## Adding accounts

**Accounts → Add**. Type the email address; Bichon auto-discovers the IMAP server for most providers. You can also set a sync schedule per account (cron), limit which folders or dates are fetched, and route an account through a SOCKS5 proxy.

**Microsoft 365 / Outlook:** Microsoft has turned off password logins for IMAP, so these need OAuth2. First add an OAuth2 provider (Settings → OAuth2, admin only) with a Microsoft Entra app registration:

- delegated permission `IMAP.AccessAsUser.All` plus `offline_access`
- the redirect URI Bichon shows you, which is built from `BICHON_PUBLIC_URL` (already set to `https://bichon.${DOMAIN}` in compose.yml)

Then choose OAuth2 when adding the account and sign in. **Not yet tested end to end against M365 in this stack.** If you need M365 archiving that definitely works, [Mail-Archiver](mail-archiver.md)'s Graph API connector is the proven route.

## Import / export

- **From the web UI:** upload `.eml` files, and bulk-restore messages back to their IMAP account.
- **MBOX export, and MBOX/PST/Thunderbird import,** need `bichon-cli`. It is **not included in the Docker image** (confirmed: `/opt/bichon/` only contains `bichon-server`). Download it from [Releases](https://github.com/rustmailer/bichon/releases) and run it from any machine. It talks to the server over the REST API with an API token (Settings → API Tokens).

## Backups

Everything lives in the `bichon-data` named volume. `homeserver.py down bichon` snapshots it into `service_data/backup/bichon/` like any other named volume. The index, blob store and metadata DB must be backed up together, and a stopped container gives a consistent snapshot. Mail is stored compressed and deduplicated (identical bodies/attachments are stored once), so the volume is usually smaller than the mailbox.

Deliberately a named volume rather than a `service_data/` bind mount: upstream warns that the index gets corrupted on network or unusual filesystems, and `service_data/` sits on an NTFS/fuseblk drive.

## Gotchas

- **`BICHON_ENCRYPT_PASSWORD` can't be rotated.** It encrypts the stored IMAP passwords and OAuth tokens, and upstream doesn't support re-encrypting. Changing it means re-entering every account's credentials. Keep it in Vaultwarden.
- **Auth.** Has its own login with real RBAC (5 built-in roles plus custom roles, per-account access), so it isn't behind Authentik forward-auth (bucket D, see [auth posture](../13-auth-posture.md)). The image also has an OIDC login endpoint for later SSO via Authentik.
- **CORS.** `BICHON_CORS_ORIGINS` is left unset (all origins allowed). The web UI uses bearer tokens rather than cookies, so this doesn't open a CSRF hole. Set it (exact origins, comma-separated, no quotes, no trailing slash) if you want to lock it down.
- **Remote images** and tracking pixels in archived mail are blocked by default; you can allow them per message.
