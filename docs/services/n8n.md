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

## Creating and activating a workflow

1. Open `https://n8n.<domain>/` and click **+ Add workflow** (or the **+** on the Overview page).
2. Add a trigger node (e.g. **Webhook**, **Schedule Trigger**, or a service-specific trigger), then chain further nodes to it — n8n runs the workflow left to right along the connections you draw between nodes.
3. To use a third-party service (Gmail, Slack, an HTTP API, etc.), add its node and create a **Credential** on it: click the credential dropdown → **Create New Credential**, fill in the API key/OAuth details for that service, then **Save**. Credentials are stored once and reusable across any node/workflow — they're what `N8N_ENCRYPTION_KEY` (see Notes below) actually protects.
4. Click **Save**, then flip the **Inactive/Active** toggle in the top-right to activate the workflow. A `Webhook` or other event-based trigger only fires in the background once activated; a manual/schedule-only workflow doesn't need activation to be run by its own schedule, but does need it to run unattended rather than only via **Execute workflow** in the editor.

### Webhook URLs

The `Webhook` trigger node shows two URLs, toggled via a switch in the node panel:

- **Test URL** — `https://n8n.${DOMAIN}/webhook-test/<path>`. Only live while the workflow is open in the editor and you've clicked **Listen for Test Event**; a single call is shown in the editor, then it stops listening.
- **Production URL** — `https://n8n.${DOMAIN}/webhook/<path>`. Only live once the workflow is **activated** (step 4 above); this is the URL to give to an external service permanently.

Both resolve under this stack's own domain because `WEBHOOK_URL=https://n8n.${DOMAIN}/` is set in `services/n8n/compose.yml` — no separate tunnel or public IP needed, the same reverse-proxy path (`nginx-plain`/cloudflared) that serves the UI also serves webhook calls.

## Notes

- `N8N_ENCRYPTION_KEY` encrypts every stored credential (API keys, tokens used by workflows) inside Postgres. Set it before the first start and never change or lose it — doing so makes every stored credential unreadable and workflows using them will need to be reconfigured from scratch.
- `N8N_SMTP_*` only covers n8n's own **system** emails (invites, password resets) — those correctly go to Mailpit. It has no effect on emails sent **from inside a workflow** (e.g. an Email/SMTP/Gmail node) — those use their own separately-configured credential and go wherever that credential actually points, real inbox included.
- `N8N_DIAGNOSTICS_ENABLED`/`N8N_VERSION_NOTIFICATIONS_ENABLED`/`N8N_PERSONALIZATION_ENABLED`/`N8N_HIRING_BANNER_ENABLED` are all set to `false` — upstream defaults phone home to n8n GmbH's own servers, and the owner-account email otherwise ends up receiving real marketing/product emails from `hello@info.n8n.io`. That's sent from n8n's own infrastructure, not this container, so it's outside anything Mailpit or `N8N_SMTP_*` can catch — the only fix is disabling it at the source.
- Health endpoint: `/healthz/readiness` (verifies DB connectivity, not just process liveness).
- Good fit for pairing with `ntfy` (this stack) for a notify step, or `ollama` for an AI step in a workflow.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
