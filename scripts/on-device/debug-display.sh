#!/bin/bash
# debug-display.sh - Diagnose the old-Intel "checkerboard" scanout artifact.
#
# Run from the parent-menu terminal (Open Terminal) on any ISO:
#   /opt/purple/scripts/debug-display.sh               # full state dump + verdict
#   /opt/purple/scripts/debug-display.sh repro         # reproduce the artifact on demand
#   /opt/purple/scripts/debug-display.sh compositor off|on|status   # the runtime A/B lever
#
# What we learned (see guides/intel-display-tuning.md):
#   - The artifact is a present-path TEAR: the panel scans out a half-updated
#     frame (old content + new content) during transitions. It survives
#     LIBGL_ALWAYS_SOFTWARE=1 because it's at scanout, not in the rendered frame.
#   - PSR/FBC-off don't fix a tear, and the modesetting driver has NO TearFree
#     option, so that mitigation was always a no-op. The fix is a vsync
#     compositor (picom) that presents whole frames.
#   - PSR/FBC are read-only kernel knobs at runtime (you can't toggle them from
#     here without a rebuild), but the compositor is a plain user process: start
#     and stop it freely, no root, to A/B the actual fix.

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; NC='\033[0m'
pass() { echo -e "${GREEN}[ ACTIVE ]${NC} $1"; }
fail() { echo -e "${RED}[  OFF  ]${NC} $1"; }
warn() { echo -e "${YELLOW}[   ?   ]${NC} $1"; }
info() { echo "             $1"; }
section() { echo; echo -e "${BLUE}--- $1 ---${NC}"; }

# Passwordless sudo? Used only to read debugfs. Everything that drives the
# verdict (module params, Xorg log, xrandr, the compositor) is readable without
# it, so a no-sudo terminal still gives a trustworthy answer.
sudo -n true 2>/dev/null && HAVE_SUDO=1 || HAVE_SUDO=0
priv() { [ "$HAVE_SUDO" = 1 ] && sudo cat "$1" 2>/dev/null; }
rd() { cat "$1" 2>/dev/null; }

find_dri() {
    local d name
    [ "$HAVE_SUDO" = 1 ] && sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null
    for d in /sys/kernel/debug/dri/*/; do
        [ -d "$d" ] || continue
        case "$(priv "$d/name")" in *i915*) echo "${d%/}"; return 0 ;; esac
    done
    [ -d /sys/kernel/debug/dri/0 ] && echo /sys/kernel/debug/dri/0
}

primary_output() { xrandr 2>/dev/null | awk '/ connected/{print $1; exit}'; }
compositor_pid() { pgrep -x picom; }

# ---------------------------------------------------------------------------
# State dump
# ---------------------------------------------------------------------------
dump() {
    local cmdline psr_p fbc_p
    cmdline=$(cat /proc/cmdline)
    DRI=$(find_dri)

    echo "==========================================================="
    echo "  Purple Display Diagnostics  ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "==========================================================="

    section "Hardware"
    info "Model:  $(rd /sys/class/dmi/id/sys_vendor) $(rd /sys/class/dmi/id/product_name)"
    info "Board:  $(rd /sys/class/dmi/id/board_name)"
    info "GPU:    $(lspci 2>/dev/null | grep -iE 'vga|display|3d' | head -1)"
    if [ -d /sys/module/i915 ]; then
        info "DRM:    i915 loaded (Intel)"
    else
        warn "i915 NOT loaded: not an Intel-GPU machine, the i915 cmdline params are no-ops here."
    fi

    section "Verdict (is each mitigation actually live?)"
    # Compositor: THE fix for the tear. A plain user process, always checkable.
    if [ -n "$(compositor_pid)" ]; then
        pass "Compositor running (picom): whole-frame vsync'd presentation, tear-free. $(ps -o args= -p "$(compositor_pid)" 2>/dev/null | grep -o -- '--backend [a-z]*')"
    else
        fail "No compositor: modesetting blits partial damage straight to scanout = tearing/checkerboard. Start it: $0 compositor on"
    fi
    # PSR / FBC: correct to have off, but they don't fix a tear. Module params
    # are world-readable, so this is reliable with or without sudo.
    psr_p=$(rd /sys/module/i915/parameters/enable_psr)
    fbc_p=$(rd /sys/module/i915/parameters/enable_fbc)
    if echo "$cmdline" | grep -q 'i915.enable_psr=0' && [ "$psr_p" = "0" ]; then
        pass "PSR disabled (cmdline + module param both 0)"
    else
        warn "PSR: cmdline=$(echo "$cmdline" | grep -o 'i915.enable_psr=[0-9]'), module param='$psr_p'"
    fi
    if echo "$cmdline" | grep -q 'i915.enable_fbc=0' && [ "$fbc_p" = "0" ]; then
        pass "FBC disabled (cmdline + module param both 0)"
    else
        warn "FBC: cmdline=$(echo "$cmdline" | grep -o 'i915.enable_fbc=[0-9]'), module param='$fbc_p'"
    fi
    info "(modesetting has no TearFree option; that lever does not exist here)"

    section "Kernel cmdline"
    info "$cmdline"

    section "i915 module parameters (effective)"
    for p in enable_psr enable_fbc enable_dc enable_dpcd_backlight enable_psr2_sel_fetch; do
        local v; v=$(rd "/sys/module/i915/parameters/$p")
        [ -n "$v" ] && info "$p = $v"
    done

    section "FBC / PSR status (debugfs)"
    if [ "$HAVE_SUDO" != 1 ]; then
        info "(skipped: needs passwordless sudo; debugfs is root-only and the"
        info " Purple terminal has no sudo. The verdict above does not rely on it.)"
    elif [ -n "$DRI" ]; then
        [ -e "$DRI/i915_fbc_status" ] && priv "$DRI/i915_fbc_status" | sed 's/^/   FBC: /'
        local psr_node
        psr_node=$(ls "$DRI"/i915_edp_psr_status "$DRI"/eDP-*/i915_psr_status 2>/dev/null | head -1)
        [ -n "$psr_node" ] && priv "$psr_node" | sed 's/^/   PSR: /'
    fi

    section "Panel depth + dithering"
    info "max bpc (connector): a low value (6) would point at panel dither; 8+ rules it out."
    xrandr --verbose 2>/dev/null | grep -iE 'max bpc|Broadcast RGB' | sort -u | sed 's/^/        /'

    section "X driver + present path"
    local xlog
    for xlog in /home/purple/.local/share/xorg/Xorg.0.log "$HOME/.local/share/xorg/Xorg.0.log" /var/log/Xorg.0.log; do
        if [ -r "$xlog" ] || { [ "$HAVE_SUDO" = 1 ] && sudo test -r "$xlog" 2>/dev/null; }; then
            info "log: $xlog"
            { [ -r "$xlog" ] && cat "$xlog" || priv "$xlog"; } \
                | grep -iE 'using driver|modesetting|TearFree|glamor' | sed 's/^/        /' | head -12
            break
        fi
    done
    info "('Option \"TearFree\" is not used' here is expected: modesetting has no such option.)"

    echo
    echo "==========================================================="
    echo "  Saved to $REPORT"
    echo "  A/B the fix (no root needed, no rebuild):"
    echo "    $0 compositor off   # then trigger a transition: should TEAR"
    echo "    $0 compositor on    # then trigger again: should be clean"
    echo "==========================================================="
}

# ---------------------------------------------------------------------------
# Compositor: the one runtime lever that works from the Purple terminal.
# ---------------------------------------------------------------------------
compositor() {
    case "$1" in
        on)
            if command -v purple-start-compositor >/dev/null 2>&1; then
                purple-start-compositor
            else
                # Resilient fallback if the launcher isn't on this image yet.
                local conf=/etc/purple/picom.conf; [ -f "$conf" ] || conf=/dev/null
                pkill -x picom 2>/dev/null
                LIBGL_ALWAYS_SOFTWARE=0 picom --config "$conf" --backend glx \
                    --log-file /tmp/purple-picom.log >/dev/null 2>&1 &
                sleep 0.6
                [ -n "$(compositor_pid)" ] && echo "compositor started (glx)" \
                    || echo "compositor failed to start; see /tmp/purple-picom.log"
            fi
            ;;
        off)
            pkill -x picom 2>/dev/null && echo "compositor stopped" || echo "compositor was not running"
            ;;
        status|"")
            local pid; pid=$(compositor_pid)
            if [ -n "$pid" ]; then
                echo "RUNNING: $(ps -o args= -p "$pid")"
            else
                echo "NOT running. Start: $0 compositor on"
            fi
            ;;
        *) echo "Usage: $0 compositor <on|off|status>" ;;
    esac
}

# ---------------------------------------------------------------------------
# On-demand repro: drive partial redraws of a few cells, the same music-grid
# keystroke pattern that exposes the tear. Same Alacritty -> X -> scanout path.
# ---------------------------------------------------------------------------
repro() {
    if [ ! -t 0 ]; then echo "repro needs an interactive terminal (run it from Open Terminal)."; exit 1; fi
    local rows=14 cols=46 base=54
    printf '\033[2J\033[?25l'
    printf '\033[1;1H\033[1;37mCheckerboard repro: flipping a few cells per frame (partial redraw).\033[0m'
    printf '\033[2;1H\033[0;37mWatch the cells as they change color. Press any key to stop.\033[0m'
    local r c
    for ((r=0; r<rows; r++)); do
        printf '\033[%d;1H' $((r+4))
        for ((c=0; c<cols; c++)); do printf '\033[48;5;%dm  ' "$base"; done
    done
    printf '\033[0m'
    trap 'printf "\033[0m\033[?25h\033[2J\033[1;1H"; exit 0' INT TERM
    local key
    while true; do
        for _ in 1 2 3 4 5 6; do
            r=$(( (RANDOM % rows) + 4 ))
            c=$(( (RANDOM % cols) * 2 + 1 ))
            printf '\033[%d;%dH\033[48;5;%dm  ' "$r" "$c" $(( (RANDOM % 6) * 36 + (RANDOM % 6) * 6 + 16 ))
        done
        printf '\033[0m'
        if read -rsn1 -t 0.07 key; then break; fi
    done
    printf '\033[0m\033[?25h\033[2J\033[1;1H'
    echo "Repro stopped. A/B it: '$0 compositor off', repro, then 'compositor on', repro."
}

REPORT=/tmp/purple-display-diag.txt
case "${1:-dump}" in
    dump|"")    dump | tee "$REPORT" ;;
    repro)      repro ;;
    compositor) shift; compositor "$@" ;;
    *)          echo "Usage: $0 [dump|repro|compositor <on|off|status>]" ;;
esac
