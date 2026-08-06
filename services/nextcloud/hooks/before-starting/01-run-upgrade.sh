#!/bin/sh
# Only run upgrade when Nextcloud is already installed (config.php is non-empty)
[ -s /var/www/html/config/config.php ] && php /var/www/html/occ upgrade --no-interaction || true
