#!/bin/sh
# Restarts the cloudflared container when the tunnel has gone stale: cloudflared's
# own healthcheck (`tunnel ready`) only checks its *local* connection count, which
# stayed "healthy" for ~11h during an incident where Cloudflare's edge had silently
# dropped every registered connection (public requests got edge error 530/1033).
# This probes the actual public path instead, and only restarts when the origin
# (nginx-plain) is confirmed reachable but the public path isn't — i.e. the tunnel
# itself is broken, not nginx or the wider network.
set -eu

: "${DOMAIN:?DOMAIN must be set}"
: "${CHECK_INTERVAL:=60}"
: "${FAIL_THRESHOLD:=3}"
: "${RESTART_COOLDOWN:=120}"

fails=0

while true; do
  sleep "$CHECK_INTERVAL"

  if curl -fsS --max-time 10 -o /dev/null "https://${DOMAIN}/"; then
    fails=0
    continue
  fi

  if ! curl -fsS --max-time 5 -H "Host: ${DOMAIN}" -o /dev/null "http://nginx-plain:80/"; then
    echo "watchdog: origin (nginx-plain) unreachable too — not a tunnel-stale case, skipping restart"
    continue
  fi

  fails=$((fails + 1))
  echo "watchdog: public path failed, origin is fine ($fails/$FAIL_THRESHOLD)"

  if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    echo "watchdog: threshold reached, restarting cloudflared"
    curl -fsS --unix-socket /var/run/docker.sock -X POST "http://localhost/containers/cloudflared/restart"
    fails=0
    sleep "$RESTART_COOLDOWN"
  fi
done
