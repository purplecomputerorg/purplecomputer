#!/usr/bin/env bash
# One-time calibration: label the hub's physical sockets so flash failure
# reports can say which stick to pull ("top row 3") instead of a device node.
#
# Plug a stick into each socket you want to label, one at a time; moving one
# stick from socket to socket works. Each plug-in prompts for that socket's
# label. Labels save as you go, so Ctrl-C is always safe.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

if [[ ! -t 0 ]]; then
    log_error "label-ports is interactive; run it from a terminal."
    exit 1
fi

# Port names (e.g. 4-1.4) of every USB disk currently on the bus.
occupied_ports() {
    local name port
    while IFS= read -r name; do
        port="$(usb_port_name "/dev/$name" 2>/dev/null || true)"
        [[ -n "$port" ]] && echo "$port"
    done < <(lsblk -d -n -o NAME,TRAN 2>/dev/null | awk '$2 == "usb" {print $1}')
    return 0
}

load_port_labels
if (( ${#PORT_LABELS[@]} )); then
    echo -e "${BOLD}Current socket labels:${NC}"
    for port in "${!PORT_LABELS[@]}"; do
        printf "  %-10s %s\n" "$port" "${PORT_LABELS[$port]}"
    done
    echo
fi

echo -e "${BOLD}${YELLOW}Plug a stick into each socket you want to label, ONE at a time.${NC}"
echo "A prompt appears for each socket as its stick is detected. Sockets already"
echo "occupied now won't prompt: unplug and replug them. Ctrl-C when done."
echo

prev="$(occupied_ports | sort)"
while true; do
    sleep 0.5
    cur="$(occupied_ports | sort)"
    new="$(comm -13 <(echo "$prev") <(echo "$cur"))"
    prev="$cur"
    for port in $new; do
        current="$(port_label "$port")"
        read -r -p "Label for socket $port${current:+ (now: \"$current\")} (Enter skips, q quits): " label
        if [[ "$label" == q ]]; then
            log_info "Labels are in $(port_labels_path)."
            exit 0
        fi
        if [[ -n "$label" ]]; then
            save_port_label "$port" "$label"
            log_info "Saved: $port -> \"$label\""
        fi
    done
done
