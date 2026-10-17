#!/bin/sh
# Put db.config.php (DB login from .env, see config/db.config.php) into config/ on
# every start. It is mounted outside /var/www/html on purpose: a file mounted
# *inside* config/ makes the directory non-empty, so on a blank volume the image
# never seeds or chowns it (it only does that while config/ is empty) and the
# installer fails with 'Cannot write into "config" directory!'. Hooks run as
# www-data, so the copy is owned correctly.
[ -f /usr/src/homeserver/db.config.php ] || exit 0
cp /usr/src/homeserver/db.config.php /var/www/html/config/db.config.php
