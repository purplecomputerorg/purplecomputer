#!/usr/bin/env bash
# Test whether a suspect USB drive is dying, and optionally deny it.
# Usage: ./check-drive.sh [--read-only] [--deny] /dev/sdX

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/flash-lib.sh"

# A healthy 32GB stick reads 100+ MB/s over USB 3.0 and 35+ over USB 2.0.
# Dying flash lands one to two orders of magnitude below that: the failure
# that prompted this script read 1.3-2.1 MB/s. The thresholds sit well under
# a slow-but-fine drive and well over a dying one, and are compared against
# the negotiated link speed so a USB 2.0 port doesn't read as a failure.
READ_FLOOR_USB3=40
READ_FLOOR_USB2=15
WRITE_FLOOR=8
SAMPLE_MB=256
WRITE_MB=512

READ_ONLY=false
AUTO_DENY=false
DEV=""
for arg in "$@"; do
    case "$arg" in
        --read-only) READ_ONLY=true ;;
        --deny) AUTO_DENY=true ;;
        -h|--help)
            echo "Usage: $0 [--read-only] [--deny] /dev/sdX"
            echo "  --read-only  skip the destructive write test"
            echo "  --deny       append a failing drive to $(denylist_path)"
            exit 0 ;;
        *) DEV="$arg" ;;
    esac
done

[[ -z "$DEV" ]] && { log_error "Usage: $0 [--read-only] [--deny] /dev/sdX"; exit 1; }
[[ -b "$DEV" ]] || { log_error "$DEV is not a block device."; exit 1; }

read_lsblk() { lsblk -dno "$1" "$DEV" 2>/dev/null | xargs; }
SERIAL="$(read_lsblk SERIAL)"
MODEL="$(read_lsblk MODEL)"
SIZE="$(read_lsblk SIZE)"

# Refuse anything that isn't a small removable USB stick: this script writes
# random data, so a wrong device argument must not be able to eat a real disk.
[[ "$(read_lsblk TRAN)" == "usb" ]] || { log_error "$DEV is not a USB device."; exit 1; }
SIZE_BYTES="$(sudo blockdev --getsize64 "$DEV" 2>/dev/null)" || {
    log_error "$DEV has no medium. Unplug it and plug it back in."; exit 1; }
if [[ "$SIZE_BYTES" -gt "$MAX_UNLISTED_BYTES" ]]; then
    log_error "$DEV is $SIZE, too large to be a Purple Key. Refusing to test it."
    exit 1
fi

USB_PATH="$(readlink -f "/sys/block/$(basename "$DEV")" | grep -o 'usb[0-9]*/[0-9.-]*/[0-9.-]*' | head -1)"
USB_DEV="$(echo "$USB_PATH" | awk -F/ '{print $NF}')"
LINK_SPEED="$(cat "/sys/bus/usb/devices/$USB_DEV/speed" 2>/dev/null || echo 0)"
READ_FLOOR=$READ_FLOOR_USB3
[[ "${LINK_SPEED%%.*}" -lt 5000 ]] && READ_FLOOR=$READ_FLOOR_USB2

echo ""
echo -e "${BOLD}Drive under test${NC}"
echo "  device:     $DEV"
echo "  model:      $MODEL ($SIZE)"
echo "  serial:     $SERIAL"
echo "  usb path:   $USB_PATH"
echo "  link speed: ${LINK_SPEED} Mbps"
is_denied "$SERIAL" && log_warn "Already on the denylist: $DENY_REASON"
ALREADY_DENIED="$DENY_REASON"
if [[ "${LINK_SPEED%%.*}" -lt 5000 ]]; then
    log_warn "Negotiated USB 2.0. If this is a USB 3 port, the drive may be failing to train SuperSpeed."
fi

FAILURES=()
note_failure() { FAILURES+=("$1"); echo -e "  ${RED}FAIL${NC}  $1"; }
note_pass() { echo -e "  ${GREEN}OK${NC}    $1"; }

# dd's rate is the last comma-separated field of its summary line.
dd_rate_mb() {
    local out
    out="$("$@" 2>&1 | tr '\r' '\n' | grep -a "copied" | tail -1 || true)"
    echo "$out" | sed 's/.*, //' | awk '{ if ($2 ~ /^GB/) print $1 * 1024; else if ($2 ~ /^kB/) print $1 / 1024; else print $1 }'
}

drop_caches() { sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true; }

echo ""
echo -e "${BOLD}1. Read throughput${NC} (${SAMPLE_MB}MB, floor ${READ_FLOOR} MB/s)"
drop_caches
READ_RATE="$(dd_rate_mb sudo dd if="$DEV" bs=4M count=$((SAMPLE_MB / 4)) iflag=direct of=/dev/null)"
READ_RATE="${READ_RATE:-0}"
printf "  measured: %s MB/s\n" "$READ_RATE"
if awk -v r="$READ_RATE" -v f="$READ_FLOOR" 'BEGIN { exit !(r < f) }'; then
    note_failure "read throughput ${READ_RATE} MB/s is below ${READ_FLOOR} MB/s"
else
    note_pass "read throughput"
fi

if [[ "$READ_ONLY" == true ]]; then
    echo ""
    log_info "Read-only mode: skipping the write test."
else
    echo ""
    echo -e "${BOLD}2. Sustained write + verify${NC} (${WRITE_MB}MB, floor ${WRITE_FLOOR} MB/s)"
    echo -e "  ${YELLOW}This ERASES the start of $DEV.${NC}"
    if [[ ! -t 0 ]]; then
        log_error "Not a terminal; re-run with --read-only or from an interactive shell."
        exit 1
    fi
    read -p "  Type ERASE to continue: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        log_error "Aborted."
        exit 1
    fi

    PATTERN="$(mktemp -t check-drive.XXXXXX)"
    trap 'rm -f "$PATTERN"' EXIT
    dd if=/dev/urandom of="$PATTERN" bs=1M count="$WRITE_MB" status=none

    for part in "$DEV"?*; do sudo umount "$part" 2>/dev/null || true; done

    WRITE_RATE="$(dd_rate_mb sudo dd if="$PATTERN" of="$DEV" bs=4M count=$((WRITE_MB / 4)) conv=fsync oflag=sync)"
    WRITE_RATE="${WRITE_RATE:-0}"
    printf "  measured: %s MB/s\n" "$WRITE_RATE"
    if awk -v r="$WRITE_RATE" -v f="$WRITE_FLOOR" 'BEGIN { exit !(r < f) }'; then
        note_failure "write throughput ${WRITE_RATE} MB/s is below ${WRITE_FLOOR} MB/s"
    else
        note_pass "write throughput"
    fi

    sync
    sudo blockdev --flushbufs "$DEV" 2>/dev/null || true
    sleep 10
    drop_caches
    expected="$(sha256sum "$PATTERN" | awk '{print $1}')"
    actual="$(sudo dd if="$DEV" bs=4M count=$((WRITE_MB / 4)) iflag=direct status=none | sha256sum | awk '{print $1}')"
    if [[ "$expected" != "$actual" ]]; then
        note_failure "readback does not match what was written (silent corruption)"
    else
        note_pass "readback integrity"
    fi

    # Unique pattern per offset: an identical pattern everywhere would still
    # verify on a fake-capacity drive that wraps writes back to the start.
    echo ""
    echo -e "${BOLD}3. Capacity${NC} (unique 4MB pattern at 8 offsets)"
    span_mb=$(( SIZE_BYTES / 1048576 - 8 ))
    bad_offsets=0
    for i in 0 1 2 3 4 5 6 7; do
        off=$(( span_mb * i / 8 ))
        dd if=/dev/urandom of="$PATTERN.$i" bs=1M count=4 status=none
        sudo dd if="$PATTERN.$i" of="$DEV" bs=1M seek="$off" count=4 oflag=direct status=none
    done
    sync; sudo blockdev --flushbufs "$DEV" 2>/dev/null || true; sleep 5
    drop_caches
    for i in 0 1 2 3 4 5 6 7; do
        off=$(( span_mb * i / 8 ))
        e="$(sha256sum "$PATTERN.$i" | awk '{print $1}')"
        a="$(sudo dd if="$DEV" bs=1M skip="$off" count=4 iflag=direct status=none | sha256sum | awk '{print $1}')"
        [[ "$e" != "$a" ]] && bad_offsets=$((bad_offsets + 1))
        rm -f "$PATTERN.$i"
    done
    if [[ "$bad_offsets" -gt 0 ]]; then
        note_failure "$bad_offsets of 8 offsets did not read back (bad blocks or fake capacity)"
    else
        note_pass "capacity and block integrity"
    fi
fi

echo ""
if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}PASS${NC} - $DEV ($SERIAL) looks healthy."
    [[ "$READ_ONLY" == true ]] && log_info "Read-only run: writes were not tested. Re-run without --read-only to be sure."
    exit 0
fi

echo -e "${BOLD}${RED}FAIL${NC} - $DEV ($SERIAL) is bad:"
for f in "${FAILURES[@]}"; do echo "  - $f"; done
echo ""
if [[ -n "$ALREADY_DENIED" ]]; then
    log_info "Already denied. Bin the drive."
    exit 1
fi
if [[ "$AUTO_DENY" != true ]]; then
    echo "Re-run with --deny to add it to $(denylist_path), or add this line yourself:"
    echo "  $SERIAL  # ${FAILURES[0]} ($(date +%Y-%m-%d))"
    exit 1
fi
printf '%s  # %s (%s)\n' "$SERIAL" "${FAILURES[0]}" "$(date +%Y-%m-%d)" >> "$(denylist_path)"
log_info "Added $SERIAL to $(denylist_path). Bin the drive."
exit 1
