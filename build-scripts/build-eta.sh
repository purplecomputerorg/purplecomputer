#!/usr/bin/env bash
# Stage timing: each build records how long its stages took, so the next one can
# say when its ISOs and Pi image will be ready. Sourced by build-all.sh.

STAGE_TIMES="$BUILD_DIR/stage-times"
BUILD_STATUS="$BUILD_DIR/build-status"

# Fast builds compress less, so they keep their own timings.
stage_key() {
    if [ "${FAST_BUILD:-0}" = "1" ]; then echo "$1-fast"; else echo "$1"; fi
}

# Seconds the stage took on its last run; a typical full-build time until then.
stage_secs() {
    local secs
    secs=$(awk -v k="$(stage_key "$1")" '$1 == k { v = $2 } END { print v }' "$STAGE_TIMES" 2>/dev/null)
    [ -n "$secs" ] && { echo "$secs"; return; }
    case "$1" in
        x86) echo 600 ;; i386) echo 540 ;; remaster) echo 240 ;; pi) echo 1920 ;;
    esac
}

stage_label() {
    case "$1" in
        x86) echo "x86 golden image" ;; i386) echo "i386 golden image" ;;
        remaster) echo "ISOs" ;; pi) echo "Raspberry Pi image" ;;
    esac
}

clock() { date -d "@$1" +%H:%M; }

# The stages this run will do, in order (START_STEP, FAST_BUILD, PURPLE_PI).
planned_stages() {
    if [ "${PURPLE_PI:-0}" = "1" ]; then echo pi; return; fi
    if [ "${START_STEP:-0}" -le 0 ]; then
        echo x86
        [ "${FAST_BUILD:-0}" = "1" ] || echo i386
    fi
    [ "${START_STEP:-0}" -le 1 ] && echo remaster
    pi_in_full_build && echo pi
    return 0
}

# Prints, and saves for 'just build-status', when each remaining stage should finish.
# Usage: print_eta <current stage>
print_eta() {
    local now t stage started=0 lines=""
    now=$(date +%s)
    t=$now
    for stage in $(planned_stages); do
        [ "$stage" = "$1" ] && started=1
        [ "$started" = 1 ] || continue
        t=$((t + $(stage_secs "$stage")))
        lines+="  $(stage_label "$stage"): about $(clock "$t") (~$(( $(stage_secs "$stage") / 60 )) min)"$'\n'
    done
    {
        echo "[$(clock "$now")] Now building: $(stage_label "$1")"
        echo "Expected done:"
        printf '%s' "$lines"
        if [ "${PURPLE_PI:-0}" = "1" ]; then
            :
        elif [ "$1" = pi ]; then
            echo "The ISOs are done: flash (just flash) or ship (just ship-oneoff) them now."
        elif pi_in_full_build; then
            echo "The ISOs don't wait for the Pi image: flash or ship them as soon as they're done."
        fi
    } | tee "$BUILD_STATUS"
}

# Usage: timed_stage <stage> <command...>
timed_stage() {
    local stage="$1" start
    shift
    print_eta "$stage"
    start=$(date +%s)
    "$@"
    echo "$(stage_key "$stage") $(( $(date +%s) - start ))" >> "$STAGE_TIMES"
}

finish_eta() {
    echo "[$(clock "$(date +%s)")] Build finished." | tee "$BUILD_STATUS"
}
