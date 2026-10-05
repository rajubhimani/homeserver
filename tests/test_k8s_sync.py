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
from conftest import each

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
            if isinstance(doc, dict):  # host-ports.yaml is a plain list, not an object
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
    """Compose healthchecks become probes (readiness + liveness, or liveness
    only for containers without ports); a long-running container without one
    must be on tests/test_healthchecks.py's documented exception lists."""
    from test_healthchecks import IMAGE_HEALTHCHECK, NO_HEALTHCHECK
    for f, doc in _generated_docs():
        if doc.get("kind") not in ("Deployment", "StatefulSet", "DaemonSet"):
            continue
        for c in doc["spec"]["template"]["spec"]["containers"]:
            # Containers without ports carry liveness only (no traffic to steer).
            if "readinessProbe" not in c and "livenessProbe" not in c:
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


def test_shared_db_objects_mirror_compose_provisioning():
    each(sorted(SHARED_APPS), _shared_db_objects_mirror_compose_provisioning)


def _shared_db_objects_mirror_compose_provisioning(svc):
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
    # Every container the cluster runs: an endpoint naming one that has no
    # Service at all is as broken as a missing port (AppFlowy's MinIO,
    # 2026-10-04: "dns error" for appflowy-minio).
    workloads = set()
    for f, doc in _generated_docs():
        if doc.get("kind") in ("Deployment", "StatefulSet", "DaemonSet"):
            workloads |= {c["name"] for c in doc["spec"]["template"]["spec"]["containers"]}
    gaps = []
    for svc in PORTED:
        ex = gen.load_env(REPO / "services" / svc / ".env.example")
        for k, v in ex.items():
            for host, port in re.findall(r"(?:^|//|@)([a-z][a-z0-9-]+):(\d{2,5})\b", v):
                if host in ports and int(port) not in ports[host]:
                    gaps.append(f"{svc}: {k} -> {host}:{port}")
                elif host not in ports and host in workloads:
                    gaps.append(f"{svc}: {k} -> {host}:{port} (no Service)")
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


def test_localhost_ports_mirror_compose():
    """Every literal-address port Compose publishes becomes hostPort+hostIP on
    its container (localhost works on a cluster on this machine), and every
    127.0.0.1 port is in host-ports.yaml for kind's port mappings, with
    unique host and node ports."""
    hp = yaml.safe_load((GENERATED / "host-ports.yaml").read_text())
    assert len({(e["host"], e["protocol"]) for e in hp}) == len(hp), "duplicate host port"
    assert len({(e["node"], e["protocol"]) for e in hp}) == len(hp), "duplicate node port"
    in_list = {(e["svc"], e["host"]) for e in hp}
    la = next(d for d in yaml.safe_load_all((GENERATED / "apps/local-access/workloads.yaml").read_text()) if d)
    bound = {(pt["hostIP"], pt["hostPort"]) for pt in la["spec"]["template"]["spec"]["containers"][0]["ports"]}
    for svc in PORTED:
        for n, s in gen.load_compose(svc)["services"].items():
            for ip, host, tgt, proto in gen.published_ports(s):
                if ip == "127.0.0.1" and svc != "nginx-plain":
                    assert (svc, host) in in_list, f"{svc}: 127.0.0.1:{host} missing from host-ports.yaml"
                assert (ip, host) in bound, f"{svc}: {ip}:{host} not served by the local-access proxy"
    # Only the proxy holds host ports, so apps can meet Pod Security Baseline.
    for f, doc in _generated_docs():
        if doc.get("kind") in ("Deployment", "StatefulSet", "DaemonSet") and f.parent.name != "local-access":
            for c in doc["spec"]["template"]["spec"]["containers"]:
                assert not any(pt.get("hostPort") for pt in c.get("ports", [])), f"{f.parent.name}/{c['name']} holds a hostPort"


def test_cluster_cli_commands_all_exist():
    """Every action cluster.py dispatches to is defined (a refactor once
    dropped cmd_rmi and the CLI failed with a NameError at run time)."""
    src = (K8S / "cluster.py").read_text()
    spec = importlib.util.spec_from_file_location("k8s_cluster", K8S / "cluster.py")
    mod = importlib.util.module_from_spec(spec)
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec.loader.exec_module(mod)
    for name in set(re.findall(r'"[a-z]+": (cmd_[a-z_]+)', src)):
        assert callable(getattr(mod, name, None)), f"cluster.py dispatches to undefined {name}"


def test_k8s_py_resolves_targets_like_homeserver():
    """k8s.py up/down use homeserver.py's tier semantics: 'up core' brings MIN
    too, 'down core' only CORE, group: from services.json, no duplicates."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cli", K8S / "k8s.py")
    k8s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k8s)
    up_core, _ = k8s.resolve(["core"], "up")
    assert up_core == hs.SERVICES_MIN + hs.SERVICES_CORE
    down_core, _ = k8s.resolve(["core"], "down")
    assert down_core == hs.SERVICES_CORE
    down_all, _ = k8s.resolve(["all"], "down")
    assert down_all[0] == hs.SERVICES_EXTRA[-1], "down all stops in reverse order"
    grp = next(iter(hs.SERVICE_GROUPS))
    g, expanded = k8s.resolve([f"group:{grp}", f"group:{grp}"], "up")
    assert expanded and len(g) == len(set(g)) == len(set(hs.SERVICE_GROUPS[grp]))


def test_every_service_has_an_ingress_policy():
    """Each ported service ships a NetworkPolicy selecting its pods, and every
    in-cluster endpoint another service uses is allowed on its port."""
    for svc in PORTED:
        f = GENERATED / "apps" / svc / "networkpolicies.yaml"
        assert f.is_file(), f"{svc}: no network policy"
        pol = next(d for d in yaml.safe_load_all(f.read_text()) if d)
        assert pol["spec"]["podSelector"]["matchLabels"]["homeserver/service"] == svc
    for src in PORTED:
        for target, ports in gen.endpoint_targets(src).items():
            pol = gen.network_policy(target)
            ok = any(any((fr.get("podSelector") or {}).get("matchLabels", {}).get("homeserver/service") == src
                         or (fr.get("namespaceSelector") or {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "apps"
                         for fr in r["from"])
                     and (not r.get("ports") or ports & {p["port"] for p in r["ports"]})
                     for r in pol["spec"]["ingress"])
            if target in ("shared-postgres", "shared-mariadb"):
                continue  # covered by the shared_db rule, checked by the generator
            assert ok, f"{src} -> {target}:{sorted(ports)} not allowed by {target}'s policy"


def test_config_file_upstreams_have_service_ports():
    """Ports a service's own config files use for its containers (nginx.conf,
    Caddyfile, Envoy cds.yaml) are on those containers' Services: Docker
    reaches any port, Kubernetes only declared ones (AppFlowy's gotrue,
    Plane's web, Supabase's auth/rest/... on 2026-10-04)."""
    ports = _service_ports()
    gaps = []
    for svc in PORTED:
        comp = gen.load_compose(svc)["services"]
        cname = {n: (s.get("container_name") or n) for n, s in comp.items()}
        for n, wanted in gen.repo_config_ports(svc, comp, cname).items():
            name = re.sub(r"[^a-z0-9-]", "-", cname[n].lower())
            have = ports.get(name, set()) | ports.get(n, set())
            gaps += [f"{svc}/{name}:{p}" for p in sorted(wanted - have)]
    assert not gaps, f"config files reach ports their Services don't have: {gaps}"


# ── GitOps (docs/17 "GitOps") ────────────────────────────────────────────

def _apps_objects(svc: str) -> list[dict]:
    out = []
    for f in sorted((GENERATED / "apps" / svc).glob("*.yaml")):
        if f.name != "kustomization.yaml":
            out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def test_services_are_generated_stopped():
    """The base of every service is stopped: ArgoCD creates config, volumes
    and databases, and only the env's running list switches them on. Objects
    that hold data are never pruned or deleted by ArgoCD."""
    for svc in PORTED:
        for o in _apps_objects(svc):
            k, spec, ann = o["kind"], o.get("spec") or {}, o["metadata"].get("annotations") or {}
            where = f"{svc}: {k}/{o['metadata']['name']}"
            if k == "Deployment":
                assert spec["replicas"] == 0, where
            elif k == "DaemonSet":
                assert spec["template"]["spec"]["nodeSelector"].get(gen.STOPPED_NODE_SELECTOR[0]), where
            elif k in ("Job", "MariaDB"):
                assert spec["suspend"] is True, where
            elif k == "Cluster":
                assert ann.get(gen.CNPG_HIBERNATION) == "on", where
            if k in gen.KEEP_KINDS:
                assert ann.get("argocd.argoproj.io/sync-options") == "Prune=false,Delete=false", where


def test_env_overlays_follow_the_running_list():
    """envs/<env>/<svc> switches the service on exactly when
    kubernetes/deploy/<env>.yaml runs it (one patch per stopped object), and
    turns on WAL archiving for its databases when the env has backups on."""
    for env in gen.ENVS:
        running = gen.running_services(env)
        for svc in PORTED:
            k = GENERATED / "envs" / env / svc / "kustomization.yaml"
            if not k.is_file():
                continue
            patches = yaml.safe_load(k.read_text()).get("patches") or []
            backups = gen.db_backup_patches(_apps_objects(svc)) if gen.backup_settings(env)["enabled"] else []
            expected = (gen.running_patches(_apps_objects(svc)) if svc in running else []) + backups
            assert patches == expected, (f"{env}/{svc}: overlay doesn't match kubernetes/deploy/{env}.yaml "
                                         f"(running: {svc in running}, backups: {bool(backups)})")
        for app, spec in gen.shared_db_apps().items():
            if app in running and not gen.external_db(app):
                assert gen.SHARED[spec["engine"]] in running, f"{env}: {app} runs without its shared database"


def test_no_secret_in_git_and_every_referenced_secret_is_built():
    """Git holds no Secret objects. Every Secret a generated object reads
    (envFrom, secretKeyRef, CNPG/mariadb-operator references) is built by an
    ExternalSecret of the same service, or of the shared server it uses."""
    built, refs = {}, []

    def walk(node, svc):
        if isinstance(node, dict):
            for key in ("secretRef", "secretKeyRef", "passwordSecret", "superuserSecret",
                        "rootPasswordSecretKeyRef", "passwordSecretKeyRef"):
                if isinstance(node.get(key), dict) and node[key].get("name"):
                    refs.append((svc, node[key]["name"]))
            if isinstance(node.get("secret"), dict) and node["secret"].get("secretName"):
                refs.append((svc, node["secret"]["secretName"]))
            for v in node.values():
                walk(v, svc)
        elif isinstance(node, list):
            for v in node:
                walk(v, svc)

    for svc in PORTED:
        for o in _apps_objects(svc):
            assert o["kind"] != "Secret", f"{svc}: a Secret object in git"
            if o["kind"] == "ExternalSecret":
                built[o["spec"]["target"]["name"]] = svc
                assert o["spec"]["dataFrom"] == [{"extract": {"key": svc}}], f"{svc} reads another service's store"
            else:
                walk(o, svc)
    missing = sorted({f"{svc}: {name}" for svc, name in refs if name not in built})
    assert not missing, "Secrets nothing builds:\n  " + "\n  ".join(missing)


def test_gitops_projects_and_addons():
    """Services can only reach their own namespaces; the ApplicationSet's
    project is fixed (never templated); every add-on version is pinned in
    versions.env and every add-on folder exists."""
    addons = yaml.safe_load((K8S / "cluster/addons.yaml").read_text())
    for a in addons:
        if a.get("chart"):
            assert a["version"] in gen.VERSIONS, f"{a['name']}: {a['version']} not in versions.env"
            if a.get("values"):
                assert (REPO / a["values"]).is_file(), a["name"]
        else:
            assert (REPO / a["path"]).is_dir(), f"{a['name']}: {a['path']} missing"
    for env in gen.ENVS:
        docs = {d["metadata"]["name"]: d for f in (GENERATED / "gitops" / env).glob("*.yaml")
                if f.name != "kustomization.yaml" for d in yaml.safe_load_all(f.read_text()) if d}
        appset = docs["services"]
        assert appset["spec"]["template"]["spec"]["project"] == "homeserver"
        assert appset["spec"]["syncPolicy"]["preserveResourcesOnDeletion"] is True
        assert "argocd.argoproj.io/skip-reconcile" in appset["spec"]["preservedFields"]["annotations"]
        proj = docs["homeserver"]["spec"]
        assert {d["namespace"] for d in proj["destinations"]} == {gen.NAMESPACE, gen.LOCAL_ACCESS_NS, gen.SECRET_STORE_NS}
        assert {a["name"] for a in addons} <= set(docs)


def test_k8s_py_up_down_edit_the_running_list(tmp_path, monkeypatch):
    """'down jellyfin' while core runs records it as stopped; 'up jellyfin'
    clears that; 'down core' leaves MIN running, as homeserver.py does."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cli2", K8S / "k8s.py")
    k8s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k8s)
    (tmp_path / "test.yaml").write_text("# comment kept\nrepo: r\nrevision: b\nrunning: [min, core]\nstopped: []\n")
    for mod in (k8s, gen, _sys.modules["generate"]):
        monkeypatch.setattr(mod, "DEPLOY_DIR", tmp_path)
    jelly = "jellyfin" if "jellyfin" in PORTED else hs.SERVICES_CORE[-1]
    _, after = k8s.edit("test", "down", [jelly])
    assert jelly not in after and "authentik" in after
    assert "# comment kept" in (tmp_path / "test.yaml").read_text()
    _, after = k8s.edit("test", "up", [jelly])
    assert jelly in after
    _, after = k8s.edit("test", "down", ["core"])
    assert set(hs.SERVICES_MIN) & set(PORTED) <= after and not (set(hs.SERVICES_CORE) & after)


def test_kubernetes_scripts_have_no_undefined_names():
    """A name used but never imported or defined only fails when that code
    path runs (cluster.py import lost own_db_keys on 2026-10-04): pyflakes
    finds it statically."""
    proc = subprocess.run(["python", "-m", "pyflakes", *map(str, sorted(K8S.glob("*.py")))],
                          cwd=REPO, capture_output=True, text=True)
    errors = [l for l in proc.stdout.splitlines() if "undefined name" in l or "imported but unused" in l]
    assert not errors, "\n".join(errors)


def test_init_steps_get_their_compose_environment():
    """A Compose one-shot step that runs as an init container gets what its
    Compose service declares: the whole .env when it has env_file, and every
    `environment:` key. Without them airflow-init migrated a throwaway
    SQLite file and temporal-schema-setup ran with empty arguments
    (2026-10-04 smoke tests)."""
    gaps = []
    for svc in PORTED:
        f = GENERATED / "apps" / svc / "workloads.yaml"
        if not f.is_file():
            continue
        comp = gen.load_compose(svc)["services"]
        by_name = {re.sub(r"[^a-z0-9-]", "-", (s.get("container_name") or n).lower()): s for n, s in comp.items()}
        for d in yaml.safe_load_all(f.read_text()):
            pod = ((d or {}).get("spec") or {}).get("template", {}).get("spec", {})
            for ic in pod.get("initContainers") or []:
                s = by_name.get(ic["name"])
                if not s:
                    continue  # generated waits (wait-db, wait-<svc>)
                refs = {x["secretRef"]["name"] for x in ic.get("envFrom") or [] if "secretRef" in x}
                if s.get("env_file") and f"{svc}-env" not in refs:
                    gaps.append(f"{svc}/{ic['name']}: no .env (env_file)")
                have = {e["name"] for e in ic.get("env") or []}
                missing = set(s.get("environment") or {}) - have
                if missing:
                    gaps.append(f"{svc}/{ic['name']}: missing {sorted(missing)}")
    assert not gaps, "\n".join(gaps)


def test_dagster_chart_values_match_compose():
    """Dagster runs from its official chart: its Services keep Compose's
    names and ports (the route and .env endpoints don't change), its database
    is the shared one from .env.example, the chart version is the dagster
    version the code image is built with, and run pods carry the label the
    shared-postgres network policy admits."""
    if "dagster" not in PORTED:
        pytest.skip("dagster not ported")
    comp = gen.load_compose("dagster")["services"]
    ex = gen.load_env(REPO / "services/dagster/.env.example")
    v = gen.dagster_values(True)
    release = gen.load_overrides("dagster")["helm"]["release"]
    assert f"{release}-{v['dagsterWebserver']['nameOverride']}" == comp["dagster-webserver"]["container_name"]
    assert v["dagsterWebserver"]["service"]["port"] == 3000
    code = v["dagster-user-deployments"]["deployments"][0]
    assert code["name"] == comp["dagster-user-code"]["container_name"] and code["port"] == 4000
    assert f"{code['image']['repository']}:{code['image']['tag']}" == comp["dagster-user-code"]["image"]
    assert v["postgresql"]["postgresqlHost"] == ex["DB_HOST"] and v["postgresql"]["enabled"] is False
    assert gen.dagster_version() in comp["dagster-user-code"]["image"]
    assert v["runLauncher"]["config"]["k8sRunLauncher"]["labels"]["homeserver/service"] == "dagster"
    stopped = gen.dagster_values(False)
    assert stopped["dagsterWebserver"]["replicaCount"] == 0 and not stopped["dagsterDaemon"]["enabled"]
    assert not stopped["dagster-user-deployments"]["enabled"]
    # The code is in the image now: no service_data mount on Compose.
    assert not any("user-code" in str(m.get("source", "")) for m in comp["dagster-user-code"].get("volumes") or [])


def test_backups_cover_every_database_and_volume():
    """With backups on (kubernetes/deploy/<env>.yaml), every running service's
    Postgres has a nightly base backup and its shared-server databases a
    nightly dump. Velero leaves out database volumes (backed up by Barman and
    the dumps) and host folders (photos, media), everywhere."""
    for env in gen.ENVS:
        if not gen.backup_settings(env)["enabled"]:
            continue
        for svc in gen.running_services(env):
            f = GENERATED / "envs" / env / svc / "backups.yaml"
            objs = [d for d in yaml.safe_load_all(f.read_text()) if d] if f.is_file() else []
            scheduled = {o["spec"]["cluster"]["name"] for o in objs if o["kind"] == "ScheduledBackup"}
            clusters = {o["metadata"]["name"] for o in _apps_objects(svc) if o["kind"] == "Cluster"}
            assert clusters <= scheduled, f"{env}/{svc}: no nightly backup for {sorted(clusters - scheduled)}"
            if svc in gen.shared_db_apps() and not gen.external_db(svc):
                assert any(o["kind"] == "CronJob" for o in objs), f"{env}/{svc}: no database dump job"
    for app, spec in gen.shared_db_apps().items():  # every app's dump job builds (postgres and mariadb)
        job = gen.dump_cronjob(app, spec, gen.backup_settings("prod"), {})
        assert all(db in job["spec"]["jobTemplate"]["spec"]["template"]["spec"]["initContainers"][0]["command"][2]
                   for db in spec["dbs"])
    for svc in PORTED:
        for o in _apps_objects(svc):
            if o["kind"] in ("Cluster", "MariaDB"):
                meta = o["spec"].get("inheritedMetadata") or o["spec"].get("inheritMetadata")
                assert meta["labels"].get("velero.io/exclude-from-backup") == "true", f"{svc}: {o['metadata']['name']}"
            if o["kind"] in ("Deployment", "DaemonSet"):
                tmpl = o["spec"]["template"]
                host = {v["name"] for v in tmpl["spec"].get("volumes") or []
                        if "-host-" in (v.get("persistentVolumeClaim") or {}).get("claimName", "")}
                excl = set((tmpl["metadata"].get("annotations") or {}).get("backup.velero.io/backup-volumes-excludes", "").split(","))
                assert host <= excl, f"{svc}/{o['metadata']['name']}: host folders {sorted(host - excl)} would be copied by Velero"


def test_local_access_never_takes_traefiks_node_ports():
    """Traefik's node ports (kubernetes/cluster/traefik/values.yaml) belong to
    Traefik alone; the local-access proxy's NodePort Service must not claim
    them, or one of the two Services fails to apply."""
    values = yaml.safe_load((K8S / "cluster/traefik/values.yaml").read_text())
    traefik = {p["nodePort"] for p in values["ports"].values() if isinstance(p, dict) and p.get("nodePort")}
    svc = next(d for d in yaml.safe_load_all((GENERATED / "apps/local-access/services.yaml").read_text()) if d)
    taken = {p["nodePort"] for p in svc["spec"]["ports"]}
    assert not traefik & taken, f"local-access claims Traefik's node ports {sorted(traefik & taken)}"


def test_port_variable_defaults_match_env_example():
    """Compose ports written as ${VAR:-default} are read with the default;
    .env.example must set the same value, or Docker and Kubernetes would
    publish different localhost ports."""
    gaps = []
    for svc in PORTED:
        d = REPO / "services" / svc
        f = d / "compose.prod.yml"
        if not f.is_file():
            continue
        ex = gen.load_env(d / ".env.example")
        for var, default in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-(\d+)\}", f.read_text()):
            if ex.get(var, default) != default:
                gaps.append(f"{svc}: {var}={ex[var]} in .env.example, {default} in compose.prod.yml")
    assert not gaps, "\n".join(gaps)


def test_import_never_starts_a_stopped_service(tmp_path, monkeypatch):
    """import --from-export scaled every exported service back up, the tunnel
    included, though git lists it as stopped: while the apps are still being
    filled, a connected tunnel would expose them empty (their first visitor
    can create the admin account). Only the running list may be started."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cluster_import", K8S / "cluster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import generate
    scaled = []
    monkeypatch.setattr(generate, "running_services", lambda env: {"docs"})
    monkeypatch.setattr(mod, "argo_pause", lambda svc, paused: None)
    monkeypatch.setattr(mod, "scale", lambda svc, n: scaled.append((svc, n)))
    (tmp_path / "export.json").write_text(json.dumps({
        "docs": {"volumes": [], "dbs": []}, "cloudflared": {"volumes": [], "dbs": []}}))
    mod.import_export(type("A", (), {"from_export": str(tmp_path), "services": [], "env": "prod"})())
    assert scaled == [("docs", 1)], scaled


def test_a_probe_never_goes_through_the_pods_own_service():
    """Temporal's Compose healthcheck is `nc -z temporal 7233` (its own name,
    resolved by Docker DNS to itself). On Kubernetes that name is a Service,
    which routes only to ready pods, so the pod could never become ready and
    everything waiting on `temporal:7233` waited forever (2026-10-05). The
    generator turns it into a tcpSocket probe on the pod's own IP."""
    docs = [d for d in yaml.safe_load_all((K8S / "generated/apps/temporal/workloads.yaml").read_text()) if d]
    main = next(c for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "temporal"
                for c in d["spec"]["template"]["spec"]["containers"] if c["name"] == "temporal")
    for probe in ("readinessProbe", "livenessProbe", "startupProbe"):
        assert main[probe].get("tcpSocket") == {"port": 7233}, (probe, main[probe])
        assert "exec" not in main[probe]


def test_dagster_webserver_probe_follows_its_service_port():
    """The chart's readiness probe is fixed to port 80 (its default service
    port); the webserver serves on 3000 like Compose, so a probe left on 80 is
    refused forever and the pod is never Ready (2026-10-05)."""
    docs = [d for d in yaml.safe_load_all((K8S / "generated/gitops/prod/applications.yaml").read_text()) if d]
    app = next(d for d in docs if d["metadata"]["name"] == "dagster-chart")
    values = app["spec"]["source"]["helm"]["valuesObject"]["dagsterWebserver"]
    assert values["readinessProbe"]["httpGet"]["port"] == values["service"]["port"] == 3000


def test_a_route_is_found_by_the_compose_service_key_too():
    """nginx-plain's grafana.${DOMAIN} block points at `grafana`, the Compose
    service key; the container is named `observability`. Routes were matched by
    container name only, so Grafana's public hostname answered 404 on the
    cluster (2026-10-05)."""
    docs = [d for d in yaml.safe_load_all((K8S / "generated/envs/prod/observability/routes.yaml").read_text()) if d]
    route = next(d for d in docs if d["kind"] == "HTTPRoute")
    assert any(h.startswith("grafana.") for h in route["spec"]["hostnames"])
    assert route["spec"]["rules"][0]["backendRefs"][0] == {"name": "grafana", "port": 3000}


def test_uptime_kuma_k8s_plan_replaces_docker_monitors():
    """Docker Container monitors need the Docker socket, so on Kubernetes all of
    them were down (2026-10-05). The plan is public-URL checks plus TCP checks
    on databases and caches, disabled for services that aren't running."""
    import sys as _sys
    _sys.path.insert(0, str(REPO / "services" / "uptime-kuma"))
    import k8s_monitors
    plan = k8s_monitors.plan("prod", run={"vaultwarden", "nextcloud", "nextcloud-db", "shared-postgres"})
    by_name = {m["name"]: m for m in plan}
    assert len(by_name) == len(plan)  # unique: the script skips existing names
    assert by_name["vaultwarden.prajnatech.in"] == {
        "name": "vaultwarden.prajnatech.in", "kind": "http", "url": "https://vaultwarden.prajnatech.in/",
        "active": True, "service": "vaultwarden"}
    assert by_name["nextcloud-db (tcp)"]["hostname"] == "nextcloud-db-rw" and by_name["nextcloud-db (tcp)"]["port"] == 5432
    assert by_name["shared-mariadb (tcp)"]["port"] == 3306
    assert by_name["nextcloud-redis (tcp)"]["port"] == 6379
    assert not by_name["authentik.prajnatech.in"]["active"]  # not in `run`: created disabled


def test_argocd_admin_password_is_applied_from_a_hash_and_never_logged(monkeypatch, capsys):
    """bootstrap sets argocd-secret's admin.password from the bcrypt hash in
    kubernetes/.env (ArgoCD's documented method), so the password survives a
    rebuild; the hash must not appear in the command echo, and a value that
    isn't a bcrypt hash is refused rather than locking the owner out."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cluster_pw", K8S / "cluster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    h = "$2a$10$" + "a" * 53
    calls = []
    monkeypatch.setattr(mod, "cfg", lambda: {"K8S_CLUSTER_NAME": "x", mod.ARGOCD_HASH_KEY: h})
    monkeypatch.setattr(mod, "run", lambda cmd, input=None, check=True: calls.append(cmd))
    assert mod.apply_argocd_password() is True
    patch = next(c for c in calls if "patch" in c)
    assert patch[patch.index("secret") + 1] == "argocd-secret"
    assert json.loads(patch[patch.index("-p") + 1])["stringData"]["admin.password"] == h
    assert any("argocd-initial-admin-secret" in c for c in calls)
    monkeypatch.setattr(mod, "cfg", lambda: {"K8S_CLUSTER_NAME": "x", mod.ARGOCD_HASH_KEY: "hunter2"})
    with pytest.raises(SystemExit):
        mod.apply_argocd_password()
    monkeypatch.setattr(mod, "cfg", lambda: {"K8S_CLUSTER_NAME": "x"})
    assert mod.apply_argocd_password() is False


def test_argocd_apps_retry_forever_and_plain_routes_skip_server_side_apply():
    """With `retry.limit: 10`, apps that raced a late CRD gave up for good on a
    fresh cluster (2026-10-05). `limit < 0` is ArgoCD's unlimited. ops-routes is
    plain HTTPRoutes: under ServerSideApply the defaults the API server adds show
    as permanent drift, so it applies client-side."""
    docs = [d for d in yaml.safe_load_all((K8S / "generated/gitops/prod/applications.yaml").read_text()) if d]
    apps = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Application"}
    for name, app in apps.items():
        retry = (app["spec"].get("syncPolicy") or {}).get("retry")
        assert retry is None or retry["limit"] < 0, name
    assert "ServerSideApply=true" not in apps["ops-routes"]["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in apps["cloudnative-pg"]["spec"]["syncPolicy"]["syncOptions"]


def _fake_cluster(over=None):
    """A healthy minimal cluster, for cluster.py verify."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ready = {"conditions": [{"type": "Ready", "status": "True"}]}
    data = {
        ("nodes",): [{"metadata": {"name": "n"}, "status": ready}],
        ("pods", "-A"): [{"metadata": {"namespace": "apps", "name": "p"}, "status": {"phase": "Running", **ready}}],
        ("applications.argoproj.io", "-n", "argocd"): [
            {"metadata": {"name": "docs"}, "status": {"sync": {"status": "Synced"}, "health": {"status": "Healthy"}}},
            {"metadata": {"name": "mealie"}, "status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Missing"}}}],
        ("clusters.postgresql.cnpg.io", "-A"): [{"metadata": {"name": "db"}, "spec": {"instances": 1},
                                                 "status": {"phase": "Cluster in healthy state", "readyInstances": 1}}],
        ("mariadbs.k8s.mariadb.com", "-A"): [{"metadata": {"name": "m"}, "status": ready}],
        ("backupstoragelocations.velero.io", "-n", "velero"): [{"metadata": {"name": "default"}, "status": {"phase": "Available"}}],
        ("backups.velero.io", "-n", "velero"): [{"metadata": {"name": "b"}, "status": {"phase": "Completed", "completionTimestamp": now}}],
        ("backups.postgresql.cnpg.io", "-A"): [{"metadata": {"name": "x"}, "spec": {"cluster": {"name": "db"}},
                                                "status": {"phase": "completed", "stoppedAt": now}}],
        ("deployments", "-n", "apps"): [{"metadata": {"name": "cloudflared"}, "status": {"readyReplicas": 1}}],
    }
    data.update(over or {})
    return lambda *args: data.get(args, [])


def test_verify_passes_a_healthy_cluster_and_catches_real_failures():
    """cluster.py verify: the checks the 2026-10-04/05 rebuilds were done by hand."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    import verify
    run, ported = {"docs", "cloudflared"}, {"docs", "mealie", "cloudflared"}  # mealie is stopped on purpose
    ok = lambda url: 200  # noqa: E731

    def check(kg, http=ok, tunnel=lambda: True):
        return {n: (good, d) for n, good, d in verify.verify_checks(run, ported, kg, http, tunnel, ["https://docs.x/"])}

    healthy = check(_fake_cluster())
    assert all(good for good, _ in healthy.values()), healthy  # a stopped service's OutOfSync app is not a failure

    pod = {"metadata": {"namespace": "apps", "name": "bad"}, "status": {"phase": "Running", "conditions": []}}
    assert not check(_fake_cluster({("pods", "-A"): [pod]}))["pods running and ready"][0]
    stale = {"metadata": {"name": "old"}, "status": {"phase": "Completed", "completionTimestamp": "2020-01-01T00:00:00Z"}}
    assert not check(_fake_cluster({("backups.velero.io", "-n", "velero"): [stale]}))["Velero backup recent and clean"][0]
    assert not check(_fake_cluster({("backups.postgresql.cnpg.io", "-A"): []}))["Postgres base backups recent"][0]
    assert not check(_fake_cluster(), tunnel=lambda: False)["tunnel connected to Cloudflare"][0]
    assert not check(_fake_cluster(), http=lambda u: 530)["public hostnames answer (from this machine)"][0]
    sick = {"metadata": {"name": "docs"}, "status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Healthy"}}}
    assert not check(_fake_cluster({("applications.argoproj.io", "-n", "argocd"): [sick]}))["ArgoCD apps synced and healthy"][0]


def test_verify_host_checks_ignore_sata_ports_without_a_disk(tmp_path):
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    import verify
    for host, policy, disk in (("host0", "max_performance", True), ("host4", "keep_firmware_settings", False)):
        d = tmp_path / "sys/class/scsi_host" / host
        (d / "device").mkdir(parents=True)
        (d / "link_power_management_policy").write_text(policy + "\n")
        if disk:
            (d / "device" / "target0:0:0").mkdir()
    ok, detail = verify.host_checks(tmp_path)["SATA link power = max_performance"]
    assert ok and detail == "max_performance"
    (tmp_path / "sys/class/scsi_host/host0/link_power_management_policy").write_text("med_power_with_dipm\n")
    assert not verify.host_checks(tmp_path)["SATA link power = max_performance"][0]


def test_unpausing_a_service_refreshes_its_argocd_app_at_once(monkeypatch):
    """After export/import scaled a service to 0, ArgoCD took minutes to notice
    and bring it back (2026-10-05). Unpausing now asks for a hard refresh."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cluster_unpause", K8S / "cluster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "cfg", lambda: {"K8S_CLUSTER_NAME": "x"})
    calls = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0})())
    mod.argo_pause("beszel", True)
    assert not any("argocd.argoproj.io/refresh=hard" in c for c in calls)
    calls.clear()
    mod.argo_pause("beszel", False)
    assert any("argocd.argoproj.io/refresh=hard" in c for c in calls)


def test_restore_plan_orders_the_steps_and_never_deletes_a_database_volume():
    """cluster.py restore: Velero skips what still exists, so workloads and the
    claim are deleted first; the old folder is moved aside, never deleted; ArgoCD
    is paused for the duration and resumed after; no --yes means a dry run."""
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    import restore
    vols = [{"pvc": "beszel-data", "pv": "pvc-1", "node_path": "/var/k8s/fast/apps/beszel-data"}]
    steps = restore.plan("beszel", "velero-apps-nightly-X", vols, "T")
    acts = [s.action for s in steps]
    assert acts.index("pause") < acts.index("kubectl") < acts.index("node_mv") < acts.index("velero_restore") \
        < acts.index("wait_restore") < acts.index("unpause") < acts.index("wait_ready")
    deleted = [s.args for s in steps if s.action == "kubectl"]
    assert ("-n", "apps", "delete", "pvc", "beszel-data", "--wait=true") in deleted
    # Only the listed volume is deleted: one claim, one volume, plus the workloads. Never a database volume.
    assert {a[4] for a in deleted if "pvc" in a} == {"beszel-data"}
    assert {a[2] for a in deleted if a[:2] == ("delete", "pv")} == {"pvc-1"}
    mv = next(s for s in steps if s.action == "node_mv")
    assert mv.args == ("/var/k8s/fast/apps/beszel-data", "/var/k8s/fast/restore-aside/beszel-data.T")  # moved, not removed
    assert not any("rm " in " ".join(map(str, s.args)) for s in steps)
    man = restore.restore_manifest("beszel", "velero-apps-nightly-X", "T")
    assert man["spec"]["labelSelector"] == {"matchLabels": {"homeserver/service": "beszel"}}
    assert man["spec"]["backupName"] == "velero-apps-nightly-X" and man["metadata"]["name"] == "restore-beszel-T"
    assert "Dry run: nothing was changed" in restore.render("beszel", "b", steps, yes=False)
    assert "Dry run" not in restore.render("beszel", "b", steps, yes=True)


def test_restore_command_is_registered_and_refuses_more_than_one_service():
    import sys as _sys
    _sys.path.insert(0, str(K8S))
    spec = importlib.util.spec_from_file_location("k8s_cluster_restore", K8S / "cluster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.cmd_restore) and callable(mod.cmd_verify) and callable(mod.cmd_argocd_password)
    with pytest.raises(SystemExit):
        mod.cmd_restore(type("A", (), {"services": ["beszel", "docs"], "backup": None, "yes": False, "env": "prod"})())
