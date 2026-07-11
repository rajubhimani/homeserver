---
name: homeserver-docker-backend
description: Use when modifying homeserver.py itself, especially adding a new Docker/Compose operation, touching SubprocessBackend or PythonOnWhalesBackend, or debugging which backend is active.
---

# homeserver.py's Docker backend abstraction

`homeserver.py` never calls `docker`/`subprocess` directly — every Docker interaction (compose up/down/pull/logs, `ps`, `inspect`, volume/network management, the tar/untar operations backup/restore use) goes through the `DockerBackend` abstract interface (in `homeserver.py`, above the `# ── Helpers ──` section). Two implementations:

- **`SubprocessBackend`** (default, `DOCKER_BACKEND=subprocess` or unset) — calls `docker`/`docker compose` via `subprocess.run()` and parses their text output. Zero extra dependencies.
- **`PythonOnWhalesBackend`** (opt-in, `DOCKER_BACKEND=python-on-whales` in root `.env`) — routes the same operations through the [python-on-whales](https://github.com/gabrieldemarmiesse/python-on-whales) package, which still calls the same underlying `docker`/`docker compose` CLI, but raises typed `DockerException` (with `.stderr`/`.return_code`/`.docker_command`) instead of leaving the caller to parse raw CLI text. Install with `uv sync --extra docker-sdk` first; if selected but not installed, `create_backend()` warns and falls back to `SubprocessBackend` automatically.

Both backends implement the **full** `DockerBackend` interface, not just compose operations — deliberate, so the two never partially diverge and nothing else in the script needs to know which backend is active.

**When adding a new Docker operation:** add the method to the `DockerBackend` ABC first, then implement it in both `SubprocessBackend` and `PythonOnWhalesBackend` before using it anywhere else — never call `subprocess`/`docker` directly outside those two classes.

## Windows-specific notes

`homeserver.py` runs natively via `uv run homeserver.py ...` — no Git Bash, WSL, or shell compatibility layer needed. `subprocess.run()` with list-form arguments never goes through a shell, so there is no MSYS path-mangling risk (POSIX-looking paths in argv/env vars silently getting rewritten to Windows paths before reaching `docker` — this bit the retired shell-script entrypoint repeatedly: a `DOCKER_SOCKET` env var or any `docker exec`/`run` argument containing a container-internal path like `/var/log/...` would get corrupted). This is a structural property of using Python's subprocess module correctly — if you ever see a path arriving mangled, that's a real bug to fix at the source, not something to work around with a flag.

**Do not** run this stack from inside a WSL2 distro against a repo checked out on a Windows drive (`/mnt/c/...`, `/mnt/d/...`) — the drvfs/9p filesystem translation doesn't give real POSIX ownership guarantees and will intermittently produce `FATAL: data directory has wrong ownership` for Postgres containers, or in rare cases silent file corruption. Run from native Windows or a repo cloned natively inside the WSL distro's own filesystem instead.

## `python-on-whales` version pin

`pyproject.toml` pins `python-on-whales>=0.81,<0.82` and Python itself to `>=3.14,<3.15` — patch releases stay usable, but neither jumps a minor version silently. If bumping either, update the pin deliberately and re-run `uv lock`.
