"""Shared Valkey for services that declare "shared_cache": an ACL login per
service limited to its own key prefix, started on demand and never stopped
automatically. See docs/services/valkey.md."""

from __future__ import annotations

import pytest

import homeserver as hs

CACHE = hs.SHARED_CACHE_SERVICE
SPEC = {"user": "=app_user", "password": "=app_pw_123", "prefix": "=app:"}


@pytest.fixture
def app(monkeypatch):
    """A real above-CORE service with a shared_cache spec added."""
    entry = dict(hs._SERVICES_BY_SLUG["miniflux"])
    entry["shared_cache"] = dict(SPEC)
    monkeypatch.setitem(hs._SERVICES_BY_SLUG, "miniflux", entry)
    monkeypatch.setattr(hs, "shared_cache_external", lambda s: None)
    return "miniflux"


def cache_input(fake):
    return "\n".join(x["input"] for x in fake.exec_calls if x["container"] == CACHE)


def test_valkey_is_a_normal_extra_service_not_a_shared_tier():
    assert hs._SERVICES_BY_SLUG[CACHE]["tier"] == "extra"
    assert CACHE in hs.SERVICES_EXTRA


def test_creds_resolve_literals_and_env_keys(app):
    assert hs.shared_cache_creds(app) == {"user": "app_user", "password": "app_pw_123", "prefix": "app:"}


def test_no_spec_means_no_shared_cache():
    assert hs.shared_cache_creds("outline") is None


def test_up_starts_valkey_then_provisions_a_prefix_limited_login(fake, cli, app):
    cli("prod", "up", app)
    order = [e[1] for e in fake.events if e[0] == "up"]
    assert order.index(CACHE) < order.index(app)
    sql = cache_input(fake)
    assert "ACL SETUSER app_user reset on >app_pw_123 ~app:* &app:*" in sql, "login must be limited to its own prefix"
    assert "-@dangerous" in sql and "-@admin" in sql, "no FLUSHALL/CONFIG/KEYS for app logins"
    assert "ACL SAVE" in sql, "login must survive a Valkey restart"


def test_down_never_stops_valkey(fake, cli, app):
    cli("prod", "up", app)
    cli("prod", "down", app)
    assert CACHE in fake.running, "valkey is also used by hand, so it is never stopped automatically"


def test_passwords_never_appear_in_exec_argv(fake, cli, app):
    cli("prod", "up", app)
    secrets = {"app_pw_123", hs._cache_admin_password()} - {""}
    for call in fake.exec_calls:
        for s in secrets:
            assert not any(s in a for a in call["cmd"]), f"password leaked into argv: {call['cmd']}"


def test_provisioning_is_idempotent_and_rotates_the_password(fake, cli, app):
    cli("prod", "up", app)
    cli("prod", "down", app)
    cli("prod", "up", app)
    assert cache_input(fake).count("ACL SETUSER app_user reset on >app_pw_123") == 2


def test_default_login_and_unsafe_names_are_refused(fake, monkeypatch, app):
    for bad in ({"user": "=default"}, {"prefix": "=a b:"}, {"password": "=pw with space"}, {"prefix": "=*"}, {"prefix": "=app"}):
        entry = dict(hs._SERVICES_BY_SLUG[app])
        entry["shared_cache"] = {**SPEC, **bad}
        monkeypatch.setitem(hs._SERVICES_BY_SLUG, app, entry)
        fake.exec_calls.clear()
        assert hs.provision_shared_cache(app) is False
        assert not fake.exec_calls, f"nothing may run for {bad}"


def test_outside_cache_host_skips_the_shared_server(fake, monkeypatch, app):
    monkeypatch.setattr(hs, "shared_cache_external", lambda s: "my-cache.example.com")
    assert hs.shared_cache_creds(app) is None
    assert hs.shared_cache_ready(app, "prod") is True
    assert not fake.exec_calls and CACHE not in fake.running


def test_drop_removes_keys_then_login(fake, app):
    fake.running.add(CACHE)
    assert hs.drop_shared_cache(app) is True
    assert "ACL DELUSER app_user" in cache_input(fake)
