"""Sound check: play a short chord through the speaker, record it with the
built-in mic, and report the machine's loop gain (how many dB the acoustic
path adds from digital out to digital in at 100%/100%) plus whether the
speaker was heard at all. purple-audio-probe runs it today; the same chime
and analysis are meant to run at startup once loop gain is shown to predict
the right default volume. Rationale: docs/PLAN-audio-volume.md, "Hands-on probe".

Stdlib only, no boot_log: runnable as `python3 -m purple_tui.sound_check`.
"""

from __future__ import annotations

import array
import math
import re
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .audio import FULL_SCALE, db_to_linear

TONES = (520, 660, 780)  # C major, tuned to whole cycles per 50 ms window so Goertzel reads exact amplitude
TONE_DB = -12.0  # per fundamental; the full chord peaks near -3 dBFS
CHIME_RATE = 22050
RECORD_RATE = 16000
SINK_PCT = 60
SOURCE_LADDER = (100, 50, 25, 12)  # mic gain drops a step whenever the chord clips
CLIP_TOLERANCE = 8  # samples at the rail before a take counts as clipped
HEARD_SNR_DB = 10.0
ATTACK, STAGGER, HOLD, RELEASE = 0.06, 0.18, 0.9, 0.7  # chime envelope, seconds


def _note(t: float, onset: float, freq: float, hold_end: float) -> float:
    """One bell-like note: soft 60 ms onset, octave and fifth partials that fade
    fast, a steady fundamental while the chord rings, then a long smooth release."""
    a = t - onset
    if a < 0:
        return 0.0
    env = 0.5 - 0.5 * math.cos(math.pi * min(a, ATTACK) / ATTACK)
    if t > hold_end:
        env *= 0.5 + 0.5 * math.cos(math.pi * min(t - hold_end, RELEASE) / RELEASE)
    partials = (0.25 * math.exp(-a / 0.4) * math.sin(4 * math.pi * freq * t)
                + 0.1 * math.exp(-a / 0.15) * math.sin(6 * math.pi * freq * t))
    return env * (math.sin(2 * math.pi * freq * t) + partials)


def render_chime(rate: int = CHIME_RATE) -> array.array:
    """Rising arpeggio into a held chord that fades: 0.4 s lead-in, about 2.3 s
    of sound, 0.2 s tail. The fundamentals sit at a steady TONE_DB for HOLD
    seconds once all three notes are in, which is the stretch analyze() measures."""
    hold_end = STAGGER * (len(TONES) - 1) + ATTACK + HOLD
    amp = db_to_linear(TONE_DB)
    out = array.array("h")
    out.frombytes(bytes(2 * int(rate * 0.4)))
    for i in range(int(rate * (hold_end + RELEASE))):
        t = i / rate
        out.append(int(amp * sum(_note(t, k * STAGGER, f, hold_end) for k, f in enumerate(TONES))))
    out.frombytes(bytes(2 * int(rate * 0.2)))
    return out


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
        """Mic level the chord would reach at sink 100% / source 100%, relative to what was sent."""
        return sum(self.tone_db) / len(self.tone_db) - TONE_DB - self.sink_db - self.source_db

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
    """Ambient floor from the first 0.5 s, chord level from the loudest 0.6 s, per-tone SNR."""
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    win = rate // 20
    if len(samples) < 10 * win:
        return SoundCheck(note="mic not delivering")
    wins = [samples[i:i + win] for i in range(0, len(samples) - win + 1, win)]
    tone = [[_goertzel(c, f, rate) for f in TONES] for c in wins]
    n_ambient = rate // 2 // win
    pct = lambda xs, q: sorted(xs)[int(len(xs) * q)]
    floor = pct([_rms(c) for c in wins[:n_ambient]], 0.1)
    tone_floor = [pct([t[k] for t in tone[:n_ambient]], 0.1) for k in range(len(TONES))]
    top = sorted(range(len(wins)), key=lambda i: sum(tone[i]), reverse=True)[:12]
    chord = [pct([tone[i][k] for i in top], 0.5) for k in range(len(TONES))]
    snr = min(_db(chord[k]) - _db(tone_floor[k]) for k in range(len(TONES)))
    return SoundCheck(
        heard=snr > HEARD_SNR_DB,
        clipped=sum(1 for x in samples if abs(x) >= FULL_SCALE - 67),
        floor_db=_db(floor),
        tone_db=tuple(_db(t) for t in chord),
        snr_db=snr,
    )


def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5).stdout


def _volume_db(kind: str, name: str) -> float:
    m = re.search(r"(-?[\d.]+|-inf) dB", _pactl(f"get-{kind}-volume", name))
    return float(m.group(1)) if m else 0.0


def _saved_state(kind: str, name: str) -> tuple[str, str]:
    pct = re.search(r"(\d+)%", _pactl(f"get-{kind}-volume", name))
    return (f"{pct.group(1)}%" if pct else "100%", "1" if "yes" in _pactl(f"get-{kind}-mute", name) else "0")


def _capture(sink: str, source: str, wav: Path) -> bytes:
    """Record the mic while the chime plays 0.7 s in; about 3.5 s total."""
    with tempfile.TemporaryDirectory() as d:
        rec_path = Path(d) / "rec.raw"
        rec = subprocess.Popen(
            ["parecord", "--raw", "--channels=1", f"--rate={RECORD_RATE}", "--format=s16le", "-d", source, str(rec_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.7)
        subprocess.run(["paplay", "-d", sink, str(wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        time.sleep(0.3)
        rec.terminate()
        try:
            rec.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rec.kill()
            rec.wait()
        return rec_path.read_bytes() if rec_path.exists() else b""


def run(sink: Optional[str] = None, source: Optional[str] = None, sink_pct: int = SINK_PCT,
        ladder: tuple[int, ...] = SOURCE_LADDER, log: Callable[[str], None] = lambda line: None) -> SoundCheck:
    """One chord per mic-gain step down the ladder until a take is clean. Restores sink and source state."""
    sink = sink or _pactl("get-default-sink").strip()
    source = source or _pactl("get-default-source").strip()
    if not sink or not source or source.endswith(".monitor"):
        return SoundCheck(note="no microphone")
    saved = {kind: _saved_state(kind, name) for kind, name in (("sink", sink), ("source", source))}
    result = SoundCheck(note="mic not delivering")
    try:
        with tempfile.TemporaryDirectory() as d:
            wav = write_chime(Path(d) / "chime.wav")
            _pactl("set-sink-mute", sink, "0")
            _pactl("set-source-mute", source, "0")
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
    try:
        print(run(log=print).summary())
    except Exception as e:
        print(f"sound check: failed ({type(e).__name__}: {e})")
        sys.exit(1)
