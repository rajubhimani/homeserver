"""homeserver.py waits as long as each container's own healthcheck allows, not
a fixed 180s: Docker only calls a container unhealthy after start_period plus
retries rounds of interval+timeout, so first boots that run long migrations
(Grafana ~5.5 min) must not be reported as failures."""

from __future__ import annotations

import homeserver as hs


def test_deadline_follows_the_containers_healthcheck(fake):
    fake.healthchecks["grafana"] = {"interval": 60, "timeout": 5, "start_period": 600, "retries": 5}
    assert hs.health_deadline("grafana") == 600 + 5 * (60 + 5) + 30


def test_deadline_never_drops_below_the_default(fake):
    fake.healthchecks["tiny"] = {"interval": 5, "timeout": 2, "start_period": 0, "retries": 3}
    assert hs.health_deadline("tiny") == hs.HEALTH_TIMEOUT


def test_no_healthcheck_uses_the_default(fake):
    assert hs.health_deadline("nothing") == hs.HEALTH_TIMEOUT


def test_slow_first_boot_is_waited_out_not_reported_as_failure(fake, monkeypatch):
    """A container that stays 'starting' for 5 minutes then turns healthy:
    the old fixed 180s wait reported failure; now it succeeds."""
    fake.healthchecks["slowapp"] = {"interval": 60, "timeout": 5, "start_period": 600, "retries": 5}
    fake.running.add("slowapp")
    clock = {"t": 0}
    monkeypatch.setattr(hs.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(fake, "container_health", lambda n: "healthy" if clock["t"] >= 300 else "starting")
    assert hs.wait_healthy("slowapp") is True
