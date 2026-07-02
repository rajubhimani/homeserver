#!/bin/sh
# Fix ownership on bind-mounted directories that may have been written by Podman rootless
# (Podman maps host UIDs into subuids like 524320; Docker needs www-data/33)
chown -R www-data:www-data \
  /var/www/html/config \
  /var/www/html/data \
  /var/www/html/custom_apps
