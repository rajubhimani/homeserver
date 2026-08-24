#!/bin/sh
#
# Stops coolify-proxy and coolify-sentinel — the two containers Coolify
# creates and manages itself (via the mounted Docker socket), which
# aren't declared in compose.yml at all and so aren't touched by
# `homeserver.py dev down coolify`. See docs/services/coolify.md
# ("Architecture") for why they're self-managed instead of being
# compose.yml services like everything else here.
#
# Only safe to run AFTER `down coolify` (or with `coolify` itself
# already stopped) — while the main app is running, its ServerManagerJob
# reconciles server state every minute and will just recreate these if
# it sees them missing while the database still says they should exist.
#
# Usage:
#   uv run homeserver.py dev down coolify
#   sh services/coolify/stop-self-managed.sh
#
set -e

for name in coolify-proxy coolify-sentinel; do
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    docker stop "$name" > /dev/null
    echo "Stopped $name."
  else
    echo "$name not running, nothing to do."
  fi
done
