"""setup_windows.py — Docker resource limits for Docker Desktop on Windows.

Completely different mechanism from the Linux modules: there's no systemd,
no real cgroups accessible this way, and disk is the WSL2 VHDX (already
covered by homeserver.py's own `gc` command — see docs/08-maintenance.md's
"Reclaiming disk space" section, not duplicated here).

Docker Desktop stores its own settings (including the Resources tab's
CPU/memory/disk sliders) in a JSON file under %APPDATA%\\Docker\\ — the
exact filename and key names have changed across Docker Desktop versions
(settings.json historically, settings-store.json in newer releases), and
aren't guaranteed stable. Rather than guessing key names and silently
writing new ones, this reads whatever's actually there, prints every
CPU/memory/disk-shaped key it finds, and only ever modifies keys that
already exist — refuses to blind-create ones it can't confirm.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from _common import confirm, error, info, parse_size_to_bytes, success, warn

CANDIDATE_FILENAMES = ["settings-store.json", "settings.json"]

# Case-insensitive substrings that flag a key as CPU/memory/disk-related —
# not exact names, since these have drifted across Docker Desktop versions.
CPU_HINTS = ["cpu"]
MEMORY_HINTS = ["memorymib", "memory"]
DISK_HINTS = ["disksizemib", "disksize"]


def _settings_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    for name in CANDIDATE_FILENAMES:
        p = Path(appdata) / "Docker" / name
        if p.is_file():
            return p
    return None


def _find_keys(data: dict, hints: list[str]) -> list[str]:
    return [k for k in data if any(h in k.lower() for h in hints)]


def describe(cfg: dict[str, str]) -> None:
    path = _settings_path()
    if not path:
        error("Couldn't find Docker Desktop's settings file under %APPDATA%\\Docker\\")
        error(f"Looked for: {', '.join(CANDIDATE_FILENAMES)}")
        return
    info(f"Found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        error(f"{path} exists but isn't valid JSON")
        return

    cpu_keys = _find_keys(data, CPU_HINTS)
    mem_keys = _find_keys(data, MEMORY_HINTS)
    disk_keys = _find_keys(data, DISK_HINTS)

    info(f"CPU-shaped keys found: {cpu_keys or '(none)'}")
    info(f"Memory-shaped keys found: {mem_keys or '(none)'}")
    info(f"Disk-shaped keys found: {disk_keys or '(none)'}")
    if not (cpu_keys or mem_keys or disk_keys):
        warn("No recognizable keys found — this Docker Desktop version may use different")
        warn("field names than this script expects. Set limits manually via Docker Desktop's")
        warn("own Settings -> Resources -> Advanced UI instead.")
        return
    print()
    for k in cpu_keys:
        print(f"  {k}: {data[k]}  -> would become {cfg['DOCKER_CPU_CORES']}")
    for k in mem_keys:
        target_mib = parse_size_to_bytes(cfg["DOCKER_MEMORY_LIMIT"]) // (1024 * 1024)
        print(f"  {k}: {data[k]}  -> would become {target_mib}")
    for k in disk_keys:
        target_mib = parse_size_to_bytes(cfg["DOCKER_DISK_LIMIT"]) // (1024 * 1024)
        print(f"  {k}: {data[k]}  -> would become {target_mib}")


def apply(cfg: dict[str, str], assume_yes: bool) -> int:
    path = _settings_path()
    if not path:
        error("Couldn't find Docker Desktop's settings file under %APPDATA%\\Docker\\")
        error(f"Looked for: {', '.join(CANDIDATE_FILENAMES)}")
        error("Set limits manually via Docker Desktop's own Settings -> Resources -> Advanced instead.")
        return 1

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        error(f"{path} exists but isn't valid JSON — not touching it.")
        return 1

    cpu_keys = _find_keys(data, CPU_HINTS)
    mem_keys = _find_keys(data, MEMORY_HINTS)
    disk_keys = _find_keys(data, DISK_HINTS)

    if not (cpu_keys or mem_keys or disk_keys):
        error("No recognizable CPU/memory/disk keys found in this file — refusing to guess.")
        error("Set limits manually via Docker Desktop's own Settings -> Resources -> Advanced instead.")
        return 1

    info(f"Found in {path}:")
    for k in cpu_keys + mem_keys + disk_keys:
        info(f"  {k} = {data[k]}")
    warn("About to overwrite the keys above and restart Docker Desktop.")
    if not confirm("Proceed?", assume_yes):
        info("Cancelled")
        return 1

    backup = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    info(f"Backed up original to {backup}")

    for k in cpu_keys:
        data[k] = int(cfg["DOCKER_CPU_CORES"])
    for k in mem_keys:
        data[k] = parse_size_to_bytes(cfg["DOCKER_MEMORY_LIMIT"]) // (1024 * 1024)
    for k in disk_keys:
        data[k] = parse_size_to_bytes(cfg["DOCKER_DISK_LIMIT"]) // (1024 * 1024)

    path.write_text(json.dumps(data, indent=2))
    success(f"Wrote {path}")
    warn("Fully quit Docker Desktop (system tray icon -> Quit Docker Desktop) and relaunch it")
    warn("for these to take effect — a container restart alone won't reload this file.")
    return 0


def apply_disk_quota(cfg: dict[str, str], assume_yes: bool) -> int:
    info("Disk is handled by the same settings file as CPU/memory here — run `apply`, not a separate step.")
    info("For reclaiming space already used (not capping future use), see: uv run homeserver.py gc")
    return 0


def status(cfg: dict[str, str]) -> None:
    describe(cfg)
