#!/bin/bash
# Runs Purple on the bare kernel display of a Developer Mode Chromebook. Everything it needs
# sits beside this file. Run as root.
#   bash purple-run.sh          stage 1, from a shell: stops Chrome, brings ChromeOS back after
#   bash purple-run.sh --job    stage 2, the upstart job in Purple's own boot slot
# PURPLE_MAX_SECONDS=120 ends Purple after that long (a safety net for first runs).
# Design: guides/chromebook-dev-mode-plan.md
set -u
DEST="$(cd "$(dirname "$0")" && pwd)"
RUN_LOG="$DEST/logs/run.log"
UI_READY=/tmp/purple-ui-ready

[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash, then bash $0"; exit 1; }

save_logs() {
    cp /tmp/purple-*.log "$DEST/logs/" 2>/dev/null
    stick="$(cat "$DEST/stick-path" 2>/dev/null)"
    [ -d "$stick" ] && mkdir -p "$stick/logs" && cp "$DEST"/logs/* "$stick/logs/" 2>/dev/null
    sync
}

# The way back to a shell: Chrome returns, and with it the Ctrl+Alt+Forward console.
back_to_chromeos() {
    save_logs
    start frecon
    start ui
    echo "=== finished $(date) ==="
    # No console to come back to: a reboot restores it.
    pgrep -x frecon >/dev/null || reboot
}

run_purple() {
    echo "=== starting $(date) ==="
    export HOME="$DEST/home" PURPLE_DISPLAY=kms SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=alsa
    export PURPLE_DEBUG_FLAG="$DEST/debug" PYGAME_HIDE_SUPPORT_PROMPT=1 PATH="$DEST/bin:$PATH"
    # ChromeOS's glibc lacks strfromf128, which onnxruntime (piper) references.
    export LD_PRELOAD="$DEST/libf128shim.so"
    [ -w "$HOME" ] || echo "WARNING: $HOME is not writable, settings will not save"
    cd "$DEST/app" || return 1
    timeout "${PURPLE_MAX_SECONDS:-0}" "$DEST/python/bin/python3" -m purple_tui
    echo "purple exited: $?"
}

# Firmware gives a new slot one try; a slot that reached the UI is marked good so it keeps booting.
# Chrome normally announces the login prompt, which the rest of ChromeOS's boot waits for.
when_ui_is_up() {
    for _ in $(seq 120); do
        if [ -e "$UI_READY" ]; then
            cgpt add -i 6 -S 1 "$(rootdev -s -d)" && echo "slot marked good"
            initctl emit --no-wait login-prompt-visible
            return
        fi
        sleep 1
    done
    echo "UI never came up"
}

mkdir -p "$DEST/logs"
rm -f "$UI_READY"
case "${1:-}" in
--job)
    exec >>"$RUN_LOG" 2>&1
    start cras
    when_ui_is_up &
    run_purple
    # A locked install exits here and upstart respawns Purple. A debug one hands over to
    # ChromeOS's UI and stays "running" so the respawn does not fight it.
    [ -e "$DEST/debug" ] || exit 1
    back_to_chromeos
    exec sleep infinity
    ;;
--detached)
    trap back_to_chromeos EXIT
    stop ui
    run_purple
    ;;
*)
    setsid nohup bash "$0" --detached >"$RUN_LOG" 2>&1 &
    echo "Purple is starting. To leave it, hold Ctrl+\\ for 3 seconds. Do not force power off."
    ;;
esac
