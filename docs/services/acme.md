# acme

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** gets one Let's Encrypt wildcard certificate (`*.${DOMAIN}` + `${DOMAIN}`) for this server and renews it automatically, so `nginx-plain` can serve every site over HTTPS with a certificate this server owns. **Port:** none | **Tier:** MIN | **Requires:** a Cloudflare API token (DNS edit) | **Containers:** `acme` (lego), `acme-reload`

## What it does and what it does not do

```
Browser ══HTTPS══▶ Cloudflare edge ══encrypted tunnel══▶ cloudflared ──▶ nginx-plain
          Cloudflare's cert           (outbound only)                   :80 plain  or  :443 with THIS certificate
```

- It covers every one-label subdomain (`immich.${DOMAIN}`, `nextcloud.${DOMAIN}`, anything added later) with a single certificate. A two-label name (`a.b.${DOMAIN}`) would not match; none exists today.
- **It does not remove Cloudflare from the path.** A browser reaching a public hostname through the Cloudflare Tunnel still negotiates HTTPS with Cloudflare's edge, which has to read the request to route it. Cloudflare can therefore see what passes through (URLs, cookies, form fields including login passwords, uploaded files), unless the app encrypts it first (Vaultwarden does). That is how a proxied HTTP tunnel works. Hiding traffic from Cloudflare needs a relay that forwards the encrypted connection untouched (for example a VPS with SNI passthrough), which this service does not do.
- What it does give: (1) the tunnel can be switched to `https://nginx-plain:443` with certificate verification on, so the last hop is encrypted and checked too, and (2) a trusted padlock when you reach `nginx-plain` directly on the LAN or over the VPN (see below).
- Before this existed, the only certificate for the domain was Cloudflare's Universal SSL one (also `*.${DOMAIN}` + `${DOMAIN}`, issued through Let's Encrypt, held and renewed by Cloudflare).

## Setup

1. Create a Cloudflare API token (dash.cloudflare.com → My Profile → API Tokens → Create Custom Token) with **Zone / DNS / Edit** and **Zone / Zone / Read**, limited to this domain's zone.
2. Fill `services/acme/.env` (see `.env.example`): `CLOUDFLARE_DNS_API_TOKEN` (and optionally `ACME_EMAIL`). Leave `ACME_SERVER=letsencrypt-staging` first.
3. `uv run homeserver.py prod up acme`, then `docker logs -f acme`. A first issuance takes a minute or two (DNS propagation).
4. When the staging certificate was written, `acme-reload` restarts `nginx-plain` once so it opens its HTTPS listeners. Check: `openssl x509 -in service_data/data/nginx-plain/certs/fullchain.pem -noout -issuer -ext subjectAltName`.
5. Switch to production: set `ACME_SERVER=letsencrypt` and `uv run homeserver.py prod up acme`. Each CA has its own state directory under `service_data/data/acme/lego/`, so this requests a fresh certificate; `acme-reload` then reloads nginx-plain.

Until `CLOUDFLARE_DNS_API_TOKEN` is set the container idles and says so in its log; nothing else changes. `ACME_EMAIL` is optional (Let's Encrypt stopped expiry emails in 2025; lego registers without one).

## How it works

- `acme.sh` runs `lego run` every `ACME_CHECK_INTERVAL` (12 h). `lego run` is idempotent: it requests a certificate if there is none, renews when due, and does nothing otherwise. By default it renews with a third of the lifetime left, so Let's Encrypt's move of the classic profile from 90 days to 64 days (2027-02-10) and 45 days (2028-02-16) needs no change. A failed run is retried after `ACME_RETRY_INTERVAL` and leaves the existing certificate in place.
- It copies `certificates/wildcard.crt` and `.key` to `fullchain.pem` and `privkey.pem` in nginx-plain's certificate directory (`CERTS_DIR`, the `certs/` folder under `service_data/data/nginx-plain/`), through a temp file and `mv`, only when the content changed.
- `acme-reload.sh` checks the certificate every 60 s. A changed certificate gets `SIGHUP` to `nginx-plain` (no dropped connections). If `nginx-plain` has no HTTPS listener yet (first certificate), it restarts it instead.
- `nginx-plain` side: `services/nginx-plain/docker-entrypoint.d/30-enable-tls.sh` runs at startup. If the certificate files exist it writes `conf.d/00-tls.conf` (protocols TLS 1.2/1.3, session cache) and adds `listen 443 ssl; http2 on;` after every `listen 80;`. Without certificates it does nothing, so a machine that never sets up acme keeps serving plain HTTP only. `listen 80` stays everywhere: the tunnel, the landing page health checks and the watchdogs keep using it.
- The tested flow (not just read from docs): lego v5.5.2 against a local Pebble ACME test server with an always-valid challenge, then an nginx container with the real template: certificate written as `certificates/wildcard.crt|.key`, a second `run` skipped as not due, `--renew-force` replaced the files, 72 server blocks got the HTTPS listener, HTTPS (HTTP/2, TLS 1.3) and plain HTTP both answered, and `SIGHUP` reloaded cleanly. The Cloudflare DNS-01 step itself was not run (it needs your token).

## Using it

**Re-encrypt the tunnel (optional, manual in the Cloudflare dashboard).** Ingress is managed on Cloudflare's side. For each Public Hostname (Zero Trust → Networks → Tunnels → this tunnel → Public Hostname), change the service from `http://nginx-plain:80` to `https://nginx-plain:443`, and under Additional settings → TLS leave *No TLS Verify* off and turn on *Match SNI to Host* (or set *Origin Server Name* to the hostname), so the wildcard certificate matches. Set the zone's SSL/TLS mode to **Full (strict)**. Do one hostname at a time, immich first, watching `docker logs cloudflared`; switch it back to `http://nginx-plain:80` if it fails. Use the production certificate, not staging, or verification fails by design.

**Trusted HTTPS on the LAN or VPN.** With the production certificate, `https://immich.${DOMAIN}` is valid anywhere the name resolves to `nginx-plain`. Add an AdGuard Home DNS rewrite (Filters → DNS rewrites) `*.${DOMAIN}` → the server's LAN IP (or `10.8.0.1` for VPN clients). That needs host port 443 published on that address; `compose.prod.yml` currently publishes `127.0.0.1:8443` and `10.8.0.1:8443` only, so until you add a `443` mapping, use `https://immich.${DOMAIN}:8443` over the VPN. Mind that a rewrite sends those names to the server even when the tunnel is up.

## Env vars

All in `services/acme/.env` (twelve-factor; see `.env.example`): `ACME_EMAIL`, `CLOUDFLARE_DNS_API_TOKEN`, `ACME_SERVER`, `ACME_PROFILE`, `ACME_RENEW_DAYS`, `ACME_CHECK_INTERVAL`, `ACME_RETRY_INTERVAL`, `ACME_DNS_PROVIDER`, `ACME_PROPAGATION_WAIT`, `ACME_LEGO_ARGS`, plus the paths `DATA_ROOT` and `CERTS_DIR` (not auto-injected: keep it equal to nginx-plain's `certs` directory). Another DNS host works by changing `ACME_DNS_PROVIDER` and supplying that provider's variables (`lego dnshelp`).

## Notes

- `privkey.pem` is mode 600; `service_data/data/acme/` and the certs directory are inside the normal snapshots.
- Do not run staging and production against the same name at the same time: the staging certificate overwrites `fullchain.pem` whenever `ACME_SERVER` is staging.
- Image: `goacme/lego:v5.5.2` (current release on Docker Hub, 2026-09-23). Its entrypoint is the `/lego` binary, which is why the data volume is mounted at `/data`.
- Kubernetes: not ported (retired); cert-manager would do this there. See `kubernetes/scope.yaml`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
