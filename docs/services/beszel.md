# Beszel

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Lightweight server monitoring — CPU, memory, disk, network, and Docker container stats with alerts.
**Port:** `8106` (host) → `8090` (container) | **Data:** `service_data/data/beszel/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~42MB (hub + agent combined)

## Setup

```bash
cp services/beszel/.env.example services/beszel/.env
uv run homeserver.py dev up beszel
```

Two containers start: `beszel` (hub, web UI + storage) and `beszel-agent` (monitors this Docker host). The agent **crash-loops** until it has a token/key pair from the hub — this is expected (`restart: unless-stopped` just keeps retrying) and stops once you pair it below.

## First login and pairing

1. Browse to `http://<ip>:8106` — create the admin account on first launch
2. Hub UI → **Add System** (or **Settings → Tokens** for a universal token) → copy the token + public key
3. Set them in `services/beszel/.env`:

   ```bash
   BESZEL_AGENT_TOKEN=<token from hub>
   BESZEL_AGENT_KEY=<public key from hub>
   ```

4. Restart: `uv run homeserver.py dev up beszel`

The system indicator in the hub UI turns green once the agent connects.

## Architecture notes

`beszel-agent` runs with `network_mode: host` instead of joining the `homeserver` bridge network — it's the only service that does. This is required for it to report real host-level network throughput; on the bridge network it would only see its own virtual interface. It talks to the hub over a shared local Unix socket (`${DATA_ROOT}/socket`), not the Docker network, so it has no need to resolve other containers by name.

Because of the host-network mode, the agent's `HUB_URL` must point at the hub's **published host port** (`http://localhost:8106`), not its container port (`8090`) — update it if the hub's port mapping ever changes.

`TOKEN`/`KEY` are blank on first start — the agent refuses to run without them and crash-loops (`Failed to load public keys: no key provided`) until paired as above. The crash-loop is expected/harmless (`restart: unless-stopped`), not a bug.

It also reports per-container Docker stats via the mounted `${DOCKER_SOCKET}` (read-only).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
