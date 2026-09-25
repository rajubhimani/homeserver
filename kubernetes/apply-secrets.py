#!/usr/bin/env python3
"""kubernetes/apply-secrets.py — reads kubernetes/.env and creates/updates
the matching Kubernetes Secrets. Same role as homeserver.py injecting a
service's .env into its containers — .env is the source of truth, this
script is what actually applies it.

Python port of apply-secrets.sh, same reasoning homeserver.py itself
replaced homeserver.sh (see that file's own docstring): a bash script run
through Git Bash/MSYS on Windows gets its POSIX-looking paths and argument
strings silently mangled before the underlying process actually launches —
this affected the original script's Documenso cert `-subj` argument badly
enough that it needed a doubled-leading-slash workaround just to survive
Git Bash. subprocess.run() with list-form args never goes through a shell
at all, so that workaround (and the whole class of bug) doesn't apply here.

Usage: uv run kubernetes/apply-secrets.py
"""

from __future__ import annotations

import base64
import datetime
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

K8S_DIR = Path(__file__).resolve().parent
ENV_PATH = K8S_DIR / ".env"
ENV_EXAMPLE_PATH = K8S_DIR / ".env.example"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}▶ {msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}✔ {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"{RED}✖ {msg}{RESET}", file=sys.stderr)
    sys.exit(1)


def load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser — comments, blank lines, quoted
    values. Same convention as homeserver.py's own load_env_file (not
    python-dotenv, no new project dependency)."""
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


_PLACEHOLDER_MARKERS = ("your_", "please_change", "change_me", "changeme")


def is_placeholder(value: str) -> bool:
    """Same heuristic as sync-env-from-compose.py's own is_placeholder —
    every .env.example default in this repo follows the your_..._here
    convention, so this reliably tells a real value apart from one nobody
    has filled in yet."""
    if not value.strip():
        return True
    lowered = value.strip().lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


# Keys needing a specific byte-format, not just "any random string" — see
# each one's own comment in .env.example for the exact constraint this
# mirrors. Everything else still a placeholder falls back to a generic
# secrets.token_urlsafe(32) (32 bytes, URL-safe alphabet — no '+', '/', or
# '=' to trip up anything that splits on those).
def _urlsafe(nbytes: int) -> str:
    return secrets.token_urlsafe(nbytes)


def _hex64() -> str:
    return secrets.token_hex(32)  # 32 bytes -> 64 hex chars


def _base64_prefixed(nbytes: int = 32) -> str:
    # BookStack/InvoiceShelf Laravel APP_KEY convention: "base64:" + real
    # (non-urlsafe) base64 — Laravel's own key format, not negotiable.
    return f"base64:{base64.b64encode(secrets.token_bytes(nbytes)).decode()}"


def _standard_base64(nbytes: int = 32) -> str:
    # Plausible's TOTP_VAULT_KEY specifically: must decode to exactly 32
    # raw bytes with a *standard* base64 decoder (its own .env.example
    # comment: a same-length hex string only decodes to 16 bytes and
    # Plausible refuses to boot) — token_urlsafe's '-'/'_' alphabet isn't
    # valid standard base64, so this needs the real thing.
    return base64.b64encode(secrets.token_bytes(nbytes)).decode()


def _fernet_key() -> str:
    # Airflow's Fernet key: exactly 32 raw bytes, standard urlsafe base64
    # WITH padding intact (44 chars, trailing '=') — the `cryptography`
    # Fernet class rejects anything else, including token_urlsafe's
    # padding-stripped output.
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


SPECIAL_GENERATORS: dict[str, Callable[[], str]] = {
    "FIREFLY_APP_KEY": lambda: _urlsafe(24),  # exactly 32 chars — see its own comment
    "DOCUMENSO_ENCRYPTION_KEY": lambda: _urlsafe(24),
    "DOCUMENSO_ENCRYPTION_SECONDARY_KEY": lambda: _urlsafe(24),
    "SUPABASE_VAULT_ENC_KEY": lambda: _urlsafe(24),
    "SUPABASE_REALTIME_DB_ENC_KEY": lambda: _urlsafe(12),  # exactly 16 chars
    "BOOKSTACK_APP_KEY": _base64_prefixed,
    "INVOICESHELF_APP_KEY": _base64_prefixed,
    "OUTLINE_SECRET_KEY": _hex64,
    "OUTLINE_UTILS_SECRET": _hex64,
    "N8N_ENCRYPTION_KEY": _hex64,
    "PLAUSIBLE_TOTP_VAULT_KEY": _standard_base64,
    "AIRFLOW_FERNET_KEY": _fernet_key,
    "HOMEBOX_AUTH_API_KEY_PEPPER": lambda: _urlsafe(48),
    "SILVERBULLET_SB_USER": lambda: f"admin:{_urlsafe(24)}",  # format: username:password
}

# TUNNEL_TOKEN and DOMAIN: real values nothing in this repo can invent
# (a Cloudflare-issued credential, and your own actual domain) — left
# exactly as .env.example ships them (still placeholders) for the user
# to fill in by hand. TUNNEL_TOKEN is read via the required env["..."]
# form here, so Env.__getitem__ below fails clearly on it rather than
# silently pushing a fake token into the cluster; DOMAIN isn't read by
# this script at all (only by apply-domain-routes.py, which has its own
# equivalent check) but still must never get a random auto-generated
# "domain" string.
#
# Everything else here ships genuinely blank in .env.example on purpose
# (Beszel's agent pairing, RocketChat's optional admin bootstrap, and
# Supabase's unused asymmetric/opaque keys — see each one's own comment)
# and is read via the optional env.get(...) form, so leaving it blank is
# already the correct, working state — not a placeholder needing a value.
NO_AUTO_GENERATE = {
    "TUNNEL_TOKEN",
    "DOMAIN",
    "BESZEL_AGENT_TOKEN",
    "BESZEL_AGENT_KEY",
    "ROCKETCHAT_ADMIN_PASSWORD",
    "ROCKETCHAT_REG_TOKEN",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_ANON_KEY_ASYMMETRIC",
    "SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC",
    "SUPABASE_OPENAI_API_KEY",
}


def _generate_for(key: str) -> str:
    return SPECIAL_GENERATORS.get(key, lambda: _urlsafe(32))()


def ensure_env_populated() -> None:
    """Creates kubernetes/.env from .env.example if it doesn't exist yet,
    then replaces every value still holding a .env.example placeholder
    with a real, randomly-generated one (format-aware via
    SPECIAL_GENERATORS, generic token_urlsafe(32) otherwise) — except
    NO_AUTO_GENERATE's real external credentials, left for the user.
    Idempotent: a key already holding a real value (typed by hand, or
    pulled in by sync-env-from-compose.py) is never touched or
    regenerated on a later run.

    Also merges in any key .env.example has that this existing .env
    predates entirely — e.g. a key added to .env.example after someone's
    .env was first created, which would otherwise be silently absent
    (not even a placeholder) and only surface as a confusing "not set"
    failure deep into main(), instead of being generated like any other
    new key."""
    if not ENV_PATH.is_file():
        if not ENV_EXAMPLE_PATH.is_file():
            fail(f"neither {ENV_PATH} nor {ENV_EXAMPLE_PATH} exist — this repo is missing kubernetes/.env.example")
        info(f"{ENV_PATH} doesn't exist yet — creating it from .env.example")
        shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    example_values = load_env_file(ENV_EXAMPLE_PATH)
    line_re = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
    new_lines: list[str] = []
    generated: list[str] = []
    seen_keys: set[str] = set()

    for line in lines:
        m = line_re.match(line)
        if not m:
            new_lines.append(line)
            continue
        key, value = m.group(1), m.group(2)
        seen_keys.add(key)
        if key in NO_AUTO_GENERATE or not is_placeholder(value):
            new_lines.append(line)
            continue
        new_value = _generate_for(key)
        new_lines.append(f"{key}={new_value}")
        generated.append(key)

    missing_keys = [k for k in example_values if k not in seen_keys]
    if missing_keys:
        new_lines.append("")
        new_lines.append("# --- keys added to .env.example after this .env was created ---")
        for key in missing_keys:
            example_value = example_values[key]
            if key in NO_AUTO_GENERATE or not is_placeholder(example_value):
                new_lines.append(f"{key}={example_value}")
                continue
            new_lines.append(f"{key}={_generate_for(key)}")
            generated.append(key)

    if generated or missing_keys:
        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    if generated:
        success(f"auto-generated {len(generated)} secret(s) in {ENV_PATH}: {', '.join(generated)}")
    if missing_keys and len(missing_keys) > len(generated):
        info(f"added {len(missing_keys) - len(generated)} new non-secret key(s) from .env.example that this .env predated")


class Env:
    """Thin wrapper so a missing or still-placeholder required key fails
    with a clear message (which .env var, which secret it was needed for)
    instead of a raw KeyError or a placeholder string silently getting
    pushed into the cluster as a real secret — same fail-fast behavior
    bash's `set -u` gave the original script, just with a friendlier
    error. By the time this runs, ensure_env_populated() has already
    replaced every generatable placeholder, so a key still showing up
    here as a placeholder is one of NO_AUTO_GENERATE's real external
    credentials the user genuinely has to supply."""

    def __init__(self, data: dict[str, str]):
        self._data = data

    def __getitem__(self, key: str) -> str:
        value = self._data.get(key)
        if value is None:
            fail(f"{key} not set in kubernetes/.env")
        if is_placeholder(value):
            fail(f"{key} is still a placeholder in kubernetes/.env — this one can't be auto-generated, fill in a real value (see its comment in .env.example)")
        return value

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)


def kubectl(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    if not shutil.which("kubectl"):
        fail("kubectl not found on PATH — see kubernetes/README.md's Prerequisites section")
    return subprocess.run(
        ["kubectl", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )


def apply_secret(name: str, namespace: str, literals: dict[str, str]) -> None:
    """kubectl create secret generic <name> -n <ns> --from-literal=k=v ...
    --dry-run=client -o yaml | kubectl apply -f -  — same idempotent
    create-or-update pattern as the bash version, just without an actual
    shell pipe (capture stdout, feed it to the next call's stdin directly)."""
    args = ["create", "secret", "generic", name, "-n", namespace]
    for key, value in literals.items():
        args.append(f"--from-literal={key}={value}")
    args += ["--dry-run=client", "-o", "yaml"]
    try:
        manifest = kubectl(args).stdout
        kubectl(["apply", "-f", "-"], input_text=manifest)
    except subprocess.CalledProcessError as e:
        fail(f"failed to apply secret '{name}': {e.stderr.strip() if e.stderr else e}")


def apply_secret_from_file(name: str, namespace: str, file_key: str, file_path: Path) -> None:
    try:
        manifest = kubectl(
            ["create", "secret", "generic", name, "-n", namespace, f"--from-file={file_key}={file_path}", "--dry-run=client", "-o", "yaml"]
        ).stdout
        kubectl(["apply", "-f", "-"], input_text=manifest)
    except subprocess.CalledProcessError as e:
        fail(f"failed to apply secret '{name}': {e.stderr.strip() if e.stderr else e}")


# Builds the RSA key + self-signed cert + PKCS12 entirely in Python via the
# `cryptography` package (ephemeral-installed with `uv run --with`, same
# pattern bcrypt_hash() below already uses — no new project dependency).
# Documenso's own signing library can only read the *old* PKCS12 scheme
# (PBE-SHA1-3DES key/cert encryption, SHA1 MAC — confirmed against
# Documenso's own SIGNING.md and issue #1087, unresolved as of the version
# pinned in kubernetes/apps/documenso/), which OpenSSL 3.x moved behind a
# 'legacy' provider that isn't loaded by default and, on at least one
# Windows OpenSSL distribution, isn't installed at all. `cryptography`'s
# own PKCS12 encryption_builder() can produce that exact legacy scheme
# directly — no system openssl involved, so no provider/PATH/install
# variance to debug across machines. Also requires a non-empty passphrase
# (DOCUMENSO_SIGNING_PASSPHRASE): Documenso's docs flag an empty one as a
# known cause of "Failed to get private key bags" at signing time.
_DOCUMENSO_CERT_SCRIPT = """
import datetime
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID

out_path, passphrase = sys.argv[1], sys.argv[2].encode()
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "documenso.k8s.local")])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=3650))
    .sign(key, hashes.SHA256())
)
encryption = (
    PrivateFormat.PKCS12.encryption_builder()
    .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
    .hmac_hash(hashes.SHA1())
    .build(passphrase)
)
p12 = pkcs12.serialize_key_and_certificates(b"documenso", key, cert, None, encryption)
with open(out_path, "wb") as f:
    f.write(p12)
"""


def generate_documenso_cert(passphrase: str) -> Path:
    """Documenso refuses to start without a valid cert.p12 for local
    document signing. This pilot has no real signing use, so generate a
    throwaway self-signed one on the fly rather than committing a cert to
    the repo. See _DOCUMENSO_CERT_SCRIPT's comment above for why this
    doesn't shell out to openssl."""
    cert_dir = Path(tempfile.mkdtemp(prefix="documenso-cert-"))
    p12_path = cert_dir / "cert.p12"
    try:
        subprocess.run(
            ["uv", "run", "--with", "cryptography", "python", "-c", _DOCUMENSO_CERT_SCRIPT, str(p12_path), passphrase],
            cwd=K8S_DIR.parent,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(cert_dir, ignore_errors=True)
        fail(f"documenso cert generation failed: {e.stderr.decode(errors='replace') if e.stderr else e}")
    return p12_path


def bcrypt_hash(password: str) -> str:
    """ArgoCD only accepts a bcrypt hash in its Secret, never plaintext.
    Same `uv run --with bcrypt` ephemeral-install pattern the original
    bash script already used (repo already uses uv for homeserver.py;
    this pulls bcrypt into a throwaway venv, no project dependency added)."""
    result = subprocess.run(
        ["uv", "run", "--with", "bcrypt", "python", "-c", "import bcrypt, sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt(10)).decode())", password],
        cwd=K8S_DIR.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> None:
    ensure_env_populated()
    env = Env(load_env_file(ENV_PATH))

    # Applied first, deliberately — everything below this can fail partway
    # through (a missing .env key, a slow/unready cluster) and still leave
    # a working ArgoCD login, which is often the fastest way to see what's
    # actually wrong with the rest.
    info("hashing ArgoCD admin password...")
    argocd_hash = bcrypt_hash(env["ARGOCD_ADMIN_PASSWORD"])
    mtime = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        kubectl(
            [
                "-n", "argocd", "patch", "secret", "argocd-secret",
                "-p", f'{{"stringData": {{"admin.password": "{argocd_hash}", "admin.passwordMtime": "{mtime}"}}}}',
            ]
        )
    except subprocess.CalledProcessError as e:
        fail(f"failed to patch argocd-secret: {e.stderr.strip() if e.stderr else e}")
    success("argocd admin password applied")

    apply_secret("postgres-shared-credentials", "data", {"postgres-password": env["POSTGRES_SHARED_PASSWORD"]})
    success("postgres-shared-credentials applied")

    apply_secret("mariadb-shared-credentials", "data", {"root-password": env["MARIADB_SHARED_ROOT_PASSWORD"]})
    success("mariadb-shared-credentials applied")

    apply_secret("guacamole-db-credentials", "apps", {"password": env["GUACAMOLE_DB_PASSWORD"]})
    success("guacamole-db-credentials applied")

    apply_secret("vaultwarden-credentials", "apps", {"admin-token": env["VAULTWARDEN_ADMIN_TOKEN"]})
    success("vaultwarden-credentials applied")

    apply_secret("forgejo-db-credentials", "apps", {"password": env["FORGEJO_DB_PASSWORD"]})
    success("forgejo-db-credentials applied")

    apply_secret("firefly-db-credentials", "apps", {"password": env["FIREFLY_DB_PASSWORD"]})
    apply_secret("firefly-credentials", "apps", {"app-key": env["FIREFLY_APP_KEY"], "cron-token": env["FIREFLY_CRON_TOKEN"]})
    success("firefly-db-credentials + firefly-credentials applied")

    apply_secret("nextcloud-db-credentials", "apps", {"password": env["NEXTCLOUD_DB_PASSWORD"]})
    apply_secret("nextcloud-credentials", "apps", {"admin-password": env["NEXTCLOUD_ADMIN_PASSWORD"]})
    success("nextcloud-db-credentials + nextcloud-credentials applied")

    # db-url is pre-composed here, not built via k8s's $(VAR) substitution in
    # the deployment manifest — that only resolves references to variables
    # defined *earlier* in the same env list, which silently failed and
    # crash-looped immich-server/immich-ml (see deployment.yaml's comment).
    immich_db_password = env["IMMICH_DB_PASSWORD"]
    apply_secret(
        "immich-db-credentials",
        "apps",
        {"password": immich_db_password, "db-url": f"postgresql://immich:{immich_db_password}@immich-db:5432/immich"},
    )
    apply_secret("immich-credentials", "apps", {"secret": env["IMMICH_SECRET"]})
    success("immich-db-credentials + immich-credentials applied")

    apply_secret("silverbullet-credentials", "apps", {"sb-user": env["SILVERBULLET_SB_USER"]})
    success("silverbullet-credentials applied")

    apply_secret("openproject-credentials", "apps", {"secret-key-base": env["OPENPROJECT_SECRET_KEY_BASE"]})
    success("openproject-credentials applied")

    apply_secret("mealie-db-credentials", "apps", {"password": env["MEALIE_DB_PASSWORD"]})
    success("mealie-db-credentials applied")

    miniflux_db_password = env["MINIFLUX_DB_PASSWORD"]
    apply_secret(
        "miniflux-db-credentials",
        "apps",
        {"password": miniflux_db_password, "database-url": f"postgres://miniflux:{miniflux_db_password}@miniflux-db/miniflux?sslmode=disable"},
    )
    apply_secret("miniflux-credentials", "apps", {"admin-password": env["MINIFLUX_ADMIN_PASSWORD"]})
    success("miniflux-db-credentials + miniflux-credentials applied")

    apply_secret("vikunja-db-credentials", "apps", {"password": env["VIKUNJA_DB_PASSWORD"]})
    success("vikunja-db-credentials applied")

    apply_secret("bookstack-db-credentials", "apps", {"root-password": env["BOOKSTACK_DB_ROOT_PASSWORD"], "password": env["BOOKSTACK_DB_PASSWORD"]})
    apply_secret("bookstack-credentials", "apps", {"app-key": env["BOOKSTACK_APP_KEY"]})
    success("bookstack-db-credentials + bookstack-credentials applied")

    outline_db_password = env["OUTLINE_DB_PASSWORD"]
    apply_secret(
        "outline-db-credentials",
        "apps",
        {"password": outline_db_password, "database-url": f"postgres://outline:{outline_db_password}@outline-db:5432/outline?sslmode=disable"},
    )
    apply_secret("outline-credentials", "apps", {"secret-key": env["OUTLINE_SECRET_KEY"], "utils-secret": env["OUTLINE_UTILS_SECRET"]})
    success("outline-db-credentials + outline-credentials applied")

    apply_secret("wallabag-db-credentials", "apps", {"password": env["WALLABAG_DB_PASSWORD"]})
    apply_secret("wallabag-credentials", "apps", {"secret": env["WALLABAG_SECRET"]})
    success("wallabag-db-credentials + wallabag-credentials applied")

    atuin_db_password = env["ATUIN_DB_PASSWORD"]
    apply_secret(
        "atuin-db-credentials",
        "apps",
        {"password": atuin_db_password, "db-uri": f"postgres://atuin:{atuin_db_password}@atuin-db/atuin"},
    )
    success("atuin-db-credentials applied")

    nocodb_db_password = env["NOCODB_DB_PASSWORD"]
    apply_secret(
        "nocodb-db-credentials",
        "apps",
        {"password": nocodb_db_password, "nc-db-uri": f"pg://nocodb-db:5432?u=nocodb&p={nocodb_db_password}&d=nocodb"},
    )
    apply_secret("nocodb-credentials", "apps", {"jwt-secret": env["NOCODB_JWT_SECRET"]})
    success("nocodb-db-credentials + nocodb-credentials applied")

    apply_secret("listmonk-db-credentials", "apps", {"password": env["LISTMONK_DB_PASSWORD"]})
    apply_secret("listmonk-credentials", "apps", {"admin-password": env["LISTMONK_ADMIN_PASSWORD"]})
    success("listmonk-db-credentials + listmonk-credentials applied")

    documenso_db_password = env["DOCUMENSO_DB_PASSWORD"]
    apply_secret(
        "documenso-db-credentials",
        "apps",
        {"password": documenso_db_password, "database-url": f"postgres://documenso:{documenso_db_password}@documenso-db:5432/documenso"},
    )
    documenso_signing_passphrase = env["DOCUMENSO_SIGNING_PASSPHRASE"]
    apply_secret(
        "documenso-credentials",
        "apps",
        {
            "nextauth-secret": env["DOCUMENSO_NEXTAUTH_SECRET"],
            "encryption-key": env["DOCUMENSO_ENCRYPTION_KEY"],
            "encryption-secondary-key": env["DOCUMENSO_ENCRYPTION_SECONDARY_KEY"],
            "signing-passphrase": documenso_signing_passphrase,
        },
    )
    success("documenso-db-credentials + documenso-credentials applied")

    p12_path = generate_documenso_cert(documenso_signing_passphrase)
    try:
        apply_secret_from_file("documenso-cert", "apps", "cert.p12", p12_path)
    finally:
        shutil.rmtree(p12_path.parent, ignore_errors=True)
    success("documenso-cert applied")

    apply_secret("invoiceshelf-db-credentials", "apps", {"root-password": env["INVOICESHELF_DB_ROOT_PASSWORD"], "password": env["INVOICESHELF_DB_PASSWORD"]})
    apply_secret("invoiceshelf-credentials", "apps", {"app-key": env["INVOICESHELF_APP_KEY"]})
    success("invoiceshelf-db-credentials + invoiceshelf-credentials applied")

    apply_secret("orangehrm-db-credentials", "apps", {"root-password": env["ORANGEHRM_DB_ROOT_PASSWORD"], "password": env["ORANGEHRM_DB_PASSWORD"]})
    success("orangehrm-db-credentials applied")

    calcom_db_password = env["CALCOM_DB_PASSWORD"]
    apply_secret(
        "calcom-db-credentials",
        "apps",
        {"password": calcom_db_password, "database-url": f"postgresql://calcom:{calcom_db_password}@calcom-db:5432/calcom"},
    )
    apply_secret("calcom-credentials", "apps", {"nextauth-secret": env["CALCOM_NEXTAUTH_SECRET"], "encryption-key": env["CALCOM_ENCRYPTION_KEY"]})
    success("calcom-db-credentials + calcom-credentials applied")

    plausible_db_password = env["PLAUSIBLE_DB_PASSWORD"]
    plausible_ch_password = env["PLAUSIBLE_CLICKHOUSE_PASSWORD"]
    apply_secret(
        "plausible-db-credentials",
        "apps",
        {
            "password": plausible_db_password,
            "clickhouse-password": plausible_ch_password,
            "database-url": f"postgres://postgres:{plausible_db_password}@plausible-db:5432/plausible",
            "clickhouse-url": f"http://plausible:{plausible_ch_password}@plausible-events-db:8123/plausible_events_db",
        },
    )
    apply_secret("plausible-credentials", "apps", {"secret-key-base": env["PLAUSIBLE_SECRET_KEY_BASE"], "totp-vault-key": env["PLAUSIBLE_TOTP_VAULT_KEY"]})
    success("plausible-db-credentials + plausible-credentials applied")

    apply_secret("n8n-db-credentials", "apps", {"password": env["N8N_DB_PASSWORD"]})
    apply_secret("n8n-credentials", "apps", {"encryption-key": env["N8N_ENCRYPTION_KEY"]})
    success("n8n-db-credentials + n8n-credentials applied")

    apply_secret("stirling-pdf-lite-credentials", "apps", {"admin-password": env["STIRLING_PDF_LITE_ADMIN_PASSWORD"]})
    success("stirling-pdf-lite-credentials applied")

    apply_secret("open-webui-credentials", "apps", {"secret-key": env["OPEN_WEBUI_SECRET_KEY"]})
    success("open-webui-credentials applied")

    apply_secret("beszel-credentials", "apps", {"agent-token": env.get("BESZEL_AGENT_TOKEN"), "agent-key": env.get("BESZEL_AGENT_KEY")})
    success("beszel-credentials applied")

    apply_secret("cloudflared-credentials", "apps", {"tunnel-token": env["TUNNEL_TOKEN"]})
    success("cloudflared-credentials applied")

    apply_secret("paperless-db-credentials", "apps", {"password": env["PAPERLESS_DB_PASSWORD"]})
    apply_secret("paperless-credentials", "apps", {"secret-key": env["PAPERLESS_SECRET_KEY"], "admin-password": env["PAPERLESS_ADMIN_PASSWORD"]})
    success("paperless-db-credentials + paperless-credentials applied")

    apply_secret("authentik-db-credentials", "apps", {"password": env["AUTHENTIK_DB_PASSWORD"]})
    apply_secret("authentik-credentials", "apps", {"secret-key": env["AUTHENTIK_SECRET_KEY"]})
    success("authentik-db-credentials + authentik-credentials applied")

    # db-url/gotrue-db-url are pre-composed here, not built via k8s's $(VAR)
    # substitution in the deployment manifest — same reasoning as immich's
    # db-url above. gotrue-db-url's search_path override is copied verbatim
    # from appflowy/compose.yml's GOTRUE_DB_DATABASE_URL.
    appflowy_db_password = env["APPFLOWY_DB_PASSWORD"]
    apply_secret(
        "appflowy-db-credentials",
        "apps",
        {
            "password": appflowy_db_password,
            "db-url": f"postgres://appflowy:{appflowy_db_password}@appflowy-db/appflowy",
            "gotrue-db-url": f"postgres://appflowy:{appflowy_db_password}@appflowy-db/appflowy?options=-c%20search_path%3Dauth%2Cpublic",
            "minio-root-user": env["APPFLOWY_MINIO_ROOT_USER"],
            "minio-root-password": env["APPFLOWY_MINIO_ROOT_PASSWORD"],
        },
    )
    apply_secret("appflowy-credentials", "apps", {"jwt-secret": env["APPFLOWY_JWT_SECRET"]})
    success("appflowy-db-credentials + appflowy-credentials applied")

    plane_db_password = env["PLANE_DB_PASSWORD"]
    apply_secret(
        "plane-db-credentials",
        "apps",
        {
            "password": plane_db_password,
            "database-url": f"postgresql://plane:{plane_db_password}@plane-db/plane",
            "rabbitmq-password": env["PLANE_RABBITMQ_PASSWORD"],
            "minio-root-user": env["PLANE_MINIO_ROOT_USER"],
            "minio-root-password": env["PLANE_MINIO_ROOT_PASSWORD"],
        },
    )
    apply_secret("plane-credentials", "apps", {"secret-key": env["PLANE_SECRET_KEY"]})
    success("plane-db-credentials + plane-credentials applied")

    apply_secret("karakeep-credentials", "apps", {"meili-master-key": env["KARAKEEP_MEILI_MASTER_KEY"], "nextauth-secret": env["KARAKEEP_NEXTAUTH_SECRET"]})
    success("karakeep-credentials applied")

    apply_secret("penpot-db-credentials", "apps", {"password": env["PENPOT_DB_PASSWORD"]})
    apply_secret("penpot-credentials", "apps", {"secret-key": env["PENPOT_SECRET_KEY"]})
    success("penpot-db-credentials + penpot-credentials applied")

    apply_secret("observability-credentials", "apps", {"admin-user": env["OBSERVABILITY_GRAFANA_ADMIN_USER"], "admin-password": env["OBSERVABILITY_GRAFANA_ADMIN_PASSWORD"]})
    success("observability-credentials applied")

    # Supabase's own dedicated Postgres (one password, many roles) + every
    # app secret. Connection strings use the exact role names
    # supabase/volumes/db/roles.sql actually creates (authenticator,
    # supabase_auth_admin, supabase_storage_admin, supabase_functions_admin,
    # pgbouncer) — every role shares the one Postgres superuser password,
    # same as upstream Supabase's own self-hosting docker-compose.
    supabase_pg_password = env["SUPABASE_POSTGRES_PASSWORD"]
    apply_secret(
        "supabase-db-credentials",
        "apps",
        {
            "password": supabase_pg_password,
            "auth-db-url": f"postgres://supabase_auth_admin:{supabase_pg_password}@supabase-db:5432/postgres",
            "rest-db-uri": f"postgres://authenticator:{supabase_pg_password}@supabase-db:5432/postgres",
            "storage-db-url": f"postgres://supabase_storage_admin:{supabase_pg_password}@supabase-db:5432/postgres",
            "functions-db-url": f"postgres://supabase_functions_admin:{supabase_pg_password}@supabase-db:5432/postgres",
            "pooler-database-url": f"postgres://pgbouncer:{supabase_pg_password}@supabase-db:5432/postgres",
        },
    )
    apply_secret(
        "supabase-credentials",
        "apps",
        {
            "jwt-secret": env["SUPABASE_JWT_SECRET"],
            "anon-key": env["SUPABASE_ANON_KEY"],
            "service-role-key": env["SUPABASE_SERVICE_ROLE_KEY"],
            "dashboard-username": env["SUPABASE_DASHBOARD_USERNAME"],
            "dashboard-password": env["SUPABASE_DASHBOARD_PASSWORD"],
            "secret-key-base": env["SUPABASE_SECRET_KEY_BASE"],
            "realtime-db-enc-key": env["SUPABASE_REALTIME_DB_ENC_KEY"],
            "vault-enc-key": env["SUPABASE_VAULT_ENC_KEY"],
            "pg-meta-crypto-key": env["SUPABASE_PG_META_CRYPTO_KEY"],
            "s3-access-key-id": env["SUPABASE_S3_PROTOCOL_ACCESS_KEY_ID"],
            "s3-access-key-secret": env["SUPABASE_S3_PROTOCOL_ACCESS_KEY_SECRET"],
            "pooler-tenant-id": env["SUPABASE_POOLER_TENANT_ID"],
            "publishable-key": env.get("SUPABASE_PUBLISHABLE_KEY"),
            "secret-key": env.get("SUPABASE_SECRET_KEY"),
            "anon-key-asymmetric": env.get("SUPABASE_ANON_KEY_ASYMMETRIC"),
            "service-role-key-asymmetric": env.get("SUPABASE_SERVICE_ROLE_KEY_ASYMMETRIC"),
            "openai-api-key": env.get("SUPABASE_OPENAI_API_KEY"),
        },
    )
    success("supabase-db-credentials + supabase-credentials applied")

    apply_secret("dagster-db-credentials", "apps", {"password": env["DAGSTER_DB_PASSWORD"]})
    success("dagster-db-credentials applied")

    mattermost_db_password = env["MATTERMOST_DB_PASSWORD"]
    apply_secret(
        "mattermost-db-credentials",
        "apps",
        {
            "password": mattermost_db_password,
            "datasource": f"postgres://mattermost:{mattermost_db_password}@postgres-shared.data.svc.cluster.local:5432/mattermost?sslmode=disable&connect_timeout=10",
        },
    )
    success("mattermost-db-credentials applied")

    airflow_db_password = env["AIRFLOW_DB_PASSWORD"]
    apply_secret(
        "airflow-db-credentials",
        "apps",
        {
            "password": airflow_db_password,
            "sql-alchemy-conn": f"postgresql+psycopg2://airflow:{airflow_db_password}@postgres-shared.data.svc.cluster.local:5432/airflow",
        },
    )
    apply_secret(
        "airflow-credentials",
        "apps",
        {
            "fernet-key": env["AIRFLOW_FERNET_KEY"],
            "jwt-secret": env["AIRFLOW_JWT_SECRET"],
            "api-secret-key": env["AIRFLOW_API_SECRET_KEY"],
            "admin-username": env["AIRFLOW_ADMIN_USERNAME"],
            "admin-password": env["AIRFLOW_ADMIN_PASSWORD"],
            "admin-email": env["AIRFLOW_ADMIN_EMAIL"],
        },
    )
    success("airflow-db-credentials + airflow-credentials applied")

    apply_secret("temporal-db-credentials", "apps", {"password": env["TEMPORAL_DB_PASSWORD"]})
    success("temporal-db-credentials applied")

    apply_secret("rocketchat-credentials", "apps", {"admin-password": env.get("ROCKETCHAT_ADMIN_PASSWORD"), "reg-token": env.get("ROCKETCHAT_REG_TOKEN")})
    success("rocketchat-credentials applied")

    apply_secret("homebox-credentials", "apps", {"api-key-pepper": env["HOMEBOX_AUTH_API_KEY_PEPPER"]})
    success("homebox-credentials applied")

    apply_secret(
        "zulip-db-credentials",
        "apps",
        {
            "password": env["ZULIP_DB_PASSWORD"],
            "rabbitmq-password": env["ZULIP_RABBITMQ_PASSWORD"],
            "redis-password": env["ZULIP_REDIS_PASSWORD"],
            "memcached-password": env["ZULIP_MEMCACHED_PASSWORD"],
        },
    )
    apply_secret("zulip-credentials", "apps", {"secret-key": env["ZULIP_SECRET_KEY"], "email-password": env["ZULIP_EMAIL_PASSWORD"]})
    success("zulip-db-credentials + zulip-credentials applied")


if __name__ == "__main__":
    main()
