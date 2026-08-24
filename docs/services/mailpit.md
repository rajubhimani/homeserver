# Mailpit

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

A shared SMTP catcher — any service in this stack can point its mail-sending config at `mailpit:1025` and see exactly what it would have sent, in a real inbox UI, with nothing ever actually delivered anywhere. No MX records, no port 25 open to the internet, no real mail server to operate or secure. Started life scoped inside Airflow's own `compose.yml` (built to prove `AIRFLOW__EMAIL__*` alerting actually works — see `docs/services/airflow/airflow.md`'s `example_email_alert_on_failure.py`), then promoted here so any other service can use the same instance instead of each standing up its own.

## Setup

```bash
cp services/mailpit/.env.example services/mailpit/.env
mkdir -p service_data/data/mailpit/data
uv run homeserver.py dev up mailpit
```

Open `https://mailpit.<domain>/` (or `http://<host>:8140` in dev) — empty inbox until something sends it mail.

## Using it day to day

Everything below is the web UI (same URL as above). Confirmed against Mailpit's own current docs, not assumed from memory.

- **Message list:** every caught email, newest first. Click one to open it in a reading pane with tabs for **HTML**, **Text**, **HTML Source**, and (for anything with attachments) the raw MIME parts — image attachments get inline thumbnails. Real-time: new mail appears via websocket without a manual refresh.
- **Search box** (top of the message list) supports field filters, not just free text: `from:`, `to:`, `cc:`, `bcc:`, `reply-to:`, `addressed:` (matches any of From/To/Cc/Bcc/Reply-To), `subject:`, `message-id:`, and `tag:` (quote multi-word values, e.g. `subject:"password reset"`). Prefix any term with `!` or `-` to exclude it — e.g. `subject:invoice !from:billing@example.com`. `is:read`, `is:unread`, `is:tagged`/`!is:tagged` filter by status; `has:attachment`/`!has:attachment` and `has:inline`/`!has:inline` filter by attachment presence (not `is:attachment` — that's not a real filter); `larger:2M`/`smaller:1.5MB` filter by message size; `before:2026/08/01` / `after:2026/07/01` filter by date (use `yyyy/mm/dd` to avoid ambiguity). Combine several filters in one search box.
- **Tags:** manual (select a message → Tag) or automatic via filtering rules / plus-addressing (`someone+tagname@example.com`) — useful for grouping test emails by which service/feature sent them.
- **HTML checker:** open a message → **Check HTML** tab-equivalent action scores mail-client rendering compatibility and flags unsupported CSS — handy when debugging a service's HTML email templates rather than just confirming delivery.
- **Link/image check:** validates that links and linked images in a message actually resolve, useful for catching broken URLs in generated emails before they'd reach a real inbox.
- **REST API for scripted checks** (also useful beyond the failure-alert example below): `GET /api/v1/messages` lists caught mail, `GET /api/v1/message/{ID}` fetches one in full — good for asserting "did service X actually send an email" from an automated test instead of checking the UI by hand.

## Using it from another service

Point that service's SMTP settings at:

- **Host:** `mailpit` (container name, resolves on the shared `homeserver` network from any compose project in this stack)
- **Port:** `1025`
- **Auth:** none required (`MP_SMTP_AUTH_ACCEPT_ANY=1`) — send with any credentials, real or fake, or none at all
- **TLS:** none — plain, unencrypted, LAN-internal only by design

Airflow's `.env` (`SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_FROM_EMAIL=...`) is the worked example — copy that pattern for any other service that supports a configurable SMTP relay.

## Architecture

Single container, `axllent/mailpit`. Persistent message storage via `MP_DATABASE=/data/mailpit.db` (bind-mounted to `DATA_ROOT/data`) — caught mail survives a container restart, unlike Mailpit's own default (an auto-generated temporary file, deleted when the process stops). `MP_SMTP_AUTH_ACCEPT_ANY`/`MP_SMTP_AUTH_ALLOW_INSECURE` are both set so any sender's config "just works" without matching credentials — appropriate here because nothing this container touches is a real inbox; there's no delivery to protect.

## Health endpoint

The compose healthcheck runs `wget -qO- http://localhost:8025/api/v1/info` inside the container. Confirmed live against the running `v1.30.7` container — it returns `200` with a JSON body describing the instance, not just a bare `ok`:

```json
{"Version":"v1.30.7","LatestVersion":"v1.30.7","Database":"/data/mailpit.db","DatabaseSize":561152,"Messages":47,"Unread":0,"Tags":{},"RuntimeStats":{"Uptime":14847,"Memory":35498264,"MessagesDeleted":0,"SMTPAccepted":0,"SMTPAcceptedSize":0,"SMTPRejected":0,"SMTPIgnored":0}}
```

Same endpoint from outside the container: `curl http://mailpit:8025/api/v1/info` from another service on the `homeserver` network, or `curl http://<host>:8140/api/v1/info` from the host in dev.

## Notes

- **Not a real mail server.** It cannot send anything past itself — there's no relay, no MX, no outbound delivery path. If you ever need genuine outbound email (password resets a real user needs to receive, etc.), point that specific service at a real external SMTP provider instead — Mailpit is for development/testing/alerting-verification only.
- **Gated behind Authentik forward-auth** — Mailpit has no login of its own (same situation as Temporal/Dagster/Dozzle/Excalidraw, see their own docs), so `mailpit.${DOMAIN}` requires an Authentik login at the nginx layer before any request reaches the container. See [Forward-auth for other services](authentik.md#forward-auth-for-other-services-nginx-auth_request) in `authentik.md`. **This is also why Mailpit moved from `min` to `core` tier** — Authentik (the thing now gating it) is core-tier, and gating a min-tier service behind a core-tier dependency would otherwise break `min`'s "works standalone" contract. Its REST API (used by the failure-alert check below) is gated by the same blanket vhost rule; nothing in this stack was found to call it outside a browser, so no path-scoping exception was carved out.
- REST API for scripted checks (used to verify `example_email_alert_on_failure.py` actually worked): `curl http://mailpit:8025/api/v1/messages` from inside the network, or `http://<host>:8140/api/v1/messages` from the host in dev — see "Health endpoint" above for the same-family `/api/v1/info` endpoint the compose healthcheck itself uses.
- **No mobile app or desktop client exists for Mailpit** — it's a self-contained web UI plus API, nothing to install on a phone/tablet. Anything claiming otherwise wasn't found in Mailpit's own docs or repo; treat any such claim as unverified.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
