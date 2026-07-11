#!/bin/sh
# Runs after the base image's own 18-load-element-modules.sh, which copies
# /app/config*.json (our bind-mounted config.json, containing
# DOMAIN_PLACEHOLDER) into /tmp/element-web-config/config.json — the actual
# path nginx serves /config.json from (see nginx-templates/default.conf.template
# in the upstream image). /app itself is not writable by the unprivileged
# nginx user, so the substitution has to happen on this tmp copy instead.
set -e
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" /tmp/element-web-config/config.json
