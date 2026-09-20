# Shared by probe.sh, install.sh and install-slot.sh. Sourced from the stick; callers set SRC and
# LOGS first, and DEST when Purple goes somewhere other than the running system's /usr/local.
# Design: guides/chromebook-dev-mode-plan.md
DEST="${DEST:-/usr/local/purple}"
PY="$DEST/python/bin/python3"

[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash, then bash $0"; exit 1; }
mkdir -p /usr/local/purple

log() { echo "$@" | tee -a "${LOGS[@]}"; }
# Inventory commands may fail without ending the run.
show() { log "\$ $*"; "$@" 2>&1 | tee -a "${LOGS[@]}"; }
# Anything else stops at the first failure.
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

# The stick is FAT (no exec bits, no symlinks), so Python runs from /usr/local.
install_python() {
    step cp "$SRC/libf128shim.so" "$DEST/"
    [ -x "$PY" ] || step tar -xzf "$SRC/python-x86_64.tar.gz" -C "$DEST"
    "$PY" -c "import pygame, piper, evdev, rich" 2>/dev/null && return
    step "$PY" -m pip install --no-index --find-links "$SRC/wheels" pygame-ce numpy piper-tts evdev-binary rich
}

# Purple itself, laid out the same in both stages: the launcher finds everything beside itself.
# Debug install: Exit to System in the parent menu, Ctrl+\ held 3 s leaves Purple, no keyboard grab.
install_app() {
    local voices="$DEST/home/.local/share/piper-voices" fonts="$DEST/home/.local/share/fonts"
    step mkdir -p "$DEST"
    install_python
    step rm -rf "$DEST/app"
    step mkdir -p "$DEST/app" "$DEST/logs" "$voices" "$fonts"
    step tar -xzf "$SRC/purple-app.tar.gz" -C "$DEST/app"
    step cp "$SRC"/voice/*.onnx* "$voices/"
    step mkdir -p "$DEST/bin" "$DEST/home/.local/share/flite-voices"
    step cp "$SRC"/voice/*.flitevox "$DEST/home/.local/share/flite-voices/"
    step cp "$SRC/flite" "$DEST/bin/"
    step chmod +x "$DEST/bin/flite"
    step cp "$SRC/NotoColorEmoji.ttf" "$fonts/"
    step cp "$SRC/purple-run.sh" "$DEST/"
    step touch "$DEST/debug"
    step "$PY" -m compileall -q "$DEST/app"
    check_deps
}

# Everything Purple reaches outside its own tree, from an audit of purple_tui (imports incl. lazy
# ones, subprocess calls, shutil.which). A miss is logged, not fatal: most features degrade alone.
PY_MODULES="pygame numpy evdev rich piper onnxruntime"
TOOLS_NEEDED="cras_test_client dbus-send dbus-monitor udevadm poweroff sudo timeout setsid pgrep initctl cgpt rootdev"
TOOLS_OPTIONAL="flite keyd"   # Quick voice; grave-to-Escape and RightAlt-to-F2 remaps
check_deps() {
    local name
    log "=== dependency check ==="
    for name in $PY_MODULES; do
        LD_PRELOAD="$DEST/libf128shim.so" "$PY" -c "import $name" 2>/dev/null \
            && log "ok       python: $name" || log "MISSING  python: $name"
    done
    for name in $TOOLS_NEEDED; do
        command -v "$name" >/dev/null && log "ok       tool: $name" || log "MISSING  tool: $name"
    done
    for name in $TOOLS_OPTIONAL; do
        command -v "$name" >/dev/null || [ -x "$DEST/bin/$name" ] \
            && log "ok       optional: $name" || log "absent   optional: $name"
    done
}
