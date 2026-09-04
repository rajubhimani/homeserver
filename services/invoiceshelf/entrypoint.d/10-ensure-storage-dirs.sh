#!/bin/sh
# compose.yml bind-mounts the *entire* /var/www/html/storage directory,
# which hides the subdirectories Laravel/InvoiceShelf need (the image
# normally ships them pre-populated, but the container's own entrypoint
# doesn't recreate them once storage/ is an empty bind mount) -- a fresh
# install or a --fresh restart both hit this the same way, since either
# starts from an empty storage/. templates/pdf specifically fails the
# boot-time "php artisan optimize" step outright ("does not exist");
# the others fail more quietly later (cache/session errors, missing
# upload targets) rather than at boot, but are just as required.
# serversideup/php's own /etc/entrypoint.d/* mechanism (run in order
# before the app boots) is the right place for this, same as
# 99-fix-env-permissions.sh. See docs/services/invoiceshelf.md.
for dir in \
    framework/cache/data \
    framework/sessions \
    framework/views \
    framework/testing \
    app/public \
    app/templates/pdf \
    app/estimates \
    app/invoices \
    app/company_logo \
    app/backup
do
    mkdir -p "/var/www/html/storage/$dir"
done
chown -R www-data:www-data /var/www/html/storage
