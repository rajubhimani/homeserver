#!/bin/sh
set -e
YEAR=$(date +%Y)
sed \
  -e "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" \
  -e "s/AUTHOR_PLACEHOLDER/${AUTHOR}/g" \
  -e "s/LOCATION_PLACEHOLDER/${LOCATION}/g" \
  -e "s/YEAR_PLACEHOLDER/${YEAR}/g" \
  -e "s/SITE_NAME_PLACEHOLDER/${SITE_NAME}/g" \
  -e "s/TAGLINE_PLACEHOLDER/${TAGLINE}/g" \
  -e "s/PLAUSIBLE_SCRIPT_PLACEHOLDER/${PLAUSIBLE_SCRIPT}/g" \
  /template/index.html > /usr/share/nginx/html/index.html
# nginx.conf needs DOMAIN too — some health checks (Zulip's) validate the
# Host header strictly and reject anything but the real configured domain.
# The health checks proxy through variables, so nginx needs an explicit DNS
# resolver. "auto" takes this container's own nameserver from
# /etc/resolv.conf: Docker's embedded DNS (127.0.0.11) under Compose,
# kube-dns under Kubernetes. Upstreams get UPSTREAM_SUFFIX appended (empty
# under Compose; ".apps.svc.cluster.local" under Kubernetes, because nginx's
# resolver doesn't apply the pod's search domains).
RESOLVER="${NGINX_RESOLVER:-auto}"
if [ "$RESOLVER" = "auto" ]; then
  RESOLVER=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf)
  case "$RESOLVER" in *:*) RESOLVER="[$RESOLVER]" ;; esac
fi
sed \
  -e "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" \
  -e "s/RESOLVER_PLACEHOLDER/${RESOLVER}/g" \
  -e "s/UPSTREAM_SUFFIX_PLACEHOLDER/${UPSTREAM_SUFFIX:-}/g" \
  -e "s/WG_EASY_HOST_PLACEHOLDER/${WG_EASY_HOST:-172.18.0.1}/g" \
  /template/nginx.conf > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
