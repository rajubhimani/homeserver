#!/bin/sh
# Reloads nginx-plain when acme.sh has put a new certificate in place.
# A renewal only needs SIGHUP. The very first certificate needs a restart instead: nginx-plain
# enables its HTTPS listeners at startup, only when the certificate files exist
# (docker-entrypoint.d/30-enable-tls.sh), so while port 443 refuses connections it is restarted.
set -eu

: "${CHECK_INTERVAL:=60}"
CERT=/certs/fullchain.pem
last=""

docker_api() {
  curl -fsS --unix-socket /var/run/docker.sock -X POST "http://localhost/containers/nginx-plain/$1"
}

while true; do
  sleep "$CHECK_INTERVAL"
  [ -s "$CERT" ] || continue
  now=$(cksum < "$CERT")
  [ "$now" = "$last" ] && continue

  # nginx-plain not running: nothing to reload, it reads the certificate when it starts.
  if ! curl -s --max-time 3 -o /dev/null "http://nginx-plain/_health"; then
    echo "acme-reload: nginx-plain is not answering, will retry"
    continue
  fi

  # -k: only asks whether the listener exists, the certificate itself is checked elsewhere.
  if curl -sk --max-time 5 -o /dev/null "https://nginx-plain:443/_health"; then
    echo "acme-reload: new certificate, reloading nginx-plain"
    docker_api "kill?signal=HUP"
  else
    echo "acme-reload: nginx-plain has no HTTPS listener yet, restarting it to enable it"
    docker_api "restart"
  fi
  last=$now
done
