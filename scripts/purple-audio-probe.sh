#!/bin/bash
# Purple Computer: hands-on audio probe. Run from the parent-menu terminal on a
# machine that sounds too loud or too quiet, then photograph the SUMMARY block
# at the end (the full log is saved next to the boot dumps).
#
# Unlike purple-audio-dump this one is ACTIVE: it plays the startup chime and
# records it with the built-in mic (purple_tui/sound_check.py, the same check
# the app runs at startup), and it loads the speech model to time it.
# Rationale and what to look for: docs/PLAN-audio-volume.md, "Hands-on probe".
set +e

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
for LOG_DIR in /var/log/purple /tmp "$HOME" "$PWD"; do
    LOG="$LOG_DIR/audio-probe-$STAMP.log"
    ( : > "$LOG" ) 2>/dev/null && break
done
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
SUMMARY_FILE="$WORK/summary"
SRC=${PURPLE_SRC:-/opt/purple}

if [ "$(id -u)" = 0 ] && id purple >/dev/null 2>&1; then
    pa() { sudo -u purple env XDG_RUNTIME_DIR=/run/user/1000 "$@"; }
else
    export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
    pa() { "$@"; }
fi

exec > >(tee "$LOG") 2>&1
section() { echo; echo "===== $* ====="; }
note() { echo "$*" >> "$SUMMARY_FILE"; }

echo "purple-audio-probe $(date -Iseconds)"

section "machine"
for f in sys_vendor product_name product_version board_name; do
    printf '%-16s %s\n' "$f" "$(cat /sys/class/dmi/id/$f 2>/dev/null)"
done
echo "kernel $(uname -r)"
note "machine: $(cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name 2>/dev/null | tr '\n' ' ')"

section "sound cards"
cat /proc/asound/cards 2>/dev/null

section "codec pins (speaker / headphone / mic), with amp caps"
# Within a node block the Amp-Out caps line precedes Pin Default, so buffer it.
for codec in /proc/asound/card*/codec#*; do
    [ -f "$codec" ] || continue
    awk -v file="$codec" '
        /^Codec:/ { print file ": " $0 }
        /^Node/ { node = $1 " " $2; amp = "" }
        /Amp-Out caps/ { amp = $0 }
        /Pin Default/ && /Speaker|HP Out|Mic|Line Out/ {
            print "  " node ":" $0
            if (amp != "") print "      " amp
        }' "$codec"
done
SPK=$(cat /proc/asound/card*/codec#* 2>/dev/null | grep -c 'Pin Default.*\[Fixed\] Speaker')
note "speaker pins (fixed): $SPK"

section "smart amps and codec drivers"
lsmod | grep -E 'snd_soc|cs35l|tas2|max98|snd_hda_codec_|snd_sof' | awk '{print $1}' | sort | tr '\n' ' '; echo
ls /sys/bus/acpi/devices 2>/dev/null | grep -E 'CSC35|CLSA|TXNW|TIAS|MX983|ESSX|10EC|INT34' | tr '\n' ' '; echo
AMP=$(lsmod | grep -cE 'cs35l|tas2|max98')
note "smart amp modules: $AMP"

section "alsa mixer (dB-mapped)"
amixer -M scontents 2>&1 | grep -E "^Simple|Playback.*\[|Capture.*\[|Limits"

section "pulse: defaults, sinks, sources"
pa pactl info 2>&1 | grep -E 'Server Name|Default (Sink|Source)'
pa pactl list sinks 2>&1 | grep -E 'Name:|Description:|^\s+Volume:|Base Volume|Active Port|Mute:'
echo "--- sources ---"
pa pactl list sources 2>&1 | grep -E 'Name:|Description:|^\s+Volume:|Base Volume|Active Port|Mute:'

if [ ! -d "$SRC/purple_tui" ]; then
    section "mic loopback and speech timing"
    echo "$SRC/purple_tui not found (set PURPLE_SRC); skipped"
else
    section "mic loopback: the startup chime at the Medium step, recorded by the default source"
    # Drops the mic gain a step each time the chord clips, restores sink and
    # source state, and prints the summary line last.
    OUT=$(pa env PYTHONPATH="$SRC" python3 -m purple_tui.sound_check 2>&1)
    echo "$OUT"
    note "$(echo "$OUT" | tail -1)"

    section "speech model timing (load, first and second synthesis)"
    lscpu 2>/dev/null | grep -E 'Model name|^CPU\(s\):'; free -m 2>/dev/null | sed -n 2p
    PYTHONPATH="$SRC" python3 - "$SUMMARY_FILE" <<'PY'
import os, sys, tempfile, time
t = time.monotonic()
from purple_tui.tts import load_voice, synthesize_to_file, find_voice_model
print(f"  import tts        {time.monotonic() - t:5.1f}s")
model = find_voice_model()
print(f"  model             {model} ({model.stat().st_size // 2**20 if model else 0} MB)")
t = time.monotonic(); voice = load_voice(); load = time.monotonic() - t
print(f"  load model        {load:5.1f}s")
times = []
for text in ("apple.", "banana.", "2 plus 3 equals 5."):
    fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    t = time.monotonic(); synthesize_to_file(voice, text, path); times.append(time.monotonic() - t)
    os.unlink(path)
    print(f"  synth {text!r:22} {times[-1]:5.1f}s")
print(f"speech: load {load:.1f}s, first synth {times[0]:.1f}s, then {times[1]:.1f}s / {times[2]:.1f}s",
      file=open(sys.argv[1], "a"))
PY
fi

section "boot log (volume, mixer, piper)"
grep -iE 'volume|mixer|piper|hotplug' /tmp/purple-boot.log 2>/dev/null | tail -20

section "SUMMARY"
cat "$SUMMARY_FILE" 2>/dev/null
echo "log: $LOG"
