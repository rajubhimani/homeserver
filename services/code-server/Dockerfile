# code-server with the Docker CLI, Compose and Buildx, plus the developer
# essentials (uv, Node LTS, compilers, common CLI tools). Everything is baked
# into the image, so a recreated container has it all again. The Docker CLI
# talks to the isolated code-server-docker (Docker-in-Docker) sidecar, never to
# the host's Docker; its binaries are copied from Docker's official cli image
# so they match the sidecar's engine version exactly.
ARG DOCKER_VERSION
ARG CODE_SERVER_VERSION
ARG UV_VERSION
ARG NODE_VERSION
FROM docker:${DOCKER_VERSION}-cli AS docker-cli
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM node:${NODE_VERSION}-trixie-slim AS node

FROM codercom/code-server:${CODE_SERVER_VERSION}
ARG DEV_PACKAGES
ARG GH_VERSION

USER root
# Debian packages (the list is DEV_PACKAGES in .env). `python3` is the system
# Python; uv installs and manages other versions per project.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ${DEV_PACKAGES} \
 && rm -rf /var/lib/apt/lists/*

# Debian names these commands batcat / fdfind; give them their usual names
RUN ln -s /usr/bin/batcat /usr/local/bin/bat && ln -s /usr/bin/fdfind /usr/local/bin/fd

# GitHub CLI from GitHub's own release (Debian's package is years behind),
# checksum-verified against the release's checksums file
RUN set -eux; \
    f="gh_${GH_VERSION}_linux_$(dpkg --print-architecture)"; \
    base="https://github.com/cli/cli/releases/download/v${GH_VERSION}"; \
    cd /tmp; \
    curl -fsSLO "$base/$f.tar.gz"; \
    curl -fsSL -o gh.sums "$base/gh_${GH_VERSION}_checksums.txt"; \
    grep " $f.tar.gz\$" gh.sums | sha256sum -c -; \
    tar -xzf "$f.tar.gz"; \
    install -m 755 "$f/bin/gh" /usr/local/bin/gh; \
    rm -rf /tmp/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx

COPY --from=uv /uv /uvx /usr/local/bin/

# Node.js LTS, laid out the way the official node image does it
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack

# Startup script: makes the persisted dirs below exist with the right modes
COPY --chmod=755 persist.sh /entrypoint.d/10-persist.sh
USER 1000

# What you install as the user lives in ~/.local, which is a persisted volume:
#   uv tool install / uv python install -> ~/.local/bin and ~/.local/share/uv
#   npm install -g                       -> ~/.local (via NPM_CONFIG_PREFIX)
#   git config --global                  -> ~/.config/git/config
#   Claude Code login and settings       -> ~/.config/claude (CLAUDE_CONFIG_DIR)
#   gh auth login                        -> ~/.config/gh (gh's default)
ENV PATH=/home/coder/.local/bin:${PATH} \
    NPM_CONFIG_PREFIX=/home/coder/.local \
    GIT_CONFIG_GLOBAL=/home/coder/.config/git/config \
    CLAUDE_CONFIG_DIR=/home/coder/.config/claude \
    UV_LINK_MODE=copy
