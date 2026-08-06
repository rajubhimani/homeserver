#!/bin/sh
# Fix ownership on bind-mounted directories that may have been written by Podman rootless
# (Podman maps host UIDs into subuids like 524320; Docker needs www-data/33).
# Best-effort: Docker Desktop's Windows host-path bind mounts reject chown
# entirely (EPERM) regardless of target UID, so a hard failure here would
# crash-loop the container on Windows even though no chown was ever needed
# there in the first place.
chown -R www-data:www-data \
  /var/www/html/config \
  /var/www/html/data \
  /var/www/html/custom_apps \
  2>/dev/null || true
