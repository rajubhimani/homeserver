# Open WebUI + Ollama

[← New Services](../10-new-services.md) | [Home](../../setup.md)

---

## Purpose

Self-hosted chat UI for local LLMs. `ollama` serves models over its API; `open-webui` is the
ChatGPT-like front end that talks to it.

**By default, `open-webui` talks to a native/host-installed Ollama, not a container** — the
`ollama` service is gated behind the `docker-ollama` compose profile and only starts when
explicitly requested. This keeps the door open for direct GPU access on the host without
waiting on container GPU passthrough setup.

## Ports / access

| Service | Container | Dev port | Container port |
| --- | --- | --- | --- |
| Ollama (optional, `docker-ollama` profile) | `ollama` | 8110 | 11434 |
| Open WebUI | `open-webui` | 8109 | 8080 |

Public URL: `https://open-webui.yourdomain.com` (Open WebUI only — Ollama's API, whether host-native
or containerized, is never exposed publicly).

## Data paths

- `service_data/data/ollama/` — unused placeholder; the `ollama` container keeps no state here.
- `service_data/cache/ollama/` — **downloaded models** (can be tens of GB), only used if
  running the `docker-ollama` profile. Deliberately outside `service_data/data/ollama/` so
  `homeserver.py`'s backup/snapshot step (which tars the whole `DATA_ROOT` on every
  `down`/`backup`) never sweeps up the model weights. Grouped under `service_data/cache/`
  alongside other services' regenerable caches. See `MODELS_ROOT` in `services/ollama/.env`.
- `service_data/data/open-webui/data/` — chat history, user accounts, settings (small, gets
  backed up normally).
- `service_data/cache/open-webui/cache/` — embedding model cache (`sentence-transformers/
  all-MiniLM-L6-v2`, ~1.7GB once downloaded). Same reasoning as `ollama`'s `MODELS_ROOT`
  above: kept outside `service_data/data/open-webui/` so it isn't re-archived on every
  backup/snapshot. Fully regenerable — deleting it just re-downloads the model on next use.
  Grouped under `service_data/cache/` alongside other services' regenerable caches (e.g.
  jellyfin's `METADATA_ROOT`). See `MODELS_ROOT` in `services/open-webui/.env`.

## Setup (default: native host Ollama)

1. Install Ollama on the host and start it with `OLLAMA_HOST=0.0.0.0` so it accepts
   connections from the Docker network (default is loopback-only).
2. Pull a model: `ollama pull llama3.2` (or any model from the
   [Ollama library](https://ollama.com/library)).
3. `uv run homeserver.py dev up open-webui` — `services/open-webui/.env`'s
   `OLLAMA_BASE_URL=http://host.docker.internal:11434` already points at the host; the
   `host.docker.internal:host-gateway` entry in `services/open-webui/compose.yml` makes that hostname
   resolve on Linux, Mac, and Windows alike.
4. Open `https://open-webui.yourdomain.com` (or `http://localhost:8109` in dev) and create the first
   account — it becomes the admin automatically. Set `ENABLE_SIGNUP=false` in `services/open-webui/.env`
   once your account exists if you don't want further public signups.

## Using the containerized Ollama instead

Useful if you don't want to install Ollama on the host at all, or before GPU passthrough is
set up on the host:

1. `uv run homeserver.py dev up ollama open-webui --profile docker-ollama`
2. Change `OLLAMA_BASE_URL` in `services/open-webui/.env` to `http://ollama:11434` and restart
   `open-webui`.
3. Pull a model into the container: `docker exec -it ollama ollama pull llama3.2`.

Don't run a host Ollama and the `ollama` container at the same time pointed at the same
`OLLAMA_BASE_URL` — pick one per `services/open-webui/.env`.

## GPU passthrough (future, for the containerized path)

`services/ollama/compose.yml` has no `deploy.resources` block yet — CPU-only. When a GPU is available:

1. Install `nvidia-container-toolkit` on the host.
2. Add to `services/ollama/compose.yml` under the `ollama` service:

   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: all
             capabilities: [gpu]
   ```

3. Recreate the container (`uv run homeserver.py dev update ollama`). No changes needed to
   Open WebUI or model data — same volume, same API.

If instead you're running Ollama natively on the host, GPU access is whatever the host install
already gives it — no homeserver-side config needed.

### Image variant

`services/open-webui/compose.yml` picks its image tag from `OPEN_WEBUI_IMAGE_TAG` in
`services/open-webui/.env`, defaulting to `v0.11.0-slim` (no bundled local RAG/embeddings/Whisper/TTS
stack — smaller image, less runtime memory). When GPU passthrough lands and local RAG or
voice features are wanted, change it to the standard tag (`v0.11.0`, no `-slim` suffix) and
run `uv run homeserver.py dev update open-webui` to pull and recreate. Chat history and
settings carry over unchanged — the image swap doesn't touch `service_data/data/open-webui/`.

A compose profile was considered for this instead but rejected: a profile-gated "full"
variant would coexist with the unprofiled "slim" service rather than replace it, and both
share `container_name: open-webui` — running `--profile full` would try to start both at
once and collide. The env var avoids that entirely.

## Gotchas

- Ollama has no `/health` endpoint; the health route and healthcheck both use `ollama list`
  (CLI) / a TCP-level check instead of an HTTP probe.
- `ollama` won't start with a plain `up all`/`up open-webui` — it's profile-gated. Forgetting
  `--profile docker-ollama` when you meant to use the container looks like Open WebUI can't
  reach any models, when actually no Ollama backend is running at all (check whether you
  meant the host install instead).
- First inference on a freshly pulled model is slow (model load into RAM) — subsequent
  requests are faster since Ollama keeps it warm in memory for a few minutes.
- CPU inference is usable for small models (up to ~7B) but slow for anything larger.

---

[← New Services](../10-new-services.md) | [Home](../../setup.md)
