#!/bin/sh
# Clone the live Nextcloud (services/nextcloud, 34.x) into the nextcloud35
# sandbox, then start it on the Nextcloud 35 image so its own entrypoint runs
# the upgrade. Read-only against the live instance: pg_dump plus read-only
# volume mounts, no maintenance mode, no restart.
#
#   ./clone.sh           first clone (refuses if the sandbox already exists)
#   ./clone.sh --reset   wipe the sandbox and clone again from the live data
set -eu
cd "$(dirname "$0")"

VOLS="html config data custom-apps"
DC="docker compose"

if [ "${1:-}" = "--reset" ]; then
  $DC down -v
  for v in $VOLS; do docker volume rm -f "nextcloud35_nextcloud35-$v" >/dev/null; done
elif docker volume inspect nextcloud35_nextcloud35-config >/dev/null 2>&1; then
  echo "Sandbox volumes already exist. Use ./clone.sh --reset to start over." >&2
  exit 1
fi

for c in nextcloud nextcloud-db; do
  docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true \
    || { echo "Live container '$c' isn't running; nothing to clone from." >&2; exit 1; }
done

. ./.env

echo "==> Starting sandbox db + redis"
$DC up -d --wait nextcloud35-db nextcloud35-redis

echo "==> Copying database (pg_dump of the live db, roles first)"
docker exec nextcloud-db pg_dumpall -U "$POSTGRES_USER" --roles-only \
  | grep -v -E "^(CREATE|ALTER) ROLE $POSTGRES_USER( |;)" \
  | docker exec -i nextcloud35-db psql -q -U "$POSTGRES_USER" -d postgres
docker exec nextcloud-db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
  | docker exec -i nextcloud35-db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error

# The live instance's Notifications web-push key was encrypted with a
# different `secret` than config.php now has. 34 only logs "HMAC does not
# match" on every notifications poll; the 35 upgrade aborts on it. Dropping
# the pair makes Notifications generate a fresh one (0 push subscriptions
# existed on 2026-09-30, so nothing is lost). Same fix is needed on the live
# instance before its real upgrade.
echo "==> Dropping the undecryptable notifications web-push key (see comment)"
docker exec nextcloud35-db psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "delete from oc_appconfig where appid='notifications' and configkey in ('webpush_vapid_privkey','webpush_vapid_pubkey')"

# OnlyOffice document keys are cached per file in oc_onlyoffice_filekey; a
# cloned key equals the live one, and the same key open on two instances is
# one shared editing session. Clearing the table makes the sandbox mint its
# own (random GUID) keys.
docker exec nextcloud35-db psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "delete from oc_onlyoffice_filekey"

echo "==> Copying volumes: $VOLS"
for v in $VOLS; do
  docker volume create \
    --label com.docker.compose.project=nextcloud35 \
    --label "com.docker.compose.volume=nextcloud35-$v" \
    "nextcloud35_nextcloud35-$v" >/dev/null
  docker run --rm \
    -v "nextcloud_nextcloud-$v:/from:ro" \
    -v "nextcloud35_nextcloud35-$v:/to" \
    alpine:3.24.2 sh -c 'cp -a /from/. /to/'
done

echo "==> Pointing the cloned config.php at the sandbox db/redis"
docker run --rm -v nextcloud35_nextcloud35-config:/c "nextcloud:${NEXTCLOUD35_IMAGE:-35.0.1}" php -r '
  $f = "/c/config.php"; include $f;
  $CONFIG["dbhost"] = "nextcloud35-db";
  $CONFIG["redis"]["host"] = "nextcloud35-redis";
  $CONFIG["overwrite.cli.url"] = "http://localhost:8095";
  unset($CONFIG["overwriteprotocol"]);
  $CONFIG["trusted_domains"] = ["localhost", "localhost:8095", "10.8.0.1:8095", "nextcloud35"];
  file_put_contents($f, "<?php\n\$CONFIG = " . var_export($CONFIG, true) . ";\n");
  echo "dbhost=", $CONFIG["dbhost"], " redis=", $CONFIG["redis"]["host"], "\n";
'

grep -q '^NEXTCLOUD35_ONLYOFFICE_JWT=' .env \
  || echo "NEXTCLOUD35_ONLYOFFICE_JWT=$(openssl rand -hex 32)" >> .env

echo "==> Starting Nextcloud ${NEXTCLOUD35_IMAGE:-35.0.1} (runs the 34 -> 35 upgrade)"
$DC up -d nextcloud35 nextcloud35-onlyoffice
echo "Follow with: docker logs -f nextcloud35   then open http://localhost:8095"
