#!/bin/bash
# Purple Computer: post-boot audio diagnostic dump.
#
# Fires once per boot, ~12s after purple-x11.service starts (giving the TUI's
# mixer warmup retry chain 0.5+1+2s and the first 5s retry-poll tick time to
# land), and writes a snapshot to /var/log/purple/audio-<boot-id-prefix>.log.
#
# Read-only. Does NOT touch audio state, open any PCM device, spawn pulseaudio,
# or call pactl in a way that could autospawn a daemon. Safe to run alongside
# everything; will never wedge audio or race purple_tui's own probes.
#
# Keeps the 10 most recent boot dumps so broken-boot post-mortems don't need
# live shells or repro.
set +e

LOG_DIR=/var/log/purple
mkdir -p "$LOG_DIR"

BOOT_ID=$(tr -d - < /proc/sys/kernel/random/boot_id 2>/dev/null)
BOOT_ID=${BOOT_ID:0:8}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/audio-${STAMP}-${BOOT_ID}.log"

# Prune to the 10 newest audio-*.log files.
ls -1t "$LOG_DIR"/audio-*.log 2>/dev/null | tail -n +11 | xargs -r rm -f

# All stdout/stderr below goes to the log file.
exec >"$LOG" 2>&1

section() { echo; echo "===== $* ====="; }

echo "purple-audio-dump $(date -Iseconds) boot=$BOOT_ID"
echo "uname: $(uname -a)"

section "asound cards"
cat /proc/asound/cards 2>/dev/null

section "dmesg audio (hda/codec/sof)"
dmesg 2>/dev/null | grep -iE 'hda|codec|snd_sof|sof-audio' | tail -80

section "pulse config on disk"
ls -la /etc/pulse/default.pa.d/ 2>&1
echo "--- grep load-module module-switch-on-connect in /etc/pulse ---"
grep -rn module-switch-on-connect /etc/pulse/ 2>&1

section "systemd user unit symlinks (purple)"
ls -la /etc/systemd/user/sockets.target.wants/ /etc/systemd/user/default.target.wants/ 2>&1

section "purple runtime dirs"
ls -la /run/user/1000/pulse/ 2>/dev/null
ls -la /home/purple/.config/pulse/ 2>/dev/null

section "purple-x11 process env"
PID=$(pgrep -f purple_tui | head -1)
if [ -n "$PID" ]; then
    echo "purple_tui pid: $PID"
    tr '\0' '\n' < /proc/$PID/environ | grep -E '^(SDL|PULSE|XDG|DBUS|HOME|USER)=' | sort
else
    echo "(purple_tui not running)"
fi

section "pulseaudio.socket status (purple user)"
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    systemctl --user status pulseaudio.socket --no-pager 2>&1
section "pulseaudio.service status (purple user)"
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    systemctl --user status pulseaudio.service --no-pager 2>&1

section "user journal for pulseaudio.service this boot"
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    journalctl --user -u pulseaudio.service -b --no-pager 2>&1

section "user journal for pulseaudio.service PREVIOUS boot (if persistent)"
# Requires /var/log/journal to exist (enabled in the golden image). On live
# boots the overlay is tmpfs, so -b -1 just returns nothing. That's fine.
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    journalctl --user -u pulseaudio.service -b -1 --no-pager 2>&1

section "pactl info (purple user, no autospawn)"
# --no-autospawn: never start a new daemon just to query. We want to see the
# real state, not accidentally fix it.
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    pactl --no-autospawn info 2>&1
section "pactl list short sinks"
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 \
    pactl --no-autospawn list short sinks 2>&1

section "purple boot heartbeat (audio-related)"
grep -iE 'mixer|audio|pulse|hotplug' /var/log/purple/boot.log 2>/dev/null | tail -40

echo
echo "===== END $(date -Iseconds) ====="
