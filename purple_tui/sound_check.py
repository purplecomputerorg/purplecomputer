"""Startup chime that doubles as a loudness check: play a short marimba
arpeggio through the speaker, record it with the built-in mic, and report the
machine's loop gain (how many dB the acoustic path adds from digital out to
digital in at 100%/100%). At first boot a machine that plays it hot starts a
step lower and one that plays it faint starts at Full.
The app and purple-audio-probe both call run(). Rationale and the calibration
status: docs/PLAN-audio-volume.md, "Hands-on probe".

run() never raises and never plays unless pactl, a real sink, and a real
unmuted mic are all present: nobody needs a microphone to use Purple.
No boot_log import here, so `python3 -m purple_tui.sound_check` stays cheap.
"""

from __future__ import annotations

import array
import functools
import math
import re
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .audio import FULL_SCALE
from .synth import generate_marimba

TONES = (523.25, 659.25, 783.99)  # C5 E5 G5, rising
NOTE_SECONDS, STAGGER = 0.9, 0.22
CHIME_PEAK_DB = -8.0
CHIME_RATE = 22050
RECORD_RATE = 16000
SINK_PCT = 58  # the Medium step
SOURCE_PCT = 50
PROBE_LADDER = (SOURCE_PCT, 12)  # the probe retries a clipped take at lower mic gain; the app plays once
CLIP_TOLERANCE = 8  # samples at the rail before a take counts as clipped
HEARD_SNR_DB = 10.0
# First-boot verdicts. The one measured anchor is the Surface Laptop (too loud
# at Loud): its mic clipped at sink 40% / source 100%, so its loop gain is at
# least +34 dB. Hot is that and anything within a few dB; quiet leaves a 15 dB
# margin below it. Mic gain structure varies by machine, so expect a step off
# on some; every verdict is one key press from right and then remembered.
HOT_LOOP_GAIN_DB = 30.0
QUIET_LOOP_GAIN_DB = 15.0
MIC_ALIVE_FLOOR_DB = -70.0  # a "not heard" only counts when the mic is clearly delivering room noise
HOT_MACHINE_VOLUME = 58  # Medium
QUIET_MACHINE_VOLUME = 100  # Full


def render_chime(rate: int = CHIME_RATE) -> array.array:
    """Three marimba notes rising 0.22 s apart, 0.3 s lead-in, 0.2 s tail, peak at CHIME_PEAK_DB."""
    notes = [generate_marimba(f, NOTE_SECONDS, rate) for f in TONES]
    lead, stagger = int(rate * 0.3), int(rate * STAGGER)
    mix = [0.0] * (lead + stagger * (len(notes) - 1) + len(notes[-1]) + int(rate * 0.2))
    for k, note in enumerate(notes):
        for i, x in enumerate(note):
            mix[lead + k * stagger + i] += x
    gain = FULL_SCALE * 10 ** (CHIME_PEAK_DB / 20) / max(map(abs, mix))
    return array.array("h", (int(x * gain) for x in mix))


def write_chime(path: Path) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(CHIME_RATE)
        w.writeframes(render_chime().tobytes())
    return path


@dataclass
class SoundCheck:
    heard: bool = False
    clipped: int = 0
    floor_db: float = -math.inf
    tone_db: tuple[float, ...] = ()
    snr_db: float = -math.inf
    sink_pct: int = 0
    sink_db: float = 0.0
    source_pct: int = 0
    source_db: float = 0.0
    note: str = ""

    @property
    def clean(self) -> bool:
        return self.clipped < CLIP_TOLERANCE

    @property
    def loop_gain_db(self) -> float:
        """Mic level the chime would reach at sink 100% / source 100%, relative to what was sent."""
        sent = _sent_tone_db()
        return sum(m - s for m, s in zip(self.tone_db, sent)) / len(sent) - self.sink_db - self.source_db

    def detail(self) -> str:
        if self.note:
            return f"  {self.note}"
        tones = " ".join(f"{t:.1f}" for t in self.tone_db)
        return (f"  sink {self.sink_pct}% ({self.sink_db:+.1f} dB), source {self.source_pct}% ({self.source_db:+.1f} dB): "
                f"tones {tones} dBFS at mic, floor {self.floor_db:.1f} dBFS, SNR {self.snr_db:.0f} dB, clipped {self.clipped}")

    def summary(self) -> str:
        if self.note:
            return f"sound check: {self.note}"
        flags = ("" if self.clean else " CLIP") + ("" if self.heard else " NOT HEARD")
        return (f"sound check: loop gain {self.loop_gain_db:+.0f} dB (sink {self.sink_pct}%, source {self.source_pct}%), "
                f"SNR {self.snr_db:.0f} dB, floor {self.floor_db:.0f} dBFS{flags}")


def _db(amplitude: float) -> float:
    return 20 * math.log10(max(amplitude, 1e-9) / FULL_SCALE)


def _goertzel(chunk: array.array, freq: float, rate: int) -> float:
    """Peak amplitude of one tone in `chunk`; exact when the tone spans whole cycles."""
    w = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in chunk:
        s0 = x + w * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(max(s1 * s1 + s2 * s2 - w * s1 * s2, 0)) * 2 / len(chunk)


def _rms(chunk: array.array) -> float:
    mean = sum(chunk) / len(chunk)  # DC offset from a hot capture path is not noise
    return math.sqrt(max(math.sumprod(chunk, chunk) / len(chunk) - mean * mean, 0))


def analyze(raw: bytes, rate: int = RECORD_RATE) -> SoundCheck:
    """Ambient floor from the first 0.5 s; each tone's level is its loudest
    100 ms window, stepped 25 ms so a fast marimba decay reads the same
    wherever the recording happened to start."""
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    win, hop = rate // 10, rate // 40
    if len(samples) < 10 * win:
        return SoundCheck(note="mic not delivering")
    starts = range(0, len(samples) - win + 1, hop)
    tone = [[_goertzel(samples[i:i + win], f, rate) for f in TONES] for i in starts]
    ambient = [k for k, i in enumerate(starts) if i + win <= rate // 2]
    pct = lambda xs, q: sorted(xs)[int(len(xs) * q)]
    floor = pct([_rms(samples[starts[k]:starts[k] + win]) for k in ambient], 0.1)
    tone_floor = [pct([tone[k][j] for k in ambient], 0.1) for j in range(len(TONES))]
    peak = [max(t[j] for t in tone) for j in range(len(TONES))]
    snr = min(_db(peak[j]) - _db(tone_floor[j]) for j in range(len(TONES)))
    return SoundCheck(
        heard=snr > HEARD_SNR_DB,
        clipped=sum(1 for x in samples if abs(x) >= FULL_SCALE - 67),
        floor_db=_db(floor),
        tone_db=tuple(_db(t) for t in peak),
        snr_db=snr,
    )


def default_volume(check: SoundCheck) -> Optional[int]:
    """First-boot level for this machine, or None to keep the default. A clipped
    reading is a lower bound on loop gain, so it can only ever confirm hot."""
    if check.note:
        return None
    if not check.heard:
        return QUIET_MACHINE_VOLUME if check.floor_db > MIC_ALIVE_FLOOR_DB else None
    if check.loop_gain_db >= HOT_LOOP_GAIN_DB:
        return HOT_MACHINE_VOLUME
    if check.clean and check.loop_gain_db <= QUIET_LOOP_GAIN_DB:
        return QUIET_MACHINE_VOLUME
    return None


@functools.cache
def _sent_tone_db() -> tuple[float, ...]:
    """Per-tone level of the chime itself under the same windowing analyze() applies to the mic."""
    return analyze(render_chime(RECORD_RATE).tobytes()).tone_db


def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5).stdout


def _volume_db(kind: str, name: str) -> float:
    m = re.search(r"(-?[\d.]+|-inf) dB", _pactl(f"get-{kind}-volume", name))
    return float(m.group(1)) if m else 0.0


def _saved_state(kind: str, name: str) -> tuple[str, str]:
    pct = re.search(r"(\d+)%", _pactl(f"get-{kind}-volume", name))
    return (f"{pct.group(1)}%" if pct else "100%", "1" if "yes" in _pactl(f"get-{kind}-mute", name) else "0")


def _capture(sink: str, source: str, wav: Path) -> bytes:
    """Record the mic while the chime plays 0.7 s in; about 3 s total. The
    audio streams through a pipe and is analyzed in memory: it never touches disk."""
    rec = subprocess.Popen(
        ["parecord", "--raw", "--channels=1", f"--rate={RECORD_RATE}", "--format=s16le", "-d", source],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.7)
    subprocess.run(["paplay", "-d", sink, str(wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    time.sleep(0.3)
    rec.terminate()
    try:
        return rec.communicate(timeout=2)[0]
    except subprocess.TimeoutExpired:
        rec.kill()
        return rec.communicate()[0]


def _ready(sink: str, source: str) -> str:
    """Why the chime must not play, or an empty string. A muted mic is respected, not overridden."""
    if not all(shutil.which(tool) for tool in ("pactl", "paplay", "parecord")):
        return "pulse tools missing"
    if not sink or sink.startswith("auto_null"):
        return "no speaker"
    if not source or source.endswith(".monitor"):
        return "no microphone"
    if "yes" in _pactl("get-source-mute", source):
        return "microphone muted"
    return ""


def run(sink: Optional[str] = None, source: Optional[str] = None, sink_pct: int = SINK_PCT,
        ladder: tuple[int, ...] = (SOURCE_PCT,), log: Callable[[str], None] = lambda line: None) -> SoundCheck:
    """One chime per mic-gain step down the ladder until a take is clean; the
    default ladder is a single take. Restores sink and source state. Never
    raises: any failure is a note."""
    try:
        return _run(sink, source, sink_pct, ladder, log)
    except Exception as e:
        return SoundCheck(note=f"failed ({type(e).__name__}: {e})")


def _run(sink: Optional[str], source: Optional[str], sink_pct: int, ladder: tuple[int, ...],
         log: Callable[[str], None]) -> SoundCheck:
    if not shutil.which("pactl"):
        return SoundCheck(note="pulse tools missing")
    sink = sink or _pactl("get-default-sink").strip()
    source = source or _pactl("get-default-source").strip()
    if reason := _ready(sink, source):
        return SoundCheck(note=reason)
    saved = {kind: _saved_state(kind, name) for kind, name in (("sink", sink), ("source", source))}
    result = SoundCheck(note="mic not delivering")
    try:
        with tempfile.TemporaryDirectory() as d:
            wav = write_chime(Path(d) / "chime.wav")
            _pactl("set-sink-mute", sink, "0")
            _pactl("set-sink-volume", sink, f"{sink_pct}%")
            for pct in ladder:
                _pactl("set-source-volume", source, f"{pct}%")
                result = analyze(_capture(sink, source, wav))
                result.sink_pct, result.sink_db = sink_pct, _volume_db("sink", sink)
                result.source_pct, result.source_db = pct, _volume_db("source", source)
                log(result.detail())
                if result.clean or not result.heard:
                    break
    finally:
        for kind, name in (("sink", sink), ("source", source)):
            volume, mute = saved[kind]
            _pactl(f"set-{kind}-volume", name, volume)
            _pactl(f"set-{kind}-mute", name, mute)
    return result


if __name__ == "__main__":
    print(run(ladder=PROBE_LADDER, log=print).summary())
