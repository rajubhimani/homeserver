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
                assert gen_images[key] == s["image"].replace("$$", "$"), f"{key}: {gen_images[key]} != compose {s['image']}"


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
