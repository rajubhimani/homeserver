"""setup_fedora.py — Docker resource limits for Fedora (and any other
systemd + cgroup v2 + btrfs Linux host).

CPU + memory + log rotation are handled by _common.py's shared cgroup-slice
mechanism (identical on any systemd + cgroup v2 Linux host — not
Fedora-specific). The only thing this module owns is the disk cap, which
genuinely differs by filesystem:

Disk: a btrfs qgroup limit on the docker data-root. Docker's own
`overlay2.size` storage-opt needs XFS/ext4 + project quotas — it does not
work on btrfs. qgroups apply per-subvolume, and the data-root is very
likely a plain directory (not its own subvolume) on Fedora's default btrfs
layout, so this may require a one-time conversion.
"""

from __future__ import annotations

from _common import (
    apply_cgroup_limits,
    cgroup_status,
    confirm,
    describe_cgroup_plan,
    docker_root_dir,
    error,
    filesystem_type,
    info,
    run,
    success,
    sudo_run,
    warn,
)


def describe(cfg: dict[str, str]) -> None:
    describe_cgroup_plan(cfg)
    print()
    root = docker_root_dir()
    fstype = filesystem_type(root)
    if fstype != "btrfs":
        warn(f"Docker data-root is on {fstype}, not btrfs — the qgroup mechanism doesn't apply here.")
        warn("This looks like the wrong setup_*.py for this host; check docker-limits.py's platform detection.")
        return
    info(f"Disk cap ({cfg['DOCKER_DISK_LIMIT']}) would use a btrfs qgroup on {root}.")
    result = run(["sudo", "btrfs", "subvolume", "show", root], capture_output=True)
    if result.returncode == 0:
        info(f"{root} is already its own subvolume — no conversion needed.")
    else:
        warn(f"{root} is not its own subvolume yet — `disk-quota` will need to convert it")
        warn("(stops Docker, moves existing data — disruptive, confirmed separately).")


def apply(cfg: dict[str, str], assume_yes: bool) -> int:
    return apply_cgroup_limits(cfg, assume_yes)


def apply_disk_quota(cfg: dict[str, str], assume_yes: bool) -> int:
    root = docker_root_dir()
    fstype = filesystem_type(root)
    if fstype != "btrfs":
        error(f"{root} is on {fstype}, not btrfs — this mechanism doesn't apply.")
        return 1

    result = run(["sudo", "btrfs", "subvolume", "show", root], capture_output=True)
    is_subvolume = result.returncode == 0

    if not is_subvolume:
        warn(f"{root} is not its own btrfs subvolume — converting requires stopping Docker")
        warn("and moving all existing image/container/volume data.")
        if not confirm(f"Convert {root} to its own subvolume now?", assume_yes):
            info("Cancelled")
            return 1

        backup = f"{root}.bak"
        info("Stopping Docker...")
        sudo_run(["systemctl", "stop", "docker"])
        info(f"Moving {root} -> {backup}...")
        if sudo_run(["mv", root, backup]).returncode != 0:
            error("Move failed — Docker is stopped but data wasn't touched. Investigate before retrying.")
            return 1
        info(f"Creating subvolume at {root}...")
        if sudo_run(["btrfs", "subvolume", "create", root]).returncode != 0:
            error(f"Subvolume creation failed — restore with: sudo mv {backup} {root}")
            return 1
        info("Copying data back in (reflinked — fast, no extra disk used)...")
        copy = sudo_run(["cp", "-a", "--reflink=always", f"{backup}/.", f"{root}/"])
        if copy.returncode != 0:
            error(f"Copy failed — original data is safe at {backup}. Investigate before deleting it.")
            return 1

        du_new = run(["sudo", "du", "-sh", root], capture_output=True).stdout.strip()
        du_old = run(["sudo", "du", "-sh", backup], capture_output=True).stdout.strip()
        info(f"New: {du_new}")
        info(f"Old: {du_old}")
        if not confirm(f"Sizes look right? Delete {backup} and start Docker?", assume_yes):
            warn(f"Leaving {backup} in place — delete manually once you've verified, then: sudo systemctl start docker")
            return 1
        sudo_run(["rm", "-rf", backup])
        sudo_run(["systemctl", "start", "docker"])
        success(f"{root} is now its own subvolume")

    info(f"Enabling btrfs quota on {root}...")
    sudo_run(["btrfs", "quota", "enable", root])
    info(f"Setting qgroup limit to {cfg['DOCKER_DISK_LIMIT']}...")
    result = sudo_run(["btrfs", "qgroup", "limit", cfg["DOCKER_DISK_LIMIT"], root])
    if result.returncode != 0:
        error("qgroup limit failed — see output above")
        return 1
    success(f"Disk quota set: {root} capped at {cfg['DOCKER_DISK_LIMIT']}")
    return 0


def status(cfg: dict[str, str]) -> None:
    cgroup_status(cfg)
    print()
    root = docker_root_dir()
    info(f"btrfs qgroup usage for {root}:")
    run(["sudo", "btrfs", "qgroup", "show", "-r", root])
