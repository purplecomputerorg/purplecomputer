"""Startup chime that doubles as a loudness check: play a short marimba
arpeggio through the speaker, record it with the built-in mic, and report the
machine's loop gain: how many dB the acoustic path adds from digital out at
sink 100% to digital in with the mic at its base volume (pactl's 0 dB
hardware gain, the one reference comparable across analog and digital mics:
"100%" is +66 dB of boost on one laptop and +20 dB on another). At first
boot a machine that plays the chime loud starts at volume 4 instead of 7.
The check only ever turns the volume down: a low reading can mean a quiet
speaker or an insensitive mic, and those look the same.
The app and purple-audio-probe both call run(). Rationale and the calibration
status: docs/PLAN-audio-volume.md, "Hands-on probe".

run() never raises and never plays unless pactl, a real sink, and a real
unmuted mic are all present: nobody needs a microphone to use Purple.
No boot_log import here, so `python3 -m purple_tui.sound_check` stays cheap.

Privacy: the mic audio is reduced to tone levels as it streams in. At most a
tenth of a second of sound exists at any moment, nothing is written anywhere,
and every measurement is a Goertzel filter at the chime's own three pitches,
so the check cannot represent speech. No recording ever exists.
"""

from __future__ import annotations

import array
import functools
import math
import re
import select
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Union

from .audio import FULL_SCALE
from .constants import VOLUME_LEVELS
from .synth import generate_marimba

TONES = (523.25, 659.25, 783.99)  # C5 E5 G5, rising
NOTE_SECONDS, STAGGER = 0.9, 0.22
LEAD_SECONDS, TAIL_SECONDS = 0.3, 0.2
CHIME_PEAK_DB = -8.0
CHIME_RATE = 22050
RECORD_RATE = 16000
SINK_PCT = 58  # the Medium step
SOURCE_PCT = 20  # both measured mics clipped at 50%, and one barely heard the chime at 12%
PROBE_LADDER = (SOURCE_PCT, 12)  # the probe retries a clipped take at lower mic gain; the app plays once
CLIP_TOLERANCE = 8  # samples at the rail before a take counts as clipped
HEARD_SNR_DB = 10.0
READY_POLL = 0.5  # seconds between looks for a sound card that is still enumerating at boot
# Measured loop gains: HP 15 (digital mic) +7 dB, too loud at 7 and right at
# 4; Surface Laptop -11 dB, right at 7; HP Stream -34 dB and MacBook Air 2011
# -35 dB, the Air plainly the louder of the two by ear. So the top end sorts
# machines and the bottom end does not: loud is anything above the midpoint
# of the HP 15 and the Surface, and nothing else moves.
LOUD_LOOP_GAIN_DB = -2.0
LOUD_MACHINE_VOLUME = VOLUME_LEVELS[4]


def render_chime(rate: int = CHIME_RATE) -> array.array:
    """Three marimba notes rising 0.22 s apart, 0.3 s lead-in, 0.2 s tail, peak at CHIME_PEAK_DB."""
    notes = [generate_marimba(f, NOTE_SECONDS, rate) for f in TONES]
    lead, stagger = int(rate * LEAD_SECONDS), int(rate * STAGGER)
    mix = [0.0] * (lead + stagger * (len(notes) - 1) + len(notes[-1]) + int(rate * TAIL_SECONDS))
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
    source_base_db: float = 0.0
    note: str = ""

    @property
    def clean(self) -> bool:
        return self.clipped < CLIP_TOLERANCE

    @property
    def loop_gain_db(self) -> float:
        """Mic level the chime would reach at sink 100% with the mic at its base volume, relative to what was sent."""
        sent = _sent_tone_db()
        return sum(m - s for m, s in zip(self.tone_db, sent)) / len(sent) - self.sink_db - (self.source_db - self.source_base_db)

    def detail(self) -> str:
        if self.note:
            return f"  {self.note}"
        tones = " ".join(f"{t:.1f}" for t in self.tone_db)
        return (f"  sink {self.sink_pct}% ({self.sink_db:+.1f} dB), source {self.source_pct}% ({self.source_db:+.1f} dB, "
                f"base {self.source_base_db:+.1f} dB): "
                f"tones {tones} dBFS at mic, floor {self.floor_db:.1f} dBFS, SNR {self.snr_db:.0f} dB, clipped {self.clipped}")

    def summary(self) -> str:
        if self.note:
            return f"sound check: {self.note}"
        flags = ("" if self.clean else " CLIP") + ("" if self.heard else " NOT HEARD")
        return (f"sound check: loop gain {self.loop_gain_db:+.0f} dB (sink {self.sink_pct}%, source {self.source_pct}%, "
                f"mic base {self.source_base_db:+.0f} dB), "
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


def analyze(chunks: Union[Iterable[bytes], bytes], rate: int = RECORD_RATE) -> SoundCheck:
    """Reduce audio to tone levels as it arrives: each tone's level is its
    loudest 100 ms window, stepped 25 ms so a fast marimba decay reads the
    same wherever the recording happened to start, and the floor is the same
    measurement over the first 0.5 s, before the chime. Only Goertzel filters
    at the chime's own pitches ever read the samples (so DC offset and speech
    alike are invisible), and at most one window of audio is held at a time."""
    win, hop = rate // 10, rate // 40
    window, rest = array.array("h"), b""
    start = total = clipped = 0
    peak = [0.0] * len(TONES)
    ambient: list[list[float]] = [[] for _ in TONES]
    for chunk in ((chunks,) if isinstance(chunks, bytes) else chunks):
        buf = rest + chunk
        cut = len(buf) // 2 * 2
        rest = buf[cut:]
        samples = array.array("h")
        samples.frombytes(buf[:cut])
        total += len(samples)
        clipped += sum(1 for x in samples if abs(x) >= FULL_SCALE - 67)
        window.extend(samples)
        while len(window) >= win:
            for j, t in enumerate(_goertzel(window[:win], f, rate) for f in TONES):
                peak[j] = max(peak[j], t)
                if start + win <= rate // 2:
                    ambient[j].append(t)
            del window[:hop]
            start += hop
    if total < 10 * win:
        return SoundCheck(note="mic not delivering")
    floor = [sorted(a)[int(len(a) * 0.1)] for a in ambient]
    snr = min(_db(p) - _db(f) for p, f in zip(peak, floor))
    return SoundCheck(
        heard=snr > HEARD_SNR_DB,
        clipped=clipped,
        floor_db=max(map(_db, floor)),
        tone_db=tuple(map(_db, peak)),
        snr_db=snr,
    )


def default_volume(check: SoundCheck) -> Optional[int]:
    """Volume 4 for a machine that plays the chime loud, else None to keep the
    default. A clipped reading is a lower bound on loop gain, so it still counts."""
    if check.note or not check.heard:
        return None
    return LOUD_MACHINE_VOLUME if check.loop_gain_db >= LOUD_LOOP_GAIN_DB else None


@functools.cache
def _sent_tone_db() -> tuple[float, ...]:
    """Per-tone level of the chime itself under the same windowing analyze() applies to the mic."""
    return analyze(render_chime(RECORD_RATE).tobytes()).tone_db


def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5).stdout


def _volume_db(kind: str, name: str) -> float:
    m = re.search(r"(-?[\d.]+|-inf) dB", _pactl(f"get-{kind}-volume", name))
    return float(m.group(1)) if m else 0.0


def _base_db(kind: str, name: str) -> float:
    """Base volume of the device (the capture or playback chain at 0 dB hardware gain)."""
    block = re.search(rf"Name: {re.escape(name)}\n(.*?)(?=\n\S|\Z)", _pactl("list", f"{kind}s"), re.S)
    m = block and re.search(r"Base Volume:.*?(-?[\d.]+|-inf) dB", block.group(1))
    return float(m.group(1)) if m else 0.0


def _saved_state(kind: str, name: str) -> tuple[str, str]:
    pct = re.search(r"(\d+)%", _pactl(f"get-{kind}-volume", name))
    return (f"{pct.group(1)}%" if pct else "100%", "1" if "yes" in _pactl(f"get-{kind}-mute", name) else "0")


def _capture(sink: str, source: str, wav: Path) -> SoundCheck:
    """Record the mic while the chime plays 0.7 s in; about 3 s total. The
    audio streams through a pipe straight into analyze(): no complete
    recording ever exists, in memory or on disk."""
    rec = subprocess.Popen(
        ["parecord", "--raw", "--channels=1", f"--rate={RECORD_RATE}", "--format=s16le", "-d", source],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
    )
    try:
        return analyze(_stream(rec, sink, wav))
    finally:
        rec.terminate()
        try:
            rec.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rec.kill()
            rec.wait()
        rec.stdout.close()


def _stream(rec: subprocess.Popen, sink: str, wav: Path) -> Iterator[bytes]:
    """Mic audio in 25 ms chunks. The chime starts 0.7 s in whether or not the
    mic delivers, capture ends 0.3 s after it finishes playing, 15 s hard cap."""
    deadline = time.monotonic() + 15
    play_at, play, tail_end = time.monotonic() + 0.7, None, None
    try:
        while time.monotonic() < deadline and (tail_end is None or time.monotonic() < tail_end):
            if play is None and time.monotonic() >= play_at:
                play = subprocess.Popen(["paplay", "-d", sink, str(wav)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if play and tail_end is None and play.poll() is not None:
                tail_end = time.monotonic() + 0.3
            if select.select([rec.stdout], [], [], 0.1)[0]:
                chunk = rec.stdout.read(RECORD_RATE // 40 * 2)
                if not chunk:
                    return
                yield chunk
    finally:
        if play and play.poll() is None:
            play.kill()
            play.wait()


def _devices(sink: Optional[str], source: Optional[str], wait: float) -> tuple[str, str, str]:
    """Sink, source, and why the chime must not play (or ""), waiting up to
    `wait` seconds for a card that is still enumerating at boot."""
    deadline = time.monotonic() + wait
    while True:
        found = (sink or _pactl("get-default-sink").strip(), source or _pactl("get-default-source").strip())
        reason = _ready(*found)
        if reason not in ("no speaker", "no microphone") or time.monotonic() >= deadline:
            return *found, reason
        time.sleep(READY_POLL)


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
        ladder: tuple[int, ...] = (SOURCE_PCT,), wait: float = 0.0,
        log: Callable[[str], None] = lambda line: None) -> SoundCheck:
    """One chime per mic-gain step down the ladder until a take is clean; the
    default ladder is a single take. Restores sink and source state. Never
    raises: any failure is a note."""
    try:
        return _run(sink, source, sink_pct, ladder, wait, log)
    except Exception as e:
        return SoundCheck(note=f"failed ({type(e).__name__}: {e})")


def _run(sink: Optional[str], source: Optional[str], sink_pct: int, ladder: tuple[int, ...],
         wait: float, log: Callable[[str], None]) -> SoundCheck:
    if not shutil.which("pactl"):
        return SoundCheck(note="pulse tools missing")
    sink, source, reason = _devices(sink, source, wait)
    if reason:
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
                result = _capture(sink, source, wav)
                result.sink_pct, result.sink_db = sink_pct, _volume_db("sink", sink)
                result.source_pct, result.source_db = pct, _volume_db("source", source)
                result.source_base_db = _base_db("source", source)
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
