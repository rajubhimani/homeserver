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
#    - MEDIA_MOUNTS (media drive): also a hard requirement for Docker, since
#      Jellyfin/Nextcloud/Immich bind paths on it and dockerd's own autostart
#      bypasses homeserver.py's mount check. Trade-off: a dead media disk
#      keeps the whole stack down until it is fixed or the drop-in removed.
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
# 6. The host never sleeps. GNOME's default suspends an idle desktop after 15
#    minutes, even on mains power: on 2026-10-05 the machine slept (S3) from
#    10:19 to 16:07, every container froze, the Cloudflare tunnel's connections
#    were dead on wake-up and every public site answered 530. Masking the sleep
#    targets makes suspend/hibernate impossible for every user and the login
#    screen. See docs/08-maintenance.md "The host went to sleep".
# 7. Nightly backup at 03:00: `homeserver.py prod backup running` stops each running service for a few
#    seconds, snapshots it onto the HDD (service_data/backup, newest BACKUP_RETENTION kept) and starts it
#    again, so after an SSD wipe or a bad day at most yesterday's data is lost (after the 2026-10-05
#    reinstall Docker's volumes were gone and only the three-day-old snapshots remained). Persistent: a
#    night the machine was off runs at the next boot. A failure alerts through the same ntfy path as item 3.
# 8. SELinux boolean virt_use_fusefs=on. /mnt/media is NTFS via ntfs-3g (fuseblk), which SELinux labels
#    fusefs_t; without the boolean QEMU/libvirt VMs get "Permission denied" opening an ISO there even though
#    the file is rwxrwxrwx (hit 2026-10-06, virt-manager Win11 install). FUSE can't be relabelled, so the
#    boolean is the fix. No-op on hosts without SELinux.
# 9. Host firewall default-deny inbound (firewalld). The zone on the default-route interface must not
#    allow a broad port range: with a real public IPv6 address (this host has one) every allowed port is
#    internet-reachable, and GNOME Remote Desktop's RDP (3389) + dev-mode Docker ports were exposed that way
#    (2026-09-04, docs/09-firewall.md). The fix was done by hand and lost in the 2026-10-04 reinstall, so it
#    lives here now: remove the 1025-65535 tcp/udp allows, keep only WireGuard's port, and enable
#    masquerade (wg-easy full-tunnel clients need it). Guacamole is unaffected: guacd reaches the host over
#    the Docker bridges, which are in firewalld's 'docker' zone (target ACCEPT). --remove deliberately does
#    NOT reopen the range. No-op on hosts without firewalld.
# 10. wg-easy host prerequisites (docs/services/wg-easy.md, "Prerequisites" 2-3): the iptable_nat/ip6table_nat
#    modules (without them wg-quick fails: "can't initialize iptables table 'nat'") and IPv6 forwarding. wg-easy
#    runs network_mode: host, so none of this can be set from the container. Both persist across reboots.
# 11. Public DNS servers next to the router's. The host resolves only through the router (192.168.1.1) and
#    two ISP IPv6 servers; on 2026-10-06 those timed out (cloudflared: "lookup region1.v2.argotunnel.com: i/o
#    timeout" at 10:30/11:00/12:26 IST, the watchdog's "Could not resolve host" later) and the public sites
#    degraded for hours. systemd-resolved's DNS= adds global servers that are tried together with the per-link
#    ones and fail over on timeout (man resolved.conf). NOT FallbackDNS=: that is only used when no other
#    server is known, so it never helps against a flaky one. Docker containers inherit it through
#    /run/systemd/resolve/resolv.conf when they are (re)created. Trade-off: some lookups leave via
#    Cloudflare/Quad9 instead of the ISP resolver.
set -euo pipefail

REQUIRED_MOUNTS="/mnt/mydata"
MEDIA_MOUNTS="/mnt/media"
WATCH_MOUNTS="$REQUIRED_MOUNTS $MEDIA_MOUNTS"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DROPIN=/etc/systemd/system/docker.service.d/wait-for-data-mounts.conf
SYSCTL=/etc/sysctl.d/90-homeserver-nonlocal-bind.conf
DNS_DROPIN=/etc/systemd/resolved.conf.d/90-homeserver-dns.conf
PUBLIC_DNS="1.1.1.1 9.9.9.9"
WG_MODULES=/etc/modules-load.d/wg-easy.conf
WG_SYSCTL=/etc/sysctl.d/99-wg-easy.conf
WATCH_BIN=/usr/local/bin/homeserver-mount-watch
WATCH_ENV=/etc/homeserver-mount-watch.env
WATCH_UNIT=/etc/systemd/system/homeserver-mount-watch
BACKUP_BIN=/usr/local/bin/homeserver-nightly-backup
BACKUP_UNIT=/etc/systemd/system/homeserver-nightly-backup
FWD_BIN=/usr/local/bin/homeserver-docker-forward
FWD_UNIT=/etc/systemd/system/homeserver-docker-forward.service
# Non-Docker interfaces that must keep forwarding through Docker's DROP policy.
# Missing interfaces are fine (rules match by name, no error) -- e.g. no VMs yet.
FORWARD_ALLOW_IFACES="virbr0 wg0"
WG_PORT=51820   # wg-easy's WireGuard UDP port (set in wg-easy's admin UI, default 51820)
ALPM_RULE=/etc/udev/rules.d/90-homeserver-sata-alpm.rules
TUNED_PROFILE=balanced-nolpm
PPD_CONF=/etc/tuned/ppd.conf
# Newer tuned (2.23+) reads custom profiles from /etc/tuned/profiles/, older from /etc/tuned/.
if [ -d /etc/tuned/profiles ]; then TUNED_DIR=/etc/tuned/profiles/$TUNED_PROFILE; else TUNED_DIR=/etc/tuned/$TUNED_PROFILE; fi

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0 $*" >&2; exit 1; }

if [ "${1:-}" = "--remove" ]; then
  systemctl disable --now homeserver-mount-watch.timer 2>/dev/null || true
  systemctl disable --now homeserver-nightly-backup.timer 2>/dev/null || true
  rm -f "$BACKUP_BIN" "$BACKUP_UNIT.service" "$BACKUP_UNIT.timer"
  if [ -x "$FWD_BIN" ]; then "$FWD_BIN" undo || true; fi
  systemctl disable homeserver-docker-forward.service 2>/dev/null || true
  systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true
  rm -f "$DROPIN" "$SYSCTL" "$WG_MODULES" "$WG_SYSCTL" "$DNS_DROPIN" "$WATCH_BIN" "$WATCH_ENV" "$WATCH_UNIT.service" "$WATCH_UNIT.timer" "$FWD_BIN" "$FWD_UNIT" "$ALPM_RULE"
  sysctl -w net.ipv4.ip_nonlocal_bind=0 >/dev/null
  # (item 9, the firewall lockdown, is intentionally left in place: undoing it would reopen 1025-65535 to the internet.)
  if command -v setsebool >/dev/null && getsebool virt_use_fusefs >/dev/null 2>&1; then setsebool -P virt_use_fusefs off; fi
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
  systemctl try-restart systemd-resolved 2>/dev/null || true
  echo "Removed. (docker.service ordering takes effect on next boot; SATA link power is back to the tuned/kernel default.)"
  exit 0
fi

# ── 1. Docker waits for data mounts ──
mkdir -p "$(dirname "$DROPIN")"
cat >"$DROPIN" <<EOF
# Installed by homeserver docker/host-boot-safety.sh -- see that script.
[Unit]
RequiresMountsFor=$REQUIRED_MOUNTS $MEDIA_MOUNTS
EOF
echo "✔ $DROPIN"

# ── 2. Allow binding 10.8.0.1 before wg0 exists ──
echo "net.ipv4.ip_nonlocal_bind = 1" >"$SYSCTL"
sysctl -q -p "$SYSCTL"
echo "✔ $SYSCTL (net.ipv4.ip_nonlocal_bind=$(sysctl -n net.ipv4.ip_nonlocal_bind))"

# ── 3. Mount watchdog → ntfy ──
# Uses the stack's ntfy alert token/topic (services/ntfy/.env). Its URL points at the container name
# (http://ntfy/...), which the host can't resolve -- use ntfy's published port.
token=$(sed -n 's/^NTFY_ALERT_TOKEN=//p' "$REPO_ROOT/services/ntfy/.env" 2>/dev/null || true)
topic=$(sed -n 's|^NTFY_ALERT_URL=.*/||p' "$REPO_ROOT/services/ntfy/.env" 2>/dev/null || true)
cat >"$WATCH_ENV" <<EOF
WATCH_MOUNTS="$WATCH_MOUNTS"
NTFY_URL=http://127.0.0.1:8118/${topic:-homeserver-alerts}
NTFY_TOKEN=$token
EOF
chmod 600 "$WATCH_ENV"
[ -n "$token" ] || echo "⚠ No NTFY_ALERT_TOKEN in services/ntfy/.env -- edit $WATCH_ENV, alerts will only go to the journal"

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
# ── 6. Never suspend ──
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null
echo "✔ sleep, suspend, hibernate and hybrid-sleep targets masked (the host stays up)"

# ── 7. Nightly backup ──
OWNER="${SUDO_USER:-$(stat -c %U "$REPO_ROOT")}"
cat >"$BACKUP_BIN" <<EOF
#!/usr/bin/env bash
# Nightly snapshot of every running service (docker/host-boot-safety.sh, item 7). Runs as root so it can
# read the ntfy settings; the backup itself runs as $OWNER, who owns the repo and the snapshots.
. /etc/homeserver-mount-watch.env
out=\$(runuser -u $OWNER -- bash -lc 'cd "$REPO_ROOT" && uv run homeserver.py prod backup running --no-wg' 2>&1); rc=\$?
printf '%s\n' "\$out" | sed 's/\x1b\[[0-9;]*m//g' | tail -25
if [ \$rc -ne 0 ] || printf '%s' "\$out" | grep -q -E 'FAILED|✖'; then
  msg="Nightly backup had failures (exit \$rc). Read: journalctl -u homeserver-nightly-backup"
  [ -n "\$NTFY_TOKEN" ] && curl -fsS -m 10 -H "Authorization: Bearer \$NTFY_TOKEN" -H "Title: Homeserver nightly backup failed" \\
    -H "Priority: high" -H "Tags: warning,floppy_disk" -d "\$msg" "\$NTFY_URL" >/dev/null
  exit 1
fi
EOF
chmod 755 "$BACKUP_BIN"
cat >"$BACKUP_UNIT.service" <<EOF
[Unit]
Description=Homeserver nightly backup (snapshot every running service onto the HDD)
After=docker.service
Requires=docker.service
RequiresMountsFor=$REQUIRED_MOUNTS
[Service]
Type=oneshot
ExecStart=$BACKUP_BIN
TimeoutStartSec=3h
EOF
cat >"$BACKUP_UNIT.timer" <<EOF
[Unit]
Description=Homeserver nightly backup at 03:00
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now homeserver-nightly-backup.timer >/dev/null
echo "✔ homeserver-nightly-backup.timer enabled (03:00 daily, runs as $OWNER)"

# ── 8. SELinux: let VMs read the NTFS (FUSE) media drive ──
if command -v setsebool >/dev/null && getsebool virt_use_fusefs >/dev/null 2>&1; then
  setsebool -P virt_use_fusefs on
  echo "✔ SELinux virt_use_fusefs=$(getsebool virt_use_fusefs | awk '{print $3}') (VMs can open ISOs on /mnt/media)"
else
  echo "- SELinux virt_use_fusefs: not applicable on this host (skipped)"
fi

# ── 9. Host firewall: default-deny inbound, only WireGuard open ──
if command -v firewall-cmd >/dev/null && systemctl is-active --quiet firewalld; then
  wan_if=$(ip route show default | awk '/^default/ {print $5; exit}')
  zone=$(firewall-cmd --get-zone-of-interface="$wan_if" 2>/dev/null || true)
  [ -n "$zone" ] || zone=$(firewall-cmd --get-default-zone)
  changed=0
  for proto in tcp udp; do
    if firewall-cmd --permanent --zone="$zone" --query-port="1025-65535/$proto" >/dev/null 2>&1; then
      firewall-cmd --permanent --zone="$zone" --remove-port="1025-65535/$proto" >/dev/null; changed=1
    fi
  done
  if ! firewall-cmd --permanent --zone="$zone" --query-port="$WG_PORT/udp" >/dev/null 2>&1; then
    firewall-cmd --permanent --zone="$zone" --add-port="$WG_PORT/udp" >/dev/null; changed=1
  fi
  if ! firewall-cmd --permanent --zone="$zone" --query-masquerade >/dev/null 2>&1; then
    firewall-cmd --permanent --zone="$zone" --add-masquerade >/dev/null; changed=1
  fi
  [ "$changed" = 0 ] || firewall-cmd --reload >/dev/null
  echo "✔ firewalld zone '$zone' ($wan_if): ports=$(firewall-cmd --zone="$zone" --list-ports) masquerade=$(firewall-cmd --zone="$zone" --query-masquerade)"
else
  echo "- firewalld not active: host firewall step skipped"
fi

# ── 10. wg-easy host prerequisites: NAT modules + IPv6 forwarding ──
printf 'iptable_nat\nip6table_nat\n' >"$WG_MODULES"
modprobe -a iptable_nat ip6table_nat
printf 'net.ipv6.conf.all.forwarding=1\nnet.ipv6.conf.default.forwarding=1\n' >"$WG_SYSCTL"
sysctl -q -p "$WG_SYSCTL"
echo "✔ $WG_MODULES + $WG_SYSCTL (ip6table_nat loaded: $(lsmod | grep -c '^ip6table_nat'), ipv6 forwarding=$(sysctl -n net.ipv6.conf.all.forwarding))"

# ── 11. Public DNS next to the router's ──
if systemctl is-active --quiet systemd-resolved; then
  mkdir -p "$(dirname "$DNS_DROPIN")"
  printf '# Installed by homeserver docker/host-boot-safety.sh -- see item 11 there.\n[Resolve]\nDNS=%s\n' "$PUBLIC_DNS" >"$DNS_DROPIN"
  systemctl restart systemd-resolved
  echo "✔ $DNS_DROPIN (global DNS: $(resolvectl status | awk '/^Global/{g=1} g&&/DNS Servers/{sub(/.*DNS Servers: /,""); print; exit}'))"
else
  echo "- systemd-resolved not active: public DNS step skipped"
fi

echo
echo "Done. Docker's mount ordering applies from the next boot; check with:"
echo "  systemctl show docker -p RequiresMountsFor -p After | tr ' ' '\\n' | grep mnt"
echo "  journalctl -u homeserver-mount-watch -n 5"
echo "  sudo iptables -S DOCKER-USER     # VM/VPN forwarding rules (item 4)"
echo "  grep . /sys/class/scsi_host/host*/link_power_management_policy   # item 5: max_performance"
echo "  systemctl is-enabled suspend.target      # item 6: masked"
echo "  systemctl list-timers homeserver-nightly-backup   # item 7: next 03:00 run"
echo "  getsebool virt_use_fusefs                # item 8: on"
echo "  resolvectl status | sed -n 1,8p          # item 11: Global DNS Servers: $PUBLIC_DNS"
echo "  lsmod | grep -E 'iptable_nat|ip6table_nat'   # item 10: both loaded (wg-easy)"
echo "  firewall-cmd --list-all                  # item 9: ports = $WG_PORT/udp only, masquerade: yes"
