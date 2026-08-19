#!/bin/sh
# Regenerates /etc/nginx/browser_htpasswd from BROWSER_HUB_USER/PASSWORD on
# every container start — keeps the browser hub's login in .env like every
# other credential in this stack, instead of a separately hand-run htpasswd
# command. See docs/services/browser-hub.md.
set -e

if [ -n "$BROWSER_HUB_USER" ] && [ -n "$BROWSER_HUB_PASSWORD" ]; then
    hash=$(mkpasswd -m sha512 "$BROWSER_HUB_PASSWORD")
    echo "${BROWSER_HUB_USER}:${hash}" > /etc/nginx/browser_htpasswd
else
    echo "browser-hub: BROWSER_HUB_USER/BROWSER_HUB_PASSWORD not set in .env — browser hub login will reject everyone until set" >&2
    echo "unset:*" > /etc/nginx/browser_htpasswd
fi
