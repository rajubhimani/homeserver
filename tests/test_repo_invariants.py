"""Repo-wide consistency checks — services.json, compose files, .env.example and
docs must agree. These catch drift that only shows up on a fresh clone or a
later edit (CLAUDE.md: a compose/.env change isn't done until .env.example and
the service's doc match). Exceptions are listed explicitly with a reason;
adding one should be a deliberate decision, not a way to silence a failure."""

from __future__ import annotations

import json
import re

import pytest

import homeserver as hs
from conftest import each

REPO = hs.BASE_DIR
SERVICES = json.loads((REPO / "services.json").read_text())["services"]
BY_SLUG = {s["slug"]: s for s in SERVICES}
KNOWN_TIERS = {"min", "core", "daily", "browser", "office", "automation-ai", "extra", "manual", "shared"}
ABOVE_CORE = {"daily", "browser", "office", "automation-ai", "extra", "manual"}
INJECTED_VARS = {"DOMAIN", "DATA_ROOT", "DOCKER_SOCKET"}  # set by homeserver.py's compose_env / root .env


def service_dirs() -> list[str]:
    return sorted(p.name for p in (REPO / "services").iterdir()
                  if p.is_dir() and (p / hs.base_file(p.name)).is_file())


def compose_text(svc: str, name: str | None = None) -> str:
    return (REPO / "services" / svc / (name or hs.base_file(svc))).read_text()


def env_example_keys(svc: str) -> set[str]:
    p = REPO / "services" / svc / ".env.example"
    return set(re.findall(r"^([A-Z_0-9]+)=", p.read_text(), re.M)) if p.is_file() else set()


def strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] if line.lstrip().startswith("#") else line for line in text.splitlines())


# ── services.json ─────────────────────────────────────────────────

def test_slugs_are_unique():
    slugs = [s["slug"] for s in SERVICES]
    assert len(slugs) == len(set(slugs))


def test_tier_is_known():
    each([s for s in SERVICES if s.get("tier")], _tier_is_known, ids=lambda s: s["slug"])


def _tier_is_known(entry):
    assert entry["tier"] in KNOWN_TIERS


def test_bundle_and_requires_reference_real_services():
    for s in SERVICES:
        if s.get("bundle"):
            assert s["bundle"] in BY_SLUG
        for r in s.get("requires", []):
            assert r in BY_SLUG, f"{s['slug']} requires unknown {r}"


# Directories that are deliberately not services.json entries.
UNLISTED_DIRS = {
    hs.PROXY_STANDBY: "Nginx Proxy Manager — manual standby proxy, addressed via PROXY_STANDBY",
}


def test_every_service_dir_is_registered():
    each(service_dirs(), _every_service_dir_is_registered)


def _every_service_dir_is_registered(svc):
    assert svc in BY_SLUG or svc in UNLISTED_DIRS, f"services/{svc} has a compose file but no services.json entry"


def test_every_service_has_dev_and_prod_overrides():
    each(service_dirs(), _every_service_has_dev_and_prod_overrides)


def _every_service_has_dev_and_prod_overrides(svc):
    d = REPO / "services" / svc
    assert (d / "compose.dev.yml").is_file() and (d / "compose.prod.yml").is_file()


# ── ports (CLAUDE.md compose file pattern) ────────────────────────

# Published on every interface in prod on purpose.
PUBLIC_PROD_PORTS = {
    "syncthing": "device sync + LAN discovery need peer reachability — docs/services/syncthing.md",
}


def test_prod_ports_are_loopback_and_mirrored_on_wireguard():
    each(service_dirs(), _prod_ports_are_loopback_and_mirrored_on_wireguard)


def _prod_ports_are_loopback_and_mirrored_on_wireguard(svc):
    text = strip_comments(compose_text(svc, "compose.prod.yml"))
    loopback = set(re.findall(r"127\.0\.0\.1:([^:\"\s]+):(\d+)", text))
    mirrored = set(re.findall(r"10\.8\.0\.1:([^:\"\s]+):(\d+)", text))
    assert loopback <= mirrored, f"missing 10.8.0.1 mirror for {sorted(loopback - mirrored)}"
    if svc not in PUBLIC_PROD_PORTS:
        public = re.findall(r'^\s*-\s*"?((?:0\.0\.0\.0:)?\d+:\d+[^"\s]*)"?\s*$', text, re.M)
        assert not public, f"prod publishes on all interfaces: {public}"


def test_every_prod_host_port_is_in_the_services_reference():
    ref = (REPO / "docs" / "11-services-reference.md").read_text()
    missing = []
    for svc in service_dirs():
        text = strip_comments(compose_text(svc, "compose.prod.yml"))
        for port in re.findall(r"127\.0\.0\.1:(?:\$\{[A-Z_]+:-)?(\d+)\}?:", text):
            if not re.search(rf"\b{port}\b", ref):
                missing.append(f"{svc}:{port}")
    assert not missing, f"ports missing from docs/11-services-reference.md: {missing}"


# ── .env.example ──────────────────────────────────────────────────

def test_env_file_services_ship_an_env_example():
    each(service_dirs(), _env_file_services_ship_an_env_example)


def _env_file_services_ship_an_env_example(svc):
    if "env_file" in compose_text(svc):
        assert (REPO / "services" / svc / ".env.example").is_file()


def test_compose_variables_without_defaults_are_in_env_example():
    each(service_dirs(), _compose_variables_without_defaults_are_in_env_example)


def _compose_variables_without_defaults_are_in_env_example(svc):
    keys = env_example_keys(svc) | INJECTED_VARS
    missing = set()
    # Only the files homeserver.py actually loads, not vendored references
    # like supabase's upstream-docker-compose.yml.
    names = [hs.base_file(svc), "compose.dev.yml", "compose.prod.yml", "compose.podman.yml"]
    for f in [REPO / "services" / svc / n for n in names if (REPO / "services" / svc / n).is_file()]:
        for m in re.finditer(r"(?<!\$)\$\{([A-Z_0-9]+)(:?[-?][^}]*)?\}", strip_comments(f.read_text())):
            if not m.group(2) and m.group(1) not in keys:
                missing.add(m.group(1))
    assert not missing, f"used in compose with no default, missing from .env.example: {sorted(missing)}"


# ── shared databases ──────────────────────────────────────────────

SHARED_USERS = [s for s in SERVICES if s.get("shared_db")]
ENGINE_IMAGE = {"postgres": r"postgres", "mariadb": r"mariadb|mysql"}


def test_shared_db_apps_are_wired_consistently():
    each(SHARED_USERS, _shared_db_apps_are_wired_consistently, ids=lambda s: s["slug"])


def _shared_db_apps_are_wired_consistently(entry):
    svc, spec = entry["slug"], entry["shared_db"]
    assert entry["tier"] in ABOVE_CORE, "only services above CORE may use a shared database"
    assert spec["engine"] in hs.SHARED_DB_SERVICES
    keys = env_example_keys(svc)
    for field in ("db", "user", "password"):
        assert spec[field].startswith("=") or spec[field] in keys, f"{field} key {spec[field]} not in .env.example"
    text = strip_comments(compose_text(svc))
    assert not re.search(rf"image:\s*\S*({ENGINE_IMAGE[spec['engine']]}):", text), "still runs its own database container"
    host = hs.SHARED_DB_SERVICES[spec["engine"]]
    # The host may live in compose, in a config file baked into the image
    # (dagster.yaml), or — for apps configured through a web installer
    # (orangehrm) — only in the doc that tells you what to type.
    svc_dir = REPO / "services" / svc
    config_text = "".join(p.read_text(errors="ignore") for p in svc_dir.rglob("*")
                          if p.is_file() and p.name != ".env" and p.suffix in {".yml", ".yaml", ".py", ".conf", ".toml"})
    docs = [REPO / "docs" / "services" / f"{svc}.md", REPO / "docs" / "services" / svc / f"{svc}.md"]
    doc_text = "".join(d.read_text() for d in docs if d.is_file())
    assert host in config_text or host in doc_text, f"nothing points {svc} at {host}"
    assert host in doc_text, f"docs/services/{svc}.md doesn't say its database is on {host}"
    assert not (svc_dir / "postgres-init").exists()


def test_docs_do_not_describe_a_removed_db_container():
    each(SHARED_USERS, _docs_do_not_describe_a_removed_db_container, ids=lambda s: s["slug"])


def _docs_do_not_describe_a_removed_db_container(entry):
    """Once an app moves to a shared server, its own <svc>-db container is
    gone; docs still describing it (outside clearly historical lines) are stale."""
    svc = entry["slug"]
    stale = []
    for doc in sorted((REPO / "docs").rglob("*.md")):
        for n, line in enumerate(doc.read_text().splitlines(), 1):
            if re.search(rf"(?<![\w-]){re.escape(svc)}-db(?![\w-])", line) and not HISTORY_WORDS.search(line):
                stale.append(f"{doc.relative_to(REPO)}:{n}")
    assert not stale, f"docs still describe {svc}-db: {stale}"


def test_shared_servers_publish_no_ports():
    each(list(hs.SHARED_DB_SERVICES.values()), _shared_servers_publish_no_ports)


def _shared_servers_publish_no_ports(server):
    assert "ports:" not in strip_comments(compose_text(server, "compose.prod.yml"))
    assert "ports:" not in strip_comments(compose_text(server, "compose.dev.yml"))


# ── docs ──────────────────────────────────────────────────────────

# Services documented somewhere other than docs/services/<slug>.md.
DOC_ELSEWHERE = {
    "landing": "docs/07-landing.md",
    "nginx-plain": "docs/04-nginx.md",
    "stirling-pdf-lite": "docs/services/stirling-pdf.md",
}


def test_every_managed_service_is_documented():
    each([s["slug"] for s in SERVICES if hs.is_managed_service(s)], _every_managed_service_is_documented)


def _every_managed_service_is_documented(svc):
    docs = REPO / "docs" / "services"
    if svc in DOC_ELSEWHERE:
        assert (REPO / DOC_ELSEWHERE[svc]).is_file()
    else:
        assert (docs / f"{svc}.md").is_file() or (docs / svc).is_dir(), f"no docs/services/{svc}.md"


def _pinned_images() -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    for svc in service_dirs():
        env = hs.load_env_file(REPO / "services" / svc / ".env.example")
        for m in re.finditer(r"^\s*image:\s*(\S+)", strip_comments(compose_text(svc)), re.M):
            img = re.sub(r"\$\{(\w+)(:-([^}]*))?\}", lambda x: env.get(x.group(1), x.group(3) or ""), m.group(1))
            repo, _, tag = img.rpartition(":")
            pins.setdefault(repo, set()).add(tag)
    # Base images of locally built images (dagster, temporal-worker, ...).
    for dockerfile in (REPO / "services").rglob("Dockerfile*"):
        for m in re.finditer(r"^FROM\s+(\S+?):(\S+)", dockerfile.read_text(), re.M):
            pins.setdefault(m.group(1), set()).add(m.group(2))
    return pins


HISTORY_WORDS = re.compile(r"→|->|bumped|from `|was |previously|earlier|upgrad|hit going|as of|then-pinned|"
                           r"confirmed (live|on)|captured|unchanged in|before|old |migrat|reverted|tried|official|upstream", re.I)


def test_docs_do_not_cite_stale_image_tags():
    """A doc line naming repo:tag for an image this stack pins must use the
    current tag — unless the line is clearly historical (bumped/→/as of...)."""
    pins = _pinned_images()
    pattern = re.compile(r"`((?:[a-z0-9.-]+/)*[a-z0-9._-]+):(v?\d[\w.-]*)`")
    stale = []
    for doc in sorted((REPO / "docs").rglob("*.md")):
        for n, line in enumerate(doc.read_text().splitlines(), 1):
            if HISTORY_WORDS.search(line):
                continue
            for m in pattern.finditer(line):
                repo, tag = m.groups()
                if repo in pins and tag not in pins[repo]:
                    stale.append(f"{doc.relative_to(REPO)}:{n} {repo}:{tag} (compose: {sorted(pins[repo])})")
    assert not stale, "stale image tags in docs:\n" + "\n".join(stale)


def test_claude_md_tier_lists_match_services_json():
    claude = REPO / "CLAUDE.md"
    if not claude.is_file():
        pytest.skip("CLAUDE.md is gitignored/local-only")
    text = claude.read_text()
    tiers = {"SERVICES_MIN": "min", "SERVICES_CORE": "core", "SERVICES_DAILY": "daily", "SERVICES_OFFICE": "office",
             "SERVICES_AUTOMATION_AI": "automation-ai", "SERVICES_EXTRA": "extra"}
    for key, tier in tiers.items():
        m = re.search(rf"\*\*{key}\*\*[^:]*:\s*(.+)", text)
        assert m, f"{key} line missing from CLAUDE.md"
        listed = [re.sub(r"\s*\(.*", "", x).strip() for x in m.group(1).split("→")]
        actual = [s["slug"] for s in SERVICES if s.get("tier") == tier and not s.get("virtual")]
        assert listed == actual, f"CLAUDE.md {key} out of date"


def test_starting_services_doc_covers_every_action_and_flag():
    """docs/15-starting-services.md must mention every CLI action and flag
    homeserver.py accepts, so new ones can't ship undocumented."""
    src = (REPO / "homeserver.py").read_text()
    doc = (REPO / "docs" / "15-starting-services.md").read_text()
    block = src[src.index("    if action not in ("):]
    block = block[: block.index(")")]
    actions = {a for a in re.findall(r'"([a-z]+)"', block)}
    flags = set(re.findall(r'tok (?:==|in) \(?"(--[a-z-]+)"', src)) | set(re.findall(r'tok == "(--[a-z-]+)"', src))
    missing = sorted(a for a in actions if f"`{a}" not in doc) + sorted(f for f in flags if f not in doc)
    assert not missing, f"docs/15-starting-services.md doesn't mention: {missing}"


def test_cache_containers_use_valkey_not_redis():
    """Managed-cloud parity (docs/10): AWS ElastiCache and GCP Memorystore run
    Valkey (ElastiCache's Redis OSS is frozen at 7.1), so every Redis-protocol
    cache here is Valkey, the engine a move would land on."""
    offenders = sorted(
        f"{p.parent.name}: {line.strip()}"
        for p in (REPO / "services").glob("*/compose.yml")
        for line in p.read_text().splitlines()
        if re.match(r"^\s*image:\s*[\"']?(docker\.io/)?(library/)?redis[:@\"'\s]", line)
    )
    assert not offenders, f"use valkey/valkey instead of redis: {offenders}"


def test_env_examples_have_docker_and_kubernetes_sections():
    """Every .env.example is laid out Common / Docker Compose only / Kubernetes
    (scripts/env_sections.py), so it's clear what each runtime uses: run
    `uv run scripts/env_sections.py` after adding a key."""
    import subprocess
    proc = subprocess.run(["uv", "run", "scripts/env_sections.py", "--check"], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, "not arranged (run uv run scripts/env_sections.py):\n" + proc.stdout


def test_env_files_are_owner_only():
    """.env files hold passwords and tokens: mode 600, so only the owner reads
    them (homeserver.py, docker compose and cluster.py all run as the owner).
    Fix with: chmod 600 .env kubernetes/.env services/*/.env"""
    loose = [str(f.relative_to(REPO)) for f in [REPO / ".env", REPO / "kubernetes/.env", *REPO.glob("services/*/.env")]
             if f.is_file() and f.stat().st_mode & 0o077]
    assert not loose, f"readable by others (chmod 600): {loose}"


# Images that deliberately track a moving tag, each with its documented reason.
MOVING_TAG_EXCEPTIONS = {
    # Public-facing remote browsers: security patches as soon as they ship
    # (docs/services/firefox.md, "Image tag — deliberate exception").
    "brave", "chromium", "firefox", "mullvad-browser", "librewolf", "zen", "helium", "chrome", "edge", "vivaldi",
}
MOVING_TAGS = {"latest", "release", "stable", "main", "master", "nightly", "edge", "dev", ""}


def test_images_are_pinned():
    """Every image is pinned to a version, or by digest when the project
    publishes no version tags (Excalidraw). Moving tags only for the
    documented exceptions above."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("k8s_generate", REPO / "kubernetes/generate.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    bad = []
    for s in hs._SERVICES_DATA["services"]:
        if not hs.is_managed_service(s) or s["slug"] in MOVING_TAG_EXCEPTIONS:
            continue
        for n, c in gen.load_compose(s["slug"])["services"].items():
            if not c.get("image"):
                continue
            img = gen.image_ref(s["slug"], c["image"], s["slug"])
            if "@sha256:" in img:
                continue
            name = img.rsplit("/", 1)[-1]
            if (name.split(":", 1)[1] if ":" in name else "") in MOVING_TAGS:
                bad.append(f"{s['slug']}/{c.get('container_name') or n}: {img}")
    assert not bad, f"images on a moving tag (pin a version, or a digest): {bad}"


def test_fixed_container_ips_are_inside_the_pinned_homeserver_subnet():
    """Browsers carry a static ipv4_address (and nginx-plain's LAN-isolation rules name the same IPs). The
    'homeserver' network's subnet is pinned in homeserver.py; an IP outside it makes `compose create` fail
    with 'no configured subnet contains IP address' (hit 2026-10-06 after the network was recreated)."""
    import ipaddress
    net = ipaddress.ip_network(hs.HOMESERVER_SUBNET)
    pat = re.compile(r"^\s*ipv4_address:\s*(\S+)", re.M)
    ips = {}
    for f in sorted((REPO / "services").glob("*/compose*.yml")):
        for m in pat.finditer(f.read_text()):
            ips[f"{f.parent.name}/{f.name}"] = m.group(1)
    assert ips, "expected the browsers' static IPs"
    outside = {k: v for k, v in ips.items() if ipaddress.ip_address(v) not in net}
    assert not outside, f"outside {net}: {outside}"
    script = (REPO / "services/nginx-plain/browser-lan-block.sh").read_text()
    listed = set(re.findall(r"^\s+(\d+\.\d+\.\d+\.\d+)\s+#", script, re.M))
    assert listed == set(ips.values()), "browser-lan-block.sh must list exactly the browsers' static IPs"
