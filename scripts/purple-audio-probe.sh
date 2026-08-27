#!/bin/bash
# Purple Computer: hands-on audio probe. Run from the parent-menu terminal on a
# machine that sounds too loud or too quiet, then photograph the SUMMARY block
# at the end (the full log is saved next to the boot dumps).
#
# Unlike purple-audio-dump this one is ACTIVE: it plays a short chime at three
# volume steps and records it with the built-in mic, and it loads the speech
# model to time it. It restores the sink and source volumes it found.
# Rationale and what to look for: docs/PLAN-audio-volume.md, "Hands-on probe".
set +e

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
for LOG_DIR in /var/log/purple /tmp "$HOME" "$PWD"; do
    LOG="$LOG_DIR/audio-probe-$STAMP.log"
    ( : > "$LOG" ) 2>/dev/null && break
done
WORK=$(mktemp -d)
SUMMARY_FILE="$WORK/summary"
SRC=${PURPLE_SRC:-/opt/purple}
LEVELS="40 60 80"

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

section "mic loopback: chime at $LEVELS % through the default sink, recorded by the default source"
SINK=$(pa pactl get-default-sink 2>/dev/null)
SOURCE=$(pa pactl get-default-source 2>/dev/null)
echo "sink=$SINK source=$SOURCE"
case "$SOURCE" in
    ""|*.monitor) echo "no microphone source: loopback skipped"; note "mic: none (loopback skipped)";;
    *)
    saved_sink=$(pa pactl get-sink-volume "$SINK" 2>/dev/null | grep -oE '[0-9]+%' | head -1)
    saved_sink_mute=$(pa pactl get-sink-mute "$SINK" 2>/dev/null | awk '{print $2}')
    saved_src=$(pa pactl get-source-volume "$SOURCE" 2>/dev/null | grep -oE '[0-9]+%' | head -1)
    saved_src_mute=$(pa pactl get-source-mute "$SOURCE" 2>/dev/null | awk '{print $2}')
    echo "found: sink $saved_sink mute=$saved_sink_mute, source $saved_src mute=$saved_src_mute"
    restore() {
        pa pactl set-sink-volume "$SINK" "${saved_sink:-60%}"
        pa pactl set-sink-mute "$SINK" "$([ "$saved_sink_mute" = yes ] && echo 1 || echo 0)"
        pa pactl set-source-volume "$SOURCE" "${saved_src:-100%}"
        pa pactl set-source-mute "$SOURCE" "$([ "$saved_src_mute" = yes ] && echo 1 || echo 0)"
    }
    trap 'restore; rm -rf "$WORK"' EXIT
    pa pactl set-source-mute "$SOURCE" 0
    pa pactl set-source-volume "$SOURCE" 100%
    pa pactl set-sink-mute "$SINK" 0

    python3 - "$WORK/chime.wav" <<'PY'
import math, sys, wave
rate, tones, level = 22050, (1000, 1500, 2500), 10 ** (-14 / 20)
def seg(seconds, gen):
    return [gen(i) for i in range(int(rate * seconds))]
chime = seg(1.0, lambda i: sum(level * math.sin(2 * math.pi * f * i / rate) for f in tones))
fade = int(rate * 0.01)
for i in range(fade):
    chime[i] *= i / fade; chime[-1 - i] *= i / fade
samples = seg(0.4, lambda i: 0.0) + chime + seg(0.2, lambda i: 0.0)
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(b"".join(int(s * 32767).to_bytes(2, "little", signed=True) for s in samples))
PY
    chmod a+r "$WORK/chime.wav"; chmod a+rwx "$WORK"
    for L in $LEVELS; do
        pa pactl set-sink-volume "$SINK" "${L}%"
        sleep 0.3
        pa parecord --raw --channels=1 --rate=16000 --format=s16le -d "$SOURCE" "$WORK/rec_$L.raw" &
        REC=$!
        sleep 0.7
        pa paplay -d "$SINK" "$WORK/chime.wav"
        sleep 0.3
        kill -INT $REC 2>/dev/null; wait $REC 2>/dev/null
        python3 - "$WORK/rec_$L.raw" "$L" "$SUMMARY_FILE" <<'PY'
import array, math, sys
raw = open(sys.argv[1], "rb").read()
level = sys.argv[2]
summary = open(sys.argv[3], "a")
s = array.array("h"); s.frombytes(raw[: len(raw) // 2 * 2])
rate, win = 16000, 800  # 50 ms windows
if len(s) < 10 * win:
    print(f"  {level}%: recording too short ({len(s)} samples), mic not delivering")
    print(f"chime@{level}%: mic not delivering", file=summary); sys.exit(0)
def db(x): return 20 * math.log10(max(x, 1e-9) / 32767)
def goertzel(chunk, f):
    k, w = 0.0, 2 * math.cos(2 * math.pi * f / rate); s1 = s2 = 0.0
    for x in chunk:
        s0 = x + w * s1 - s2; s2, s1 = s1, s0
    return math.sqrt(max(s1 * s1 + s2 * s2 - w * s1 * s2, 0)) * 2 / len(chunk)
wins = [s[i:i + win] for i in range(0, len(s) - win, win)]
rms = [math.sqrt(sum(x * x for x in c) / len(c)) for c in wins]
tone = [[goertzel(c, f) for f in (1000, 1500, 2500)] for c in wins]
ambient_wins = wins[: int(0.5 * rate / win)]
floor = sorted(rms[: len(ambient_wins)])[len(ambient_wins) // 10]
tone_floor = [sorted(t[i] for t in tone[: len(ambient_wins)])[len(ambient_wins) // 10] for i in range(3)]
score = [sum(t) for t in tone]
top = sorted(range(len(wins)), key=lambda i: score[i], reverse=True)[:12]
chime_rms = sorted(rms[i] for i in top)[6]
chime_tone = [sorted(tone[i][k] for i in top)[6] for k in range(3)]
snr = [db(chime_tone[k]) - db(tone_floor[k]) for k in range(3)]
clipped = sum(1 for x in s if abs(x) >= 32700)
heard = min(snr) > 10
print(f"  {level}%: ambient floor {db(floor):6.1f} dBFS | chime {db(chime_rms):6.1f} dBFS broadband, "
      f"tones {' '.join(f'{db(t):.1f}' for t in chime_tone)} dBFS | SNR {' '.join(f'{x:.0f}' for x in snr)} dB | "
      f"clipped {clipped} | {'HEARD' if heard else 'not heard'}")
print(f"chime@{level}%: {db(chime_rms):.1f} dBFS at mic, floor {db(floor):.1f}, SNR {min(snr):.0f} dB"
      f"{' CLIP' if clipped else ''}{'' if heard else ' NOT HEARD'}", file=summary)
PY
    done
    restore
    trap 'rm -rf "$WORK"' EXIT
    echo "restored: sink $saved_sink, source $saved_src"
    ;;
esac

section "speech model timing (load, first and second synthesis)"
if [ -d "$SRC/purple_tui" ]; then
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
else
    echo "$SRC/purple_tui not found (set PURPLE_SRC); skipped"
fi

section "boot log (volume, mixer, piper)"
grep -iE 'volume|mixer|piper|hotplug' /tmp/purple-boot.log 2>/dev/null | tail -20

section "SUMMARY"
cat "$SUMMARY_FILE" 2>/dev/null
echo "log: $LOG"
