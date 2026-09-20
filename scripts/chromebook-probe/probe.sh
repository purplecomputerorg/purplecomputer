#!/bin/bash
# Purple Chromebook probe. Run as root from the stick: sudo bash, then bash probe.sh
# Design: guides/chromebook-dev-mode-plan.md
set -u -o pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/usr/local/purple-probe
PY="$DEST/python/bin/python3"
LOGS=("$SRC/probe.log" "$DEST/probe.log")

[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash, then bash $0"; exit 1; }
mkdir -p "$DEST"

log() { echo "$@" | tee -a "${LOGS[@]}"; }
# Inventory commands may fail without ending the probe.
show() { log "\$ $*"; "$@" 2>&1 | tee -a "${LOGS[@]}"; }
# Anything else stops the probe at the first failure.
step() { show "$@" || { log "FAILED: $*"; exit 1; }; }

inventory() {
    log "=== inventory $(date) ==="
    show uname -a
    show cat /etc/lsb-release
    show crossystem hwid fwid mainfw_type dev_default_boot
    show sh -c 'ls /usr/lib64 | grep -i -E "gbm|libdrm|libEGL|libGLES|libasound"'
    show ls -l /dev/dri /dev/uinput
    show sh -c 'for c in /sys/class/drm/card?; do echo "$c: $(readlink -f $c/device/driver)"; done'
    show ls /usr/share/alsa/ucm
    show cat /proc/asound/cards
    show aplay -l
    show cat /proc/bus/input/devices
    show cgpt show "$(rootdev -s -d)"
    show df -h /usr/local
    show free -m
    show sh -c 'initctl list | grep -E "^(ui|cras|frecon|powerd|shill) "'
}

install() {
    log "=== install ==="
    step cp -r "$SRC/wheels" "$SRC/voice" "$SRC/probe.py" "$SRC/libf128shim.so" "$DEST/"
    [ -x "$PY" ] || step tar -xzf "$SRC/python-x86_64.tar.gz" -C "$DEST"
    "$PY" -c "import pygame, piper" 2>/dev/null && return
    step "$PY" -m pip install --no-index --find-links "$DEST/wheels" pygame-ce numpy piper-tts
}

finish() {
    show start cras
    show start ui
    log "=== probe finished $(date) ==="
    sync
    # Without frecon there is no terminal to come back to.
    [ -e "$DEST/frecon_killed" ] && reboot
}

# Detached phase: survives losing the terminal, always brings ChromeOS back.
detached() {
    trap finish EXIT
    rm -f "$DEST/frecon_killed"
    show stop ui
    step "$PY" -u "$DEST/probe.py"
}

if [ "${1:-}" = --detached ]; then
    detached
    exit
fi

inventory
install
sync
setsid nohup bash "$SRC/probe.sh" --detached >/dev/null 2>&1 &
echo
echo "Probe running in the background. NOW PRESS Ctrl+Alt+Back (top-row left arrow)."
echo "Watch and listen: purple screen with text, two tones, a spoken line, four more tones, then press"
echo "keys for 10 seconds. ChromeOS comes back by itself within 5 minutes; if the probe had to"
echo "take the screen by force, the machine reboots by itself instead. Do not force power off."
echo "Results: $SRC/probe.log (on the stick) and $DEST/probe.log"
