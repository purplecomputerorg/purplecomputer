#!/usr/bin/env python3
"""Purple Computer: speech speed probe. Run from the parent-menu terminal on a
machine where speech feels slow, then photograph the SUMMARY block at the end
(the full log lands in /var/log/purple/speech-probe-*.log, or /tmp).

    purple-speech-probe                     # the shipped voice
    purple-speech-probe /mnt/*.onnx         # also time other Piper voices

On an image without this command, copy the script to a USB stick and run:

    PYTHONPATH=/opt/purple python3 purple-speech-probe.py [voices...]

Read-only: it never touches the running app, the cache, or audio state.
"""

import glob
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PHRASES = ("cat", "big dog", "seven plus three is ten")
SIMD_FLAGS = ("sse4_2", "avx", "avx2", "fma", "avx512f")
_summary: list[str] = []
_log = None


def out(line: str = "") -> None:
    print(line, flush=True)
    if _log:
        _log.write(line + "\n")


def section(title: str) -> None:
    out()
    out(f"===== {title} =====")


def note(line: str) -> None:
    _summary.append(line)


def read(path: str, default: str = "?") -> str:
    try:
        return Path(path).read_text().strip() or default
    except OSError:
        return default


def run(*argv: str) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def open_log() -> None:
    global _log
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for d in ("/var/log/purple", "/tmp", os.path.expanduser("~")):
        try:
            _log = open(f"{d}/speech-probe-{stamp}.log", "w")
            return
        except OSError:
            continue


def machine() -> None:
    section("machine")
    out(f"{read('/sys/class/dmi/id/sys_vendor')} {read('/sys/class/dmi/id/product_name')}")
    cpuinfo = read("/proc/cpuinfo", "")
    model = re.search(r"model name\s*:\s*(.*)", cpuinfo)
    cpu = model.group(1) if model else "?"
    flags = set(re.search(r"flags\s*:\s*(.*)", cpuinfo).group(1).split()) if "flags" in cpuinfo else set()
    simd = " ".join(f"{f}={'yes' if f in flags else 'NO'}" for f in SIMD_FLAGS)
    cur = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "0")
    mx = read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "0")
    gov = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    temps = [int(read(p, "0")) // 1000 for p in glob.glob("/sys/class/thermal/thermal_zone*/temp")]
    out(f"cpu: {cpu} ({os.cpu_count()} threads)")
    out(f"simd: {simd}")
    out(f"freq: {int(cur) // 1000} MHz now, {int(mx) // 1000} MHz max, governor {gov}")
    out(f"thermal: {' '.join(f'{t}C' for t in temps) or '?'}")
    out(run("free", "-m"))
    note(f"cpu: {cpu}, {os.cpu_count()} threads, {int(cur) // 1000}/{int(mx) // 1000} MHz")
    note(f"simd: {simd}")


def app_state(tts) -> None:
    section("app state")
    app = run("pgrep", "-f", "python.* -m purple_tui")
    worker = run("pgrep", "-f", "purple_tui.tts_worker")
    out(f"app running: {'yes' if app else 'no'}   speech worker alive: {'yes' if worker else 'NO'}")
    note(f"speech worker alive: {'yes' if worker else 'NO'}" if app else "app not running")
    cache = tts._CACHE_DIR
    files = list(cache.glob("*.wav")) if cache.is_dir() else []
    writable = os.access(cache, os.W_OK) if cache.is_dir() else os.access(cache.parent, os.W_OK)
    out(f"cache: {cache}  {len(files)} clips, {sum(f.stat().st_size for f in files) // 1024} KB, writable={writable}")
    note(f"cache: {len(files)} clips, writable={writable}")
    out()
    out("boot log (piper/mixer):")
    boot = [ln for ln in read("/tmp/purple-boot.log", "").splitlines() if re.search(r"piper|mixer", ln, re.IGNORECASE)]
    for line in boot[-20:]:
        out(f"  {line}")
    out()
    out(f"speech log tail ({tts._DEBUG_LOG}):")
    for line in read(tts._DEBUG_LOG, "  (none)").splitlines()[-20:]:
        out(f"  {line}")


def make_session(path: Path, threads: int):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), sess_options=so, providers=["CPUExecutionProvider"])


def time_voice(tts, path: Path, threads: int = 0) -> None:
    from piper import PiperVoice
    label = f"{path.name} [{threads or 'default'} threads]"
    section(f"voice: {label} ({path.stat().st_size // 2**20} MB)")
    t0 = time.perf_counter()
    voice = PiperVoice.load(str(path))
    if threads:
        voice.session = make_session(path, threads)
    load = time.perf_counter() - t0
    out(f"load: {load:.2f}s")
    cfg = tts._make_synth_config()
    if voice.config.num_speakers <= (cfg.speaker_id or 0):
        cfg.speaker_id = None if voice.config.num_speakers == 1 else 0
    out(f"{'phrase':28} {'phonemize':>9} {'infer':>8} {'post':>6} {'total':>7}  {'audio':>5}  RTF")
    results = []
    for i, text in enumerate(("purple",) + PHRASES):
        prepared = tts._prepare_text(text)
        t0 = time.perf_counter()
        phonemes = voice.phonemize(prepared)
        t1 = time.perf_counter()
        audio = [voice.phoneme_ids_to_audio(voice.phonemes_to_ids(p), cfg) for p in phonemes if p]
        t2 = time.perf_counter()
        import array
        samples = array.array("h")
        for a in audio:
            samples.frombytes((a * 32767).astype("int16").tobytes())
        tts.postprocess_samples(samples, voice.config.sample_rate)
        t3 = time.perf_counter()
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        t4 = time.perf_counter()
        tts.synthesize_to_file(voice, prepared, wav)
        total = time.perf_counter() - t4
        os.unlink(wav)
        secs = sum(len(a) for a in audio) / voice.config.sample_rate
        tag = " (warm-up)" if i == 0 else ""
        out(f"{prepared + tag:28} {t1 - t0:8.3f}s {t2 - t1:7.3f}s {t3 - t2:5.3f}s {total:6.3f}s  {secs:4.2f}s  {total / secs:.2f}")
        if i:
            results.append(total)
    note(f"{label}: load {load:.1f}s, word {results[0]:.2f}s, two words {results[1]:.2f}s, sentence {results[2]:.2f}s")


def main() -> None:
    open_log()
    out(f"purple-speech-probe {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    sys.path.insert(0, os.environ.get("PURPLE_SRC", "/opt/purple"))
    machine()
    try:
        from purple_tui import tts
        import onnxruntime
    except ImportError as e:
        out(f"cannot import the app: {e} (set PYTHONPATH or PURPLE_SRC)")
        return
    app_state(tts)
    out()
    out(f"onnxruntime {onnxruntime.__version__}, piper voice search: {[str(p) for p in tts._get_voice_search_paths()]}")
    shipped = tts.find_voice_model()
    note(f"shipped voice: {shipped.name if shipped else 'NOT FOUND'}")
    extra = [Path(a) for a in sys.argv[1:]]
    for path in ([shipped] if shipped else []) + extra:
        if not path.exists():
            out(f"missing: {path}")
            continue
        try:
            time_voice(tts, path)
        except Exception as e:
            out(f"{path.name}: FAILED {type(e).__name__}: {e}")
            note(f"{path.name}: FAILED {type(e).__name__}")
    if shipped and shipped.exists():
        time_voice(tts, shipped, threads=1)
    section("SUMMARY")
    for line in _summary:
        out(line)
    if _log:
        out(f"(saved to {_log.name})")


if __name__ == "__main__":
    main()
