# Open WebUI + Ollama

[← New Services](../10-new-services.md) | [Home](../../setup.md)

---

## Purpose

Self-hosted chat UI for local LLMs. `ollama` serves models over its API; `open-webui` is the
ChatGPT-like front end that talks to it.

**By default, `open-webui` talks to the containerized `ollama` service** — it starts like any
other `daily`-tier service (`up ollama`/`up daily`/`up all`, no flag needed). A native/host-installed
Ollama is also supported as an alternative, e.g. for direct GPU access on the host before
container GPU passthrough is set up.

## Ports / access

| Service | Container | Dev port | Container port |
| --- | --- | --- | --- |
| Ollama | `ollama` | 8110 | 11434 |
| Open WebUI | `open-webui` | 8109 | 8080 |

Public URL: `https://open-webui.yourdomain.com` (Open WebUI only — Ollama's API, whether host-native
or containerized, is never exposed publicly).

## Data paths

- `service_data/data/ollama/` — unused placeholder; the `ollama` container keeps no state here.
- `service_data/cache/ollama/` — **downloaded models** (can be tens of GB). Deliberately outside
  `service_data/data/ollama/` so
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

## Setup (default: containerized Ollama)

1. `uv run homeserver.py dev up ollama open-webui` (or `up daily`/`up all` — `ollama` is a
   normal `daily`-tier service, no `--profile` flag needed).
2. `services/open-webui/.env`'s `OLLAMA_BASE_URL=http://ollama:11434` already points at the
   container.
3. Pull a model into the container: `docker exec -it ollama ollama pull llama3.2` (or any model
   from the [Ollama library](https://ollama.com/library)).
4. `ENABLE_SIGNUP` defaults to `false` in this repo — set it to `true` first, `up`/restart, then open
   `https://open-webui.yourdomain.com` (or `http://localhost:8109` in dev) and create the first
   account (it becomes the admin automatically), then set it back to `false` and restart. To add
   more accounts later without reopening public signup, use the admin panel instead:
   **Admin Panel → Users → Add User** (logged in as the admin).

## Using a native host Ollama instead

Useful for direct GPU access on the host before container GPU passthrough is set up (see
below), or if you'd rather not run Ollama in a container at all:

1. Install Ollama on the host and start it with `OLLAMA_HOST=0.0.0.0` so it accepts
   connections from the Docker network (default is loopback-only).
2. Pull a model: `ollama pull llama3.2` (or any model from the
   [Ollama library](https://ollama.com/library)).
3. Change `OLLAMA_BASE_URL` in `services/open-webui/.env` to
   `http://host.docker.internal:11434` and restart `open-webui` — the
   `host.docker.internal:host-gateway` entry in `services/open-webui/compose.yml` makes that
   hostname resolve on Linux, Mac, and Windows alike.
4. Leave the `ollama` container stopped (`down ollama`) so it doesn't also try to bind the
   model API.

Don't run a host Ollama and the `ollama` container at the same time pointed at the same
`OLLAMA_BASE_URL` — pick one per `services/open-webui/.env`.

## Installing it as a phone/desktop app (PWA)

There's no separate native mobile app — Open WebUI is a Progressive Web App instead, installable straight from the browser:

- **iPhone/iPad:** must use Safari (Chrome/Firefox on iOS can't install PWAs) — Share button → scroll down → **Add to Home Screen**.
- **Android:** Chrome menu → **Add to Home Screen** / **Install app**.
- **Desktop (Chrome/Edge):** click the install icon (⊕) in the address bar, or Menu → **Install Open WebUI**.

Installed this way, it gets its own home-screen/app-launcher icon, opens in its own window (no browser chrome), and appears in the phone's share sheet — so a link or file from another app can be shared directly into a chat.

## Pulling models from the UI (no terminal needed)

Once Open WebUI is connected to an Ollama backend (host or containerized, doesn't matter —
this goes through Open WebUI's own proxy either way), models can be pulled entirely from the
browser instead of `ollama pull`/`docker exec`:

1. **Admin Panel → Settings → Models** (or **Workspace → Models**, depending on version —
   look for a **+**/download icon next to a text field).
2. Type a model name exactly as it appears on the [Ollama library](https://ollama.com/library)
   (e.g. `llama3.2`, `qwen2.5:0.5b`) and confirm the pull.
3. Open WebUI proxies the request straight to Ollama (`POST /ollama/api/pull` under the hood,
   confirmed live on this stack) and shows download progress in the UI. No CLI access to the
   `ollama` container or host install is needed at any point.
4. Once it finishes, the model shows up immediately in the model picker for a new chat.

This is the same underlying Ollama pull either way — the CLI commands in the two setup paths
above (`ollama pull ...` / `docker exec -it ollama ollama pull ...`) are just a terminal
alternative to this, not a separate mechanism.

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
`services/open-webui/.env`, defaulting to `v0.11.3-slim` (no bundled local RAG/embeddings/Whisper/TTS
stack — smaller image, less runtime memory). When GPU passthrough lands and local RAG or
voice features are wanted, change it to the standard tag (`v0.11.3`, no `-slim` suffix) and
run `uv run homeserver.py dev update open-webui` to pull and recreate. Chat history and
settings carry over unchanged — the image swap doesn't touch `service_data/data/open-webui/`.

A compose profile was considered for this instead but rejected: a profile-gated "full"
variant would coexist with the unprofiled "slim" service rather than replace it, and both
share `container_name: open-webui` — running `--profile full` would try to start both at
once and collide. The env var avoids that entirely.

## Gotchas

- Ollama has no `/health` endpoint; the health route and healthcheck both use `ollama list`
  (CLI) / a TCP-level check instead of an HTTP probe.
- First inference on a freshly pulled model is slow (model load into RAM) — subsequent
  requests are faster since Ollama keeps it warm in memory for a few minutes.
- CPU inference is usable for small models (up to ~7B) but slow for anything larger.
- **Changing `OLLAMA_BASE_URL` in `.env` after Open WebUI has already booted once does nothing
  by itself.** The env var only seeds `ollama.base_urls` in `webui.db` on first boot against an
  empty database — every boot after that reads the DB value, not the env var, so a `down`/`up`
  recreate (which never touches `service_data/data/`) keeps the old URL forever. Confirmed live
  on this stack: switching an install from host-native to `docker-ollama` by editing `.env` alone
  left Open WebUI still pointed at `http://host.docker.internal:11434` and unable to reach the
  `ollama` container. Fix in the UI too — Admin Panel → Settings → Connections → edit the Ollama
  URL directly — the env var edit alone is not enough once a database already exists.

---

[← New Services](../10-new-services.md) | [Home](../../setup.md)
