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

## Using it from another service

Point that service's SMTP settings at:

- **Host:** `mailpit` (container name, resolves on the shared `homeserver` network from any compose project in this stack)
- **Port:** `1025`
- **Auth:** none required (`MP_SMTP_AUTH_ACCEPT_ANY=1`) — send with any credentials, real or fake, or none at all
- **TLS:** none — plain, unencrypted, LAN-internal only by design

Airflow's `.env` (`SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_FROM_EMAIL=...`) is the worked example — copy that pattern for any other service that supports a configurable SMTP relay.

## Architecture

Single container, `axllent/mailpit`. Persistent message storage via `MP_DATABASE=/data/mailpit.db` (bind-mounted to `DATA_ROOT/data`) — caught mail survives a container restart, unlike Mailpit's in-memory default. `MP_SMTP_AUTH_ACCEPT_ANY`/`MP_SMTP_AUTH_ALLOW_INSECURE` are both set so any sender's config "just works" without matching credentials — appropriate here because nothing this container touches is a real inbox; there's no delivery to protect.

## Notes

- **Not a real mail server.** It cannot send anything past itself — there's no relay, no MX, no outbound delivery path. If you ever need genuine outbound email (password resets a real user needs to receive, etc.), point that specific service at a real external SMTP provider instead — Mailpit is for development/testing/alerting-verification only.
- **No auth on the web UI** — same situation as Temporal/Dagster (see their own docs' Notes sections): anyone who can reach `mailpit.<domain>` can read every caught message from every service using it. Fine for a single-user homelab behind Cloudflare Tunnel; put it behind Authentik's forward-auth if this ever needs to be shared.
- REST API for scripted checks (used to verify `example_email_alert_on_failure.py` actually worked): `curl http://mailpit:8025/api/v1/messages` from inside the network, or `http://<host>:8140/api/v1/messages` from the host in dev.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
