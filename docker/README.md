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
python docker/docker-limits.py check            # show what would be applied — read-only, safe to run anytime
python docker/docker-limits.py apply             # CPU + memory + log rotation (restarts Docker — confirms first)
python docker/docker-limits.py apply --yes       # same, skip the confirmation
python docker/docker-limits.py disk-quota        # the disk cap — separate step, more disruptive on Linux (confirms first)
python docker/docker-limits.py status            # show current applied state
```

`apply` and `disk-quota` are deliberately separate commands. `apply`
restarts Docker (interrupts every running container, but is otherwise
quick and safe). `disk-quota` is a bigger deal on Linux — see "Platform
mechanics" below — so it's never bundled into `apply` and always asks for
confirmation on its own.

Needs `sudo` — every privileged step shells out to `sudo` itself (`tee`,
`systemctl`, `btrfs`, etc.), so run these as your normal user, not as
root. A coding assistant without an interactive terminal can prepare
these files but can't run the privileged steps itself.

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
