# Atuin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted shell history sync server — searchable history across your machines (Mac/Windows/Fedora), with context (directory, exit code, duration), replacing per-machine `.bash_history`/`.zsh_history`.
**Port:** `8122` (host) → `8888` (container) | **Data:** `service_data/data/atuin/` | **Requires:** Postgres

## Setup

Server:

```bash
cp atuin/.env.example atuin/.env
uv run homeserver.py dev up atuin
```

Client (on each machine you want synced — install the [atuin CLI](https://docs.atuin.sh/) first):

```bash
atuin register -u <username> -e <email> --server-url https://atuin.<domain>
atuin login -u <username> --server-url https://atuin.<domain>
atuin sync
```

## Registration

`ATUIN_OPEN_REGISTRATION` in `.env`, default `true`. Set to `false` once your machines are registered to stop new clients from self-registering against this server.

## Notes

- History itself is end-to-end encrypted client-side before syncing — the server only ever stores encrypted blobs, never plaintext commands.
- No dedicated health endpoint documented upstream — the compose healthcheck and the landing-page health route both just check that `/` responds.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
