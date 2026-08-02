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
