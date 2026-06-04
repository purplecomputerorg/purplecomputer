#!/bin/bash
# debug-display.sh - Diagnose the old-Intel "checkerboard" scanout artifact.
#
# Run from the parent-menu terminal (Open Terminal) on any ISO:
#   /opt/purple/scripts/debug-display.sh            # full state dump + verdict
#   /opt/purple/scripts/debug-display.sh repro      # reproduce the artifact on demand
#   /opt/purple/scripts/debug-display.sh toggle fbc off|on
#   /opt/purple/scripts/debug-display.sh toggle psr off|on
#   /opt/purple/scripts/debug-display.sh toggle tearfree off|on
#
# Why this exists: the checkerboard lives at the display-engine/scanout layer
# (it survives LIBGL_ALWAYS_SOFTWARE=1), so screenshots can't catch it and you
# can't tell from the screen whether a shipped mitigation actually took effect.
# This confirms what's active, lets you A/B the knobs at runtime (no ISO
# rebuild), and gives a reliable repro. See guides/intel-display-tuning.md.

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; NC='\033[0m'
pass() { echo -e "${GREEN}[ ACTIVE ]${NC} $1"; }
fail() { echo -e "${RED}[  OFF  ]${NC} $1"; }
warn() { echo -e "${YELLOW}[   ?   ]${NC} $1"; }
info() { echo "             $1"; }
section() { echo; echo -e "${BLUE}--- $1 ---${NC}"; }

# Passwordless sudo on the live boot; falls back cleanly if a read is denied.
priv() { sudo cat "$1" 2>/dev/null; }

# Locate the i915 debugfs node (usually dri/0, but never assume the index).
find_dri() {
    local d name
    sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null
    for d in /sys/kernel/debug/dri/*/; do
        [ -d "$d" ] || continue
        name=$(priv "$d/name")
        case "$name" in
            *i915*) echo "${d%/}"; return 0 ;;
        esac
    done
    [ -d /sys/kernel/debug/dri/0 ] && echo /sys/kernel/debug/dri/0
}

# First connected output name, for xrandr toggles / property reads.
primary_output() { xrandr 2>/dev/null | awk '/ connected/{print $1; exit}'; }

# ---------------------------------------------------------------------------
# State dump
# ---------------------------------------------------------------------------
dump() {
    local cmdline psr_p fbc_p dri out tf
    cmdline=$(cat /proc/cmdline)
    DRI=$(find_dri)

    echo "==========================================================="
    echo "  Purple Display Diagnostics  ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "==========================================================="

    section "Hardware"
    info "Model:  $(cat /sys/class/dmi/id/sys_vendor 2>/dev/null) $(cat /sys/class/dmi/id/product_name 2>/dev/null)"
    info "Board:  $(cat /sys/class/dmi/id/board_name 2>/dev/null)"
    info "GPU:    $(lspci 2>/dev/null | grep -iE 'vga|display|3d' | sed 's/^/        /' | head -3)"
    if [ -d /sys/module/i915 ]; then
        info "DRM:    i915 loaded (Intel; mitigations apply)"
    else
        warn "i915 NOT loaded: this is not an Intel-GPU machine, the i915 mitigations are no-ops here."
    fi

    section "Verdict (is each mitigation actually live?)"
    # PSR
    psr_p=$(priv /sys/module/i915/parameters/enable_psr)
    if echo "$cmdline" | grep -q 'i915.enable_psr=0' && [ "$psr_p" = "0" ]; then
        pass "PSR disabled (cmdline + module param both 0)"
    elif echo "$cmdline" | grep -q 'i915.enable_psr=0'; then
        warn "PSR: cmdline says 0 but module param reads '$psr_p' (param did NOT take)"
    else
        fail "PSR not disabled (enable_psr=$psr_p, cmdline missing i915.enable_psr=0)"
    fi
    # FBC
    fbc_p=$(priv /sys/module/i915/parameters/enable_fbc)
    if echo "$cmdline" | grep -q 'i915.enable_fbc=0' && [ "$fbc_p" = "0" ]; then
        pass "FBC disabled (cmdline + module param both 0)"
    elif echo "$cmdline" | grep -q 'i915.enable_fbc=0'; then
        warn "FBC: cmdline says 0 but module param reads '$fbc_p' (param did NOT take)"
    else
        fail "FBC not disabled (enable_fbc=$fbc_p, cmdline missing i915.enable_fbc=0)"
    fi
    # TearFree (runtime property is the ground truth, not the config file)
    out=$(primary_output)
    tf=$(xrandr --verbose 2>/dev/null | awk -v o="$out" '$1==o{f=1} f&&/TearFree:/{print $2; exit}')
    if [ "$tf" = "on" ]; then
        pass "TearFree ON for $out (modesetting composed-flip path engaged)"
    elif [ -n "$tf" ]; then
        fail "TearFree property = '$tf' for $out (config did NOT engage)"
    else
        warn "TearFree property not exposed (old xserver, or driver isn't modesetting). Check Xorg log below."
    fi

    section "Kernel cmdline"
    info "$cmdline"

    section "i915 module parameters (effective)"
    for p in enable_psr enable_fbc enable_dc enable_dpcd_backlight enable_psr2_sel_fetch; do
        local v; v=$(priv "/sys/module/i915/parameters/$p")
        [ -n "$v" ] && info "$p = $v"
    done

    section "FBC status (debugfs)"
    if [ -n "$DRI" ] && [ -e "$DRI/i915_fbc_status" ]; then
        priv "$DRI/i915_fbc_status" | sed 's/^/        /'
    else
        info "(no i915_fbc_status node)"
    fi

    section "PSR status (debugfs)"
    local psr_node
    psr_node=$(ls "$DRI"/i915_edp_psr_status "$DRI"/eDP-*/i915_psr_status 2>/dev/null | head -1)
    if [ -n "$psr_node" ]; then
        priv "$psr_node" | sed 's/^/        /'
    else
        info "(no PSR status node)"
    fi

    section "Panel depth + dithering  (the Skylake/13,2 hypothesis)"
    info "If the panel is 6bpc and the pipe is 8bpp, i915 dithers, and a brief"
    info "checkerboard on color change can be DITHER, which PSR/FBC/TearFree do"
    info "NOT fix. Look for 'bpp', 'dither', or a low 'bpc' below:"
    if [ -n "$DRI" ] && [ -e "$DRI/i915_display_info" ]; then
        priv "$DRI/i915_display_info" | grep -iE 'pipe |bpp|dither|bpc|active=yes' | sed 's/^/        /' | head -30
    fi
    info "max bpc (connector property):"
    xrandr --verbose 2>/dev/null | grep -iE 'max bpc|Broadcast RGB' | sed 's/^/        /'

    section "X driver + present path (did the right driver load?)"
    local xlog
    for xlog in /var/log/Xorg.0.log /home/purple/.local/share/xorg/Xorg.0.log "$HOME/.local/share/xorg/Xorg.0.log"; do
        if sudo test -r "$xlog" 2>/dev/null; then
            info "log: $xlog"
            priv "$xlog" | grep -iE 'using driver|modesetting|TearFree|Atomic|PageFlip|glamor' | sed 's/^/        /' | head -15
            break
        fi
    done
    info "GL renderer (expect llvmpipe; software render is intentional):"
    glxinfo 2>/dev/null | grep -iE 'OpenGL renderer' | sed 's/^/        /' || info "(glxinfo not installed)"

    echo
    echo "==========================================================="
    echo "  Saved to $REPORT"
    echo "  Next: try 'repro' to trigger it, then 'toggle ... off/on'"
    echo "  one knob at a time and re-run 'repro' to see which fixes it."
    echo "==========================================================="
}

# ---------------------------------------------------------------------------
# Live A/B toggles (no ISO rebuild). Each takes effect on the next frame.
# ---------------------------------------------------------------------------
toggle() {
    local knob="$1" state="$2"
    case "$state" in on|off) ;; *) echo "Usage: toggle <fbc|psr|tearfree> <on|off>"; exit 1 ;; esac
    DRI=$(find_dri)
    case "$knob" in
        fbc)
            local v; [ "$state" = on ] && v=1 || v=0
            echo "$v" | sudo tee /sys/module/i915/parameters/enable_fbc >/dev/null \
                && echo "FBC enable_fbc -> $v (re-run 'repro' to compare)" \
                || echo "Failed to write enable_fbc (param may be read-only on this kernel)."
            ;;
        psr)
            # debugfs psr_debug: 0 = force-disable, 1 = follow default
            local v; [ "$state" = on ] && v=1 || v=0
            local node; node=$(ls "$DRI"/i915_edp_psr_debug "$DRI"/eDP-*/i915_psr_debug 2>/dev/null | head -1)
            if [ -n "$node" ]; then
                echo "$v" | sudo tee "$node" >/dev/null && echo "PSR debug -> $v via $node"
            else
                echo "No PSR debug node found (PSR may already be fully off)."
            fi
            ;;
        tearfree)
            local out; out=$(primary_output)
            xrandr --output "$out" --set TearFree "$state" 2>&1 \
                && echo "TearFree -> $state for $out (re-run 'repro' to compare)" \
                || echo "Could not set TearFree (property not exposed by this driver/xserver)."
            ;;
        *) echo "Unknown knob '$knob'. Use fbc, psr, or tearfree." ; exit 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# On-demand repro: drive partial redraws of a few cells, exactly the music-grid
# keystroke pattern that exposes the artifact. Goes through the same
# Alacritty -> X present -> scanout path as the app.
# ---------------------------------------------------------------------------
repro() {
    if [ ! -t 0 ]; then echo "repro needs an interactive terminal (run it from Open Terminal)."; exit 1; fi
    local rows=14 cols=46 base=54   # base = a calm purple-ish 256-color
    printf '\033[2J\033[?25l'
    printf '\033[1;1H\033[1;37mCheckerboard repro: flipping a few cells per frame (partial redraw).\033[0m'
    printf '\033[2;1H\033[0;37mWatch the cells as they change color. Press any key to stop.\033[0m'
    # Initial solid fill so later flips are genuine partial updates.
    local r c
    for ((r=0; r<rows; r++)); do
        printf '\033[%d;1H' $((r+4))
        for ((c=0; c<cols; c++)); do printf '\033[48;5;%dm  ' "$base"; done
    done
    printf '\033[0m'
    trap 'printf "\033[0m\033[?25h\033[2J\033[1;1H"; exit 0' INT TERM
    local key
    while true; do
        # Flip ~6 random cells to high-contrast colors: the worst case for a
        # stale compressed/dithered block to flash through for one frame.
        for _ in 1 2 3 4 5 6; do
            r=$(( (RANDOM % rows) + 4 ))
            c=$(( (RANDOM % cols) * 2 + 1 ))
            printf '\033[%d;%dH\033[48;5;%dm  ' "$r" "$c" $(( (RANDOM % 6) * 36 + (RANDOM % 6) * 6 + 16 ))
        done
        printf '\033[0m'
        if read -rsn1 -t 0.07 key; then break; fi
    done
    printf '\033[0m\033[?25h\033[2J\033[1;1H'
    echo "Repro stopped. Tip: toggle one knob off and re-run to A/B."
}

REPORT=/tmp/purple-display-diag.txt
case "${1:-dump}" in
    dump|"") dump | tee "$REPORT" ;;
    repro)   repro ;;
    toggle)  shift; toggle "$@" ;;
    *)       echo "Usage: $0 [dump|repro|toggle <fbc|psr|tearfree> <on|off>]" ;;
esac
