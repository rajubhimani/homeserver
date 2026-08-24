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

# ── Beszel agent pairing (blank is fine to start, same as Compose) ────
kubectl create secret generic beszel-credentials -n apps \
  --from-literal=agent-token="${BESZEL_AGENT_TOKEN:-}" \
  --from-literal=agent-key="${BESZEL_AGENT_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "beszel-credentials applied"

# ── Cloudflare Tunnel token ────────────────────────────────────────────
kubectl create secret generic cloudflared-credentials -n apps \
  --from-literal=tunnel-token="$TUNNEL_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "cloudflared-credentials applied"

# ── Paperless-ngx's own dedicated Postgres + app secrets ──────────────
kubectl create secret generic paperless-db-credentials -n apps \
  --from-literal=password="$PAPERLESS_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic paperless-credentials -n apps \
  --from-literal=secret-key="$PAPERLESS_SECRET_KEY" \
  --from-literal=admin-password="$PAPERLESS_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "paperless-db-credentials + paperless-credentials applied"

# ── Authentik's own dedicated Postgres + secret key ────────────────────
kubectl create secret generic authentik-db-credentials -n apps \
  --from-literal=password="$AUTHENTIK_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic authentik-credentials -n apps \
  --from-literal=secret-key="$AUTHENTIK_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "authentik-db-credentials + authentik-credentials applied"

# ── AppFlowy's own dedicated Postgres + MinIO + JWT secret ─────────────
# db-url/gotrue-db-url are pre-composed here, not built via k8s's $(VAR)
# substitution in the deployment manifest — same reasoning as immich's
# db-url above. gotrue-db-url's search_path override is copied verbatim
# from appflowy/compose.yml's GOTRUE_DB_DATABASE_URL.
kubectl create secret generic appflowy-db-credentials -n apps \
  --from-literal=password="$APPFLOWY_DB_PASSWORD" \
  --from-literal=db-url="postgres://appflowy:${APPFLOWY_DB_PASSWORD}@appflowy-db/appflowy" \
  --from-literal=gotrue-db-url="postgres://appflowy:${APPFLOWY_DB_PASSWORD}@appflowy-db/appflowy?options=-c%20search_path%3Dauth%2Cpublic" \
  --from-literal=minio-root-user="$APPFLOWY_MINIO_ROOT_USER" \
  --from-literal=minio-root-password="$APPFLOWY_MINIO_ROOT_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic appflowy-credentials -n apps \
  --from-literal=jwt-secret="$APPFLOWY_JWT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "appflowy-db-credentials + appflowy-credentials applied"

# ── Plane's own dedicated Postgres + RabbitMQ + MinIO + secret key ─────
kubectl create secret generic plane-db-credentials -n apps \
  --from-literal=password="$PLANE_DB_PASSWORD" \
  --from-literal=database-url="postgresql://plane:${PLANE_DB_PASSWORD}@plane-db/plane" \
  --from-literal=rabbitmq-password="$PLANE_RABBITMQ_PASSWORD" \
  --from-literal=minio-root-user="$PLANE_MINIO_ROOT_USER" \
  --from-literal=minio-root-password="$PLANE_MINIO_ROOT_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic plane-credentials -n apps \
  --from-literal=secret-key="$PLANE_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "plane-db-credentials + plane-credentials applied"

# ── Karakeep's Meilisearch master key + NextAuth secret ────────────────
kubectl create secret generic karakeep-credentials -n apps \
  --from-literal=meili-master-key="$KARAKEEP_MEILI_MASTER_KEY" \
  --from-literal=nextauth-secret="$KARAKEEP_NEXTAUTH_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "karakeep-credentials applied"

# ── Penpot's own dedicated Postgres + secret key ────────────────────────
kubectl create secret generic penpot-db-credentials -n apps \
  --from-literal=password="$PENPOT_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic penpot-credentials -n apps \
  --from-literal=secret-key="$PENPOT_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "penpot-db-credentials + penpot-credentials applied"

# ── Observability's Grafana admin login ─────────────────────────────────
kubectl create secret generic observability-credentials -n apps \
  --from-literal=admin-user="$OBSERVABILITY_GRAFANA_ADMIN_USER" \
  --from-literal=admin-password="$OBSERVABILITY_GRAFANA_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "observability-credentials applied"

# ── Supabase's own dedicated Postgres (one password, many roles) +
# every app secret. Connection strings use the exact role names
# supabase/volumes/db/roles.sql actually creates (authenticator,
# supabase_auth_admin, supabase_storage_admin, supabase_functions_admin,
# pgbouncer) — every role shares the one Postgres superuser password, same
# as upstream Supabase's own self-hosting docker-compose.
kubectl create secret generic supabase-db-credentials -n apps \
  --from-literal=password="$SUPABASE_POSTGRES_PASSWORD" \
  --from-literal=auth-db-url="postgres://supabase_auth_admin:${SUPABASE_POSTGRES_PASSWORD}@supabase-db:5432/postgres" \
  --from-literal=rest-db-uri="postgres://authenticator:${SUPABASE_POSTGRES_PASSWORD}@supabase-db:5432/postgres" \
  --from-literal=storage-db-url="postgres://supabase_storage_admin:${SUPABASE_POSTGRES_PASSWORD}@supabase-db:5432/postgres" \
  --from-literal=functions-db-url="postgres://supabase_functions_admin:${SUPABASE_POSTGRES_PASSWORD}@supabase-db:5432/postgres" \
  --from-literal=pooler-database-url="postgres://pgbouncer:${SUPABASE_POSTGRES_PASSWORD}@supabase-db:5432/postgres" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic supabase-credentials -n apps \
  --from-literal=jwt-secret="$SUPABASE_JWT_SECRET" \
  --from-literal=anon-key="$SUPABASE_ANON_KEY" \
  --from-literal=service-role-key="$SUPABASE_SERVICE_ROLE_KEY" \
  --from-literal=dashboard-username="$SUPABASE_DASHBOARD_USERNAME" \
  --from-literal=dashboard-password="$SUPABASE_DASHBOARD_PASSWORD" \
  --from-literal=secret-key-base="$SUPABASE_SECRET_KEY_BASE" \
  --from-literal=realtime-db-enc-key="$SUPABASE_REALTIME_DB_ENC_KEY" \
  --from-literal=vault-enc-key="$SUPABASE_VAULT_ENC_KEY" \
  --from-literal=pg-meta-crypto-key="$SUPABASE_PG_META_CRYPTO_KEY" \
  --from-literal=s3-access-key-id="$SUPABASE_S3_PROTOCOL_ACCESS_KEY_ID" \
  --from-literal=s3-access-key-secret="$SUPABASE_S3_PROTOCOL_ACCESS_KEY_SECRET" \
  --from-literal=pooler-tenant-id="$SUPABASE_POOLER_TENANT_ID" \
  --from-literal=publishable-key="${SUPABASE_PUBLISHABLE_KEY:-}" \
  --from-literal=secret-key="${SUPABASE_SECRET_KEY:-}" \
  --from-literal=anon-key-asymmetric="${SUPABASE_ANON_KEY_ASYMMETRIC:-}" \
  --from-literal=service-role-key-asymmetric="${SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC:-}" \
  --from-literal=openai-api-key="${SUPABASE_OPENAI_API_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "supabase-db-credentials + supabase-credentials applied"

# ── Dagster (DB only, no app tier ported) — shared Postgres ───────────
kubectl create secret generic dagster-db-credentials -n apps \
  --from-literal=password="$DAGSTER_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "dagster-db-credentials applied"

# ── Mattermost — shared Postgres ───────────────────────────────────────
kubectl create secret generic mattermost-db-credentials -n apps \
  --from-literal=password="$MATTERMOST_DB_PASSWORD" \
  --from-literal=datasource="postgres://mattermost:${MATTERMOST_DB_PASSWORD}@postgres-shared.data.svc.cluster.local:5432/mattermost?sslmode=disable&connect_timeout=10" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "mattermost-db-credentials applied"

# ── Airflow — shared Postgres + Fernet/JWT/API secrets + admin account ─
kubectl create secret generic airflow-db-credentials -n apps \
  --from-literal=password="$AIRFLOW_DB_PASSWORD" \
  --from-literal=sql-alchemy-conn="postgresql+psycopg2://airflow:${AIRFLOW_DB_PASSWORD}@postgres-shared.data.svc.cluster.local:5432/airflow" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic airflow-credentials -n apps \
  --from-literal=fernet-key="$AIRFLOW_FERNET_KEY" \
  --from-literal=jwt-secret="$AIRFLOW_JWT_SECRET" \
  --from-literal=api-secret-key="$AIRFLOW_API_SECRET_KEY" \
  --from-literal=admin-username="$AIRFLOW_ADMIN_USERNAME" \
  --from-literal=admin-password="$AIRFLOW_ADMIN_PASSWORD" \
  --from-literal=admin-email="$AIRFLOW_ADMIN_EMAIL" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "airflow-db-credentials + airflow-credentials applied"

# ── Temporal — shared Postgres (two databases, one role) ──────────────
kubectl create secret generic temporal-db-credentials -n apps \
  --from-literal=password="$TEMPORAL_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "temporal-db-credentials applied"

# ── Rocket.Chat — MongoDB runs with no auth, both keys optional ───────
kubectl create secret generic rocketchat-credentials -n apps \
  --from-literal=admin-password="${ROCKETCHAT_ADMIN_PASSWORD:-}" \
  --from-literal=reg-token="${ROCKETCHAT_REG_TOKEN:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "rocketchat-credentials applied"

# ── HomeBox's API key HMAC pepper ─────────────────────────────────────
kubectl create secret generic homebox-credentials -n apps \
  --from-literal=api-key-pepper="$HOMEBOX_AUTH_API_KEY_PEPPER" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "homebox-credentials applied"

# ── Zulip's own dedicated Postgres (vendor image) + RabbitMQ + Redis +
# Memcached + app secret key ───────────────────────────────────────────
kubectl create secret generic zulip-db-credentials -n apps \
  --from-literal=password="$ZULIP_DB_PASSWORD" \
  --from-literal=rabbitmq-password="$ZULIP_RABBITMQ_PASSWORD" \
  --from-literal=redis-password="$ZULIP_REDIS_PASSWORD" \
  --from-literal=memcached-password="$ZULIP_MEMCACHED_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic zulip-credentials -n apps \
  --from-literal=secret-key="$ZULIP_SECRET_KEY" \
  --from-literal=email-password="$ZULIP_EMAIL_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "zulip-db-credentials + zulip-credentials applied"

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
