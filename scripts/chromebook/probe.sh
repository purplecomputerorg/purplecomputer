#!/bin/bash
# Purple Chromebook probe. Run as root from the stick: sudo bash, then bash probe.sh
# Design: guides/chromebook-dev-mode-plan.md
set -u -o pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
LOGS=("$SRC/probe.log" /usr/local/purple/probe.log)
. "$SRC/common.sh"
PROBE="$DEST/probe"

install() {
    log "=== install ==="
    install_python
    step mkdir -p "$PROBE"
    step cp -r "$SRC/voice" "$SRC/probe.py" "$SRC/kms.py" "$PROBE/"
}

finish() {
    show start cras
    show start ui
    log "=== probe finished $(date) ==="
    sync
    # Without frecon there is no terminal to come back to.
    [ -e "$PROBE/frecon_killed" ] && reboot
}

# Detached phase: survives losing the terminal, always brings ChromeOS back.
detached() {
    trap finish EXIT
    rm -f "$PROBE/frecon_killed"
    show stop ui
    step "$PY" -u "$PROBE/probe.py"
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
echo "Results: $SRC/probe.log (on the stick) and ${LOGS[1]}"
