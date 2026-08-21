# n8n

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted workflow automation — webhook → transform → notify style glue for homelab scripts and integrations.
**Port:** `8120` (host) → `5678` (container) | **Data:** `service_data/data/n8n/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~321MB total (app 297 + db 24)

## Setup

```bash
cp services/n8n/.env.example services/n8n/.env
# set POSTGRES_PASSWORD and N8N_ENCRYPTION_KEY (openssl rand -hex 32)
uv run homeserver.py dev up n8n
```

Open `https://n8n.<domain>/` (or `http://<host>:8120` in dev) and complete the owner setup wizard on first visit.

## Registration

No public self-registration — the first account becomes the instance owner, who invites additional users from inside the app (Settings → Users). No env var toggle applies.

## Notes

- `N8N_ENCRYPTION_KEY` encrypts every stored credential (API keys, tokens used by workflows) inside Postgres. Set it before the first start and never change or lose it — doing so makes every stored credential unreadable and workflows using them will need to be reconfigured from scratch.
- `N8N_SMTP_*` only covers n8n's own **system** emails (invites, password resets) — those correctly go to Mailpit. It has no effect on emails sent **from inside a workflow** (e.g. an Email/SMTP/Gmail node) — those use their own separately-configured credential and go wherever that credential actually points, real inbox included.
- `N8N_DIAGNOSTICS_ENABLED`/`N8N_VERSION_NOTIFICATIONS_ENABLED`/`N8N_PERSONALIZATION_ENABLED`/`N8N_HIRING_BANNER_ENABLED` are all set to `false` — upstream defaults phone home to n8n GmbH's own servers, and the owner-account email otherwise ends up receiving real marketing/product emails from `hello@info.n8n.io`. That's sent from n8n's own infrastructure, not this container, so it's outside anything Mailpit or `N8N_SMTP_*` can catch — the only fix is disabling it at the source.
- Health endpoint: `/healthz/readiness` (verifies DB connectivity, not just process liveness).
- Good fit for pairing with `ntfy` (this stack) for a notify step, or `ollama` for an AI step in a workflow.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
