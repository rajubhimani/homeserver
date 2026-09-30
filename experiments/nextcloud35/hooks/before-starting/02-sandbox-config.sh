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

php /var/www/html/occ config:system:set trusted_domains 3 --value="nextcloud35"

# Point OnlyOffice at the sandbox's own document server (compose.yml). The
# browser loads the editor from :8097; server-to-server traffic stays on the
# isolated network.
if [ -n "${NEXTCLOUD35_ONLYOFFICE_JWT:-}" ]; then
  php /var/www/html/occ config:app:set onlyoffice DocumentServerUrl --value="${NEXTCLOUD35_ONLYOFFICE_PUBLIC_URL:-http://localhost:8097/}"
  php /var/www/html/occ config:app:set onlyoffice DocumentServerInternalUrl --value="http://nextcloud35-onlyoffice/"
  php /var/www/html/occ config:app:set onlyoffice StorageUrl --value="http://nextcloud35/"
  php /var/www/html/occ config:app:set onlyoffice jwt_secret --value="$NEXTCLOUD35_ONLYOFFICE_JWT"
fi

# Background jobs only run from a cron container, and the sandbox has none.
php /var/www/html/occ background:cron

# ClamAV lives on the real `homeserver` network, which the sandbox can't reach.
php /var/www/html/occ app:disable files_antivirus || true
