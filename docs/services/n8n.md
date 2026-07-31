# n8n

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted workflow automation — webhook → transform → notify style glue for homelab scripts and integrations.
**Port:** `8120` (host) → `5678` (container) | **Data:** `service_data/data/n8n/` | **Requires:** Postgres

## Setup

```bash
cp n8n/.env.example n8n/.env
# set POSTGRES_PASSWORD and N8N_ENCRYPTION_KEY (openssl rand -hex 32)
uv run homeserver.py dev up n8n
```

Open `https://n8n.<domain>/` (or `http://<host>:8120` in dev) and complete the owner setup wizard on first visit.

## Registration

No public self-registration — the first account becomes the instance owner, who invites additional users from inside the app (Settings → Users). No env var toggle applies.

## Notes

- `N8N_ENCRYPTION_KEY` encrypts every stored credential (API keys, tokens used by workflows) inside Postgres. Set it before the first start and never change or lose it — doing so makes every stored credential unreadable and workflows using them will need to be reconfigured from scratch.
- Health endpoint: `/healthz/readiness` (verifies DB connectivity, not just process liveness).
- Good fit for pairing with `ntfy` (this stack) for a notify step, or `ollama` for an AI step in a workflow.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
