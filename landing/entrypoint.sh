#!/bin/sh
set -e
YEAR=$(date +%Y)
sed \
  -e "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" \
  -e "s/AUTHOR_PLACEHOLDER/${AUTHOR}/g" \
  -e "s/LOCATION_PLACEHOLDER/${LOCATION}/g" \
  -e "s/YEAR_PLACEHOLDER/${YEAR}/g" \
  /template/index.html > /usr/share/nginx/html/index.html
exec nginx -g 'daemon off;'
