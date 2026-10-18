# code-server

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** VS Code in the browser (a self-hosted GitHub Codespaces): open `https://code-server.<domain>/` from any device and edit, run and debug code that lives on this server.
**Port:** `8163` (host) → `8080` (container) | **Data:** `service_data/data/code-server/home/` (the whole `/home/coder`) | **Package cache:** `service_data/cache/code-server/home-cache/` | **Workspace:** `WORKSPACE_ROOT` (default: this repo) | **Docker cache:** `service_data/cache/code-server/docker/` | **Requires:** nothing | **Memory:** no hard limit set

## Setup

```bash
cp services/code-server/.env.example services/code-server/.env
# set PASSWORD (or HASHED_PASSWORD, leaving PASSWORD empty)
mkdir -p service_data/data/code-server/home/{.cache,.ssh,project} service_data/cache/code-server/{docker,home-cache}
chmod 700 service_data/data/code-server/ssh
uv run homeserver.py dev up code-server   # first start builds the image (code-server + Docker CLI)
```

Open `https://code-server.<domain>/` (or `http://<host>:8163` in dev). You pass Authentik first, then code-server's own password prompt.

## Architecture

- Two containers: `code-server` (the editor) and `code-server-docker` (an isolated Docker engine, see "Docker in the editor"). The editor image is built from `services/code-server/Dockerfile`: Coder's official `codercom/code-server` ( Docker Hub is the only registry the docs name) plus the Docker CLI, Compose and Buildx copied from Docker's official `docker:<version>-cli` image, and the developer essentials below. It runs as uid 1000 (`coder`), which is the host user, so files written from the editor are owned by you.
- **Versions:** neither code-server nor Docker Engine has an LTS track, so both run the newest stable release (`CODE_SERVER_VERSION=4.140.0`, released 2026-10-01; `DOCKER_VERSION=29.8.2`, one setting for the sidecar engine and the CLI so they always match) and take every update. After changing either, rebuild the editor image with `docker compose -f services/code-server/compose.yml --env-file services/code-server/.env build`.
- `WORKSPACE_ROOT` is bind-mounted at `/home/coder/project`, which is the folder the editor opens. Edits change the real files on this host, so git, the terminal and the files are all the host's. It is a second path var like immich's `UPLOAD_LOCATION`, but it points at source code, not app data, so it is deliberately **not** under `service_data/` (a snapshot should never archive your repo).
- Extensions, settings and every login live in the persisted home folder (see "The whole home directory persists").

## Security (read this)

The integrated terminal is a **shell as uid 1000 on this host**, so whoever gets in can read and change anything that user can. Two layers guard it:

1. **Authentik forward-auth** in `nginx-plain`, the same pattern as Excalidraw and the Browser Hub (`docs/services/authentik.md`). Any Authentik user can pass it, as on those apps, so only invite people you would give a shell to.
2. code-server's own `PASSWORD` / `HASHED_PASSWORD`. Prefer the hashed form (`echo -n 'pw' | npx argon2-cli -e`).

The host's Docker socket is deliberately **not** mounted (that would make the editor root-equivalent on the host). `docker` in the terminal talks to the isolated sidecar instead, below.

## Developer essentials (baked into the image)

Installed in the image, so a recreated or updated container has them again with nothing to redo:

| Tool | How | Version setting |
| --- | --- | --- |
| uv / uvx | copied from `ghcr.io/astral-sh/uv` | `UV_VERSION` |
| Node.js + npm + corepack | copied from the official `node` image (Active LTS line, 24) | `NODE_VERSION` |
| Docker CLI, Compose, Buildx | see below | `DOCKER_VERSION` |
| `gh` (GitHub CLI) | GitHub's own release tarball, checksum-verified (Debian's package is years behind) | `GH_VERSION` |
| gcc/make (`build-essential`), `python3` + venv + pip, `pkg-config`, `jq`, `ripgrep`, `fd-find`, `unzip`, `zip`, `rsync`, `less`, `vim`, `htop`, `wget`, `cmake`, `tmux`, `git-lfs`, `sqlite3`, `postgresql-client` (17), `tree`, `bat`, plus git, curl, ssh and nano from the base. Debian names two commands `batcat` and `fdfind`; the image links them as `bat` and `fd` | apt | `DEV_PACKAGES` |

To add a tool: put its Debian package name in `DEV_PACKAGES` (or a new `COPY --from` / `RUN` in the `Dockerfile` for something not in apt), then rebuild and recreate:

```bash
docker compose -f services/code-server/compose.yml --env-file services/code-server/.env build
uv run homeserver.py dev up code-server     # recreates the container on the new image
```

`restart` alone reuses the old image; `up` recreates it. Neither touches your data.

**The whole home directory persists.** `/home/coder` is one bind mount of `service_data/data/code-server/home/`, so anything any tool writes under `~` survives a `down`/`up`, a recreate or an image rebuild: extensions and VS Code settings (`~/.local/share/code-server`), `gh auth login` (`~/.config/gh`), `git config --global`, `~/.ssh` keys, the Claude Code login (`~/.claude`, `~/.claude.json`), `~/.copilot`, shell history and dotfiles, `uv tool`/`uv python` installs and `npm install -g` (`~/.local`, first on `PATH`). No per-tool setting is needed, and a new tool's login is saved without any change here. This is the common setup for code-server in Docker (code-server's own install docs mount only `~/.local` and `~/.config`; community setups and templates mount the whole home, and LinuxServer's image keeps everything in one `/config` volume).

Details that make it work:
- **Default dotfiles:** a bind mount starts empty and hides the image's `.bashrc`/`.profile`, so `/entrypoint.d/10-persist.sh` (`services/code-server/persist.sh`) copies them from `/etc/skel` at each start, never overwriting an existing file, and sets `~/.ssh` to mode 700.
- **Ownership:** the folder is owned by uid 1000 on the host (you), the same user the container runs as, so there is nothing to `chown`.
- **Caches are separate:** `~/.cache` (uv, npm, pip downloads) is its own mount, `service_data/cache/code-server/home-cache/` (`CACHE_ROOT`), so it stays out of snapshots. Deleting it only costs a re-download.
- **Pre-create the mount points** on the host (the `mkdir` in Setup): Docker would otherwise create `home/.cache` and `home/project` owned by root. `home/project` is just the mount point for the workspace, it stays empty on the host.
- **Snapshots contain secrets:** the home folder holds SSH private keys and login tokens (gh, Claude), and it is in the service's snapshots, so keep `service_data/backup/code-server/` private. It also holds the extensions (a few hundred MB), which is why the cache is split out.
- **A shadowing gotcha:** a tool copied into `~/.local/bin` takes priority over the image's baked copy. Avoid uv's install script and bump `UV_VERSION` instead.
- Installing an apt package in the terminal is **not** persistent (system paths are in the image); add it to `DEV_PACKAGES` and rebuild.

Not persisted: anything outside `/home/coder` and the workspace (system paths such as `/usr`, `/etc`, `/opt`) lives in the image and is reset on recreate.

## Docker in the editor

`docker`, `docker compose` and `docker buildx` work in the terminal against **`code-server-docker`**, a separate Docker-in-Docker engine (`docker:<version>-dind`). It is a different engine from the host's: containers, images and networks you create there cannot see or touch the rest of the stack, and `docker ps` in the editor lists only your own. Same idea as Forgejo's CI sidecar. It cannot manage this stack; run `homeserver.py` from a host terminal.

- **How it is wired:** the sidecar joins `code-server`'s network namespace (`network_mode: service:code-server`) and listens on `tcp://127.0.0.1:2375` only. `DOCKER_HOST` is set to that in the editor. Loopback means nothing else on the `homeserver` network can reach the engine (checked: a connection from another container to `code-server:2375` is refused). TLS is off for that reason.
- **Published ports:** because the network namespace is shared, `docker run -p 3000:80 …` is on the editor's localhost, so it is reachable in the editor's browser tab at `https://code-server.<domain>/proxy/3000/` (and from the terminal at `localhost:3000`).
- **Bind mounts:** `docker run -v` paths are resolved by the sidecar, so `WORKSPACE_ROOT` is mounted into it at the same path as in the editor (`/home/coder/project`). `-v $PWD:/app` from a project folder just works; paths outside the workspace do not exist in the sidecar.
- **Privileged:** the sidecar runs `privileged: true`, which Docker-in-Docker requires. That is a wider kernel surface than a normal container, but it has no access to the host's Docker socket or the host's files other than the workspace and its own cache.
- **Storage:** `DOCKER_ROOT` (`service_data/cache/code-server/docker/`, ext4 here so the default overlay driver works) holds pulled images, containers and build cache. It is regenerable and can grow large, so it sits in the `cache/` bucket and is never in a snapshot. Its contents are owned by root (the engine writes as root), so the host user cannot list it. Reclaim space with `docker system prune -a` in the editor terminal, not by deleting files.
- **Restart together:** the sidecar is bound to the editor's network namespace, so if `code-server` is recreated, `code-server-docker` must be restarted too (`homeserver.py … restart code-server` handles both; starting only the sidecar will not).
- **Limits:** no memory/CPU limits are set on what you run in the sidecar; a runaway container there competes with the stack. For a heavy job, cap it with `docker run --memory`.
## Working from the browser

- **Terminal:** `` Ctrl+` ``. It runs in the code-server container (git, curl and the Docker CLI are available; anything else, run in a container via the sidecar).
- **Several projects:** this host sets `WORKSPACE_ROOT=/mnt/mydata/projects`, so every project is a subfolder of the folder the editor opens. Use File → Open Folder to jump into one (each gets its own window/tab and remembered state), or File → Add Folder to Workspace to keep several side by side in one window (File → Save Workspace As… keeps that set). Clone or create projects from the terminal (`git clone …`) and they appear on the host immediately.
- **Open another root:** point `WORKSPACE_ROOT` at any host path readable by uid 1000 and `uv run homeserver.py dev restart code-server`.
- **Previewing a dev server (port forwarding):** code-server's built-in proxy serves `/proxy/<port>/` on the same hostname, so a server on port 3000 (in the editor's terminal or published by a container from the sidecar) is at `https://code-server.<domain>/proxy/3000/`. It reaches only the editor's own localhost, not other containers on the `homeserver` network.
- **Extensions:** it uses the Open VSX marketplace, not Microsoft's, so a few Microsoft-only extensions are unavailable. Set `EXTENSIONS_GALLERY` to change it.
- **Install as an app (PWA):** Chrome/Edge address bar → Install, for a window without browser chrome.

## Health endpoint

`GET /healthz` on the editor returns `{"status":"alive|expired",...}` without authentication (from code-server's FAQ). The compose healthcheck and the landing page's `/health/code-server` route both use it. The sidecar's healthcheck is `docker info` (the image defines none; upstream's `docker:dind` docs give no healthcheck command, so this is a local choice).

## Notes

- Websockets are required (editor, terminal). `nginx-plain`'s block sets the upgrade headers and `proxy_read_timeout 86400s`.
- `WORKSPACE_ROOT=../..` is relative to `services/code-server/`, i.e. the repo root. `service_data/` inside it is a symlink to `/mnt/mydata/service_data`, which does not exist inside the container, so it shows as a broken link there (harmless).
- Not on Kubernetes: see the reason in `kubernetes/scope.yaml`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
