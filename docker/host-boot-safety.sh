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
# 4. homeserver-docker-forward.service -- Docker sets the host's iptables
#    FORWARD policy to DROP and only whitelists its own bridges, which
#    silently kills forwarding for everything else on the host: libvirt VMs
#    on virbr0 (VM gets a DHCP lease but no internet) and wg-easy
#    full-tunnel clients on wg0. This re-allows those interfaces in
#    DOCKER-USER (the one chain Docker never rewrites) every time Docker
#    starts -- but traffic from them *to* Docker's bridges is RETURNed to
#    Docker's own rules first, so VMs/VPN clients still can't reach
#    unpublished container ports directly. See docs/09-firewall.md
#    "Docker vs. VMs and the VPN".
# 5. SATA link power management kept at max_performance. With power saving
#    on (Fedora's tuned 'balanced' profile sets alpm=med_power_with_dipm, and
#    overrides the kernel's ahci.mobile_lpm_policy), the system SSD (WD Green)
#    failed to wake its link: 98 'SError: { PHYRdyChg CommWake }' / 'hard
#    resetting link' errors in a day, then the OS disk dropped and the host
#    froze (2026-10-02). SMART was clean. A tuned child profile keeps tuned
#    from re-enabling it; a udev rule covers hosts without tuned. See
#    docs/08-maintenance.md "System freezes / SSD drops off the bus".
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
FWD_BIN=/usr/local/bin/homeserver-docker-forward
FWD_UNIT=/etc/systemd/system/homeserver-docker-forward.service
# Non-Docker interfaces that must keep forwarding through Docker's DROP policy.
# Missing interfaces are fine (rules match by name, no error) -- e.g. no VMs yet.
FORWARD_ALLOW_IFACES="virbr0 wg0"
ALPM_RULE=/etc/udev/rules.d/90-homeserver-sata-alpm.rules
TUNED_PROFILE=balanced-nolpm
PPD_CONF=/etc/tuned/ppd.conf
# Newer tuned (2.23+) reads custom profiles from /etc/tuned/profiles/, older from /etc/tuned/.
if [ -d /etc/tuned/profiles ]; then TUNED_DIR=/etc/tuned/profiles/$TUNED_PROFILE; else TUNED_DIR=/etc/tuned/$TUNED_PROFILE; fi

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0 $*" >&2; exit 1; }

if [ "${1:-}" = "--remove" ]; then
  systemctl disable --now homeserver-mount-watch.timer 2>/dev/null || true
  if [ -x "$FWD_BIN" ]; then "$FWD_BIN" undo || true; fi
  systemctl disable homeserver-docker-forward.service 2>/dev/null || true
  rm -f "$DROPIN" "$SYSCTL" "$WATCH_BIN" "$WATCH_ENV" "$WATCH_UNIT.service" "$WATCH_UNIT.timer" "$FWD_BIN" "$FWD_UNIT" "$ALPM_RULE"
  sysctl -w net.ipv4.ip_nonlocal_bind=0 >/dev/null
  if command -v tuned-adm >/dev/null; then
    if [ -f "$PPD_CONF" ] && grep -q "^balanced=$TUNED_PROFILE$" "$PPD_CONF"; then
      sed -i "s/^balanced=$TUNED_PROFILE$/balanced=balanced/" "$PPD_CONF"
    elif tuned-adm active 2>/dev/null | grep -q ": $TUNED_PROFILE$"; then
      tuned-adm profile balanced
    fi
    rm -rf "$TUNED_DIR"
    systemctl try-restart tuned-ppd tuned 2>/dev/null || true
  fi
  systemctl daemon-reload
  echo "Removed. (docker.service ordering takes effect on next boot; SATA link power is back to the tuned/kernel default.)"
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

# ── 4. Let VMs (virbr0) and VPN clients (wg0) forward despite Docker's DROP ──
cat >"$FWD_BIN" <<EOF
#!/usr/bin/env bash
# Installed by homeserver docker/host-boot-safety.sh -- see that script, item 4.
#   homeserver-docker-forward apply|undo   (idempotent)
set -uo pipefail
IFACES="$FORWARD_ALLOW_IFACES"
EOF
cat >>"$FWD_BIN" <<'EOF'
rules() {  # one rule per line, in the order they must sit in DOCKER-USER
  for i in $IFACES; do
    echo "-i $i -o docker0 -j RETURN"   # to containers: Docker's own rules decide
    echo "-i $i -o br-+ -j RETURN"
    echo "-i $i -j ACCEPT"              # everything else (internet, LAN): allow
    echo "-o $i -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT"
  done
}
case "${1:-apply}" in
  apply)
    iptables -N DOCKER-USER 2>/dev/null || true
    rules | while read -r r; do
      iptables -C DOCKER-USER $r 2>/dev/null || iptables -A DOCKER-USER $r
    done
    echo "DOCKER-USER forwarding allowed for: $IFACES" ;;
  undo)
    rules | while read -r r; do
      while iptables -C DOCKER-USER $r 2>/dev/null; do iptables -D DOCKER-USER $r; done
    done
    echo "DOCKER-USER forwarding rules removed for: $IFACES" ;;
  *) echo "Usage: $0 [apply|undo]" >&2; exit 1 ;;
esac
EOF
chmod 755 "$FWD_BIN"

# PartOf + WantedBy=docker.service: re-runs every time Docker (re)starts,
# since Docker re-asserts its FORWARD DROP policy on every start.
cat >"$FWD_UNIT" <<EOF
[Unit]
Description=Allow libvirt VMs and WireGuard clients to forward past Docker's FORWARD DROP policy
After=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$FWD_BIN apply
ExecStop=$FWD_BIN undo
[Install]
WantedBy=docker.service
EOF
systemctl daemon-reload
systemctl enable homeserver-docker-forward.service >/dev/null
systemctl restart homeserver-docker-forward.service
echo "✔ homeserver-docker-forward.service enabled + applied ($FORWARD_ALLOW_IFACES)"

# ── 5. SATA link power management: max_performance ──
# udev: applies to every SATA host as it appears (all hosts, tuned or not).
cat >"$ALPM_RULE" <<'EOF'
# Installed by homeserver docker/host-boot-safety.sh -- see that script, item 5.
ACTION=="add", SUBSYSTEM=="scsi_host", KERNEL=="host*", ATTR{link_power_management_policy}="max_performance"
EOF
for p in /sys/class/scsi_host/host*/link_power_management_policy; do
  [ -e "$p" ] && echo max_performance >"$p" 2>/dev/null || true
done
echo "✔ $ALPM_RULE (applied now to every SATA port)"

# tuned re-applies its profile's alpm= after udev, so it needs its own profile.
if command -v tuned-adm >/dev/null; then
  mkdir -p "$TUNED_DIR"
  cat >"$TUNED_DIR/tuned.conf" <<'EOF'
# Installed by homeserver docker/host-boot-safety.sh -- see that script, item 5.
[main]
summary=balanced, but SATA links stay at max_performance (link power saving froze the host)
include=balanced

[scsi_host]
alpm=max_performance
EOF
  if [ -f "$PPD_CONF" ]; then
    # tuned-ppd: the desktop's "Balanced" power mode maps to this profile.
    # Only the [profiles] line; [battery]'s balanced=balanced-battery is untouched.
    sed -i "s/^balanced=balanced$/balanced=$TUNED_PROFILE/" "$PPD_CONF"
    systemctl try-restart tuned-ppd tuned 2>/dev/null || true
  elif tuned-adm active 2>/dev/null | grep -q ": balanced$"; then
    tuned-adm profile "$TUNED_PROFILE"
  fi
  active=$(tuned-adm active 2>/dev/null | sed -n 's/^Current active profile: //p' || true)
  if [ "$active" = "$TUNED_PROFILE" ]; then
    echo "✔ tuned profile $TUNED_PROFILE active ($TUNED_DIR)"
  else
    echo "⚠ tuned's active profile is '$active', not $TUNED_PROFILE -- if it sets alpm= (balanced/powersave do), switch: tuned-adm profile $TUNED_PROFILE"
  fi
fi
echo
echo "Done. Docker's mount ordering applies from the next boot; check with:"
echo "  systemctl show docker -p RequiresMountsFor -p After | tr ' ' '\\n' | grep mnt"
echo "  journalctl -u homeserver-mount-watch -n 5"
echo "  sudo iptables -S DOCKER-USER     # VM/VPN forwarding rules (item 4)"
echo "  grep . /sys/class/scsi_host/host*/link_power_management_policy   # item 5: max_performance"
