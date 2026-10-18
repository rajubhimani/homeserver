#!/bin/sh
# Keeps Firefly III and Ghostfolio in step (see docs/services/ghostfolio.md):
#   CASH_MAP   Firefly balance       -> Ghostfolio account cash balance
#   INVEST_MAP Ghostfolio market value -> Firefly gain/loss transaction for the
#              difference, so Firefly's net worth tracks the portfolio.
#
# Run from the repo root (needs firefly + ghostfolio up):
#   sh services/ghostfolio/firefly-sync.sh
# It re-runs itself in a throwaway alpine container on the homeserver network,
# so it reaches both apps by container name and needs nothing on the host.
set -eu

if [ -z "${IN_SYNC_CONTAINER:-}" ]; then
  dir=$(cd "$(dirname "$0")" && pwd)
  [ -f "$dir/sync.env" ] || { echo "missing $dir/sync.env (copy sync.env.example)" >&2; exit 1; }
  exec docker run --rm --network homeserver \
    -e IN_SYNC_CONTAINER=1 -e TZ="${TZ:-Asia/Kolkata}" \
    -v "$dir/firefly-sync.sh:/sync.sh:ro" \
    -v "$dir/sync.env:/sync.env:ro" \
    alpine:3.24.2 sh /sync.sh
fi

command -v jq >/dev/null || apk add --no-cache curl jq tzdata >/dev/null

set -a; . "${SYNC_ENV:-/sync.env}"; set +a
: "${FIREFLY_TOKEN:?}" "${GHOSTFOLIO_SECURITY_TOKEN:?}"
CASH_MAP=${CASH_MAP:-}; INVEST_MAP=${INVEST_MAP:-}
MIN_DELTA=${MIN_DELTA:-100}; DRY_RUN=${DRY_RUN:-0}
GAIN_ACCOUNT=${GAIN_ACCOUNT:-Investment gains}
LOSS_ACCOUNT=${LOSS_ACCOUNT:-Investment losses}
CATEGORY=${CATEGORY:-Unrealized gains/losses}

FF=${FIREFLY_URL:-http://firefly:8080}/api/v1
GF=${GHOSTFOLIO_URL:-http://ghostfolio:3333}/api/v1
TODAY=$(date +%Y-%m-%d)

ff() { curl -fsS -H "Authorization: Bearer $FIREFLY_TOKEN" -H 'Accept: application/vnd.api+json' "$@"; }
ff_balance() { ff "$FF/accounts/$1" | jq -r .data.attributes.current_balance; }
ff_currency() { ff "$FF/accounts/$1" | jq -r .data.attributes.currency_code; }

GF_JWT=$(curl -fsS -X POST "$GF/auth/anonymous" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg t "$GHOSTFOLIO_SECURITY_TOKEN" '{accessToken: $t}')" | jq -r .authToken)
gf() { curl -fsS -H "Authorization: Bearer $GF_JWT" "$@"; }
GF_ACCOUNTS=$(gf "$GF/account")
gf_field() { echo "$GF_ACCOUNTS" | jq -r --arg id "$1" --arg f "$2" '.accounts[] | select(.id == $id) | .[$f]'; }

check_currency() { # ff_id gf_id — values are copied as-is, so currencies must agree
  ffc=$(ff_currency "$1"); gfc=$(gf_field "$2" currency)
  [ -n "$gfc" ] || { echo "  ghostfolio account $2 not found, skipped" >&2; return 1; }
  [ "$ffc" = "$gfc" ] || { echo "  currency mismatch firefly #$1 $ffc vs ghostfolio $2 $gfc, skipped" >&2; return 1; }
}

for pair in $CASH_MAP; do
  ff_id=${pair%%:*}; gf_id=${pair#*:}
  check_currency "$ff_id" "$gf_id" || continue
  bal=$(ff_balance "$ff_id")
  echo "cash   firefly #$ff_id -> ghostfolio $(gf_field "$gf_id" name): $bal"
  [ "$DRY_RUN" = 1 ] && continue
  gf -X POST "$GF/account-balance" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg a "$gf_id" --argjson b "$bal" --arg d "${TODAY}T00:00:00.000Z" \
      '{accountId: $a, balance: $b, date: $d}')" >/dev/null
done

for pair in $INVEST_MAP; do
  ff_id=${pair%%:*}; gf_id=${pair#*:}
  check_currency "$ff_id" "$gf_id" || continue
  value=$(gf_field "$gf_id" value)
  bal=$(ff_balance "$ff_id")
  delta=$(awk -v v="$value" -v b="$bal" 'BEGIN { printf "%.2f", v - b }')
  abs=${delta#-}
  if awk -v a="$abs" -v m="$MIN_DELTA" 'BEGIN { exit !(a < m) }'; then
    echo "invest ghostfolio $(gf_field "$gf_id" name) $value vs firefly #$ff_id $bal: diff $delta below $MIN_DELTA, nothing to do"
    continue
  fi
  echo "invest ghostfolio $(gf_field "$gf_id" name) $value vs firefly #$ff_id $bal: booking $delta"
  [ "$DRY_RUN" = 1 ] && continue
  if [ "${delta#-}" = "$delta" ]; then
    split=$(jq -n --arg d "$TODAY" --arg a "$abs" --arg to "$ff_id" --arg src "$GAIN_ACCOUNT" --arg c "$CATEGORY" \
      '{type: "deposit", date: $d, amount: $a, source_name: $src, destination_id: $to, category_name: $c}')
  else
    split=$(jq -n --arg d "$TODAY" --arg a "$abs" --arg from "$ff_id" --arg dst "$LOSS_ACCOUNT" --arg c "$CATEGORY" \
      '{type: "withdrawal", date: $d, amount: $a, source_id: $from, destination_name: $dst, category_name: $c}')
  fi
  ff -X POST "$FF/transactions" -H 'Content-Type: application/json' \
    -d "$(echo "$split" | jq '. + {description: "Market value update (Ghostfolio)", tags: ["ghostfolio-sync"]} | {apply_rules: false, fire_webhooks: false, transactions: [.]}')" >/dev/null
done
