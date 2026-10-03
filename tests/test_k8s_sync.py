"""Kubernetes is generated from Compose (kubernetes/generate.py), never hand-
edited, so the two can't drift. These tests fail when kubernetes/generated/
is stale, when a generated file could leak a secret, or when an image differs
from Compose. Plan: research/kubernetes-compose-parity-plan.md."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import homeserver as hs

REPO = hs.BASE_DIR
K8S = REPO / "kubernetes"
GENERATED = K8S / "generated"

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="generator reads services through `docker compose config`")

_spec = importlib.util.spec_from_file_location("k8s_generate", K8S / "generate.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)
SCOPE = gen.load_scope()
PORTED = SCOPE.get("ported") or []


def test_generated_manifests_match_compose():
    """Change Compose (or an override) without re-running the generator and
    this fails: `uv run kubernetes/generate.py`, then commit the result."""
    proc = subprocess.run(["uv", "run", "kubernetes/generate.py", "--check"], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_scope_names_real_services_with_reasons():
    managed = {s["slug"] for s in hs._SERVICES_DATA["services"] if hs.is_managed_service(s)}
    skipped = SCOPE.get("skipped") or {}
    for svc in PORTED + list(skipped):
        assert svc in managed, f"scope.yaml names {svc}, which isn't a managed service"
    assert not set(PORTED) & set(skipped), "a service can't be both ported and skipped"
    assert all(str(r).strip() for r in skipped.values()), "every skipped service needs a reason"
    assert set(SCOPE.get("prod_only") or []) <= set(PORTED)


def test_min_tier_is_fully_covered():
    """Phase 1 covers MIN completely: each MIN service is ported or skipped with a reason."""
    covered = set(PORTED) | set(SCOPE.get("skipped") or {})
    assert set(hs.SERVICES_MIN) <= covered, f"MIN not covered: {sorted(set(hs.SERVICES_MIN) - covered)}"


def _generated_docs():
    for f in sorted(GENERATED.rglob("*.yaml")):
        if f.name == "kustomization.yaml":
            continue
        for doc in yaml.safe_load_all(f.read_text()):
            if doc:
                yield f, doc


SECRET_KEY = re.compile(r"PASS|SECRET|TOKEN|SALT|CREDENTIAL|(^|_)KEY$|PRIVATE_KEY|API_?KEY", re.I)
PLACEHOLDER = re.compile(r"your_|changeme|example|<.*>", re.I)


def test_no_env_value_leaks_into_generated_files():
    """Secrets reach the cluster from .env at apply time, never via git: no
    value from any .env / .env.example may appear in a generated file."""
    blob = "\n".join(f.read_text() for f in GENERATED.rglob("*.yaml"))
    leaks = []
    for env_file in list((REPO / "services").glob("*/.env")) + list((REPO / "services").glob("*/.env.example")):
        for k, v in gen.load_env(env_file).items():
            if SECRET_KEY.search(k) and len(v) >= 8 and not PLACEHOLDER.search(v) and v in blob:
                leaks.append(f"{env_file.parent.name}/{env_file.name}:{k}")
    assert not leaks, f".env values found in kubernetes/generated/: {sorted(set(leaks))}"


def test_images_match_compose_exactly():
    """Versions come only from Compose (LTS rules, upstream pins), so a
    generated image must be the Compose image, never a separate pin."""
    gen_images = {}
    for f, doc in _generated_docs():
        tmpl = (doc.get("spec") or {}).get("template", {}).get("spec") or {}
        for c in tmpl.get("containers", []):
            gen_images[(f.parent.name, c["name"])] = c["image"]
    for svc in PORTED:
        compose = gen.load_compose(svc)
        for n, s in compose["services"].items():
            key = (svc, s.get("container_name") or n)
            if key in gen_images:
                want = gen.image_ref(svc, s["image"], svc)  # ${VERSION} pinned from .env.example
                assert gen_images[key] == want, f"{key}: {gen_images[key]} != compose {s['image']} ({want})"


def test_every_workload_is_probed_or_explained():
    """Compose healthchecks become probes; a long-running container without one
    must be on tests/test_healthchecks.py's documented exception lists."""
    from test_healthchecks import IMAGE_HEALTHCHECK, NO_HEALTHCHECK
    for f, doc in _generated_docs():
        if doc.get("kind") not in ("Deployment", "StatefulSet", "DaemonSet"):
            continue
        for c in doc["spec"]["template"]["spec"]["containers"]:
            if "readinessProbe" not in c:
                assert c["name"] in IMAGE_HEALTHCHECK or c["name"] in NO_HEALTHCHECK, \
                    f"{f.parent.name}/{c['name']}: no probe and no documented reason"


# ── phase 2: databases ────────────────────────────────────────────────────

SHARED_APPS = {svc: spec for svc, spec in gen.shared_db_apps().items() if svc in PORTED}


def _db_objects(svc: str) -> list[dict]:
    f = GENERATED / "apps" / svc / "database.yaml"
    return [d for d in yaml.safe_load_all(f.read_text()) if d] if f.is_file() else []


def test_env_db_names_match_env_example():
    """The generator takes db/user names from .env.example (generated output
    can't depend on one host's .env); the real .env must agree, or the app
    would log in as a role Kubernetes never created."""
    for svc, spec in gen.shared_db_apps().items():
        env_file = REPO / "services" / svc / ".env"
        if not env_file.is_file():
            continue
        env = gen.load_env(env_file)
        for key in ("db", "user"):
            k = hs._SERVICES_BY_SLUG[svc]["shared_db"][key]
            if not k.startswith("="):
                assert env.get(k) == spec[key], f"{svc}: .env {k} differs from .env.example"


@pytest.mark.parametrize("svc", sorted(SHARED_APPS))
def test_shared_db_objects_mirror_compose_provisioning(svc):
    """Same role/user, database(s) and ownership as homeserver.py's
    provision_shared_db, and nothing an operator could ever drop."""
    spec = SHARED_APPS[svc]
    objs = _db_objects(svc)
    want_dbs = [spec["db"]] + list(hs._SERVICES_BY_SLUG[svc]["shared_db"].get("extra_dbs", []))
    dbs = [o for o in objs if o["kind"] == "Database"]
    assert [d["spec"]["name"] for d in dbs] == want_dbs
    if spec["engine"] == "postgres":
        (role,) = [o for o in objs if o["kind"] == "DatabaseRole"]
        assert role["spec"]["name"] == spec["user"] and role["spec"]["login"] is True
        assert role["spec"]["databaseRoleReclaimPolicy"] == "retain"
        assert role["spec"]["passwordSecret"]["name"] == f"{svc}-db-role"
        for d in dbs:
            assert d["spec"]["owner"] == spec["user"] and d["spec"]["databaseReclaimPolicy"] == "retain"
            assert {"name": "public", "owner": spec["user"]} in d["spec"]["schemas"]
    else:
        (user,) = [o for o in objs if o["kind"] == "User"]
        assert user["spec"]["name"] == spec["user"] and user["spec"]["host"] == "%"
        assert user["spec"]["maxUserConnections"] == 0, "Compose has no per-user connection cap"
        grants = [o for o in objs if o["kind"] == "Grant"]
        assert sorted(g["spec"]["database"] for g in grants) == sorted(want_dbs)
        assert all(g["spec"]["privileges"] == ["ALL PRIVILEGES"] for g in grants)
        # mariadb-operator's default cleanupPolicy (Delete) drops the
        # database when the CR goes away; data must outlive manifests.
        assert all(o["spec"]["cleanupPolicy"] == "Skip" for o in objs)


def test_shared_postgres_isolates_every_app_role():
    """pg_hba stands in for REVOKE ALL ON DATABASE ... FROM PUBLIC: each app
    role reaches only its own database(s), then a reject for the rest."""
    if "shared-postgres" not in PORTED:
        pytest.skip("shared-postgres not ported")
    (cluster,) = _db_objects("shared-postgres")
    hba = cluster["spec"]["postgresql"]["pg_hba"]
    pg = {s: v for s, v in gen.shared_db_apps().items() if v["engine"] == "postgres"}
    for svc, spec in pg.items():
        assert f"host {','.join(spec['dbs'])} {spec['user']} all scram-sha-256" in hba, svc
    assert hba[-1].startswith("host all ") and hba[-1].endswith(" all reject")
    assert set(hba[-1].split()[2].split(",")) == {v["user"] for v in pg.values()}


def test_shared_servers_match_compose():
    """MariaDB runs the exact Compose image; CNPG's Postgres the same release
    (bump CNPG_POSTGRES_IMAGE in kubernetes/versions.env with Compose's)."""
    if "shared-mariadb" in PORTED:
        (mdb,) = _db_objects("shared-mariadb")
        assert mdb["spec"]["image"] == next(iter(gen.load_compose("shared-mariadb")["services"].values()))["image"]
    if "shared-postgres" in PORTED:
        (cluster,) = _db_objects("shared-postgres")
        compose_img = next(iter(gen.load_compose("shared-postgres")["services"].values()))["image"]
        release = re.search(r":(\d+\.\d+)", compose_img).group(1)
        assert re.search(r":(\d+\.\d+)-", cluster["spec"]["imageName"]).group(1) == release, (compose_img, cluster["spec"]["imageName"])


def test_external_db_host_emits_no_database_objects(monkeypatch):
    """DB_HOST pointing at RDS / Cloud SQL / Azure: no role or database is
    created in-cluster, matching homeserver.py's shared_db_external()."""
    svc = next(iter(SHARED_APPS), None)
    if not svc:
        pytest.skip("no shared-db app ported")
    real = gen.load_env
    monkeypatch.setattr(gen, "load_env", lambda p: {**real(p), "DB_HOST": "db.example.rds.amazonaws.com"}
                        if Path(p).parent.name == svc else real(p))
    assert gen.external_db(svc)


def test_nginx_redirects_become_gateway_redirects():
    """nginx-plain's bare domain -> www 301 must exist on Kubernetes too."""
    if "landing" not in PORTED:
        pytest.skip("landing not ported")
    assert ("${DOMAIN}", "www.${DOMAIN}", 301) in gen.nginx_redirects()
    docs = [d for d in yaml.safe_load_all((GENERATED / "envs/test/landing/routes.yaml").read_text()) if d]
    (r,) = [d for d in docs if d["metadata"]["name"] == "landing-redirect"]
    assert r["spec"]["hostnames"] == [gen.TEST_DOMAIN if hasattr(gen, "TEST_DOMAIN") else "k8s.local"]
    assert r["spec"]["rules"][0]["filters"][0]["requestRedirect"] == {
        "scheme": "https", "hostname": "www.k8s.local", "statusCode": 301}


def test_forward_auth_hosts_stay_protected():
    """Every hostname nginx-plain puts behind authentik gets Traefik's
    ForwardAuth on Kubernetes, plus the outpost path; nothing loses its login."""
    prot = gen.nginx_protected()
    assert "browser.${DOMAIN}" in prot
    for f in GENERATED.glob("envs/test/*/routes.yaml"):
        for r in yaml.safe_load_all(f.read_text()):
            if not r or r["kind"] != "HTTPRoute" or "rules" not in r["spec"]:
                continue
            hosts = {h.replace(gen.TEST_DOMAIN, "${DOMAIN}") for h in r["spec"]["hostnames"]}
            if hosts & prot:
                assert hosts <= prot, f"{f}: protected and open hosts mixed in one route"
                filters = [fl for rule in r["spec"]["rules"] for fl in rule.get("filters", [])]
                assert any(fl.get("extensionRef", {}).get("name") == gen.AUTH_MIDDLEWARE for fl in filters), f
                assert r["spec"]["rules"][0]["matches"][0]["path"]["value"] == "/outpost.goauthentik.io/"


def test_browser_hub_block_has_no_nginx_auth_left():
    """The generated Browser Hub server block drops nginx's auth_request
    (Traefik + authentik do it) but keeps every status/browser location."""
    cm = next(d for d in yaml.safe_load_all((GENERATED / "apps/nginx-plain/configmaps.yaml").read_text()) if d)
    conf = cm["data"]["default.conf.template"]
    assert "auth_request" not in conf and "goauthentik" not in conf
    assert conf.count("location = /_status/") == 10
    assert ".apps.svc.cluster.local:3000" in conf


def test_image_versions_in_env_match_env_example():
    """Generated images pin ${..._VERSION} from .env.example; the host's real
    .env must run the same version, or Compose and Kubernetes would differ."""
    for svc in PORTED:
        env_file = REPO / "services" / svc / ".env"
        if not env_file.is_file():
            continue
        env, ex = gen.load_env(env_file), gen.load_env(REPO / "services" / svc / ".env.example")
        for s in gen.load_compose(svc)["services"].values():
            for var in gen.VAR.findall(s["image"]):
                if var[0] in ex:
                    assert env.get(var[0]) == ex[var[0]], f"{svc}: .env {var[0]} differs from .env.example"


def _service_ports() -> dict[str, set[int]]:
    """Every in-cluster Service name -> its ports (apps + operator-run DBs)."""
    out: dict[str, set[int]] = {}
    for f in GENERATED.glob("apps/*/services.yaml"):
        for d in yaml.safe_load_all(f.read_text()):
            if d:
                out[d["metadata"]["name"]] = {p["port"] for p in d["spec"]["ports"]}
    for f in GENERATED.glob("apps/*/database.yaml"):
        for d in yaml.safe_load_all(f.read_text()):
            if d and d["kind"] == "Cluster":
                for a in d["spec"]["managed"]["services"]["additional"]:
                    out[a["serviceTemplate"]["metadata"]["name"]] = {5432}
            elif d and d["kind"] == "MariaDB":
                out[d["metadata"]["name"]] = {3306}
    return out


def test_env_endpoints_reach_a_service_port():
    """A ported service's .env.example endpoint (X_HOST=<container> + X_PORT,
    or <container>:<port> in a URL) must hit a port the target's Service has.
    Docker reaches any port an image EXPOSEs; Kubernetes only declared ones,
    so a missing `expose:` silently breaks the call (Mailpit's SMTP 1025
    hung Firefly's login, 2026-10-04)."""
    ports = _service_ports()
    gaps = []
    for svc in PORTED:
        ex = gen.load_env(REPO / "services" / svc / ".env.example")
        for k, v in ex.items():
            for host, port in re.findall(r"(?:^|//|@)([a-z][a-z0-9-]+):(\d{2,5})\b", v):
                if host in ports and int(port) not in ports[host]:
                    gaps.append(f"{svc}: {k} -> {host}:{port}")
            if re.search(r"HOST(NAME)?$", k) and v in ports:
                pk = re.sub(r"HOST(NAME)?$", "PORT", k)
                if ex.get(pk, "").isdigit() and int(ex[pk]) not in ports[v]:
                    gaps.append(f"{svc}: {pk}={ex[pk]} -> {v}")
    assert not gaps, "ports missing from generated Services (add `expose:` in compose.yml): " + ", ".join(gaps)


def _image_healthcheck(image: str) -> dict | None:
    """The image's HEALTHCHECK from the local Docker cache, or None."""
    p = subprocess.run(["docker", "image", "inspect", image, "--format", "{{json .Config.Healthcheck}}"],
                       capture_output=True, text=True)
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() not in ("", "null") else None


def test_image_healthchecks_are_carried_and_current():
    """Kubernetes ignores image HEALTHCHECKs, so a container Compose leaves
    on its image's check (test_healthchecks.IMAGE_HEALTHCHECK) needs that
    check in its override (image_healthcheck), and it must still equal the
    image's: a version bump that changes the check fails here. Images not
    pulled on this host are only checked for presence."""
    from test_healthchecks import IMAGE_HEALTHCHECK
    missing, stale = [], []
    for svc in PORTED:
        ov = gen.load_overrides(svc).get("containers") or {}
        for n, s in gen.load_compose(svc)["services"].items():
            c = s.get("container_name") or n
            if c not in IMAGE_HEALTHCHECK or (ov.get(c) or {}).get("skip") or (s.get("healthcheck") or {}).get("test"):
                continue
            ovs = gen.load_overrides(svc)
            if gen.own_postgres(svc, n, s, ovs) or gen.own_mariadb(svc, n, s, ovs):
                continue  # operator-run database: CloudNativePG/mariadb-operator probe it
            hc = (ov.get(c) or {}).get("image_healthcheck")
            if not hc and not (ov.get(c) or {}).get("probes"):
                missing.append(f"{svc}/{c}")
                continue
            img = _image_healthcheck(gen.image_ref(svc, s["image"], svc)) if hc else None
            if img:
                want = {"test": img["Test"], **{k: gen.seconds(img[ik]) for ik, k in (
                    ("Interval", "interval"), ("Timeout", "timeout"), ("StartPeriod", "start_period"),
                    ("StartInterval", "start_interval")) if img.get(ik)},
                    **({"retries": img["Retries"]} if img.get("Retries") else {})}
                have = {k: (gen.seconds(v) if k in ("interval", "timeout", "start_period", "start_interval") else v)
                        for k, v in hc.items()}
                if have != want:
                    stale.append(f"{svc}/{c}")
    assert not missing, f"image healthcheck not carried to Kubernetes: {missing}"
    assert not stale, f"image_healthcheck differs from the image's HEALTHCHECK (re-copy it): {stale}"
