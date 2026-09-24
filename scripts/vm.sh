#!/usr/bin/env bash
# A pretend laptop: UEFI firmware (Esc at power-on for setup), a USB port, a
# CD drive and a blank disk that persists across runs. Screen in a browser
# (noVNC over QEMU's VNC websocket) or any VNC viewer.
#
# Usage: scripts/vm.sh <command> [args]
#   start [ref] [--release] [--debug|--backup] [--cd] [--legacy] [--empty] [--fresh]
#   insert [ref] [--release] [--debug|--backup] [--cd]
#   eject | stop | key <keys...> | shot
#
#   ref        a built commit on any branch (default: the newest build);
#              --release means the build of release/1.x HEAD
#   --cd       put the ISO in the CD drive instead of plugging it in as a USB
#              stick (Purple ISOs are made for USB; GRUB stops at a prompt)
#   --legacy   legacy BIOS (SeaBIOS, F12 boot menu) instead of UEFI
#   --empty    power on with nothing inserted
#   --fresh    wipe the disk and firmware settings first
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/build-scripts/config.sh"
source "$PROJECT_DIR/build-scripts/flash-lib.sh"

VM_DIR="${PURPLE_VM_DIR:-$HOME/.cache/purple-vm}"
MON="$VM_DIR/monitor.sock"
FW="$(dirname "$(readlink -f "$(command -v qemu-system-x86_64)")")/../share/qemu"
VNC_HOST="${PURPLE_VM_VNC_HOST:-$(tailscale ip -4 2>/dev/null | head -1 || true)}"
VNC_HOST="${VNC_HOST:-127.0.0.1}"

REF="" VARIANT=standard USB=1 LEGACY=0 EMPTY=0 FRESH=0
parse_args() {
    for arg in "$@"; do
        case "$arg" in
            --release) REF=release/1.x ;;
            --debug|--standard|--backup) VARIANT="${arg#--}" ;;
            --cd) USB=0 ;;
            --legacy) LEGACY=1 ;;
            --empty) EMPTY=1 ;;
            --fresh) FRESH=1 ;;
            -*) log_error "Unknown option: $arg"; exit 1 ;;
            *) REF="$arg" ;;
        esac
    done
}

mon() { echo "$*" | socat - "UNIX-CONNECT:$MON" | tr -d '\r' | grep -v -e '^QEMU' -e '^(qemu)' || true; }
running() { [[ -S "$MON" ]] && socat -u OPEN:/dev/null "UNIX-CONNECT:$MON" 2>/dev/null; }
need_running() { running || { log_error "VM is not running; start it with 'just vm'."; exit 1; }; }

resolve_iso() {
    if [[ -n "$REF" ]]; then
        use_build_of_ref "$REF" || { log_error "Cannot resolve git commit '$REF'"; exit 1; }
    fi
    ISO="$(list_build_isos | filter_variant "$VARIANT" | head -1)"
    [[ -n "$ISO" ]] || { log_error "No $VARIANT ISO found $(build_source_label)."; echo "Build it with 'just build${REF:+ --ref $REF}'."; exit 1; }
    log_info "$(basename "$ISO")  [$(iso_commit "$ISO")]"
}

insert() {
    resolve_iso
    if [[ "$USB" == 1 ]]; then
        mon "device_del usbstick" >/dev/null; mon "drive_del usbdrive" >/dev/null
        mon "drive_add 0 if=none,id=usbdrive,format=raw,readonly=on,file=$ISO" >/dev/null
        mon "device_add usb-storage,id=usbstick,drive=usbdrive,bus=xhci.0,removable=on,bootindex=0" >/dev/null
    else
        mon "change cd0 $ISO raw read-only"
    fi
}

start() {
    running && { log_error "VM is already running; 'just vm-stop' first."; exit 1; }
    mkdir -p "$VM_DIR"
    [[ "$FRESH" == 1 ]] && rm -f "$VM_DIR/disk.qcow2" "$VM_DIR/vars.fd"
    [[ -f "$VM_DIR/disk.qcow2" ]] || qemu-img create -q -f qcow2 "$VM_DIR/disk.qcow2" 32G
    [[ -f "$VM_DIR/vars.fd" ]] || install -m 644 "$FW/edk2-i386-vars.fd" "$VM_DIR/vars.fd"
    local firmware=()
    [[ "$LEGACY" == 1 ]] || firmware=(
        -drive "if=pflash,format=raw,readonly=on,file=$FW/edk2-x86_64-code.fd"
        -drive "if=pflash,format=raw,file=$VM_DIR/vars.fd")
    qemu-system-x86_64 -name purple-vm -enable-kvm -machine q35 -cpu host -smp 2 -m 4G \
        "${firmware[@]}" \
        -drive "id=hd,if=none,file=$VM_DIR/disk.qcow2" -device ide-hd,drive=hd,bus=ide.0 \
        -drive id=cd0,if=none,media=cdrom -device ide-cd,drive=cd0,bus=ide.1 \
        -device qemu-xhci,id=xhci -nic none \
        -audiodev none,id=snd -device intel-hda -device hda-duplex,audiodev=snd \
        -vnc "$VNC_HOST:0,password=on,websocket=on" -monitor "unix:$MON,server,nowait" \
        -S -daemonize -pidfile "$VM_DIR/pid"
    # Powered on paused, then reset, so the firmware's first device scan sees the inserted media.
    [[ "$EMPTY" == 1 ]] || insert
    # macOS Screen Sharing refuses VNC servers without a password.
    mon "set_password vnc ${PURPLE_VM_VNC_PASSWORD:-purple}" >/dev/null
    mon system_reset >/dev/null; mon cont
    start_viewer
    log_info "Screen: http://$VNC_HOST:5800/  (or vnc://$VNC_HOST:5900, password ${PURPLE_VM_VNC_PASSWORD:-purple}); Esc now for firmware setup"
}

start_viewer() {
    kill -0 "$(cat "$VM_DIR/viewer.pid" 2>/dev/null)" 2>/dev/null && return
    nohup "$PROJECT_DIR/.venv/bin/python" -m http.server 5800 --bind "$VNC_HOST" \
        --directory "$SCRIPT_DIR/vm-viewer" >/dev/null 2>&1 &
    echo $! > "$VM_DIR/viewer.pid"
}

key() {
    need_running
    for k in "$@"; do mon "sendkey $k" >/dev/null; sleep 0.1; done
}

shot() {
    need_running
    local dir="${PURPLE_SCREENSHOT_DIR:-/tmp/screenshots}" out
    mkdir -p "$dir"
    out="$dir/vm-$(date +%Y%m%d-%H%M%S).png"
    mon "screendump $out -f png" >/dev/null
    echo "$out"
}

cmd="${1:-start}"; shift || true
[[ "$cmd" == key ]] && { key "$@"; exit; }
parse_args "$@"
case "$cmd" in
    start) start ;;
    insert) need_running; insert ;;
    eject) need_running; mon "eject -f cd0" >/dev/null; mon "device_del usbstick" >/dev/null ;;
    stop) running && mon quit; kill "$(cat "$VM_DIR/viewer.pid" 2>/dev/null)" 2>/dev/null || true; rm -f "$MON" "$VM_DIR/viewer.pid" ;;
    shot) shot ;;
    *) sed -n '5,16p' "$0"; exit 1 ;;
esac
