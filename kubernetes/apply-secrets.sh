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

# ── Guacamole's own dedicated Postgres password ──────────────────────
kubectl create secret generic guacamole-db-credentials -n apps \
  --from-literal=password="$GUACAMOLE_DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "guacamole-db-credentials applied"

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
