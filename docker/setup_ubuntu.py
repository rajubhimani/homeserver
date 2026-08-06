"""setup_ubuntu.py — Docker resource limits for Ubuntu (and any other
systemd + cgroup v2 + ext4 Linux host).

CPU + memory + log rotation reuse _common.py's shared cgroup-slice
mechanism — identical logic to setup_fedora.py, not Ubuntu-specific.

Disk is the part that differs. Docker's `overlay2.size` storage-opt *can*
work on ext4, but only with project quotas already enabled on the
filesystem (`tune2fs -O quota,project` + `prjquota` mount option) — turning
that on for an already-mounted root filesystem safely typically needs an
unmount/fsck pass, which isn't something to automate blindly against
someone's root disk. Instead this uses a sized ext4 loopback image mounted
at the docker data-root: a genuine, enforced combined cap (mirrors what the
btrfs qgroup achieves on Fedora), at the cost of one more indirection layer
and a small amount of fixed overhead from the loop device.
"""

from __future__ import annotations

import shutil

from _common import (
    apply_cgroup_limits,
    cgroup_status,
    confirm,
    describe_cgroup_plan,
    docker_root_dir,
    error,
    filesystem_type,
    info,
    parse_size_to_bytes,
    run,
    success,
    sudo_run,
    warn,
)


def _loop_image_path(root: str) -> str:
    return f"{root.rstrip('/')}-disk.img"


def describe(cfg: dict[str, str]) -> None:
    describe_cgroup_plan(cfg)
    print()
    root = docker_root_dir()
    fstype = filesystem_type(root)
    img = _loop_image_path(root)
    info(f"Disk cap ({cfg['DOCKER_DISK_LIMIT']}) would use a {img} loopback ext4 image mounted at {root}.")
    if fstype == "ext4" and run(["findmnt", "-no", "OPTIONS", root], capture_output=True).stdout.find("loop") != -1:
        info(f"{root} already looks like a loop mount — `disk-quota` will treat this as already set up.")
    else:
        warn(f"{root} is currently a plain directory on {fstype} — `disk-quota` will need to convert it")
        warn("(stops Docker, moves existing data — disruptive, confirmed separately).")


def apply(cfg: dict[str, str], assume_yes: bool) -> int:
    return apply_cgroup_limits(cfg, assume_yes)


def apply_disk_quota(cfg: dict[str, str], assume_yes: bool) -> int:
    if not shutil.which("mkfs.ext4"):
        error("mkfs.ext4 not found — install e2fsprogs first (usually already present on Ubuntu).")
        return 1

    root = docker_root_dir()
    img = _loop_image_path(root)
    size_bytes = parse_size_to_bytes(cfg["DOCKER_DISK_LIMIT"])

    already_mounted = run(["findmnt", "-no", "SOURCE", "--target", root], capture_output=True).stdout.strip()
    if already_mounted == img:
        info(f"{root} is already mounted from {img} — nothing to convert.")
    else:
        warn(f"About to: create a {cfg['DOCKER_DISK_LIMIT']} ext4 image at {img}, stop Docker,")
        warn(f"move existing data out of {root}, and remount {root} from that image.")
        if not confirm("Proceed?", assume_yes):
            info("Cancelled")
            return 1

        backup = f"{root}.bak"
        info(f"Creating sparse {cfg['DOCKER_DISK_LIMIT']} image at {img}...")
        if sudo_run(["truncate", "-s", str(size_bytes), img]).returncode != 0:
            error("Failed to create image file")
            return 1
        info(f"Formatting {img} as ext4...")
        if sudo_run(["mkfs.ext4", "-q", img]).returncode != 0:
            error("mkfs.ext4 failed")
            return 1

        info("Stopping Docker...")
        sudo_run(["systemctl", "stop", "docker"])
        info(f"Moving {root} -> {backup}...")
        if sudo_run(["mv", root, backup]).returncode != 0:
            error("Move failed — Docker is stopped but data wasn't touched. Investigate before retrying.")
            return 1
        sudo_run(["mkdir", "-p", root])

        info(f"Mounting {img} at {root}...")
        if sudo_run(["mount", "-o", "loop", img, root]).returncode != 0:
            error(f"Mount failed — restore with: sudo mv {backup} {root}")
            return 1

        info("Copying data back in...")
        copy = sudo_run(["cp", "-a", f"{backup}/.", f"{root}/"])
        if copy.returncode != 0:
            error(f"Copy failed — original data is safe at {backup}. Investigate before deleting it.")
            return 1

        du_new = run(["sudo", "du", "-sh", root], capture_output=True).stdout.strip()
        du_old = run(["sudo", "du", "-sh", backup], capture_output=True).stdout.strip()
        info(f"New: {du_new}")
        info(f"Old: {du_old}")
        if not confirm(f"Sizes look right? Delete {backup}, persist the mount in fstab, and start Docker?", assume_yes):
            warn(f"Leaving {backup} in place, and {root} mounted but NOT yet in /etc/fstab.")
            warn(f"A reboot right now would leave {root} empty — Docker would recreate it fresh there.")
            return 1
        sudo_run(["rm", "-rf", backup])

        fstab_line = f"{img} {root} ext4 loop 0 0"
        info("Adding to /etc/fstab so this survives a reboot...")
        append = run(
            ["sudo", "tee", "-a", "/etc/fstab"],
            input=f"{fstab_line}\n",
            capture_output=True,
        )
        if append.returncode != 0:
            warn("Failed to update /etc/fstab automatically — add this line yourself:")
            warn(f"  {fstab_line}")

        sudo_run(["systemctl", "start", "docker"])
        success(f"{root} is now capped at {cfg['DOCKER_DISK_LIMIT']} via {img}")
        return 0

    success(f"{root} is already capped at {cfg['DOCKER_DISK_LIMIT']} via {img}")
    return 0


def status(cfg: dict[str, str]) -> None:
    cgroup_status(cfg)
    print()
    root = docker_root_dir()
    info(f"Mount info for {root}:")
    run(["findmnt", root])
    run(["df", "-h", root])
