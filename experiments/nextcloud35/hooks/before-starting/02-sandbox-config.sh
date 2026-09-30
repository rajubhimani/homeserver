#!/bin/sh
# Sandbox replacement for services/nextcloud's 02-configure-proxy.sh: point
# every URL at the local sandbox address instead of the real domain.
php /var/www/html/occ config:system:get installed 2>/dev/null | grep -q 'true' || exit 0

php /var/www/html/occ config:system:set overwrite.cli.url --value="http://localhost:8095"
php /var/www/html/occ config:system:delete overwriteprotocol
php /var/www/html/occ config:system:delete trusted_domains
php /var/www/html/occ config:system:set trusted_domains 0 --value="localhost"
php /var/www/html/occ config:system:set trusted_domains 1 --value="localhost:8095"
php /var/www/html/occ config:system:set trusted_domains 2 --value="10.8.0.1:8095"

# Background jobs only run from a cron container, and the sandbox has none.
php /var/www/html/occ background:cron

# ClamAV lives on the real `homeserver` network, which the sandbox can't reach.
php /var/www/html/occ app:disable files_antivirus || true
