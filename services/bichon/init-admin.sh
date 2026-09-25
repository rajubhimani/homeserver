#!/bin/sh
# One-shot: makes Bichon's built-in 'admin' account use BICHON_ADMIN_PASSWORD
# from .env. Bichon has no env var for this — it always creates admin with the
# publicly documented default 'admin@bichon'. Runs on every 'up', idempotent:
#   - env password already works  -> nothing to do
#   - default password works      -> switch it to the env password
#   - neither works               -> password was changed in the UI; leave it
set -eu

: "${BICHON_URL:?}"
: "${BICHON_ADMIN_PASSWORD:?BICHON_ADMIN_PASSWORD must be set in services/bichon/.env}"
DEFAULT_PASSWORD="admin@bichon"

case "$BICHON_ADMIN_PASSWORD" in
  *\"* | *\\*) echo "bichon-init: BICHON_ADMIN_PASSWORD must not contain \" or \\" >&2; exit 1 ;;
esac
[ "$BICHON_ADMIN_PASSWORD" = "$DEFAULT_PASSWORD" ] && { echo "bichon-init: BICHON_ADMIN_PASSWORD is still the public default — set a real one" >&2; exit 1; }

# Prints the access token on success, nothing on failure.
login() {
  curl -fsS -X POST "$BICHON_URL/api/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$1\"}" |
    grep '"success":true' | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'
}

if [ -n "$(login "$BICHON_ADMIN_PASSWORD")" ]; then
  echo "bichon-init: admin already uses BICHON_ADMIN_PASSWORD — nothing to do"
  exit 0
fi

token=$(login "$DEFAULT_PASSWORD")
if [ -z "$token" ]; then
  echo "bichon-init: WARNING — neither BICHON_ADMIN_PASSWORD nor the default works; admin's password was changed in the UI. Leaving it alone (update .env to match, or reset it in the UI)."
  exit 0
fi

id=$(curl -fsS -H "Authorization: Bearer $token" "$BICHON_URL/api/v1/current-user" |
  sed -n 's/.*"id":\([0-9]*\).*/\1/p')
curl -fsS -X POST "$BICHON_URL/api/v1/users/$id" -H "Authorization: Bearer $token" \
  -H 'Content-Type: application/json' -d "{\"password\":\"$BICHON_ADMIN_PASSWORD\"}" >/dev/null

if [ -n "$(login "$BICHON_ADMIN_PASSWORD")" ] && [ -z "$(login "$DEFAULT_PASSWORD")" ]; then
  echo "bichon-init: admin password set from BICHON_ADMIN_PASSWORD (default no longer works)"
else
  echo "bichon-init: ERROR — password change did not take effect" >&2
  exit 1
fi
