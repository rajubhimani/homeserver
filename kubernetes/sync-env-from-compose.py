#!/usr/bin/env python3
"""kubernetes/sync-env-from-compose.py — pulls real secret values from the
already-configured Compose stack's services/<service>/.env files into
kubernetes/.env, wherever the same secret exists on both sides under a
different name (the two orchestrators don't share a naming convention —
Compose uses e.g. POSTGRES_PASSWORD per-service, k8s.env uses
FORGEJO_DB_PASSWORD, MATTERMOST_DB_PASSWORD, etc.). Saves retyping ~110
passwords by hand when the Compose side already has them for real.

Only copies a value across when the Compose side actually looks real —
not still a `your_..._here`/`changeme`/`PLEASE_CHANGE_ME...` placeholder
(see is_placeholder()). Never overwrites an already-real value already
sitting in kubernetes/.env with a Compose-side placeholder — if there's
nothing real to copy, the existing kubernetes/.env value (or
kubernetes/.env.example's own default, if kubernetes/.env doesn't exist
yet) is left exactly as-is, for you to fill in by hand. This mirrors the
same "leave it, don't guess" idiom apply-secrets.py's Env class uses for
genuinely missing values.

Keys with no Compose equivalent at all (ARGOCD_ADMIN_PASSWORD,
POSTGRES_SHARED_PASSWORD, MARIADB_SHARED_ROOT_PASSWORD — this pilot's own
shared-server/ArgoCD secrets, not a per-service Compose thing) are never
touched by this script; fill those in by hand same as always.

Usage: uv run kubernetes/sync-env-from-compose.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

K8S_DIR = Path(__file__).resolve().parent
BASE_DIR = K8S_DIR.parent
SERVICES_DIR = BASE_DIR / "services"
ENV_EXAMPLE_PATH = K8S_DIR / ".env.example"
ENV_PATH = K8S_DIR / ".env"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}▶ {msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}✔ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠ {msg}{RESET}")


def error(msg: str) -> None:
    print(f"{RED}✖ {msg}{RESET}", file=sys.stderr)


# k8s.env key -> (services/<slug>/.env, that file's own key). Built by
# reading every relevant services/<slug>/.env.example against
# kubernetes/.env.example — same secret, different orchestrator's naming
# convention. Services with no secrets needed in kubernetes/.env.example
# (docs, mailpit, the 5 browsers, gitlab, stirling-pdf full) have nothing
# to map. Keys with no entry here (ARGOCD_ADMIN_PASSWORD,
# POSTGRES_SHARED_PASSWORD, MARIADB_SHARED_ROOT_PASSWORD) are k8s-only,
# never touched.
MAPPING: dict[str, tuple[str, str]] = {
    "GUACAMOLE_DB_PASSWORD": ("guacamole", "POSTGRES_PASSWORD"),
    "VAULTWARDEN_ADMIN_TOKEN": ("vaultwarden", "ADMIN_TOKEN"),
    "FORGEJO_DB_PASSWORD": ("forgejo", "POSTGRES_PASSWORD"),
    "FIREFLY_DB_PASSWORD": ("firefly", "POSTGRES_PASSWORD"),
    "FIREFLY_APP_KEY": ("firefly", "APP_KEY"),
    "FIREFLY_CRON_TOKEN": ("firefly", "STATIC_CRON_TOKEN"),
    "NEXTCLOUD_DB_PASSWORD": ("nextcloud", "POSTGRES_PASSWORD"),
    "NEXTCLOUD_ADMIN_PASSWORD": ("nextcloud", "NEXTCLOUD_ADMIN_PASSWORD"),
    "IMMICH_DB_PASSWORD": ("immich", "DB_PASSWORD"),
    "IMMICH_SECRET": ("immich", "IMMICH_SECRET"),
    "SILVERBULLET_SB_USER": ("silverbullet", "SB_USER"),
    "OPENPROJECT_SECRET_KEY_BASE": ("openproject", "SECRET_KEY_BASE"),
    "MEALIE_DB_PASSWORD": ("mealie", "POSTGRES_PASSWORD"),
    "MINIFLUX_DB_PASSWORD": ("miniflux", "POSTGRES_PASSWORD"),
    "MINIFLUX_ADMIN_PASSWORD": ("miniflux", "MINIFLUX_ADMIN_PASSWORD"),
    "VIKUNJA_DB_PASSWORD": ("vikunja", "POSTGRES_PASSWORD"),
    "BOOKSTACK_DB_ROOT_PASSWORD": ("bookstack", "MYSQL_ROOT_PASSWORD"),
    "BOOKSTACK_DB_PASSWORD": ("bookstack", "MYSQL_PASSWORD"),
    "BOOKSTACK_APP_KEY": ("bookstack", "APP_KEY"),
    "OUTLINE_DB_PASSWORD": ("outline", "POSTGRES_PASSWORD"),
    "OUTLINE_SECRET_KEY": ("outline", "SECRET_KEY"),
    "OUTLINE_UTILS_SECRET": ("outline", "UTILS_SECRET"),
    "WALLABAG_DB_PASSWORD": ("wallabag", "POSTGRES_PASSWORD"),
    "WALLABAG_SECRET": ("wallabag", "SYMFONY__ENV__SECRET"),
    "ATUIN_DB_PASSWORD": ("atuin", "POSTGRES_PASSWORD"),
    "NOCODB_DB_PASSWORD": ("nocodb", "POSTGRES_PASSWORD"),
    "NOCODB_JWT_SECRET": ("nocodb", "NC_AUTH_JWT_SECRET"),
    "LISTMONK_DB_PASSWORD": ("listmonk", "POSTGRES_PASSWORD"),
    "LISTMONK_ADMIN_PASSWORD": ("listmonk", "LISTMONK_ADMIN_PASSWORD"),
    "DOCUMENSO_DB_PASSWORD": ("documenso", "POSTGRES_PASSWORD"),
    "DOCUMENSO_NEXTAUTH_SECRET": ("documenso", "NEXTAUTH_SECRET"),
    "DOCUMENSO_ENCRYPTION_KEY": ("documenso", "NEXT_PRIVATE_ENCRYPTION_KEY"),
    "DOCUMENSO_ENCRYPTION_SECONDARY_KEY": ("documenso", "NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY"),
    "INVOICESHELF_DB_PASSWORD": ("invoiceshelf", "MYSQL_PASSWORD"),
    "INVOICESHELF_DB_ROOT_PASSWORD": ("invoiceshelf", "MYSQL_ROOT_PASSWORD"),
    "INVOICESHELF_APP_KEY": ("invoiceshelf", "APP_KEY"),
    "ORANGEHRM_DB_PASSWORD": ("orangehrm", "MYSQL_PASSWORD"),
    "ORANGEHRM_DB_ROOT_PASSWORD": ("orangehrm", "MYSQL_ROOT_PASSWORD"),
    "CALCOM_DB_PASSWORD": ("calcom", "POSTGRES_PASSWORD"),
    "CALCOM_NEXTAUTH_SECRET": ("calcom", "NEXTAUTH_SECRET"),
    "CALCOM_ENCRYPTION_KEY": ("calcom", "CALENDSO_ENCRYPTION_KEY"),
    "PLAUSIBLE_DB_PASSWORD": ("plausible", "POSTGRES_PASSWORD"),
    "PLAUSIBLE_CLICKHOUSE_PASSWORD": ("plausible", "CLICKHOUSE_PASSWORD"),
    "PLAUSIBLE_SECRET_KEY_BASE": ("plausible", "SECRET_KEY_BASE"),
    "PLAUSIBLE_TOTP_VAULT_KEY": ("plausible", "TOTP_VAULT_KEY"),
    "N8N_DB_PASSWORD": ("n8n", "POSTGRES_PASSWORD"),
    "N8N_ENCRYPTION_KEY": ("n8n", "N8N_ENCRYPTION_KEY"),
    "STIRLING_PDF_LITE_ADMIN_PASSWORD": ("stirling-pdf-lite", "STIRLING_ADMIN_PASSWORD"),
    "OPEN_WEBUI_SECRET_KEY": ("open-webui", "WEBUI_SECRET_KEY"),
    "BESZEL_AGENT_TOKEN": ("beszel", "BESZEL_AGENT_TOKEN"),
    "BESZEL_AGENT_KEY": ("beszel", "BESZEL_AGENT_KEY"),
    "TUNNEL_TOKEN": ("cloudflared", "TUNNEL_TOKEN"),
    "PAPERLESS_DB_PASSWORD": ("paperless", "POSTGRES_PASSWORD"),
    "PAPERLESS_SECRET_KEY": ("paperless", "PAPERLESS_SECRET_KEY"),
    "PAPERLESS_ADMIN_PASSWORD": ("paperless", "PAPERLESS_ADMIN_PASSWORD"),
    "AUTHENTIK_DB_PASSWORD": ("authentik", "POSTGRES_PASSWORD"),
    "AUTHENTIK_SECRET_KEY": ("authentik", "AUTHENTIK_SECRET_KEY"),
    "APPFLOWY_DB_PASSWORD": ("appflowy", "POSTGRES_PASSWORD"),
    "APPFLOWY_MINIO_ROOT_USER": ("appflowy", "MINIO_ROOT_USER"),
    "APPFLOWY_MINIO_ROOT_PASSWORD": ("appflowy", "MINIO_ROOT_PASSWORD"),
    "APPFLOWY_JWT_SECRET": ("appflowy", "GOTRUE_JWT_SECRET"),
    "PLANE_DB_PASSWORD": ("plane", "POSTGRES_PASSWORD"),
    "PLANE_RABBITMQ_PASSWORD": ("plane", "RABBITMQ_PASSWORD"),
    "PLANE_MINIO_ROOT_USER": ("plane", "MINIO_ROOT_USER"),
    "PLANE_MINIO_ROOT_PASSWORD": ("plane", "MINIO_ROOT_PASSWORD"),
    "PLANE_SECRET_KEY": ("plane", "SECRET_KEY"),
    "KARAKEEP_MEILI_MASTER_KEY": ("karakeep", "MEILI_MASTER_KEY"),
    "KARAKEEP_NEXTAUTH_SECRET": ("karakeep", "NEXTAUTH_SECRET"),
    "PENPOT_DB_PASSWORD": ("penpot", "POSTGRES_PASSWORD"),
    "PENPOT_SECRET_KEY": ("penpot", "PENPOT_SECRET_KEY"),
    "OBSERVABILITY_GRAFANA_ADMIN_USER": ("observability", "GRAFANA_ADMIN_USER"),
    "OBSERVABILITY_GRAFANA_ADMIN_PASSWORD": ("observability", "GRAFANA_ADMIN_PASSWORD"),
    "SUPABASE_POSTGRES_PASSWORD": ("supabase", "POSTGRES_PASSWORD"),
    "SUPABASE_JWT_SECRET": ("supabase", "JWT_SECRET"),
    "SUPABASE_ANON_KEY": ("supabase", "ANON_KEY"),
    "SUPABASE_SERVICE_ROLE_KEY": ("supabase", "SERVICE_ROLE_KEY"),
    "SUPABASE_DASHBOARD_USERNAME": ("supabase", "DASHBOARD_USERNAME"),
    "SUPABASE_DASHBOARD_PASSWORD": ("supabase", "DASHBOARD_PASSWORD"),
    "SUPABASE_SECRET_KEY_BASE": ("supabase", "SECRET_KEY_BASE"),
    "SUPABASE_REALTIME_DB_ENC_KEY": ("supabase", "REALTIME_DB_ENC_KEY"),
    "SUPABASE_VAULT_ENC_KEY": ("supabase", "VAULT_ENC_KEY"),
    "SUPABASE_PG_META_CRYPTO_KEY": ("supabase", "PG_META_CRYPTO_KEY"),
    "SUPABASE_S3_PROTOCOL_ACCESS_KEY_ID": ("supabase", "S3_PROTOCOL_ACCESS_KEY_ID"),
    "SUPABASE_S3_PROTOCOL_ACCESS_KEY_SECRET": ("supabase", "S3_PROTOCOL_ACCESS_KEY_SECRET"),
    "SUPABASE_POOLER_TENANT_ID": ("supabase", "POOLER_TENANT_ID"),
    "SUPABASE_PUBLISHABLE_KEY": ("supabase", "SUPABASE_PUBLISHABLE_KEY"),
    "SUPABASE_SECRET_KEY": ("supabase", "SUPABASE_SECRET_KEY"),
    "SUPABASE_ANON_KEY_ASYMMETRIC": ("supabase", "ANON_KEY_ASYMMETRIC"),
    "SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC": ("supabase", "SERVICE_ROLE_KEY_ASYMMETRIC"),
    "SUPABASE_OPENAI_API_KEY": ("supabase", "OPENAI_API_KEY"),
    "DAGSTER_DB_PASSWORD": ("dagster", "DAGSTER_POSTGRES_PASSWORD"),
    "MATTERMOST_DB_PASSWORD": ("mattermost", "POSTGRES_PASSWORD"),
    "AIRFLOW_DB_PASSWORD": ("airflow", "POSTGRES_PASSWORD"),
    "AIRFLOW_FERNET_KEY": ("airflow", "FERNET_KEY"),
    "AIRFLOW_JWT_SECRET": ("airflow", "JWT_SECRET"),
    "AIRFLOW_API_SECRET_KEY": ("airflow", "API_SECRET_KEY"),
    "AIRFLOW_ADMIN_USERNAME": ("airflow", "_AIRFLOW_WWW_USER_USERNAME"),
    "AIRFLOW_ADMIN_PASSWORD": ("airflow", "_AIRFLOW_WWW_USER_PASSWORD"),
    "AIRFLOW_ADMIN_EMAIL": ("airflow", "_AIRFLOW_WWW_USER_EMAIL"),
    "TEMPORAL_DB_PASSWORD": ("temporal", "POSTGRES_PASSWORD"),
    "ROCKETCHAT_ADMIN_PASSWORD": ("rocketchat", "ADMIN_PASS"),
    "ROCKETCHAT_REG_TOKEN": ("rocketchat", "REG_TOKEN"),
    "ZULIP_DB_PASSWORD": ("zulip", "ZULIP__POSTGRES_PASSWORD"),
    "ZULIP_RABBITMQ_PASSWORD": ("zulip", "ZULIP__RABBITMQ_PASSWORD"),
    "ZULIP_REDIS_PASSWORD": ("zulip", "ZULIP__REDIS_PASSWORD"),
    "ZULIP_MEMCACHED_PASSWORD": ("zulip", "ZULIP__MEMCACHED_PASSWORD"),
    "ZULIP_SECRET_KEY": ("zulip", "ZULIP__SECRET_KEY"),
    "HOMEBOX_AUTH_API_KEY_PEPPER": ("homebox", "HBOX_AUTH_API_KEY_PEPPER"),
}

_PLACEHOLDER_MARKERS = ("your_", "please_change", "change_me", "changeme")


def is_placeholder(value: str) -> bool:
    if not value.strip():
        return True
    lowered = value.strip().lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def load_env_file(path: Path) -> dict[str, str]:
    """Same minimal KEY=VALUE parser as homeserver.py/apply-secrets.py's
    own load_env_file — comments, blank lines, quoted values."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        result[key] = val
    return result


def main() -> int:
    base_path = ENV_PATH if ENV_PATH.is_file() else ENV_EXAMPLE_PATH
    if base_path is ENV_EXAMPLE_PATH:
        info(f"{ENV_PATH} doesn't exist yet — starting from .env.example")
    else:
        info(f"updating existing {ENV_PATH} in place")

    lines = base_path.read_text(encoding="utf-8").splitlines()

    updated = 0
    skipped_no_source = 0
    skipped_placeholder_source = 0
    skipped_already_real = 0

    line_re = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
    new_lines: list[str] = []
    for line in lines:
        m = line_re.match(line)
        if not m:
            new_lines.append(line)
            continue
        key, current_val = m.group(1), m.group(2)
        if key not in MAPPING:
            new_lines.append(line)
            continue

        service, compose_key = MAPPING[key]
        compose_env = load_env_file(SERVICES_DIR / service / ".env")
        compose_val = compose_env.get(compose_key, "")

        if not compose_env:
            skipped_no_source += 1
            new_lines.append(line)
            continue
        if is_placeholder(compose_val):
            skipped_placeholder_source += 1
            new_lines.append(line)
            continue
        if not is_placeholder(current_val) and current_val == compose_val:
            skipped_already_real += 1
            new_lines.append(line)
            continue

        new_lines.append(f"{key}={compose_val}")
        updated += 1

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    success(f"wrote {ENV_PATH}: {updated} value(s) copied from services/*/.env")
    if skipped_no_source:
        warn(f"{skipped_no_source} key(s) skipped — no services/<service>/.env file exists yet for that service (left at default)")
    if skipped_placeholder_source:
        warn(f"{skipped_placeholder_source} key(s) skipped — Compose side is itself still a placeholder (left at default)")
    if skipped_already_real:
        info(f"{skipped_already_real} key(s) already matched the Compose value, left as-is")
    info("keys with no Compose equivalent at all (ARGOCD_ADMIN_PASSWORD, POSTGRES_SHARED_PASSWORD, MARIADB_SHARED_ROOT_PASSWORD, etc.) are untouched — fill those in by hand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
