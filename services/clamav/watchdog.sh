#!/bin/sh
# clamav's own healthcheck (healthcheck.sh) catches a silently-failing
# freshclam -- a dead/misconfigured update process doesn't crash clamd, so
# without checking signature age the container would report "healthy"
# indefinitely with stale signatures. That healthcheck only surfaces the
# problem to `docker ps`/`docker inspect`, though, which nobody watches
# proactively. This polls the Docker API for that health status and pushes
# a real ntfy notification when it's been unhealthy for FAIL_THRESHOLD
# consecutive checks, with a cooldown so it doesn't re-alert every single
# check interval while the problem persists.
set -eu

: "${CHECK_INTERVAL:=300}"
: "${FAIL_THRESHOLD:=2}"
: "${ALERT_COOLDOWN:=21600}"
: "${NTFY_URL:?NTFY_URL must be set}"
: "${NTFY_TOKEN:?NTFY_TOKEN must be set}"

fails=0
last_alert=0

is_healthy() {
  curl -fsS --unix-socket /var/run/docker.sock \
    "http://localhost/containers/clamav/json" \
    | grep -q '"Status":"healthy"'
}

alert() {
  now=$(date +%s)
  elapsed=$((now - last_alert))
  if [ "$last_alert" -ne 0 ] && [ "$elapsed" -lt "$ALERT_COOLDOWN" ]; then
    echo "watchdog: clamav unhealthy, but alerted ${elapsed}s ago (cooldown ${ALERT_COOLDOWN}s) -- not re-alerting"
    return
  fi
  echo "watchdog: clamav unhealthy for $FAIL_THRESHOLD consecutive checks, alerting via ntfy"
  curl -fsS \
    -H "Authorization: Bearer $NTFY_TOKEN" \
    -H "Title: ClamAV signatures may be stale" \
    -H "Priority: high" \
    -H "Tags: warning,biohazard" \
    -d "clamav has been unhealthy for $((FAIL_THRESHOLD * CHECK_INTERVAL))s+. Likely cause: freshclam failing to update signatures (network/DNS/rate-limit) -- check 'docker logs clamav | grep -i freshclam'. See docs/services/clamav.md." \
    "$NTFY_URL" >/dev/null
  last_alert=$now
}

while true; do
  sleep "$CHECK_INTERVAL"

  if is_healthy; then
    fails=0
    continue
  fi

  fails=$((fails + 1))
  echo "watchdog: clamav health check failed ($fails/$FAIL_THRESHOLD)"

  if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    alert
  fi
done
