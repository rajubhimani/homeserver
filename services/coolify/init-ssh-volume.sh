#!/bin/sh
#
# Pre-creates and chowns the coolify-ssh-keys named volume before
# Coolify's first boot. Required every time that volume is freshly
# created (a genuinely new install, or after deleting the volume) —
# a brand-new Docker volume is always owned by root:root, and Coolify's
# own image runs as www-data (uid 9999), which can't write into it at
# all. Unlike the postgres/redis images used elsewhere in this stack,
# Coolify's own image does NOT self-heal this on boot (official
# database images chown their data dir as root before dropping
# privileges; Coolify's doesn't do that for this mount) — confirmed
# against Coolify's own database/seeders/PopulateSshKeysDirectorySeeder.php,
# which tries to chown the directory itself but runs as the unprivileged
# www-data user, so that call silently fails. See docs/services/coolify.md.
#
# Why a named volume at all instead of a normal service_data/ bind mount
# (every other persistent path here): service_data/ sits on an NTFS
# drive (fuseblk/ntfs-3g) on this host, which cannot store Unix
# permissions/ownership — chmod/chown against it silently no-op forever,
# and OpenSSH refuses to load a private key unless its file mode is
# exactly 0600. Named volumes live in Docker's own storage instead
# (btrfs on this host), which supports real permissions.
#
# Usage: run once, before the FIRST `up coolify` on a fresh install
# (or any time after the coolify-ssh-keys volume itself gets deleted):
#   sh services/coolify/init-ssh-volume.sh
#
set -e

VOLUME_NAME="coolify_coolify-ssh-keys"

docker volume create "$VOLUME_NAME" > /dev/null
docker run --rm -v "$VOLUME_NAME:/data" alpine chown -R 9999:9999 /data

echo "Chowned $VOLUME_NAME to 9999:9999 — safe to 'up coolify' now."
