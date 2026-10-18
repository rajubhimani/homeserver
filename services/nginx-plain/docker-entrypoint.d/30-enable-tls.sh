#!/bin/sh
# Serves every site over HTTPS as well when the acme service has put a certificate in
# /etc/nginx/certs (fullchain.pem + privkey.pem). Runs after 20-envsubst-on-templates.sh has
# written conf.d/default.conf. Without a certificate nginx-plain stays HTTP-only, exactly as
# before, so a machine that never configures acme is unaffected. The acme-reload container
# restarts nginx-plain once the first certificate appears; renewals only need SIGHUP.
set -eu

CONF=/etc/nginx/conf.d/default.conf
CERT=/etc/nginx/certs/fullchain.pem
KEY=/etc/nginx/certs/privkey.pem

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
  echo "30-enable-tls: no certificate in /etc/nginx/certs, serving HTTP only"
  exit 0
fi

cat > /etc/nginx/conf.d/00-tls.conf <<EOF
ssl_certificate     $CERT;
ssl_certificate_key $KEY;
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_session_cache   shared:SSL:10m;
ssl_session_timeout 1d;
ssl_session_tickets off;
EOF

# Every server block opens with "    listen 80;": add the TLS listener right after it.
sed -i 's/^    listen 80;$/&\n    listen 443 ssl;\n    http2 on;/' "$CONF"
echo "30-enable-tls: HTTPS enabled on $(grep -c '^    listen 443 ssl;$' "$CONF") server blocks"
