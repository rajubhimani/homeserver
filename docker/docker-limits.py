#!/usr/bin/env python3
"""docker-limits.py — cap Docker's total CPU/memory/disk usage, on whichever
platform this actually runs on.

Usage:
  python docker-limits.py check                    show what would be applied, don't touch anything
  python docker-limits.py apply [--yes]             apply CPU + memory + log rotation (restarts Docker)
  python docker-limits.py disk-quota [--yes]        apply the disk cap (separate — more disruptive on Linux)
  python docker-limits.py relocate-data-root [--yes]  move Docker's data-root to DOCKER_DATA_ROOT (separate — a full data copy)
  python docker-limits.py status                    show current applied state

relocate-data-root and disk-quota are independent and composable: relocate
moves WHERE Docker's data lives (e.g. off the OS drive onto a bigger secondary
disk), disk-quota caps HOW MUCH space it's allowed to use wherever it ends up.
Every command re-detects the data-root live via `docker info`, so running
relocate-data-root first means disk-quota (and everything else here)
automatically targets the new location — no other config to change.

This is a whole-host, all-containers knob — not specific to any one service.
Forgejo's CI storage is isolated by its own dedicated mechanism instead (a
Docker-in-Docker sidecar, see docs/services/forgejo.md); relocate-data-root
here is for when you want to move Docker's storage for everything running on
this host, which is a separate decision entirely up to you.

Config comes from docker/.env (copy docker/.env.example, same convention
as every other .env in this repo — and the same filename, so the repo's
existing .gitignore rule covers it automatically) — one config surface
regardless of platform. See docker/README.md for what each platform
actually does with these values, and why CPU/memory/log-rotation and disk
are separate steps.

Platform dispatch: Windows -> setup_windows (Docker Desktop). Linux -> the
distro's own setup_<name> module if it matches a known one (Fedora,
Ubuntu), otherwise picked by *actual filesystem* of the Docker data-root —
setup_ubuntu's loopback-image disk cap works on any filesystem, so it's the
universal fallback; setup_fedora's btrfs-qgroup cap only applies when the
data-root genuinely is btrfs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    docker_root_dir,
    error,
    filesystem_type,
    header,
    load_env_file,
    parse_size_to_bytes,
    relocate_data_root,
    warn,
)

HERE = Path(__file__).resolve().parent


def load_config() -> dict[str, str]:
    env_path = HERE / ".env"
    if not env_path.is_file():
        error(f"{env_path} not found — copy docker/.env.example to docker/.env and fill in real values.")
        sys.exit(1)
    raw = load_env_file(env_path)

    cfg = dict(raw)
    cfg.setdefault("DOCKER_CPU_CORES", "8")
    cfg.setdefault("DOCKER_MEMORY_LIMIT", "10G")
    cfg.setdefault("DOCKER_DISK_LIMIT", "50G")
    cfg.setdefault("DOCKER_DATA_ROOT", "")
    cfg.setdefault("DOCKER_LOG_MAX_SIZE", "10m")
    cfg.setdefault("DOCKER_LOG_MAX_FILE", "3")

    if not cfg.get("DOCKER_MEMORY_HIGH"):
        high_bytes = int(parse_size_to_bytes(cfg["DOCKER_MEMORY_LIMIT"]) * 0.9)
        cfg["DOCKER_MEMORY_HIGH"] = f"{high_bytes // (1024**2)}M"

    cfg["_cpu_quota_pct"] = str(int(cfg["DOCKER_CPU_CORES"]) * 100)
    cfg["_memory_high"] = cfg["DOCKER_MEMORY_HIGH"]
    return cfg


def detect_platform() -> str:
    if sys.platform == "win32":
        return "windows"

    os_release = Path("/etc/os-release")
    distro_id = ""
    if os_release.is_file():
        for line in os_release.read_text().splitlines():
            if line.startswith("ID="):
                distro_id = line.partition("=")[2].strip().strip('"')
                break

    if distro_id == "fedora":
        return "fedora"
    if distro_id == "ubuntu":
        return "ubuntu"

    # Unknown distro — pick by actual filesystem rather than guessing from
    # distro name, since either module can genuinely run anywhere: the
    # loopback approach (setup_ubuntu) works on any filesystem, the qgroup
    # approach (setup_fedora) only on btrfs.
    fstype = filesystem_type(docker_root_dir())
    if fstype == "btrfs":
        warn(f"Distro ID '{distro_id or 'unknown'}' isn't fedora/ubuntu, but docker root is btrfs — using the btrfs (setup_fedora) mechanism.")
        return "fedora"
    warn(f"Distro ID '{distro_id or 'unknown'}' isn't fedora/ubuntu, filesystem is '{fstype}' — using the universal loopback (setup_ubuntu) mechanism.")
    return "ubuntu"


def load_module(platform: str):
    if platform == "fedora":
        import setup_fedora as mod
    elif platform == "ubuntu":
        import setup_ubuntu as mod
    elif platform == "windows":
        import setup_windows as mod
    else:
        raise ValueError(f"Unknown platform: {platform}")
    return mod


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] not in ("check", "apply", "disk-quota", "relocate-data-root", "status"):
        print(__doc__)
        return 1

    action = argv[0]
    assume_yes = "--yes" in argv or "-y" in argv

    cfg = load_config()
    platform = detect_platform()
    mod = load_module(platform)

    header(f"docker-limits.py — {action} (platform: {platform})")

    if action == "check":
        mod.describe(cfg)
        return 0
    if action == "apply":
        return mod.apply(cfg, assume_yes)
    if action == "disk-quota":
        return mod.apply_disk_quota(cfg, assume_yes)
    if action == "relocate-data-root":
        if platform == "windows":
            error("Docker Desktop on Windows keeps its data-root under its own setting, not daemon.json.")
            error("Move it via Docker Desktop -> Settings -> Resources -> Advanced -> 'Disk image location'.")
            return 1
        return relocate_data_root(cfg, assume_yes)
    if action == "status":
        mod.status(cfg)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
