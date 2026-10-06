#!/bin/bash
# Host network self-heal for the poly-poly-bot VM. Runs every minute from
# net-watchdog.timer, as root, OUTSIDE the container.
#
# Why it exists (2026-10-04 10:20 UTC): systemd-networkd hit a netlink timeout
# re-applying the DHCP address ("ens4: Could not set DHCPv4 address: Connection
# timed out"), marked ens4 Failed, and never tried again. The box sat with no
# route for 49 hours: metadata server unreachable, IAP SSH refused, the bot
# blind (the live guard disarmed real money after 68 minutes). Nothing on the
# host ever retries a Failed link, so this does.
#
# The ladder, by consecutive failed minutes:
#   3  networkctl reconfigure <nic>     (the exact state networkd gave up in)
#   6  systemctl restart systemd-networkd
#   15 reboot, only if the box has been up 30+ minutes (no reboot loop)
# A healthy check resets the count. Every action is written to the journal and
# to /dev/kmsg, so it shows in the serial console even while SSH is dead.

STATE=${NET_WATCHDOG_STATE:-/run/net-watchdog.fails}

say() {
    logger -t net-watchdog "$*"
    { echo "net-watchdog: $*" > /dev/kmsg; } 2>/dev/null || true
}

nic=$(ip -o -4 route show default 2>/dev/null | awk '{print $5; exit}')
[ -n "$nic" ] || nic=$(ls /sys/class/net | grep -E '^(ens|eth|enp)' | head -1)

healthy() {
    ip -4 route show default 2>/dev/null | grep -q . || return 1
    curl -sf -m 5 -o /dev/null -H 'Metadata-Flavor: Google' \
        http://169.254.169.254/computeMetadata/v1/instance/id
}

if healthy; then
    if [ -s "$STATE" ]; then
        say "network healthy again after $(cat "$STATE") failed checks"
        rm -f "$STATE"
    fi
    exit 0
fi

fails=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$fails" > "$STATE"
say "check $fails failed (nic=$nic, default route: $(ip -4 route show default | head -1 || true))"

case "$fails" in
    3)  say "networkctl reconfigure $nic"
        networkctl reconfigure "$nic" 2>&1 | logger -t net-watchdog ;;
    6)  say "restarting systemd-networkd"
        systemctl restart systemd-networkd 2>&1 | logger -t net-watchdog ;;
esac

if [ "$fails" -ge 15 ]; then
    up=$(cut -d. -f1 /proc/uptime)
    if [ "$up" -ge 1800 ]; then
        say "network dead for $fails minutes; rebooting (uptime ${up}s)"
        systemctl reboot
    else
        say "network dead for $fails minutes but uptime ${up}s < 1800s; not rebooting again"
    fi
fi
