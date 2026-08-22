# Atuin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted shell history sync server — searchable history across your machines (Mac/Windows/Fedora), with context (directory, exit code, duration), replacing per-machine `.bash_history`/`.zsh_history`.
**Port:** `8122` (host) → `8888` (container) | **Data:** `service_data/data/atuin/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~27MB total (app 8 + db 19)

## Setup

Server:

```bash
cp services/atuin/.env.example services/atuin/.env
uv run homeserver.py dev up atuin
```

Browsing to `https://atuin.<domain>/` (or the health check hitting `/`) returns something like:

```json
{"homage":"\"Through the fathomless deeps of space swims the star turtle Great A'Tuin, bearing on its back the four giant elephants who carry on their shoulders the mass of the Discworld.\" -- Sir Terry Pratchett","version":"18.19.0"}
```

That's expected, not an error — the project is named after Discworld's Great A'Tuin, and that homage string doubles as its `/` health response. There's no web UI beyond this; Atuin is entirely CLI-driven, so this JSON is as far as a browser gets you. The actual functionality only shows up once a client is registered:

Client (on each machine you want synced — install the atuin CLI first):

```bash
# Mac/Fedora/Linux — official install script
curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh
# or, on Mac: brew install atuin
```

Windows: no native install script — use WSL and follow the Linux steps above, or check [Atuin's current install docs](https://docs.atuin.sh/guide/installation/) for any native Windows support that's landed since.

Recent atuin CLI versions (this server reports `18.19.0`) dropped the `--server-url` flag on `register`/`login` — it errors with `unexpected argument '--server-url' found`. Set the server address in the client's own config instead. **Don't just `echo ... >> config.toml`** — running any atuin command once auto-generates a fully-commented default `config.toml`, and appending lands your line *after* the `[ui]` section header, which silently scopes it to `ui.sync_address` instead of the real top-level key — Atuin then falls back to its default cloud server with no error at all. Replace the existing commented default line in place instead, which is already correctly positioned at the top level:

```bash
sed -i 's|^# sync_address = "https://api.atuin.sh"|sync_address = "https://atuin.<domain>"|' ~/.config/atuin/config.toml
grep '^sync_address' ~/.config/atuin/config.toml   # confirm it's a top-level line, not indented under a [section]
```

**`register` and `login` both need `-p <password>` supplied explicitly.** Without it, the CLI doesn't prompt locally — it silently switches to an interactive **Atuin Hub** (`hub.atuin.sh`, the project's own cloud service) OAuth flow instead, regardless of `sync_address`. This fails outright if you're headless (`Hub request failed with status: 401 Unauthorized`), and even when it succeeds it means your data went to Atuin's cloud, not this server — defeating the point of self-hosting, silently:

```bash
atuin register -u <username> -e <email> -p '<password>'
atuin login -u <username> -p '<password>'
atuin sync
```

`register` prints an encryption key on success — save it, it's required to log into any other machine (not derivable from just the username/password).

**Verify it actually landed on your own server**, don't just trust "Sync complete" — check this server's own state, since both failure modes above report success while silently talking to Atuin Hub instead:

```bash
uv run homeserver.py dev logs atuin   # or: docker logs nginx-plain | grep atuin — look for /register, /api/v0/record hits
```

**One more step before `Ctrl+R` actually changes** — `register`/`login`/`sync` only get history onto the server; the shell itself still needs wiring to actually use Atuin instead of its own history. Add to your shell's rc file (per-machine, once):

```bash
echo 'eval "$(atuin init zsh)"' >> ~/.zshrc    # zsh
echo 'eval "$(atuin init bash)"' >> ~/.bashrc  # bash — needs ble.sh >= 0.4 installed for full functionality
```

(fish/nu/xonsh/PowerShell are also supported — see [Atuin's shell integration docs](https://docs.atuin.sh/guide/shell-integration/) for the exact line on those.) Restart the shell (or `source` the rc file) and `Ctrl+R` now opens Atuin's fuzzy search instead of the shell's built-in one, backed by this server, staying synced across every machine you've logged in on.

## Viewing your synced history

There's no web UI for this, on two levels: Atuin has no dashboard at all (the JSON above is the entire HTTP surface meant for humans), and even if it did, the server couldn't show anything useful — history is end-to-end encrypted client-side before upload, so the server only ever holds blobs it can't decrypt. Viewing history only happens client-side, on a machine that's logged in:

```bash
atuin search      # interactive fuzzy-search TUI — what Ctrl+R opens once `atuin init` is wired into your shell
atuin history list # plain-text dump of history, formatting customizable — for scripting/piping, not interactive browsing
atuin stats        # usage stats: top commands, etc.
```

`atuin search` vs `atuin history list`: `search` is the interactive TUI (fuzzy/prefix/fulltext modes, filter by host/session/directory, replay a result) — this is the one you actually use day to day. `history list` is a non-interactive one-shot dump of records to stdout for scripts or piping elsewhere; it doesn't open any interface.

## Registration

`ATUIN_OPEN_REGISTRATION` in `.env`, default `true`. Set to `false` once your machines are registered to stop new clients from self-registering against this server.

## Notes

- History itself is end-to-end encrypted client-side before syncing — the server only ever stores encrypted blobs, never plaintext commands.
- No dedicated health endpoint documented upstream — the compose healthcheck and the landing-page health route both just check that `/` responds.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
