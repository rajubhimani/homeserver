#!/bin/sh
rsync -rlDog --chown www-data:www-data --delete --exclude-from=/upgrade.exclude /usr/src/nextcloud/ /var/www/html/ || true
