"""`homeserver.py archive <dir>`: one verified file holding everything a fresh
clone can't recreate — git-ignored files (.env secrets...), service_data minus
cache, and meta (README, MANIFEST, git bundle). Host tools (git, tar) are
replaced here; the real ones are exercised by the live run."""

from __future__ import annotations

import homeserver as hs


def setup_archive(fake, monkeypatch, tmp_path, verify=(True, "homeserver, meta, service_data"), free=10**12):
    dest = tmp_path / "passport"
    dest.mkdir()
    monkeypatch.setattr(hs, "archive_ignored_paths", lambda: [".env", "services/n8n/.env", "CLAUDE.md"])
    monkeypatch.setattr(hs, "archive_meta", lambda d, running: (d / "README.txt").write_text("x"))
    monkeypatch.setattr(hs, "archive_verify", lambda a: verify)
    monkeypatch.setattr(hs, "tree_size", lambda p: 0 if p.name == "cache" else 1000)
    monkeypatch.setattr(hs.shutil, "disk_usage", lambda p: type("U", (), {"free": free})())
    return dest


def test_archive_packs_ignored_files_service_data_and_meta(fake, cli, monkeypatch, tmp_path):
    dest = setup_archive(fake, monkeypatch, tmp_path)
    monkeypatch.setattr(hs.sys, "argv", ["homeserver.py", "archive", str(dest)])
    assert hs.main() == 0
    ev = next(e for e in fake.events if e[0] == "archive")
    _, mounts, members, excludes = ev
    assert set(mounts) == {"homeserver", "service_data", "meta"}
    assert "homeserver/.env" in members and "homeserver/services/n8n/.env" in members
    assert "service_data" in members and "meta" in members
    assert "service_data/cache" in excludes, "cache is regenerable and must be left out"
    archives = list(dest.glob("homeserver-archive-*.tar.gz"))
    assert len(archives) == 1
    sha = dest / f"{archives[0].name}.sha256"
    assert sha.read_text().split()[0] == hs.file_sha256(archives[0])


def test_archive_refuses_when_verification_fails(fake, cli, monkeypatch, tmp_path):
    dest = setup_archive(fake, monkeypatch, tmp_path, verify=(False, "homeserver"))
    monkeypatch.setattr(hs.sys, "argv", ["homeserver.py", "archive", str(dest)])
    assert hs.main() == 1
    assert not list(dest.glob("*.sha256")), "no checksum for an archive that didn't verify"


def test_archive_refuses_without_enough_space(fake, cli, monkeypatch, tmp_path):
    dest = setup_archive(fake, monkeypatch, tmp_path, free=10)
    monkeypatch.setattr(hs.sys, "argv", ["homeserver.py", "archive", str(dest)])
    assert hs.main() == 1
    assert not [e for e in fake.events if e[0] == "archive"]


def test_archive_refuses_a_missing_destination(fake, cli, monkeypatch, tmp_path):
    monkeypatch.setattr(hs.sys, "argv", ["homeserver.py", "archive", str(tmp_path / "not-mounted")])
    assert hs.main() == 1


def test_ignored_paths_drop_regenerable_and_duplicates(monkeypatch):
    out = "\n".join([".env", ".venv/", "__pycache__/", "service_data", "services/photoprism/",
                      "services/photoprism/.env", "tests/__pycache__/", "CLAUDE.md", ""])
    monkeypatch.setattr(hs.subprocess, "run", lambda *a, **k: type("P", (), {"stdout": out})())
    assert hs.archive_ignored_paths() == [".env", "CLAUDE.md", "services/photoprism"]
