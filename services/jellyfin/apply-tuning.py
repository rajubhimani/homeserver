#!/usr/bin/env python3
"""Apply verified Jellyfin performance/reliability tuning to database.xml, system.xml and every library's options.xml.

Usage: uv run jellyfin/apply-tuning.py   (from repo root, or `python jellyfin/apply-tuning.py`)

Stops jellyfin, edits its config XML in place, restarts it in whatever mode
(dev/prod) it was already running in. Safe to re-run any time (idempotent —
always sets the same target values regardless of current state).

Background/rationale for each value: docs/services/jellyfin.md
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent

# Fallback defaults if not set in .env -- verified working in this deployment.
# See docs/services/jellyfin.md for the "why" behind each one.
DEFAULT_LOCKING_BEHAVIOR = "Optimistic"
DEFAULT_IMAGE_EXTRACTION_TIMEOUT_MS = "30000"
DEFAULT_TRICKPLAY_PROCESS_PRIORITY = "Normal"
# compose.yml mounts MEDIA_ROOT read-only (:ro), so saving uploaded/downloaded subtitles
# next to the video fails with "Read-only file system". False stores them under
# /config/metadata instead.
DEFAULT_SAVE_SUBTITLES_WITH_MEDIA = "false"


def load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def resolve_data_root(env: dict[str, str]) -> Path:
    data_root = env.get("DATA_ROOT")
    if not data_root:
        sys.exit("DATA_ROOT not set in jellyfin/.env")
    path = (SERVICE_DIR / data_root).resolve()
    if not path.exists():
        sys.exit(f"DATA_ROOT does not exist: {path}")
    return path


def resolve_concurrency(env: dict[str, str]) -> int:
    raw = env.get("JELLYFIN_SCAN_CONCURRENCY")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            print(f"Warning: JELLYFIN_SCAN_CONCURRENCY={raw!r} is not a valid integer, falling back to CPU count")
    return os.cpu_count() or 4


def detect_running_env() -> str:
    """'dev' or 'prod' based on jellyfin's current port binding; defaults to 'dev' if not running."""
    try:
        result = subprocess.run(
            ["docker", "port", "jellyfin"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "127.0.0.1" in result.stdout:
            return "prod"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return "dev"


def run_homeserver(env_name: str, action: str) -> None:
    cmd = ["uv", "run", "homeserver.py", env_name, action, "jellyfin"]
    if action == "down":
        cmd.append("--no-backup")
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        sys.exit(f"homeserver.py {action} failed (exit {result.returncode})")


def apply_changes(path: Path, edits: list[tuple[str, str, str]]) -> list[tuple[str, str, str, str]]:
    """edits: list of (parent_tag_or_None, tag, new_value). Returns (tag_path, old, new) for reporting."""
    tree = ET.parse(path)
    root = tree.getroot()
    report = []
    for parent_tag, tag, value in edits:
        container = root.find(parent_tag) if parent_tag else root
        if container is None:
            sys.exit(f"{path.name}: could not find <{parent_tag}> — Jellyfin's config schema may have changed")
        el = container.find(tag)
        if el is None:
            sys.exit(f"{path.name}: could not find <{tag}> under <{parent_tag or path.stem}>")
        old = el.text
        el.text = value
        label = f"{parent_tag}/{tag}" if parent_tag else tag
        report.append((label, old or "", value))
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return report


def apply_library_options(config_root: Path, value: str) -> list[tuple[str, str, str]]:
    """Set <SaveSubtitlesWithMedia> in every library's options.xml. Returns (library, old, new).

    Regex, not ElementTree: options.xml carries xsi/xsd namespace attributes that
    ElementTree would rewrite as ns0:, and only this one tag changes.
    """
    report = []
    for options_xml in sorted((config_root / "root" / "default").glob("*/options.xml")):
        text = options_xml.read_text(encoding="utf-8-sig")
        match = re.search(r"<SaveSubtitlesWithMedia>(true|false)</SaveSubtitlesWithMedia>", text)
        if match is None:
            continue
        old = match.group(1)
        if old != value:
            new_text = text.replace(match.group(0), f"<SaveSubtitlesWithMedia>{value}</SaveSubtitlesWithMedia>")
            options_xml.write_text(new_text, encoding="utf-8")
        report.append((options_xml.parent.name, old, value))
    return report


def main() -> int:
    env = load_env(SERVICE_DIR / ".env")
    data_root = resolve_data_root(env)
    concurrency = resolve_concurrency(env)
    trickplay_threads = max(1, concurrency // 2)

    database_xml = data_root / "config" / "config" / "database.xml"
    system_xml = data_root / "config" / "config" / "system.xml"
    for f in (database_xml, system_xml):
        if not f.exists():
            sys.exit(
                f"{f} not found -- Jellyfin needs to have completed first-run setup "
                "before this script can run. Start it once, finish the setup wizard, then re-run this."
            )

    locking_behavior = env.get("JELLYFIN_LOCKING_BEHAVIOR") or DEFAULT_LOCKING_BEHAVIOR
    image_extraction_timeout_ms = env.get("JELLYFIN_IMAGE_EXTRACTION_TIMEOUT_MS") or DEFAULT_IMAGE_EXTRACTION_TIMEOUT_MS
    trickplay_process_priority = env.get("JELLYFIN_TRICKPLAY_PROCESS_PRIORITY") or DEFAULT_TRICKPLAY_PROCESS_PRIORITY

    save_subtitles_with_media = (env.get("JELLYFIN_SAVE_SUBTITLES_WITH_MEDIA") or DEFAULT_SAVE_SUBTITLES_WITH_MEDIA).lower()
    if save_subtitles_with_media not in ("true", "false"):
        sys.exit(f"JELLYFIN_SAVE_SUBTITLES_WITH_MEDIA must be true or false, got {save_subtitles_with_media!r}")

    env_name = detect_running_env()
    print(f"Detected env: {env_name}")
    print(f"Concurrency: {concurrency}  (trickplay threads: {trickplay_threads})")
    print(f"LockingBehavior: {locking_behavior}")
    print(f"ImageExtractionTimeoutMs: {image_extraction_timeout_ms}")
    print(f"TrickplayOptions/ProcessPriority: {trickplay_process_priority}")
    print(f"Libraries/SaveSubtitlesWithMedia: {save_subtitles_with_media}")

    run_homeserver(env_name, "down")

    report = []
    report += apply_changes(database_xml, [
        (None, "LockingBehavior", locking_behavior),
    ])
    report_db_name = database_xml.name
    system_report = apply_changes(system_xml, [
        (None, "LibraryScanFanoutConcurrency", str(concurrency)),
        (None, "LibraryMetadataRefreshConcurrency", str(concurrency)),
        (None, "ImageExtractionTimeoutMs", image_extraction_timeout_ms),
        ("TrickplayOptions", "ProcessThreads", str(trickplay_threads)),
        ("TrickplayOptions", "ProcessPriority", trickplay_process_priority),
    ])

    library_report = apply_library_options(data_root / "config", save_subtitles_with_media)

    print("\nApplied:")
    for tag, old, new in report:
        marker = "  (unchanged)" if old == new else ""
        print(f"  {report_db_name}: {tag}: {old} -> {new}{marker}")
    for tag, old, new in system_report:
        marker = "  (unchanged)" if old == new else ""
        print(f"  {system_xml.name}: {tag}: {old} -> {new}{marker}")

    for library, old, new in library_report:
        marker = "  (unchanged)" if old == new else ""
        print(f"  {library}/options.xml: SaveSubtitlesWithMedia: {old} -> {new}{marker}")

    run_homeserver(env_name, "up")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
