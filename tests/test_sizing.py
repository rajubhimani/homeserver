"""HOMESERVER_USERS sizing: compose.yml memory limits are the household size
(SIZING_BASELINE_USERS); above it, services.json "per_user_memory" rates raise
them through a throwaway override (homeserver._sizing_override)."""

from __future__ import annotations

import json

import pytest
import yaml

import homeserver as hs
from conftest import each

SERVICES = json.loads((hs.BASE_DIR / "services.json").read_text())["services"]
RATED = [(s["slug"], name, rate) for s in SERVICES for name, rate in (s.get("per_user_memory") or {}).items()]


def _compose_limit(service: str, container: str):
    svc = (yaml.safe_load((hs.SERVICES_DIR / service / hs.base_file(service)).read_text())["services"]).get(container)
    assert svc is not None, f"{container} isn't a service in services/{service}/compose.yml"
    return ((svc.get("deploy") or {}).get("resources") or {}).get("limits", {}).get("memory") or svc.get("mem_limit")


def test_every_container_has_a_memory_limit():
    """Every compose service is capped, so one runaway container gets OOM-killed
    on its own instead of pushing the whole host into the kernel OOM killer."""
    def check(path):
        for name, svc in (yaml.safe_load(path.read_text()).get("services") or {}).items():
            assert _compose_limit(path.parent.name, name), f"{name}: no deploy.resources.limits.memory"
    each(sorted(p for p in hs.SERVICES_DIR.glob("*/compose.yml")), check, ids=lambda p: p.parent.name)


def test_per_user_rates_name_real_capped_containers():
    """A rate scales a compose limit, so its container must exist and have a literal one."""
    def check(service, container, rate):
        assert hs.memory_mib(rate), f"rate {rate!r} isn't a size like '16M'"
        assert hs.memory_mib(_compose_limit(service, container)), "no literal compose memory limit to scale"
    each(RATED, check)


@pytest.mark.parametrize("base,rate,users,want", [
    ("2G", "48M", 5, 2048),          # at the baseline: the compose limit
    ("2G", "48M", 1, 2048),          # below it: never shrinks
    ("2G", "48M", 50, 4224),         # 2048 + 45*48 = 4208 -> next 64 MiB step
    ("768M", "28M", 6, 832),         # 768 + 28 = 796 -> 832
    ("2147483648", "48M", 6, 2112),  # compose config's bytes form
])
def test_scaled_memory(base, rate, users, want):
    assert hs.scaled_memory(base, rate, users) == want


def test_scaled_memory_rejects_unresolved_values():
    assert hs.scaled_memory("${OPEN_TERMINAL_MEMORY_LIMIT}", "16M", 50) is None


def test_no_override_at_household_size(monkeypatch):
    monkeypatch.setattr(hs, "HOMESERVER_USERS", hs.SIZING_BASELINE_USERS)
    assert hs._sizing_override("nextcloud", []) is None


def test_override_raises_only_rated_containers(monkeypatch, tmp_path):
    monkeypatch.setattr(hs, "HOMESERVER_USERS", 50)
    monkeypatch.setattr(hs.tempfile, "gettempdir", lambda: str(tmp_path))
    cfg = {"services": {
        "nextcloud": {"deploy": {"resources": {"limits": {"memory": "2147483648"}}}},
        "nextcloud-redis": {"deploy": {"resources": {"limits": {"memory": "536870912"}}}},
        "nextcloud-cron": {"deploy": {"resources": {"limits": {"memory": "1073741824"}}}},
        "nextcloud-db": {"deploy": {"resources": {"limits": {"memory": "536870912"}}}},
    }}
    monkeypatch.setattr(hs.BACKEND, "compose_config", lambda files, env: cfg)
    monkeypatch.setitem(hs._SERVICES_BY_SLUG, "nextcloud",
                        {**hs._SERVICES_BY_SLUG["nextcloud"], "per_user_memory": {"nextcloud": "48M", "nextcloud-cron": "16M"}})
    path = hs._sizing_override("nextcloud", [])
    limits = {k: v["deploy"]["resources"]["limits"]["memory"] for k, v in yaml.safe_load(path.read_text())["services"].items()}
    assert limits == {"nextcloud": "4224M", "nextcloud-cron": "1792M"}
