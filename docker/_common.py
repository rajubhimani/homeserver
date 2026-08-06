"""_common.py — shared helpers for docker-limits.py and the per-platform
setup_*.py modules. Pure stdlib, same style as homeserver.py (color-coded
print helpers, minimal .env parser) — this folder is meant to be as
self-contained/portable as that script, not dependent on it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SLICE_PATH = "/etc/systemd/system/docker-workloads.slice"
DAEMON_JSON_PATH = "/etc/docker/daemon.json"
SLICE_NAME = "docker-workloads.slice"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"

if sys.platform == "win32":
    import ctypes

    if ctypes.windll.kernel32.SetConsoleOutputCP(65001):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def info(msg: str) -> None:
    print(f"{CYAN}▶ {msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}✔ {msg}{RESET}")


def error(msg: str) -> None:
    print(f"{RED}✖ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠ {msg}{RESET}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}\n")


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        reply = input(f"\n{BOLD}{prompt} [y/N]{RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return reply in ("y", "yes")


def load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser — comments, blank lines, quoted values."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        result[key] = val
    return result


def parse_size_to_bytes(size: str) -> int:
    """'10G' / '512M' / '10m' -> bytes. Docker/systemd both use this shape."""
    size = size.strip()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if size[-1].upper() in units:
        return int(float(size[:-1]) * units[size[-1].upper()])
    return int(size)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with list-form args, never a shell — same reasoning as
    homeserver.py's DockerBackend._run: no shell means no quoting/escaping
    bugs across platforms.
    """
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def sudo_write(path: str, content: str) -> bool:
    """Write `content` to a root-owned path via `sudo tee`. Returns False
    (and prints why) instead of raising — every caller decides whether that's
    fatal for the step it's in.
    """
    result = run(
        ["sudo", "tee", path],
        input=content,
        capture_output=True,
    )
    if result.returncode != 0:
        error(f"Failed to write {path}: {result.stderr.strip()}")
        return False
    return True


def sudo_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return run(["sudo", *cmd], **kwargs)


def docker_root_dir() -> str:
    result = run(["docker", "info", "-f", "{{.DockerRootDir}}"], capture_output=True)
    root = result.stdout.strip() if result.returncode == 0 else ""
    return root or "/var/lib/docker"


def cgroup_info() -> tuple[str, str]:
    result = run(["docker", "info", "-f", "{{.CgroupDriver}}|{{.CgroupVersion}}"], capture_output=True)
    if result.returncode != 0:
        return "unknown", "unknown"
    driver, _, version = result.stdout.strip().partition("|")
    return driver or "unknown", version or "unknown"


def filesystem_type(path: str) -> str:
    if shutil.which("findmnt"):
        result = run(["findmnt", "-no", "FSTYPE", "--target", path], capture_output=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    result = run(["stat", "-f", "-c", "%T", path], capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def cgroup_preflight() -> bool:
    driver, version = cgroup_info()
    if driver != "systemd" or version != "2":
        error(f"Cgroup driver/version is {driver}/{version}, expected systemd/2.")
        error("This mechanism (a systemd slice + cgroup-parent) needs both.")
        return False
    if not shutil.which("systemctl"):
        error("systemctl not found — is this actually a systemd host?")
        return False
    return True


def describe_cgroup_plan(cfg: dict[str, str]) -> None:
    root = docker_root_dir()
    driver, version = cgroup_info()
    info(f"Docker data-root: {root} (filesystem: {filesystem_type(root)})")
    info(f"Cgroup driver/version: {driver}/{version}")
    print()
    info("Would write:")
    print(f"  {SLICE_PATH}")
    print(f"    MemoryMax={cfg['DOCKER_MEMORY_LIMIT']}  MemoryHigh={cfg['_memory_high']}  CPUQuota={cfg['_cpu_quota_pct']}%")
    print(f"  {DAEMON_JSON_PATH}")
    print(f"    cgroup-parent={SLICE_NAME}, log rotation {cfg['DOCKER_LOG_MAX_SIZE']} x {cfg['DOCKER_LOG_MAX_FILE']}")


def apply_cgroup_limits(cfg: dict[str, str], assume_yes: bool) -> int:
    """CPU + memory + log rotation via a systemd slice + daemon.json's
    cgroup-parent. Works identically on any systemd + cgroup v2 Linux host —
    not filesystem-specific, shared by every Linux setup_*.py module. Only
    the disk-quota mechanism differs per OS/filesystem.
    """
    if not cgroup_preflight():
        return 1

    slice_unit = f"""[Unit]
Description=Resource limit for all Docker containers

[Slice]
MemoryMax={cfg['DOCKER_MEMORY_LIMIT']}
MemoryHigh={cfg['_memory_high']}
CPUQuota={cfg['_cpu_quota_pct']}%
"""

    daemon_json_path = Path(DAEMON_JSON_PATH)
    existing: dict = {}
    if daemon_json_path.is_file():
        try:
            existing = json.loads(daemon_json_path.read_text())
        except json.JSONDecodeError:
            warn(f"{DAEMON_JSON_PATH} exists but isn't valid JSON — not touching it. Fix or remove it first.")
            return 1
    existing["cgroup-parent"] = SLICE_NAME
    existing["log-driver"] = "json-file"
    existing.setdefault("log-opts", {})
    existing["log-opts"]["max-size"] = cfg["DOCKER_LOG_MAX_SIZE"]
    existing["log-opts"]["max-file"] = cfg["DOCKER_LOG_MAX_FILE"]
    daemon_json = json.dumps(existing, indent=2) + "\n"

    info(f"About to write {SLICE_PATH} and {DAEMON_JSON_PATH}, then restart Docker.")
    warn("Restarting Docker interrupts every currently-running container.")
    if not confirm("Apply?", assume_yes):
        info("Cancelled")
        return 1

    if not sudo_write(SLICE_PATH, slice_unit):
        return 1
    success(f"Wrote {SLICE_PATH}")

    if not sudo_write(DAEMON_JSON_PATH, daemon_json):
        return 1
    success(f"Wrote {DAEMON_JSON_PATH}")

    info("Reloading systemd and restarting Docker...")
    sudo_run(["systemctl", "daemon-reload"])
    result = sudo_run(["systemctl", "restart", "docker"])
    if result.returncode != 0:
        error("Failed to restart Docker — check `systemctl status docker` / `journalctl -u docker`")
        return 1
    success("Docker restarted with the new limits active")
    info("Bring your services back up, e.g.: uv run homeserver.py dev up core")
    return 0


def cgroup_status(cfg: dict[str, str]) -> None:
    info("docker-workloads.slice:")
    run(["systemctl", "status", SLICE_NAME, "--no-pager"])
    print()
    info(f"{DAEMON_JSON_PATH}:")
    result = run(["cat", DAEMON_JSON_PATH], capture_output=True)
    print(result.stdout if result.returncode == 0 else "  (not present)")
