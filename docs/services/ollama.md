# Ollama

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Runs large language models locally and serves them over an API — the engine behind [Open WebUI](open-webui.md)'s chat interface.
**Port:** `8110` (host, dev) → `11434` (container) | **Requires:** — | **Memory:** varies heavily by loaded model; idle (no model loaded) is small

## Setup

```bash
uv run homeserver.py dev up ollama
```

Downloaded models live at `MODELS_ROOT` in `.env`. The `.env.example` default is `service_data/cache/ollama`, but on this host it is set to `/home/raju/ollama-models` on the NVMe SSD, because `service_data/` sits on a spinning HDD and model load time is disk-bound (a special case for Ollama only). Either location is outside `service_data/data/` so multi-GB model files are never swept into a config-only backup snapshot.

## Using it day to day

Ollama has no web UI of its own — almost everyone should just use [Open WebUI](open-webui.md), which talks to it directly over the internal `homeserver` Docker network (`OLLAMA_BASE_URL=http://ollama:11434`, unauthenticated, container-to-container — this never touches the reverse proxy).

`https://ollama.${DOMAIN}` exists for anything else that speaks the Ollama API directly (a script, an SDK, a CLI tool) instead of going through Open WebUI. Because that route sits behind Authentik forward-auth (see Notes below) and Ollama has no login screen to redirect through, a non-browser client needs to already be carrying a valid Authentik session cookie to get past it — there's no way for `curl`/an SDK to complete the login flow itself. If you need genuinely programmatic external access, get a session cookie via a browser login first and reuse it, or call Ollama from something running inside the stack (which reaches it over the internal network and skips this gate entirely).

## Health endpoint

The compose healthcheck runs `ollama list || exit 1` inside the container — not an HTTP path. Confirmed in `services/ollama/compose.yml`.

## Notes

- **Gated behind Authentik forward-auth** — unlike this stack's other forward-auth services, Ollama has no UI of its own at all (it's a bare API); `ollama.${DOMAIN}` was still given the same gate as soon as it got a public subdomain, so an ungated bare API wasn't the one open door into the stack. See [Ollama in authentik.md](authentik.md#forward-auth-for-other-services-nginx-auth_request) for the mechanism, and [13-auth-posture.md](../13-auth-posture.md) for why this is a different case from the other five gated services.
- No independent login/user accounts — access control is entirely the Authentik gate at the reverse-proxy layer for external requests; internal requests (Open WebUI and anything else in the stack) are unauthenticated by design, same as any other container-to-container call on the internal network.
- `MODELS_ROOT` (not `DATA_ROOT`) is where actual state lives — see the secondary-data-root note in the `homeserver-add-service` skill if this path is ever restructured.

## Troubleshooting: `ollama pull` fails with `Error: EOF` (2026-10-18)

**Symptom:** a pull stops right after `pulling manifest` with `Error: EOF` (Open WebUI shows its `/api/pull` call ending after about 2 seconds), every time, for one model while other models pull fine. The registry is reachable and the manifest returns 200 from `curl`, so it is not the network.

**Cause:** an earlier pull of that model was interrupted (killed, container restarted, or several pulls started at once). It left `*-partial*` files in `${MODELS_ROOT}/models/blobs/`: a sparse placeholder the size of the whole blob (5.5 GB for `gemma4:e4b`) plus per-part tracker files. Every retry tries to resume from that broken state and ends in EOF. A fresh Ollama container with no partials pulled the same model without trouble, which is how this was isolated.

**Fix:** stop any running pull, delete the partial files, and pull again:

```bash
docker exec ollama sh -c 'pkill -f "ollama pull"; rm -f /root/.ollama/models/blobs/*-partial*'
docker exec ollama ollama pull gemma4:e4b
```

Only `*-partial*` files are removed. Completed blobs and manifests are untouched. Pull one model at a time, and let it finish before starting the next.

## Context length: 16384 (2026-10-20)

`.env` sets `OLLAMA_CONTEXT_LENGTH=16384`. Without it Ollama falls back to a 4096-token window on this host, so a longer prompt fails with `request (7478 tokens) exceeds the available context size (4096 tokens)`. Open WebUI sends no `num_ctx` unless you set one under Admin Settings, Models, Advanced Params, so the server value applies ([FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)). A bigger window costs RAM for the KV cache, so raise it only as far as you need. Apply with `uv run homeserver.py dev restart ollama`, then check `docker exec ollama ollama ps` for the CONTEXT column.

## Memory: one model at a time (2026-10-18)

`.env` sets `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=5m`. Ollama's own defaults are up to 3 models loaded on CPU (keep-alive is 5 minutes, which we keep) ([FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)), so a large model you had stopped using stayed in RAM after you switched to another one. With these values a new model replaces the idle one, and an idle model is unloaded after 5 minutes. The cost is a reload from disk when you come back after a pause or switch models. The models are on the NVMe, so that is quick. Set `OLLAMA_KEEP_ALIVE=-1` to pin a model, or `0` to unload right after every reply.

To free memory by hand: `docker exec ollama ollama ps` lists loaded models and `docker exec ollama ollama stop <model>` unloads one.

## Reverse proxy: no buffering (2026-10-11)

The `ollama` block in `services/nginx-plain/templates/default.conf.template` sets `proxy_buffering off;` and `proxy_request_buffering off;`. Streamed generations could arrive in bursts, because nginx-plain buffered the streamed response. Same fix as Jellyfin's playback hangs (see [jellyfin.md](jellyfin.md)). Apply with `docker restart nginx-plain`, since the template is rendered at container start.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
