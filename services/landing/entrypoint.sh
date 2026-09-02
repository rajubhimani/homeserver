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
sed \
  -e "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" \
  /template/nginx.conf > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
