#!/usr/bin/env bash
# Blink a hub socket's LED (by toggling port power) to find a stick by eye.
# Usage: blink-port.sh </dev/sdX | port name like 4-1.4>
# Each blink power-cycles the socket, so only point it at a stick whose
# contents no longer matter (a failed flash, or one about to be reflashed).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

arg="${1:-}"
if [[ -z "$arg" ]]; then
    echo "Usage: $0 </dev/sdX | port name like 4-1.4>"
    exit 1
fi

if [[ "$arg" == /dev/* ]]; then
    port="$(usb_port_name "$arg" || true)"
    if [[ -z "$port" ]]; then
        log_error "$arg is not a USB device (or is gone from the bus)."
        exit 1
    fi
else
    port="$arg"
fi

ctrl="$(port_control_path "$port" || true)"
if [[ -z "$ctrl" ]]; then
    log_error "No per-port power control for socket $port; this hub (or port) can't blink."
    exit 1
fi

# Captured before blinking: the power cycling drops the original device node.
serial=""
[[ "$arg" == /dev/* ]] && serial="$(lsblk -d -n -o SERIAL "$arg" 2>/dev/null | xargs || true)"

sudo -v
blink_port_until_enter "$ctrl" "Blinking socket $(describe_port "$port")... press Enter to stop: "

if [[ -n "$serial" ]]; then
    newdev="$(dev_for_serial "$serial" 30 || true)"
    if [[ -n "$newdev" && "$newdev" != "$arg" ]]; then
        log_info "Drive came back as $newdev (was $arg) after the power cycling."
    fi
fi
