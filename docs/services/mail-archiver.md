# Mail-Archiver

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Keeps a continuously-synced copy of your real mailboxes on this server, so the mail provider becomes swappable: drop Microsoft 365 (or anyone else) whenever you like, then copy the whole history into the new provider from the same UI. Also a searchable archive in its own right.
**Port:** `8153` (host) → `5000` (container) | **Data:** `mail-archiver-postgres` named volume (the archive itself) + `service_data/data/mail-archiver/` (encryption keys, import drop folder) | **Requires:** Postgres | **Memory:** DB capped 512M in compose.yml; app: no hard limit set; measured idle with an empty archive ~134MB total (app 84 + db 50), will grow with mail

Upstream: [github.com/s1t5/mail-archiver](https://github.com/s1t5/mail-archiver) — docs index at [doc/Index.md](https://github.com/s1t5/mail-archiver/blob/main/doc/Index.md).

Not an email client — you can read, search, export and restore, but not compose/reply/send. Keep using Outlook / your phone's mail app for that; this runs in the background. See [Bichon](bichon.md) for the lighter, search-focused alternative that's also in this stack.

## Setup

```bash
cp services/mail-archiver/.env.example services/mail-archiver/.env
# set POSTGRES_PASSWORD, MAIL_ARCHIVER_ADMIN_USER, MAIL_ARCHIVER_ADMIN_PASSWORD, TZ
uv run homeserver.py dev up mail-archiver
```

Open `https://mail-archiver.<domain>/` (or `http://<host>:8153` in dev) and log in with the admin credentials from `.env`. **The first login forces a password change** (confirmed on first bring-up) — pick the real one there.

## Connecting a Microsoft 365 mailbox

Microsoft 365 no longer allows plain password logins for IMAP, so Mail-Archiver talks to it through the **Microsoft Graph API** with its own app registration. One-time, in the [Entra admin center](https://entra.microsoft.com) (needs a tenant admin):

1. **App registrations → + New registration.** Name it e.g. "Mail Archiver", **Accounts in this organizational directory only**, no redirect URI → **Register**. Copy the **Application (client) ID** and **Directory (tenant) ID** from the Overview page.
2. **API permissions → + Add a permission → Microsoft Graph → Application permissions:**
   - `Mail.Read` — enough to back up.
   - `Mail.ReadWrite` — only if you also want to *restore* into this same M365 tenant, or use retention policies that delete from the server. For a pure "backup before I leave" setup, `Mail.Read` alone is the safer choice.
3. Click **Grant admin consent for <your org>** — without this nothing works.
4. **Certificates & secrets → + New client secret.** Copy the **Value** immediately (it's never shown again). Note the expiry date — when it expires, syncing silently stops until you paste a new one in.
5. In Mail-Archiver: **Email Accounts → New Account → Provider: M365**, enter the mailbox address, Client ID, Client Secret, Tenant ID → **Create**. The first sync starts on the next interval (`MailSync__IntervalMinutes`, default 15).

> **Application permissions cover every mailbox in the tenant**, not just yours. If the tenant has other people's mailboxes in it, scope the app to only the mailboxes you intend to archive with an Exchange Online [RBAC for Applications](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac) assignment (or the older Application Access Policy).

For several mailboxes at once, use **M365 Tenant Import** (upstream's [guide](https://github.com/s1t5/mail-archiver/blob/main/doc/M365TenantImport.md)) instead of adding them one by one.

Personal Outlook.com/Hotmail accounts use the **Microsoft Personal** provider instead (device-code sign-in, no app registration needed). Any other provider: **IMAP**.

## Switching providers later

This is the "drop the provider and relax" step. Mail-Archiver copies archived mail into another mailbox and keeps the folder structure (upstream's [Mailbox Migration guide](https://github.com/s1t5/mail-archiver/blob/main/doc/MailboxMigration.md)):

1. Set up the new provider (Fastmail, Proton, Zoho, Migadu, a self-hosted server...) and point your domain's MX/SPF/DKIM/DMARC records at it. **Do this before cancelling the old one**, otherwise incoming mail bounces in between.
2. Add the new mailbox in Mail-Archiver as an **IMAP** account and let it sync once.
3. Open the old (M365) account → **Copy All Emails to Another Mailbox** → pick the new account and a target folder, tick **Preserve Folder Structure** → start. Big mailboxes run as a background job — progress is under **Jobs**.
4. Once it finishes and you've spot-checked the new mailbox, set the old account to **Disabled**. Its archive stays here.

Running a full copy twice appends everything twice. For "only mail after a date" or anything you might repeat, use upstream's [date-windowed offload](https://github.com/s1t5/mail-archiver/blob/main/doc/Offload.md) instead — it skips whatever the target already has.

You can also export any account (or a selection) as **mbox** or **zipped EML** from the UI — a plain-file copy you can import almost anywhere, independent of this app.

## Importing old mail

**Import** accepts mbox and zipped EML. Browser uploads through `mail-archiver.<domain>` are capped at 100MB per file by Cloudflare's tunnel — for anything bigger, either upload over the dev port / VPN (`http://10.8.0.1:8153`), or drop the file into `service_data/data/mail-archiver/import/` and pick it from the UI's local-import option (`LocalImport__AllowedPaths__0=/data/import` is already wired in compose.yml).

## Backups

The archive lives in Postgres (`mail-archiver-postgres` named volume) — `homeserver.py down mail-archiver` snapshots it automatically like every other named volume, into `service_data/backup/mail-archiver/`. `service_data/data/mail-archiver/data-protection-keys/` holds the key that encrypts the stored mailbox credentials/client secrets; it's covered by the same backup. Lose it and every account's credentials have to be re-entered (mail itself is unaffected).

Because this is the thing that's supposed to survive your mail provider disappearing, also keep a copy **off this machine** — the snapshot tarballs above, or periodic mbox exports, somewhere else.

## Gotchas

- **Postgres volume size.** Every message and attachment is stored in the database, so the volume grows roughly as large as your mailbox. It lives on Docker's own disk, not the `service_data/` data drive — check there's room before archiving a large mailbox.
- **Client secret expiry** (M365) — see step 4 above. Put a reminder in your calendar.
- **Deletion lock.** Once the setup is trusted, set `DeletionPolicy__DeletionAllowed=false` in `.env` so nobody (including you by accident) can delete archived mail from the UI.
- **Auth.** Has its own login with per-user account permissions (bucket D, see [auth posture](../13-auth-posture.md)), so it isn't behind Authentik forward-auth. Native OIDC (`OAuth__*` env vars — works with Authentik) is available if you want SSO later; see upstream's [OIDC guide](https://github.com/s1t5/mail-archiver/blob/main/doc/OIDC_Implementation.md).
- **No curl/wget in the image** — the container healthcheck uses bash's `/dev/tcp` instead.
