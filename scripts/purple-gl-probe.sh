#!/bin/bash
# Decide Alacritty's GL mode at session startup. Prints exactly "0" (hardware
# GL verified, use it) or "1" (keep LIBGL_ALWAYS_SOFTWARE=1) on stdout and
# always exits 0, so xinitrc's `GL_MODE=$(purple-gl-probe)` can never break
# the session. Every doubt lands on "1": the exact behavior all machines
# shipped with before this probe existed. Needs a running X server.
# History and decision rules: guides/intel-display-tuning.md
#
# The decision is cached per boot in $CACHE, so Purple's in-place restarts
# (xinitrc re-execs itself) skip the glxinfo call and keep one stable answer.
# xinitrc writes "1" into the cache when Alacritty dies under hardware GL, so
# a driver that fools glxinfo but crashes the real renderer falls back to
# software for the rest of the boot instead of crash-looping.
#
# The PURPLE_GL_* env knobs exist for the unit tests (tests/test_gl_probe.py).
# TIMEOUT is whole seconds.

LOG="${PURPLE_GL_PROBE_LOG:-/tmp/purple-gl-probe.log}"
CACHE="${PURPLE_GL_PROBE_CACHE:-/tmp/purple-gl-mode}"
FORCE_FLAG="${PURPLE_GL_FORCE_SOFTWARE_FLAG:-/opt/purple/force-software-gl}"
TIMEOUT="${PURPLE_GL_PROBE_TIMEOUT:-5}"
GLXINFO="${PURPLE_GL_PROBE_GLXINFO:-glxinfo}"

finish() {
    echo "$1" > "$CACHE" 2>/dev/null
    echo "decision: $2" >> "$LOG" 2>/dev/null
    echo "$1"
    exit 0
}
software() { finish 1 "software ($1)"; }
hardware() { finish 0 "hardware ($1)"; }

[ -f "$FORCE_FLAG" ] && { : > "$LOG" 2>/dev/null; software "forced by $FORCE_FLAG"; }

cached=$(cat "$CACHE" 2>/dev/null)
case "$cached" in
    0|1) echo "decision: $cached (cached from earlier this boot)" >> "$LOG" 2>/dev/null
         echo "$cached"; exit 0 ;;
esac

: > "$LOG" 2>/dev/null || LOG=/dev/null

command -v "$GLXINFO" >/dev/null 2>&1 || software "glxinfo not installed"

# Run glxinfo detached from our stdout and abandon it if it outlives TIMEOUT.
# `timeout` alone is not enough: a glxinfo wedged in an uninterruptible
# driver ioctl (D state) ignores TERM and even KILL, and waiting on it would
# hang the whole session before Alacritty ever launches.
out="${TMPDIR:-/tmp}/purple-gl-probe.$$"
LIBGL_ALWAYS_SOFTWARE=0 "$GLXINFO" -B > "$out" 2>>"$LOG" &
pid=$!
for _ in $(seq 1 $((TIMEOUT * 10))); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
done
if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null
    rm -f "$out"
    software "glxinfo hung after ${TIMEOUT}s, abandoned"
fi
wait "$pid"
status=$?
info=$(< "$out")
rm -f "$out"
[ "$status" -eq 0 ] || software "glxinfo failed (exit $status)"
printf '%s\n' "$info" >> "$LOG"

grep -q "^direct rendering: Yes" <<< "$info" || software "no direct rendering"

renderer=$(sed -n 's/^OpenGL renderer string: //p' <<< "$info")
[ -n "$renderer" ] || software "no renderer string"
case "$renderer" in
    *llvmpipe*|*softpipe*|*SWR*|*[Ss]oftware*) software "Mesa picked software anyway: $renderer" ;;
    *virgl*|*SVGA3D*|*VMware*|*VirtualBox*|*Parallels*|*QXL*) software "VM renderer: $renderer" ;;
esac

# Alacritty's renderer wants OpenGL 3.3 core. Older GPUs (Intel gen5 and
# earlier) keep software GL rather than trusting the less exercised GLES path.
version=$(sed -n 's/^OpenGL core profile version string: \([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1 \2/p' <<< "$info")
# shellcheck disable=SC2086  # intentional split into "major minor"
set -- $version
[ "${1:-0}" -gt 3 ] || { [ "${1:-0}" -eq 3 ] && [ "${2:-0}" -ge 3 ]; } \
    || software "core profile ${1:-?}.${2:-?} below 3.3"

hardware "$renderer, core profile $1.$2"
