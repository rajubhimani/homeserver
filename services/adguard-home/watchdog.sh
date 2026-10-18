#!/bin/sh
# adguard-home has occasionally lost its Docker network attachment entirely —
# `docker inspect` reports NetworkSettings.Networks as {} and the container
# has no eth0 at all, just loopback, so every DNS/upstream lookup fails with
# "network is unreachable". adguard-home's own healthcheck only probes its
# local web API on 127.0.0.1:3000, which stays "healthy" throughout since
# that doesn't depend on the network at all — first hit 2026-08-26, root
# cause unconfirmed (no matching docker/journalctl event found), but `docker
# restart` alone did NOT reattach it; only an explicit network
# disconnect+connect did. This watches for that specific state via the
# Docker API and repairs it the same way.
#
# Every repair is also pushed to ntfy (NTFY_URL/NTFY_TOKEN), so it's never
# silent. The suspected root cause is the reboot race fixed by
# docker/host-boot-safety.sh on 2026-09-25 (a failed 10.8.0.1 port bind can
# leave a container with no network endpoint). If no alert arrives for
# several weeks after that fix, this watchdog can be retired with evidence.
set -eu

: "${CHECK_INTERVAL:=60}"
: "${FAIL_THRESHOLD:=2}"
: "${RESTART_COOLDOWN:=60}"

fails=0

is_attached() {
  curl -fsS --unix-socket /var/run/docker.sock \
    "http://localhost/containers/adguard-home/json" \
    | grep -q '"IPAddress":"[0-9]'
}

reattach() {
  echo "watchdog: adguard-home has no network attachment, reattaching to homeserver"
  curl -fsS --unix-socket /var/run/docker.sock -X POST \
    -H "Content-Type: application/json" \
    -d '{"Container":"adguard-home","Force":true}' \
    "http://localhost/networks/homeserver/disconnect" >/dev/null 2>&1 || true
  curl -fsS --unix-socket /var/run/docker.sock -X POST \
    -H "Content-Type: application/json" \
    -d '{"Container":"adguard-home"}' \
    "http://localhost/networks/homeserver/connect"
  echo "watchdog: reattached"
  if [ -n "${NTFY_URL:-}" ] && [ -n "${NTFY_TOKEN:-}" ]; then
    curl -fsS -m 10 -H "Authorization: Bearer $NTFY_TOKEN" \
      -H "Title: AdGuard lost its network and was reattached" \
      -H "Tags: warning,electric_plug" \
      -d "adguard-watchdog found adguard-home with no network attachment and reconnected it. See docs/services/adguard-home.md." \
      "$NTFY_URL" >/dev/null || echo "watchdog: ntfy alert failed"
  fi
}

while true; do
  sleep "$CHECK_INTERVAL"

  if is_attached; then
    fails=0
    continue
  fi

  fails=$((fails + 1))
  echo "watchdog: adguard-home network check failed ($fails/$FAIL_THRESHOLD)"

  if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    reattach
    fails=0
    sleep "$RESTART_COOLDOWN"
  fi
done
