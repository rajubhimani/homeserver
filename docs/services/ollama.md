# Ollama

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Runs large language models locally and serves them over an API — the engine behind [Open WebUI](open-webui.md)'s chat interface.
**Port:** `8110` (host, dev) → `11434` (container) | **Requires:** — | **Memory:** varies heavily by loaded model; idle (no model loaded) is small

## Setup

```bash
uv run homeserver.py dev up ollama
```

Downloaded models live in `service_data/cache/ollama` (`MODELS_ROOT` in `.env`), outside `service_data/data/` so multi-GB model files are never swept into a config-only backup snapshot.

## Using it day to day

Ollama has no web UI of its own — almost everyone should just use [Open WebUI](open-webui.md), which talks to it directly over the internal `homeserver` Docker network (`OLLAMA_BASE_URL=http://ollama:11434`, unauthenticated, container-to-container — this never touches the reverse proxy).

`https://ollama.${DOMAIN}` exists for anything else that speaks the Ollama API directly (a script, an SDK, a CLI tool) instead of going through Open WebUI. Because that route sits behind Authentik forward-auth (see Notes below) and Ollama has no login screen to redirect through, a non-browser client needs to already be carrying a valid Authentik session cookie to get past it — there's no way for `curl`/an SDK to complete the login flow itself. If you need genuinely programmatic external access, get a session cookie via a browser login first and reuse it, or call Ollama from something running inside the stack (which reaches it over the internal network and skips this gate entirely).

## Health endpoint

The compose healthcheck runs `ollama list || exit 1` inside the container — not an HTTP path. Confirmed in `services/ollama/compose.yml`.

## Notes

- **Gated behind Authentik forward-auth** — unlike this stack's other forward-auth services, Ollama has no UI of its own at all (it's a bare API); `ollama.${DOMAIN}` was still given the same gate as soon as it got a public subdomain, so an ungated bare API wasn't the one open door into the stack. See [Ollama in authentik.md](authentik.md#forward-auth-for-other-services-nginx-auth_request) for the mechanism, and [13-auth-posture.md](../13-auth-posture.md) for why this is a different case from the other five gated services.
- No independent login/user accounts — access control is entirely the Authentik gate at the reverse-proxy layer for external requests; internal requests (Open WebUI and anything else in the stack) are unauthenticated by design, same as any other container-to-container call on the internal network.
- `MODELS_ROOT` (not `DATA_ROOT`) is where actual state lives — see the secondary-data-root note in the `homeserver-add-service` skill if this path is ever restructured.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
