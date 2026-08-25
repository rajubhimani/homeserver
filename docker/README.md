# docker/ — capping Docker's total resource usage

Bounds how much CPU, memory, and disk the Docker daemon (and everything
running in it) can use on this host — separate from and unrelated to any
individual service's own `deploy.resources.limits` in a `compose.yml`
(those cap one container; this caps the whole engine). Full technical
background — why a plain `docker.service` systemd drop-in doesn't work,
why `overlay2.size` doesn't apply on btrfs, etc. — lives in
[`docs/08-maintenance.md`](../docs/08-maintenance.md)'s "Capping Docker's
total resource usage" section; this folder is the runnable version of
those same commands, parameterized by `docker/.env` instead of hand-edited
every time.

## Setup

```bash
cp docker/.env.example docker/.env
# edit docker/.env — CPU cores, memory limit, disk limit, log rotation
```

## Usage

```bash
python docker/docker-limits.py check                 # show what would be applied — read-only, safe to run anytime
python docker/docker-limits.py apply                  # CPU + memory + log rotation (restarts Docker — confirms first)
python docker/docker-limits.py apply --yes            # same, skip the confirmation
python docker/docker-limits.py relocate-data-root      # move Docker's data-root to DOCKER_DATA_ROOT (confirms first)
python docker/docker-limits.py disk-quota             # cap disk usage wherever the data-root currently is (confirms first)
python docker/docker-limits.py status                 # show current applied state, including the data-root path
```

`apply`, `relocate-data-root`, and `disk-quota` are deliberately separate
commands. `apply` restarts Docker (interrupts every running container, but
is otherwise quick and safe). `relocate-data-root` and `disk-quota` are
bigger deals — full data copies, more disruptive on Linux (see "Platform
mechanics" below) — so neither is ever bundled into `apply` and both always
ask for confirmation on their own.

## Two independent knobs: where vs. how much

Both are entirely opt-in — nothing here runs automatically, and neither
command does anything unless you invoke it yourself:

- **`relocate-data-root`** — *where* Docker's data (images, containers,
  volumes, build cache) physically lives, for the **whole host, every
  container**. By default that's `/var/lib/docker` on the OS drive. If you
  have a bigger secondary disk and want to move everything Docker stores
  over to it — not just one service's — set `DOCKER_DATA_ROOT` in
  `docker/.env` and run this once. It's your call whether that's worth the
  restart/data-copy; nothing in this repo requires it.
- **`disk-quota`** — *how much* space Docker is allowed to use, wherever its
  data-root currently is. Works whether or not you've relocated it.

They compose because every command here re-detects the data-root live via
`docker info` — run `relocate-data-root` first (if at all), and `disk-quota`
(and `status`/`check`) automatically target the new location afterward, no
extra config.

**Forgejo's CI does use this host's real Docker** (`container.docker_host: automount` in `services/forgejo/compose.yml` — see `docs/services/forgejo.md` for why an isolated Docker-in-Docker sidecar was tried and reverted). So unlike a fully isolated setup, `relocate-data-root`/`disk-quota` here **do** apply to Forgejo CI's image layers and build cache, the same as every other container on the host — there's no separate CI-only storage location to reason about.

**Efficiency: this is a disk-speed trade, not a free win, whichever knob you
use.** Neither mechanism makes Docker faster — both just decide *which
physical disk* absorbs the I/O. Check what you actually have before
assuming either direction helps:

```bash
lsblk -d -o NAME,ROTA,MODEL,TRAN   # ROTA=0 -> SSD/NVMe, ROTA=1 -> spinning HDD
```

**A slow disk isn't the only thing that can go wrong here — the filesystem
matters more.** Docker's `overlay2` storage driver needs a native Linux
filesystem (ext4/xfs/btrfs) under the data-root. A FUSE-mounted filesystem
(`ntfs-3g`, exFAT-via-FUSE, etc. — check with `findmnt -T <path>`; fstype
`fuseblk` is the tell) **cannot** mount overlay2 at all (`failed to mount
overlay: invalid argument` in the daemon's own startup log). Docker silently
falls back to the `vfs` driver instead, which does a full copy of every
image layer per container rather than overlay2's copy-on-write — this is not
a modest slowdown, it's minutes-per-container versus seconds, and confirmed
on this host to also cause CI job containers to hang indefinitely rather
than just run slow (see `docs/services/forgejo.md`'s "Tried and reverted"
section for the full incident this was discovered from). A FUSE-mounted
disk also reports every file as owned by whichever UID the mount was set up
with (commonly root) regardless of which process actually wrote it, which
separately breaks anything that checks file ownership — e.g. Git's
"detected dubious ownership" safety check, hit by Forgejo's
`actions/checkout` cache. Neither `relocate-data-root` nor `DOCKER_DATA_ROOT`
should ever point at a FUSE-mounted path for these reasons — confirm the
target filesystem natively before relocating anything here, not just its
rotational speed.

If the OS drive is the faster disk (commonly true — SSD boot drive, HDD for
bulk storage) and you `relocate-data-root` onto a bigger-but-slower secondary
disk, every container on the host — including Forgejo CI, since it now
shares the host's Docker — does its image/layer I/O against the slower disk.
More headroom, less speed, for everything. Nothing here is permanent:
`DOCKER_DATA_ROOT` is just a bind mount target. Point it at a faster disk
later (e.g. add an SSD) and speed follows automatically.

**Rule of thumb:** reach for `relocate-data-root` only if the *whole host*
is tight on OS-drive space and you're fine with every container's I/O
moving to the new disk. If the OS drive is otherwise fine and the actual
concern is CI build storage specifically, Forgejo's sidecar already handles
that on its own — no action needed here at all.

Needs `sudo` — every privileged step shells out to `sudo` itself (`tee`,
`systemctl`, `btrfs`, etc.), so run these as your normal user, not as
root. A coding assistant without an interactive terminal can prepare
these files but can't run the privileged steps itself.

**Also check `fs.inotify.max_user_instances` if containers crash-loop or
come up unhealthy right after a reboot or a mass `docker restart`.**
Separate axis from CPU/memory/disk, not something this tool sets — a
host running many containers at once can exhaust the default 128-instance
inotify ceiling well before memory/CPU are the actual problem. See
["Host inotify limits" in `docs/08-maintenance.md`](../docs/08-maintenance.md#host-inotify-limits-hit-when-running-many-containers-at-once)
for the symptom and the one-line permanent fix.

## Platform dispatch

`docker-limits.py` detects what it's running on and picks the matching
module — no separate invocation needed per OS:

| Platform | Module | CPU/memory mechanism | Disk mechanism |
| --- | --- | --- | --- |
| Fedora (or any btrfs root) | `setup_fedora.py` | systemd slice + `cgroup-parent` | btrfs qgroup limit |
| Ubuntu (or any other Linux) | `setup_ubuntu.py` | systemd slice + `cgroup-parent` (same shared code) | sized ext4 loopback image |
| Windows | `setup_windows.py` | Docker Desktop's own settings file | same file, same step |

Detection: `win32` → Windows. Otherwise reads `/etc/os-release`'s `ID` —
`fedora`/`ubuntu` map directly. Anything else falls back to checking the
Docker data-root's actual filesystem: btrfs uses the qgroup mechanism,
anything else uses the loopback mechanism (which works regardless of the
underlying filesystem, since it's just an ext4 image file sitting on top
of whatever's there — the more "runs anywhere" of the two, at the cost of
one extra indirection layer).

## Platform mechanics

**CPU + memory (`_common.py`, shared by every Linux module):** a
dedicated systemd slice (`docker-workloads.slice`) with `MemoryMax`/
`MemoryHigh`/`CPUQuota`, wired in via `daemon.json`'s `cgroup-parent` so
every container's cgroup actually lands under it. A `docker.service`
drop-in does **not** work for this — see `docs/08-maintenance.md` for why
(container cgroups are siblings of `docker.service`, not children of it).

**Disk on Fedora/btrfs:** a btrfs qgroup limit on the data-root. Requires
the data-root to be its own subvolume first — `disk-quota` converts it
if needed (stops Docker, moves data via a reflinked copy, confirms sizes
match before deleting the original).

**Disk on Ubuntu/anything else:** Docker's `overlay2.size` storage-opt
needs project quotas already enabled on the filesystem, which isn't safe
to turn on automatically against an already-mounted root disk. Instead,
`disk-quota` creates a sized ext4 image file, formats it, and mounts it
at the data-root (added to `/etc/fstab` so it survives a reboot) — a
genuine combined cap, same end result as the btrfs qgroup, via a
different mechanism.

**Windows:** completely different — no systemd/cgroups involved. Docker
Desktop keeps its own Resources-tab settings (CPU/memory/disk sliders) in
a JSON file under `%APPDATA%\Docker\`. Since the exact filename and key
names have changed across Docker Desktop versions, `setup_windows.py`
never guesses or blind-creates keys — it reads what's actually in the
file, only modifies keys it can already find, and refuses (rather than
guessing) if none match. Always backs up the original file before
writing. Requires fully quitting and relaunching Docker Desktop
afterward — a container restart alone doesn't reload this file.

Reclaiming disk space already used (rather than capping future use) is a
separate, existing concern — `uv run homeserver.py gc` from the repo
root, documented in `docs/08-maintenance.md`.
