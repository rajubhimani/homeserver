"""Shared fixtures for the homeserver.py test suite.

Every behaviour test runs the *real* homeserver.py code paths (do_up, do_down,
backup_service, do_restore, main(), ...) against FakeBackend, an in-memory
implementation of the real DockerBackend ABC. Nothing ever reaches Docker:
subprocess.run is replaced with a function that fails the test, so a code path
that bypasses BACKEND (forbidden by the homeserver-docker-backend skill) is
caught here instead of touching the live stack.

FakeBackend subclasses DockerBackend, so adding an abstract method to the ABC
without teaching the fake about it makes every test error out — the interface
and its test double can't drift apart.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import homeserver as hs  # noqa: E402


class FakeBackend(hs.DockerBackend):
    """In-memory Docker. A service's compose project starts as one container
    named after the service (enough for get_running_services' ^slug(-|$)
    match), and databases on the shared servers are tracked per engine so
    provisioning/existence checks behave like the real thing."""

    def __init__(self) -> None:
        self.running: set[str] = set()
        self.created: set[str] = set()
        self.volumes: set[str] = set()
        self.dbs: dict[str, set[str]] = {"shared-postgres": set(), "shared-mariadb": set()}
        self.events: list[tuple] = []  # ordered log of lifecycle/db operations
        self.exec_calls: list[dict] = []

    @staticmethod
    def _project(files: list[Path]) -> str:
        return Path(files[0]).parent.name

    # ── compose ──
    def compose_up(self, files, env, profile, force_recreate=False, exclude=None, only=None):
        svc = self._project(files)
        names = list(only) if only else [svc]
        for n in names:
            self.running.add(n)
            self.created.add(n)
        self.events.append(("up", svc))
        return True, ""

    def compose_create(self, files, env, profile, force_recreate=False):
        self.created.add(self._project(files))
        return True, ""

    def compose_down(self, files, env, profile):
        svc = self._project(files)
        self.running = {n for n in self.running if not re.match(rf"^{re.escape(svc)}(-|$)", n)}
        self.events.append(("down", svc))
        return True

    def compose_pull(self, files, env):
        return True

    def compose_logs_follow(self, files, env):
        return None

    # ── containers ──
    def running_container_names(self):
        return sorted(self.running)

    def all_container_names(self):
        return sorted(self.running | self.created)

    def container_status(self, name):
        if name in self.running:
            return "running"
        return "exited" if name in self.created else None

    def container_health(self, name):
        return "healthy" if name in self.running else "none"

    healthchecks: dict = {}

    def container_healthcheck(self, name):
        return self.healthchecks.get(name, {})

    def container_info(self, name):
        return {}

    # ── volumes / network ──
    def volumes_for_project(self, project):
        return sorted(v for v in self.volumes if v.startswith(f"{project}_"))

    def volume_exists(self, name):
        return name in self.volumes

    def volume_create(self, name):
        self.volumes.add(name)

    def volume_remove(self, name):
        self.volumes.discard(name)
        self.events.append(("volume_remove", name))
        return True

    def network_exists(self, name):
        return True

    def network_create(self, name):
        return None

    # ── tar ──
    def tar_volume_to(self, volume, dest_dir, archive_name):
        (Path(dest_dir) / archive_name).write_bytes(b"tar")
        return True

    def tar_dir_to(self, host_dir, dest_dir, archive_name):
        (Path(dest_dir) / archive_name).write_bytes(b"tar")
        return True

    def untar_into_volume(self, volume, archive_path):
        self.events.append(("untar_volume", volume))
        return True

    def untar_into_dir(self, archive_path, dest_dir):
        self.events.append(("untar_dir", str(dest_dir)))
        return True

    def remove_dir(self, host_dir):
        import shutil
        shutil.rmtree(host_dir, ignore_errors=True)
        self.events.append(("remove_dir", str(host_dir)))
        return not Path(host_dir).exists()

    def system_prune(self):
        return True, ""

    def builder_prune(self):
        return True, ""

    # ── databases ──
    def db_pg_dump(self, container, user, db):
        self.events.append(("pg_dump", container, db))
        return True, f"PGDUMP {db}".encode(), ""

    def db_pg_restore(self, container, user, db, dump):
        return True, ""

    def db_pg_dumpall_roles(self, container, user):
        return True, b"", ""

    def db_psql_apply(self, container, user, db, sql):
        return True, ""

    def db_exec(self, container, cmd, input=None, env=None):
        sql = (input or b"").decode(errors="replace")
        self.exec_calls.append({"container": container, "cmd": list(cmd), "input": sql, "env": dict(env or {})})
        dbs = self.dbs.setdefault(container, set())

        m = re.search(r"SELECT 1 FROM pg_database WHERE datname = '([^']*)'", sql) or re.search(
            r"SHOW DATABASES LIKE '([^']*)'", sql
        )
        if m:
            return True, (b"1\n" if m.group(1) in dbs else b""), ""
        for m in re.finditer(r'CREATE DATABASE (?:IF NOT EXISTS )?["`]([^"`]+)["`]', sql):
            dbs.add(m.group(1))
            self.events.append(("create_db", container, m.group(1)))
        for m in re.finditer(r'DROP DATABASE IF EXISTS ["`]([^"`]+)["`]', sql):
            dbs.discard(m.group(1))
            self.events.append(("drop_db", container, m.group(1)))
        if cmd and cmd[0] == "pg_restore":
            self.events.append(("pg_restore", container, cmd))
        if cmd and cmd[0] == "mariadb-dump":
            self.events.append(("mariadb_dump", container, cmd[-1]))
            return True, f"SQLDUMP {cmd[-1]}".encode(), ""
        return True, b"", ""


def _no_subprocess(*args, **kwargs):
    raise AssertionError(f"test tried to run a real process: {args[0] if args else kwargs}")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Patch homeserver.py onto FakeBackend with snapshots/dumps/data under
    tmp_path. Reads each service's .env.example in place of .env, so results
    don't depend on this machine's secrets and match a fresh clone."""
    backend = FakeBackend()
    monkeypatch.setattr(hs, "BACKEND", backend)
    monkeypatch.setattr(hs, "SERVICE_DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(hs, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(hs, "DB_DUMP_ROOT", tmp_path / "db_dump")
    monkeypatch.setattr(hs, "ensure_wg_tunnel_ready", lambda service, env: None)
    monkeypatch.setattr(hs, "check_data_mounts", lambda service: True)
    monkeypatch.setattr(hs.time, "sleep", lambda s: None)
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(hs.subprocess, "run", _no_subprocess)

    real_load = hs.load_env_file

    def load_example(path: Path) -> dict[str, str]:
        path = Path(path)
        if path.name == ".env" and path.parent != hs.BASE_DIR:
            return real_load(path.with_name(".env.example"))
        return real_load(path)

    monkeypatch.setattr(hs, "load_env_file", load_example)
    return backend


@pytest.fixture
def cli(fake, monkeypatch):
    """Run homeserver.py's main() with argv, e.g. cli("prod", "up", "miniflux").
    Returns main()'s exit code. Confirmation prompts are auto-accepted (stdin
    is never a TTY under pytest, same as confirm_expansion's own rule)."""

    def run(*argv: str) -> int:
        monkeypatch.setattr(sys, "argv", ["homeserver.py", *argv])
        return hs.main()

    return run


def shared_db_users(engine: str) -> list[str]:
    return [s["slug"] for s in hs._SERVICES_DATA["services"] if (s.get("shared_db") or {}).get("engine") == engine]
