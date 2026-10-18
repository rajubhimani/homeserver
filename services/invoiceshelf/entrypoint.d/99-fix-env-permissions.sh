#!/bin/sh
# /var/www/html/.env ships root-owned (644) in this image, but the actual
# request-handling process runs as www-data (php-fpm's worker pool, not the
# root master process) — so www-data can read it but not write it. The
# install wizard's "database config" step needs to write DB settings back
# into .env and fails with a generic "cannot write configuration" error
# without this. .env isn't on a mounted volume, so this must run on every
# container start, not just once — this file is serversideup/php's own
# documented drop-in mechanism (/etc/entrypoint.d/*, run in order before the
# app boots) for exactly this kind of fixup. See docs/services/invoiceshelf.md.
chown www-data:www-data /var/www/html/.env
chmod 664 /var/www/html/.env
