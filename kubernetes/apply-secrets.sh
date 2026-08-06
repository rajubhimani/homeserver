#!/usr/bin/env bash
# Reads kubernetes/.env and creates/updates the matching Kubernetes Secrets.
# Same role as homeserver.py injecting a service's .env into its containers —
# .env is the source of truth, this script is what actually applies it.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "kubernetes/.env not found — copy .env.example to .env and fill in real values first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

# ── Shared Postgres superuser password ──────────────────────────────
kubectl create secret generic postgres-shared-credentials -n data \
  --from-literal=postgres-password="$POSTGRES_SHARED_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "postgres-shared-credentials applied"

# ── Shared MariaDB root password ──────────────────────────────────────
kubectl create secret generic mariadb-shared-credentials -n data \
  --from-literal=root-password="$MARIADB_SHARED_ROOT_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "mariadb-shared-credentials applied"

# ── Guacamole's own dedicated Postgres password ──────────────────────
kubectl create secret generic guacamole-db-credentials -n apps \
  --from-literal=password="$GUACAMOLE_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "guacamole-db-credentials applied"

# ── Vaultwarden admin token ───────────────────────────────────────────
kubectl create secret generic vaultwarden-credentials -n apps \
  --from-literal=admin-token="$VAULTWARDEN_ADMIN_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "vaultwarden-credentials applied"

# ── Forgejo's own dedicated Postgres password ─────────────────────────
kubectl create secret generic forgejo-db-credentials -n apps \
  --from-literal=password="$FORGEJO_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "forgejo-db-credentials applied"

# ── Firefly's own dedicated Postgres password + app secrets ──────────
kubectl create secret generic firefly-db-credentials -n apps \
  --from-literal=password="$FIREFLY_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic firefly-credentials -n apps \
  --from-literal=app-key="$FIREFLY_APP_KEY" \
  --from-literal=cron-token="$FIREFLY_CRON_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "firefly-db-credentials + firefly-credentials applied"

# ── Nextcloud's own dedicated Postgres password + admin password ─────
kubectl create secret generic nextcloud-db-credentials -n apps \
  --from-literal=password="$NEXTCLOUD_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic nextcloud-credentials -n apps \
  --from-literal=admin-password="$NEXTCLOUD_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "nextcloud-db-credentials + nextcloud-credentials applied"

# ── Immich's own dedicated Postgres password + app secret ────────────
# db-url is pre-composed here, not built via k8s's $(VAR) substitution in
# the deployment manifest — that only resolves references to variables
# defined *earlier* in the same env list, which silently failed and
# crash-looped immich-server/immich-ml (see deployment.yaml's comment).
kubectl create secret generic immich-db-credentials -n apps \
  --from-literal=password="$IMMICH_DB_PASSWORD" \
  --from-literal=db-url="postgresql://immich:${IMMICH_DB_PASSWORD}@immich-db:5432/immich" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic immich-credentials -n apps \
  --from-literal=secret="$IMMICH_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "immich-db-credentials + immich-credentials applied"

# ── SilverBullet basic-auth login ─────────────────────────────────────
kubectl create secret generic silverbullet-credentials -n apps \
  --from-literal=sb-user="$SILVERBULLET_SB_USER" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "silverbullet-credentials applied"

# ── OpenProject secret key ────────────────────────────────────────────
kubectl create secret generic openproject-credentials -n apps \
  --from-literal=secret-key-base="$OPENPROJECT_SECRET_KEY_BASE" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "openproject-credentials applied"

# ── Mealie's own dedicated Postgres password ──────────────────────────
kubectl create secret generic mealie-db-credentials -n apps \
  --from-literal=password="$MEALIE_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "mealie-db-credentials applied"

# ── Miniflux's own dedicated Postgres password + admin account ────────
kubectl create secret generic miniflux-db-credentials -n apps \
  --from-literal=password="$MINIFLUX_DB_PASSWORD" \
  --from-literal=database-url="postgres://miniflux:${MINIFLUX_DB_PASSWORD}@miniflux-db/miniflux?sslmode=disable" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic miniflux-credentials -n apps \
  --from-literal=admin-password="$MINIFLUX_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "miniflux-db-credentials + miniflux-credentials applied"

# ── Vikunja's own dedicated Postgres password ─────────────────────────
kubectl create secret generic vikunja-db-credentials -n apps \
  --from-literal=password="$VIKUNJA_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "vikunja-db-credentials applied"

# ── BookStack's own dedicated MariaDB + app key ───────────────────────
kubectl create secret generic bookstack-db-credentials -n apps \
  --from-literal=root-password="$BOOKSTACK_DB_ROOT_PASSWORD" \
  --from-literal=password="$BOOKSTACK_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic bookstack-credentials -n apps \
  --from-literal=app-key="$BOOKSTACK_APP_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "bookstack-db-credentials + bookstack-credentials applied"

# ── Outline's own dedicated Postgres + core secrets ───────────────────
kubectl create secret generic outline-db-credentials -n apps \
  --from-literal=password="$OUTLINE_DB_PASSWORD" \
  --from-literal=database-url="postgres://outline:${OUTLINE_DB_PASSWORD}@outline-db:5432/outline?sslmode=disable" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic outline-credentials -n apps \
  --from-literal=secret-key="$OUTLINE_SECRET_KEY" \
  --from-literal=utils-secret="$OUTLINE_UTILS_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "outline-db-credentials + outline-credentials applied"

# ── Wallabag's own dedicated Postgres + Symfony secret ────────────────
kubectl create secret generic wallabag-db-credentials -n apps \
  --from-literal=password="$WALLABAG_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic wallabag-credentials -n apps \
  --from-literal=secret="$WALLABAG_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "wallabag-db-credentials + wallabag-credentials applied"

# ── Atuin's own dedicated Postgres ────────────────────────────────────
kubectl create secret generic atuin-db-credentials -n apps \
  --from-literal=password="$ATUIN_DB_PASSWORD" \
  --from-literal=db-uri="postgres://atuin:${ATUIN_DB_PASSWORD}@atuin-db/atuin" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "atuin-db-credentials applied"

# ── NocoDB's own dedicated Postgres + JWT secret ──────────────────────
kubectl create secret generic nocodb-db-credentials -n apps \
  --from-literal=password="$NOCODB_DB_PASSWORD" \
  --from-literal=nc-db-uri="pg://nocodb-db:5432?u=nocodb&p=${NOCODB_DB_PASSWORD}&d=nocodb" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic nocodb-credentials -n apps \
  --from-literal=jwt-secret="$NOCODB_JWT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "nocodb-db-credentials + nocodb-credentials applied"

# ── Listmonk's own dedicated Postgres + admin bootstrap account ───────
kubectl create secret generic listmonk-db-credentials -n apps \
  --from-literal=password="$LISTMONK_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic listmonk-credentials -n apps \
  --from-literal=admin-password="$LISTMONK_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "listmonk-db-credentials + listmonk-credentials applied"

# ── Documenso's own dedicated Postgres + app secrets ──────────────────
kubectl create secret generic documenso-db-credentials -n apps \
  --from-literal=password="$DOCUMENSO_DB_PASSWORD" \
  --from-literal=database-url="postgres://documenso:${DOCUMENSO_DB_PASSWORD}@documenso-db:5432/documenso" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic documenso-credentials -n apps \
  --from-literal=nextauth-secret="$DOCUMENSO_NEXTAUTH_SECRET" \
  --from-literal=encryption-key="$DOCUMENSO_ENCRYPTION_KEY" \
  --from-literal=encryption-secondary-key="$DOCUMENSO_ENCRYPTION_SECONDARY_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "documenso-db-credentials + documenso-credentials applied"

# Documenso refuses to start without a valid cert.p12 for local document
# signing. This pilot has no real signing use, so generate a throwaway
# self-signed one on the fly rather than committing a cert to the repo.
DOCUMENSO_CERT_DIR=$(mktemp -d)
openssl genrsa -out "$DOCUMENSO_CERT_DIR/private.key" 2048 >/dev/null 2>&1
# Doubled leading slash ("//CN=...") tells Git Bash's path-conversion to
# leave just this one argument alone, without disabling conversion for the
# surrounding -key/-out paths too (see kubernetes/TROUBLESHOOTING.md)
openssl req -new -x509 -key "$DOCUMENSO_CERT_DIR/private.key" -out "$DOCUMENSO_CERT_DIR/certificate.crt" -days 3650 -subj "//CN=documenso.k8s.local" >/dev/null 2>&1
openssl pkcs12 -export -out "$DOCUMENSO_CERT_DIR/cert.p12" -inkey "$DOCUMENSO_CERT_DIR/private.key" -in "$DOCUMENSO_CERT_DIR/certificate.crt" -legacy -passout pass: >/dev/null 2>&1
kubectl create secret generic documenso-cert -n apps \
  --from-file=cert.p12="$DOCUMENSO_CERT_DIR/cert.p12" \
  --dry-run=client -o yaml | kubectl apply -f -
rm -rf "$DOCUMENSO_CERT_DIR"
echo "documenso-cert applied"

# ── InvoiceShelf's own dedicated MariaDB + Laravel app key ────────────
kubectl create secret generic invoiceshelf-db-credentials -n apps \
  --from-literal=root-password="$INVOICESHELF_DB_ROOT_PASSWORD" \
  --from-literal=password="$INVOICESHELF_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic invoiceshelf-credentials -n apps \
  --from-literal=app-key="$INVOICESHELF_APP_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "invoiceshelf-db-credentials + invoiceshelf-credentials applied"

# ── OrangeHRM's own dedicated MariaDB ──────────────────────────────────
kubectl create secret generic orangehrm-db-credentials -n apps \
  --from-literal=root-password="$ORANGEHRM_DB_ROOT_PASSWORD" \
  --from-literal=password="$ORANGEHRM_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "orangehrm-db-credentials applied"

# ── Cal.com's own dedicated Postgres + app secrets ────────────────────
kubectl create secret generic calcom-db-credentials -n apps \
  --from-literal=password="$CALCOM_DB_PASSWORD" \
  --from-literal=database-url="postgresql://calcom:${CALCOM_DB_PASSWORD}@calcom-db:5432/calcom" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic calcom-credentials -n apps \
  --from-literal=nextauth-secret="$CALCOM_NEXTAUTH_SECRET" \
  --from-literal=encryption-key="$CALCOM_ENCRYPTION_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "calcom-db-credentials + calcom-credentials applied"

# ── Plausible's own dedicated Postgres + ClickHouse + app secrets ─────
kubectl create secret generic plausible-db-credentials -n apps \
  --from-literal=password="$PLAUSIBLE_DB_PASSWORD" \
  --from-literal=clickhouse-password="$PLAUSIBLE_CLICKHOUSE_PASSWORD" \
  --from-literal=database-url="postgres://postgres:${PLAUSIBLE_DB_PASSWORD}@plausible-db:5432/plausible" \
  --from-literal=clickhouse-url="http://plausible:${PLAUSIBLE_CLICKHOUSE_PASSWORD}@plausible-events-db:8123/plausible_events_db" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic plausible-credentials -n apps \
  --from-literal=secret-key-base="$PLAUSIBLE_SECRET_KEY_BASE" \
  --from-literal=totp-vault-key="$PLAUSIBLE_TOTP_VAULT_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "plausible-db-credentials + plausible-credentials applied"

# ── n8n's own dedicated Postgres + credential encryption key ──────────
kubectl create secret generic n8n-db-credentials -n apps \
  --from-literal=password="$N8N_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic n8n-credentials -n apps \
  --from-literal=encryption-key="$N8N_ENCRYPTION_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "n8n-db-credentials + n8n-credentials applied"

# ── Stirling-PDF Lite admin login ──────────────────────────────────────
kubectl create secret generic stirling-pdf-lite-credentials -n apps \
  --from-literal=admin-password="$STIRLING_PDF_LITE_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "stirling-pdf-lite-credentials applied"

# ── Open WebUI session secret ───────────────────────────────────────────
kubectl create secret generic open-webui-credentials -n apps \
  --from-literal=secret-key="$OPEN_WEBUI_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "open-webui-credentials applied"

# ── ArgoCD admin password ────────────────────────────────────────────
# ArgoCD only accepts a bcrypt hash in its Secret, never plaintext — hash it
# here via uv (repo already uses uv for homeserver.py; --with bcrypt pulls
# the package into an ephemeral venv, no project dependency added).
HASH=$(cd .. && uv run --with bcrypt python -c "
import bcrypt, sys
print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt(10)).decode())
" "$ARGOCD_ADMIN_PASSWORD")

kubectl -n argocd patch secret argocd-secret -p "{\"stringData\": {
  \"admin.password\": \"$HASH\",
  \"admin.passwordMtime\": \"$(date -u +%FT%TZ)\"
}}"
echo "argocd admin password applied"
