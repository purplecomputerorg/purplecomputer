#!/usr/bin/env bash
# Live status of a flash-all run, by physical slot label. Reads the run's
# log/state dir under /tmp (newest by default, or pass one); safe to run any
# time, touches nothing.
#
# Final verdicts (SHIP READY / FAILED) come from the run's result files.
# After the write passes, the stage comes from flash-all's stage files;
# before it, from the per-drive log. "written+verified" is real, but a drive
# only becomes SHIP READY after the post-settle re-verify and eject.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

LOG_DIR="${1:-$(ls -dt /tmp/purple-flash-all.*/ 2>/dev/null | head -1)}"
LOG_DIR="${LOG_DIR%/}"
if [[ -z "$LOG_DIR" || ! -d "$LOG_DIR" ]]; then
    log_error "No flash-all run found under /tmp (and none given)."
    exit 1
fi
STATE_DIR="$LOG_DIR/state"

# Slot label for a device currently on the bus, else empty.
live_slot() {
    local port
    port="$(usb_port_name "$1" 2>/dev/null || true)"
    [[ -z "$port" ]] || port_label "$port"
}

# Newest attempt log for a drive stem (sda -> sda.try2.log over sda.log).
newest_log() { { ls -t "$LOG_DIR/$1".try*.log "$LOG_DIR/$1.log" 2>/dev/null || true; } | head -1; }

# FINAL[stem] = "status|tries|slot" from result files, keyed by the stem of
# the log path so it matches how mid-run rows are keyed.
declare -A FINAL
for f in "$STATE_DIR"/result.*; do
    [[ -f "$f" ]] || continue
    IFS='|' read -r status dev tries lg slot < "$f"
    stem="$(basename "${lg:-$dev}")"; stem="${stem%.log}"; stem="${stem%.try*}"
    [[ -n "$slot" ]] || slot="$(live_slot "$dev")"
    FINAL["$stem"]="$status|$tries|$slot"
done

READY=0; FAILED=0; WORKING=0
ROWS=()
declare -A SEEN
for f in "$LOG_DIR"/*.log; do
    stem="$(basename "$f" .log)"
    [[ "$stem" == *.boot-settle ]] && continue
    stem="${stem%.try*}"
    [[ -n "${SEEN[$stem]:-}" ]] && continue
    SEEN["$stem"]=1

    if [[ -n "${FINAL[$stem]:-}" ]]; then
        IFS='|' read -r status tries slot <<< "${FINAL[$stem]}"
        if [[ "$status" == ok ]]; then
            txt="${GREEN}SHIP READY${NC} (verified, ejected$( (( tries > 1 )) && echo ", after retry" || true))"
            READY=$((READY + 1))
        else
            txt="${RED}FAILED${NC} after $tries attempt(s), do NOT ship"
            FAILED=$((FAILED + 1))
        fi
    else
        WORKING=$((WORKING + 1))
        slot="$(live_slot "/dev/$stem")"
        log="$(newest_log "$stem")"
        stage="$(cat "$STATE_DIR/stage.$stem" 2>/dev/null || true)"
        if grep -aq "VERIFICATION PASSED" "$log" 2>/dev/null; then
            txt="${YELLOW}written+verified${NC}; ${stage:-waiting to settle}, not final yet"
        elif grep -aq "Verifying write" "$log" 2>/dev/null; then
            txt="verifying write (reading back)"
        else
            prog="$(tr '\r' '\n' < "$log" 2>/dev/null | grep -a "copied" | tail -1 | sed -E 's/^[0-9]+ bytes \(([^,)]*)[^)]*\) copied,/\1 done,/' || true)"
            txt="flashing${prog:+: $prog}"
        fi
        [[ "$log" == *.try*.log ]] && txt="$txt (retry)"
    fi
    ROWS+=("${slot:-?}|/dev/$stem|$txt")
done

if (( ${#ROWS[@]} == 0 )); then
    log_error "No per-drive logs in $LOG_DIR yet."
    exit 1
fi

echo -e "${BOLD}Run: $LOG_DIR${NC}"
printf "  %-12s %-10s %b\n" "SLOT" "DEVICE" "STATUS"
echo "  ------------------------------------------------------------------"
while IFS='|' read -r slot dev txt; do
    printf "  %-12s %-10s %b\n" "$slot" "$dev" "$txt"
done < <(printf '%s\n' "${ROWS[@]}" | sort)
echo
echo -e "  ${GREEN}$READY ship-ready${NC}, ${RED}$FAILED failed${NC}, $WORKING still working."
(( WORKING )) && echo -e "  ${YELLOW}Only SHIP READY is final: a working drive still has settle, re-verify, and eject ahead.${NC}"
exit 0
