#!/bin/sh
#
# Reapplies two fixes Coolify's own database resets on every fresh
# install (a new DB volume, or after wiping and reinstalling): the
# coolify-proxy port conflict and the Sentinel push URL. Both live in
# Coolify's database, not this repo's compose.yml, so they don't survive
# a fresh install on their own — see docs/services/coolify.md.
#
# Run this once the "localhost" server is connected (Settings -> Private
# Keys, then Servers -> localhost -> Validate Server), not before —
# both actions need a working SSH connection to the host to actually do
# anything.
#
# Usage:
#   sh services/coolify/fix-proxy-sentinel.sh
#
set -e

# Read the port from the actually-running container, not a compose file —
# this works regardless of dev/prod mode or any future port renumbering.
COOLIFY_HOST_PORT=$(docker port coolify 8080/tcp 2>/dev/null | head -1 | grep -oE '[0-9]+$')
if [ -z "$COOLIFY_HOST_PORT" ]; then
  echo "Could not determine coolify's published host port — is the coolify container running? Aborting." >&2
  exit 1
fi

echo "Using coolify host port: $COOLIFY_HOST_PORT"

# 1. Proxy fix: drop Traefik's optional dashboard (port 8080), which
#    otherwise conflicts with landing's own host port 8080. 80/443 stay
#    untouched. See "Coolify's own proxy (coolify-proxy) needs port 8080
#    freed up" in docs/services/coolify.md for the full explanation.
cat > /tmp/coolify-proxy-fix.yaml << 'EOF'
name: coolify-proxy
networks:
  coolify:
    external: true
services:
  traefik:
    container_name: coolify-proxy
    image: 'traefik:v3.7'
    restart: unless-stopped
    extra_hosts:
      - 'host.docker.internal:host-gateway'
    networks:
      - coolify
    ports:
      - '80:80'
      - '443:443'
      - '443:443/udp'
    healthcheck:
      test: 'wget -qO- http://localhost:80/ping || exit 1'
      interval: 4s
      timeout: 2s
      retries: 5
    volumes:
      - '/var/run/docker.sock:/var/run/docker.sock:ro'
      - '/data/coolify/proxy/:/traefik'
    command:
      - '--ping=true'
      - '--ping.entrypoint=http'
      - '--entrypoints.http.address=:80'
      - '--entrypoints.https.address=:443'
      - '--entrypoints.http.http.encodequerysemicolons=true'
      - '--entryPoints.http.http2.maxConcurrentStreams=250'
      - '--entrypoints.https.http.encodequerysemicolons=true'
      - '--entryPoints.https.http2.maxConcurrentStreams=250'
      - '--entrypoints.https.http3'
      - '--providers.file.directory=/traefik/dynamic/'
      - '--providers.file.watch=true'
      - '--certificatesresolvers.letsencrypt.acme.httpchallenge=true'
      - '--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=http'
      - '--certificatesresolvers.letsencrypt.acme.storage=/traefik/acme.json'
      - '--providers.docker=true'
      - '--providers.docker.exposedbydefault=false'
    labels:
      - coolify.managed=true
      - coolify.proxy=true
EOF

docker cp /tmp/coolify-proxy-fix.yaml coolify:/tmp/coolify-proxy-fix.yaml
rm -f /tmp/coolify-proxy-fix.yaml

echo "Applying proxy fix..."
docker exec coolify php artisan tinker --execute="
\$server = App\Models\Server::find(0);
\$config = file_get_contents('/tmp/coolify-proxy-fix.yaml');
App\Actions\Proxy\SaveProxyConfiguration::run(\$server, \$config);
\$result = App\Actions\Proxy\StartProxy::run(\$server, async: false, force: true);
echo 'Proxy start result: ' . \$result . PHP_EOL;
"

# 2. Sentinel fix: Coolify hardcodes http://host.docker.internal:8000
#    for the localhost server's metrics-push URL (its own standard
#    install publishes the app on host port 8000). This stack maps
#    coolify to a different host port, so that default is wrong here.
echo "Applying sentinel URL fix (pointing at host port $COOLIFY_HOST_PORT)..."
docker exec coolify php artisan tinker --execute="
\$server = App\Models\Server::find(0);
\$settings = \$server->settings;
\$settings->sentinel_custom_url = 'http://host.docker.internal:$COOLIFY_HOST_PORT';
\$settings->save();
echo 'Sentinel URL set to: ' . \$settings->fresh()->sentinel_custom_url . PHP_EOL;
"

echo "Done. Check the Coolify UI's Server page — proxy should show running, metrics should populate within a minute or two."
