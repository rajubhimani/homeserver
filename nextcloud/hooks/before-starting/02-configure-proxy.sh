#!/bin/sh
# Skip if Nextcloud isn't installed yet (first-run)
php /var/www/html/occ config:system:get installed 2>/dev/null | grep -q 'true' || exit 0

php /var/www/html/occ config:system:set overwrite.cli.url --value="https://nextcloud.${DOMAIN:-localhost}"
php /var/www/html/occ config:system:set overwriteprotocol --value="https"

# Trust all RFC 1918 private ranges — works with both Docker and Podman networks
php /var/www/html/occ config:system:set trusted_proxies 0 --value="127.0.0.1"
php /var/www/html/occ config:system:set trusted_proxies 1 --value="10.0.0.0/8"
php /var/www/html/occ config:system:set trusted_proxies 2 --value="172.16.0.0/12"
php /var/www/html/occ config:system:set trusted_proxies 3 --value="192.168.0.0/16"
