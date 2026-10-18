#!/bin/sh
# Issues and renews one Let's Encrypt wildcard certificate (*.DOMAIN + DOMAIN) with
# lego and the DNS-01 challenge, then copies it to the directory nginx-plain reads.
# DNS-01 needs no inbound port, so it works behind CGNAT and while the site is only
# reachable through the Cloudflare Tunnel. acme-reload.sh (the second container) notices
# the new files and reloads nginx-plain.
#
# `lego run` is idempotent: it requests a certificate when there is none, renews it when
# it is due (by default with a third of its lifetime left, so Let's Encrypt's move from
# 90 to 64 to 45 day certificates needs no change here) and otherwise does nothing.
set -eu

: "${DOMAIN:?DOMAIN must be set}"
: "${ACME_EMAIL:=}"
: "${ACME_SERVER:=letsencrypt-staging}"
: "${ACME_DNS_PROVIDER:=cloudflare}"
: "${ACME_PROFILE:=}"
: "${ACME_RENEW_DAYS:=0}"
: "${ACME_PROPAGATION_WAIT:=}"
: "${ACME_LEGO_ARGS:=}"
: "${ACME_CHECK_INTERVAL:=43200}"
: "${ACME_RETRY_INTERVAL:=3600}"
: "${CLOUDFLARE_DNS_API_TOKEN:=}"
export CLOUDFLARE_DNS_API_TOKEN

CERTS=/certs
# One lego directory per CA, so switching staging -> production issues a fresh certificate
# instead of finding the staging one and deciding nothing is due.
LEGO_PATH=/data/$(printf '%s' "$ACME_SERVER" | tr -c 'A-Za-z0-9' '_')
export LEGO_PATH
mkdir -p "$LEGO_PATH" "$CERTS"

# Copy src to dst only when the content differs, via a temp file so nginx never reads half a file.
install_if_changed() {
  src=$1 dst=$2 mode=$3
  cmp -s "$src" "$dst" 2>/dev/null && return 0
  tmp=$(mktemp "$dst.XXXXXX")
  if ! { cp "$src" "$tmp" && chmod "$mode" "$tmp" && mv "$tmp" "$dst"; }; then
    rm -f "$tmp"
    return 1
  fi
  echo "acme: updated $dst"
}

sync_certs() {
  issued=$LEGO_PATH/certificates
  [ -s "$issued/wildcard.crt" ] && [ -s "$issued/wildcard.key" ] || return 0
  install_if_changed "$issued/wildcard.crt" "$CERTS/fullchain.pem" 644
  install_if_changed "$issued/wildcard.key" "$CERTS/privkey.pem" 600
}

run_lego() {
  set -- --accept-tos --server "$ACME_SERVER" --dns "$ACME_DNS_PROVIDER" \
    --cert.name wildcard -d "*.${DOMAIN}" -d "$DOMAIN"
  [ -n "$ACME_EMAIL" ] && set -- "$@" --email "$ACME_EMAIL"
  [ "$ACME_RENEW_DAYS" != 0 ] && set -- "$@" --renew-days "$ACME_RENEW_DAYS"
  [ -n "$ACME_PROFILE" ] && set -- "$@" --profile "$ACME_PROFILE"
  [ -n "$ACME_PROPAGATION_WAIT" ] && set -- "$@" --dns.propagation.wait "$ACME_PROPAGATION_WAIT"
  # shellcheck disable=SC2086  # ACME_LEGO_ARGS is a space separated list of extra flags
  /lego --log.format text $ACME_LEGO_ARGS run "$@"
}

if [ "$ACME_DNS_PROVIDER" = cloudflare ] && [ -z "$CLOUDFLARE_DNS_API_TOKEN" ]; then
  echo "acme: CLOUDFLARE_DNS_API_TOKEN is not set in services/acme/.env, so no certificate is requested (see docs/services/acme.md). Idling."
  while true; do touch /tmp/alive; sleep 3600; done
fi

echo "acme: certificate for *.${DOMAIN} and ${DOMAIN} from ${ACME_SERVER}, checking every ${ACME_CHECK_INTERVAL}s"
while true; do
  if run_lego; then
    sync_certs
    wait_for=$ACME_CHECK_INTERVAL
  else
    echo "acme: lego failed, retrying in ${ACME_RETRY_INTERVAL}s (existing certificate stays in place)"
    sync_certs
    wait_for=$ACME_RETRY_INTERVAL
  fi
  touch /tmp/alive
  sleep "$wait_for"
done
