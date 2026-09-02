#!/usr/bin/env bash
# Blink hub socket LEDs to find sticks by eye.
#
# No arguments: tour every USB stick one at a time, flashing its activity LED
# with read pulses while printing its /dev name and socket label. Safe on any
# stick: no power cycling, so /dev names stay put and contents are untouched.
#
# With </dev/sdX | socket like 4-1.4 or 1.4>: blink that one socket by toggling
# port power. Each blink power-cycles the socket, so only point it at a stick
# whose contents no longer matter (a failed flash, or one about to be
# reflashed).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

arg="${1:-}"
if [[ -z "$arg" ]]; then
    names=() descs=() ports=()
    while IFS= read -r line; do
        eval "$line"
        [[ "$TRAN" == "usb" && "$TYPE" == "disk" ]] || continue
        [[ -n "$SIZE" && "$SIZE" -gt "$MAX_UNLISTED_BYTES" ]] && continue
        names+=("$NAME")
        descs+=("$(awk -v b="$SIZE" 'BEGIN{printf "%.1fG", b/1e9}') $(echo "$MODEL" | xargs)")
        ports+=("$(usb_port_name "/dev/$NAME" 2>/dev/null || echo '?')")
    done < <(lsblk -d -n -b -o NAME,SIZE,MODEL,TRAN,TYPE -P 2>/dev/null)
    if (( ! ${#names[@]} )); then
        log_error "No USB disks on the bus."
        exit 1
    fi

    echo -e "${BOLD}USB sticks on the bus:${NC}"
    for i in "${!names[@]}"; do
        printf "  %-10s %-28s socket %s\n" "/dev/${names[$i]}" "${descs[$i]}" "$(describe_port "${ports[$i]}")"
    done
    load_port_labels
    present=" $(for p in "${ports[@]}"; do port_key "$p"; done | paste -sd' ') "
    for key in "${!PORT_LABELS[@]}"; do
        [[ "$present" == *" $key "* ]] || \
            echo -e "  ${YELLOW}socket $(describe_port "$(resolve_port_name "$key")") has no device; power-blink it with 'just blink $key'${NC}"
    done
    echo
    sudo -v
    for i in "${!names[@]}"; do
        dev="/dev/${names[$i]}"
        sock="$(describe_port "${ports[$i]}")"
        # A wedged stick reads nothing, so read pulses would blink nothing;
        # probe first and offer the power blink instead of sitting there dark.
        if sudo dd if="$dev" of=/dev/null bs=1M count=1 iflag=direct status=none 2>/dev/null; then
            blink_dev_reads_until_enter "$dev" \
                "Blinking $dev, socket $sock... Enter for next, q+Enter to stop: "
        else
            read -r -p "$dev (socket $sock) is unreadable, so its LED can't pulse. p+Enter power-blinks the socket (only if its contents no longer matter), Enter skips: "
            if [[ "$REPLY" == p ]]; then
                ctrl="$(port_control_path "${ports[$i]}" || true)"
                if [[ -n "$ctrl" ]]; then
                    blink_port_until_enter "$ctrl" "Blinking socket $sock by power (socket label stays; its /dev/sdX name may change)... Enter to stop: "
                else
                    log_error "No per-port power control for socket ${ports[$i]}."
                fi
            fi
        fi
        [[ "$REPLY" == q ]] && break
    done
    exit 0
fi

if [[ "$arg" == /dev/* ]]; then
    port="$(usb_port_name "$arg" || true)"
    if [[ -z "$port" ]]; then
        log_error "$arg is not a USB device (or is gone from the bus)."
        exit 1
    fi
else
    port="$(resolve_port_name "$arg")"
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
