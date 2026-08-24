#!/usr/bin/env bash
# Blocks the 5 remote-browser containers (Firefox/Chromium/Ungoogled
# Chromium/Brave/Mullvad Browser — services/{firefox,chromium,...}/compose.yml)
# from reaching this host's LAN, while leaving their internet access
# untouched. Scoped to just these 5 static IPs deliberately — never applied
# stack-wide, since e.g. Guacamole's whole job is reaching LAN devices.
#
# Usage:
#   browser-lan-block.sh apply   — add the rules (default if no argument)
#   browser-lan-block.sh undo    — remove everything this script has ever added
#
# Both subcommands are idempotent — safe to run repeatedly, safe to run
# `undo` even if `apply` was never run (no-ops on rules that aren't there).
#
# Two independent mechanisms are needed, confirmed live — see
# docs/services/browser-hub.md for the full writeup of why each exists:
#
# 1. DOCKER-USER iptables chain (genuine LAN devices, e.g. the router) — the
#    one chain Docker guarantees it will never rewrite/reorder on daemon
#    restart, unlike rules added directly to FORWARD. Matches on the
#    ORIGINAL (pre-NAT) destination via conntrack --ctorigdst, not a plain
#    -d match — Docker's own DNAT for port-published containers rewrites
#    the destination *before* DOCKER-USER ever sees the packet, so a plain
#    match silently never fires.
#
# 2. firewalld rich rule, --zone=docker specifically (this host's own
#    published dev ports, e.g. Jellyfin on :8096) — this traffic goes
#    through a per-port `docker-proxy` userspace relay process, not
#    iptables DNAT at all. It's delivered locally (INPUT chain) straight to
#    that process, never traversing FORWARD/DOCKER-USER regardless of match
#    type, so mechanism 1 above cannot see it no matter how it's written.
#    firewalld (not raw iptables -I INPUT) is required here because this
#    host runs it and it owns/regenerates INPUT from its own config on
#    every reload — a raw INPUT rule would vanish on the next
#    `firewall-cmd --reload`. --zone=docker specifically is required too:
#    Fedora's docker-ce package creates a separate "docker" firewalld zone
#    containing every docker/br-* bridge interface, apart from the host's
#    default zone — a rich rule added without --zone lands in the default
#    zone and is silently never evaluated for bridge traffic at all.
#
# IPv6 is deliberately not covered: confirmed live, the browser containers
# have no IPv6 connectivity whatsoever (`ip -6 addr` shows only loopback,
# outbound IPv6 fails with "no route") — the `homeserver` Docker network is
# IPv4-only, so there is nothing for an IPv6 rule to restrict.
set -euo pipefail

MODE="${1:-apply}"

# Edit these for your own network if they differ from what this host uses
# (check LAN subnet with: ip addr show | grep 'inet ' | grep -v 172.1; check
# host's own LAN-facing IP the same way — it's the /32 inside that subnet).
LAN_SUBNET="192.168.1.0/24"
HOST_LAN_IP="192.168.1.7"
FIREWALLD_ZONE="docker"

BROWSER_IPS=(
    172.18.255.240 # firefox
    172.18.255.241 # chromium
    172.18.255.242 # ungoogled-chromium
    172.18.255.243 # brave
    172.18.255.244 # mullvad-browser
)

apply() {
    for ip in "${BROWSER_IPS[@]}"; do
        if ! iptables -C DOCKER-USER -s "$ip" -m conntrack --ctorigdst "$LAN_SUBNET" -j DROP 2>/dev/null; then
            iptables -I DOCKER-USER -s "$ip" -m conntrack --ctorigdst "$LAN_SUBNET" -j DROP
            echo "Added: DOCKER-USER block $ip -> $LAN_SUBNET (orig-dst match)"
        else
            echo "Already present: DOCKER-USER block $ip -> $LAN_SUBNET"
        fi

        rule="rule family=\"ipv4\" source address=\"$ip\" destination address=\"$HOST_LAN_IP\" drop"
        if ! firewall-cmd --zone="$FIREWALLD_ZONE" --query-rich-rule="$rule" >/dev/null 2>&1; then
            firewall-cmd --zone="$FIREWALLD_ZONE" --permanent --add-rich-rule="$rule" >/dev/null
            echo "Added: firewalld rich rule (zone=$FIREWALLD_ZONE) $ip -> $HOST_LAN_IP"
        else
            echo "Already present: firewalld rich rule (zone=$FIREWALLD_ZONE) $ip -> $HOST_LAN_IP"
        fi
    done
    firewall-cmd --reload >/dev/null
    echo "firewalld reloaded — LAN isolation active"
}

undo() {
    for ip in "${BROWSER_IPS[@]}"; do
        if iptables -C DOCKER-USER -s "$ip" -m conntrack --ctorigdst "$LAN_SUBNET" -j DROP 2>/dev/null; then
            iptables -D DOCKER-USER -s "$ip" -m conntrack --ctorigdst "$LAN_SUBNET" -j DROP
            echo "Removed: DOCKER-USER block $ip -> $LAN_SUBNET"
        else
            echo "Not present (nothing to remove): DOCKER-USER block $ip -> $LAN_SUBNET"
        fi

        rule="rule family=\"ipv4\" source address=\"$ip\" destination address=\"$HOST_LAN_IP\" drop"
        if firewall-cmd --zone="$FIREWALLD_ZONE" --query-rich-rule="$rule" >/dev/null 2>&1; then
            firewall-cmd --zone="$FIREWALLD_ZONE" --permanent --remove-rich-rule="$rule" >/dev/null
            echo "Removed: firewalld rich rule (zone=$FIREWALLD_ZONE) $ip -> $HOST_LAN_IP"
        else
            echo "Not present (nothing to remove): firewalld rich rule for $ip"
        fi
    done
    firewall-cmd --reload >/dev/null
    echo "firewalld reloaded — LAN isolation removed, browsers can reach the LAN again"
}

case "$MODE" in
    apply) apply ;;
    undo) undo ;;
    *)
        echo "Usage: $0 [apply|undo]" >&2
        exit 1
        ;;
esac
