#!/bin/sh
set -e
sed \
  -e "s/SITE_TITLE_PLACEHOLDER/${SITE_TITLE}/g" \
  -e "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" \
  -e "s/PLAUSIBLE_SCRIPT_PLACEHOLDER/${PLAUSIBLE_SCRIPT}/g" \
  /template/index.html > /usr/share/nginx/html/index.html
exec nginx -g 'daemon off;'
