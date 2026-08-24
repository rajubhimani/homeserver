#!/bin/sh
set -e
sed \
  -e "s/SITE_TITLE_PLACEHOLDER/${SITE_TITLE}/g" \
  /template/index.html > /usr/share/nginx/html/index.html
exec nginx -g 'daemon off;'
