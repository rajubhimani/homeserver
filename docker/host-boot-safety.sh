#!/usr/bin/env bash
# One-time host setup (needs root) that makes a reboot safe for this stack.
# Idempotent — safe to re-run. See docs/08-maintenance.md "Boot safety".
#
#   sudo docker/host-boot-safety.sh            # install
#   sudo docker/host-boot-safety.sh --remove   # undo everything below
#
# 1. docker.service waits for the data drives. Both are 'nofail' in fstab, so
#    the host boots without them, and Docker used to start ~9s before
#    /mnt/mydata finished mounting -- containers then bind-mounted the empty
#    directory *under* the mountpoint on the root disk.
#    - REQUIRED_MOUNTS (repo + service_data): hard requirement -- Docker does
#      not start at all if it's missing. Better than writing to the wrong disk.
#    - ORDERED_MOUNTS (media drive): ordering only -- Docker waits for the
#      mount attempt, but a dead media disk doesn't take the whole stack down.
#      homeserver.py's own mount check blocks the services that need it.
# 2. net.ipv4.ip_nonlocal_bind=1 -- every prod service also publishes on
#    10.8.0.1, which only exists once the wg-easy *container* has brought up
#    wg0. Without this, anything Docker autostarts before wg-easy fails with
#    "cannot assign requested address" and is never retried.
# 3. homeserver-mount-watch.timer -- every 5 min, alerts via ntfy if a data
#    drive is unmounted or read-only (NTFS falls back to read-only after a
#    Windows Fast Startup/hibernate; Immich then fails every upload silently).
#    Installed outside the repo so it still runs if /mnt/mydata is missing.
set -euo pipefail

REQUIRED_MOUNTS="/mnt/mydata"
ORDERED_MOUNTS="/mnt/media"
WATCH_MOUNTS="$REQUIRED_MOUNTS $ORDERED_MOUNTS"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DROPIN=/etc/systemd/system/docker.service.d/wait-for-data-mounts.conf
SYSCTL=/etc/sysctl.d/90-homeserver-nonlocal-bind.conf
WATCH_BIN=/usr/local/bin/homeserver-mount-watch
WATCH_ENV=/etc/homeserver-mount-watch.env
WATCH_UNIT=/etc/systemd/system/homeserver-mount-watch

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0 $*" >&2; exit 1; }

if [ "${1:-}" = "--remove" ]; then
  systemctl disable --now homeserver-mount-watch.timer 2>/dev/null || true
  rm -f "$DROPIN" "$SYSCTL" "$WATCH_BIN" "$WATCH_ENV" "$WATCH_UNIT.service" "$WATCH_UNIT.timer"
  sysctl -w net.ipv4.ip_nonlocal_bind=0 >/dev/null
  systemctl daemon-reload
  echo "Removed. (docker.service ordering takes effect on next boot.)"
  exit 0
fi

# ── 1. Docker waits for data mounts ──
unit_for() { systemd-escape -p --suffix=mount "$1"; }
ordered_units=""
for m in $ORDERED_MOUNTS; do ordered_units="${ordered_units:+$ordered_units }$(unit_for "$m")"; done
mkdir -p "$(dirname "$DROPIN")"
cat >"$DROPIN" <<EOF
# Installed by homeserver docker/host-boot-safety.sh -- see that script.
[Unit]
RequiresMountsFor=$REQUIRED_MOUNTS
Wants=$ordered_units
After=$ordered_units
EOF
echo "✔ $DROPIN"

# ── 2. Allow binding 10.8.0.1 before wg0 exists ──
echo "net.ipv4.ip_nonlocal_bind = 1" >"$SYSCTL"
sysctl -q -p "$SYSCTL"
echo "✔ $SYSCTL (net.ipv4.ip_nonlocal_bind=$(sysctl -n net.ipv4.ip_nonlocal_bind))"

# ── 3. Mount watchdog → ntfy ──
# Reuses clamav's ntfy alert token/topic. Its URL points at the container name
# (http://ntfy/...), which the host can't resolve -- use ntfy's published port.
token=$(sed -n 's/^NTFY_ALERT_TOKEN=//p' "$REPO_ROOT/services/clamav/.env" 2>/dev/null || true)
topic=$(sed -n 's|^NTFY_ALERT_URL=.*/||p' "$REPO_ROOT/services/clamav/.env" 2>/dev/null || true)
cat >"$WATCH_ENV" <<EOF
WATCH_MOUNTS="$WATCH_MOUNTS"
NTFY_URL=http://127.0.0.1:8118/${topic:-homeserver-alerts}
NTFY_TOKEN=$token
EOF
chmod 600 "$WATCH_ENV"
[ -n "$token" ] || echo "⚠ No NTFY_ALERT_TOKEN in services/clamav/.env -- edit $WATCH_ENV, alerts will only go to the journal"

cat >"$WATCH_BIN" <<'EOF'
#!/usr/bin/env bash
# Alerts (ntfy + journal) if a homeserver data drive is unmounted or read-only.
# Installed by docker/host-boot-safety.sh. Re-alerts at most every 6h per problem.
. /etc/homeserver-mount-watch.env
state=/run/homeserver-mount-watch; mkdir -p "$state"
for m in $WATCH_MOUNTS; do
  if ! mountpoint -q "$m"; then problem="not mounted"
  elif findmnt -no OPTIONS "$m" | tr ',' '\n' | grep -qx ro; then problem="mounted read-only"
  else rm -f "$state/${m//\//_}"; continue; fi
  msg="$m is $problem -- services using it are failing or writing to the wrong disk. See docs/08-maintenance.md 'Boot safety'."
  echo "$msg"
  stamp="$state/${m//\//_}"
  if [ -f "$stamp" ] && [ $(( $(date +%s) - $(stat -c %Y "$stamp") )) -lt 21600 ]; then continue; fi
  if [ -n "$NTFY_TOKEN" ] && curl -fsS -m 10 -H "Authorization: Bearer $NTFY_TOKEN" \
      -H "Title: Homeserver data drive problem" -H "Priority: high" -H "Tags: warning,floppy_disk" \
      -d "$msg" "$NTFY_URL" >/dev/null; then
    touch "$stamp"
  fi
done
EOF
chmod 755 "$WATCH_BIN"

cat >"$WATCH_UNIT.service" <<EOF
[Unit]
Description=Homeserver data-drive mount check (alerts via ntfy)
[Service]
Type=oneshot
ExecStart=$WATCH_BIN
EOF
cat >"$WATCH_UNIT.timer" <<EOF
[Unit]
Description=Run homeserver data-drive mount check every 5 minutes
[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now homeserver-mount-watch.timer >/dev/null
echo "✔ homeserver-mount-watch.timer enabled (watching: $WATCH_MOUNTS)"

systemctl start homeserver-mount-watch.service
echo
echo "Done. Docker's mount ordering applies from the next boot; check with:"
echo "  systemctl show docker -p RequiresMountsFor -p After | tr ' ' '\\n' | grep mnt"
echo "  journalctl -u homeserver-mount-watch -n 5"
