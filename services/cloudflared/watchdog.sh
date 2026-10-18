#!/bin/sh
# Restarts the cloudflared container when the tunnel has gone stale: cloudflared's
# own healthcheck (`tunnel ready`) only checks its *local* connection count, which
# stayed "healthy" for ~11h during an incident where Cloudflare's edge had silently
# dropped every registered connection (public requests got edge error 530/1033).
#
# Two probes, best first:
#  1. Cloudflare API (needs CLOUDFLARE_API_TOKEN, "Cloudflare Tunnel: Read"): asks the
#     edge itself for this tunnel's status. "down" (no connections) or "degraded" is a
#     failure, "healthy" is good. Account and tunnel IDs come from TUNNEL_TOKEN (base64
#     JSON {"a": account, "t": tunnel, "s": secret}), so there is nothing else to set.
#  2. Fallback when no token is set or the API doesn't answer: request WATCHDOG_HOST, a
#     hostname routed to this tunnel, and read the status code: 530 is Cloudflare's "no
#     connector for this tunnel" answer, whatever the app behind it is doing. The
#     bare apex ${DOMAIN} and docs.${DOMAIN} can't be used: Cloudflare answers those
#     itself, and they stayed up while every tunnelled hostname returned 530 (2026-10-17).
# A host with no DNS/network (curl 000) is logged and ignored: restarting cloudflared
# doesn't fix that.
set -eu

: "${DOMAIN:?DOMAIN must be set}"
: "${WATCHDOG_HOST:=immich.${DOMAIN}}"
: "${CHECK_INTERVAL:=60}"
: "${FAIL_THRESHOLD:=3}"
: "${RESTART_COOLDOWN:=120}"
: "${CLOUDFLARE_API_TOKEN:=}"
: "${TUNNEL_TOKEN:=}"

account="" tunnel=""
if [ -n "$CLOUDFLARE_API_TOKEN" ]; then
  creds=$(printf '%s' "$TUNNEL_TOKEN" | tr '_-' '/+' | base64 -d 2>/dev/null || true)
  account=$(printf '%s' "$creds" | sed -n 's/.*"a":"\([^"]*\)".*/\1/p')
  tunnel=$(printf '%s' "$creds" | sed -n 's/.*"t":"\([^"]*\)".*/\1/p')
  if [ -z "$account" ] || [ -z "$tunnel" ]; then
    echo "watchdog: can't read the account/tunnel IDs from TUNNEL_TOKEN, using the hostname probe only"
  else
    echo "watchdog: probing tunnel ${tunnel} through the Cloudflare API (fallback: ${WATCHDOG_HOST})"
  fi
fi

# Prints good | bad | unknown.
check() {
  if [ -n "$account" ] && [ -n "$tunnel" ]; then
    body=$(curl -s --max-time 10 -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      "https://api.cloudflare.com/client/v4/accounts/${account}/cfd_tunnel/${tunnel}" || true)
    status=$(printf '%s' "$body" | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p' | head -n 1)
    case "$status" in
      healthy) echo good; return ;;
      down|degraded) echo "watchdog: Cloudflare reports the tunnel as ${status}" >&2; echo bad; return ;;
    esac
    echo "watchdog: no usable answer from the Cloudflare API (token wrong or API unreachable?), using the hostname probe" >&2
  fi
  code=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' "https://${WATCHDOG_HOST}/" || true)
  case "$code" in
    530) echo "watchdog: ${WATCHDOG_HOST} answered 530, the tunnel has no live connector" >&2; echo bad ;;
    000) echo "watchdog: no answer from ${WATCHDOG_HOST} (DNS/network down on this host?) — not a tunnel-stale case" >&2; echo unknown ;;
    *) echo good ;;
  esac
}

fails=0

while true; do
  sleep "$CHECK_INTERVAL"

  result=$(check)
  if [ "$result" != "bad" ]; then
    # One good answer only cancels one failure: the edge flaps between 530 and 200
    # while some connections are dead, and resetting to 0 hid that for hours.
    if [ "$result" = "good" ] && [ "$fails" -gt 0 ]; then fails=$((fails - 1)); fi
    continue
  fi

  fails=$((fails + 1))
  echo "watchdog: tunnel looks stale ($fails/$FAIL_THRESHOLD)"

  if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    echo "watchdog: threshold reached, restarting cloudflared"
    curl -fsS --unix-socket /var/run/docker.sock -X POST "http://localhost/containers/cloudflared/restart"
    fails=0
    sleep "$RESTART_COOLDOWN"
  fi
done
