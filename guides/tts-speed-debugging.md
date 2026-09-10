# TTS Speed Debugging

Speech on slow machines (HP Stream, Celeron/Pentium Silver, older Core 2) can take
seconds per word. This is how to find out where the time goes on a real device.

## What the model costs

`en_US-libritts-high` synthesis is the whole steady-state cost: phonemizing,
trimming, WAV writing and sound loading are all under 5 ms combined. On a Ryzen
6600U a two-word phrase is about 0.15 s. Gemini Lake Celerons have no AVX/AVX2,
run near 1.1 GHz under load, and do about half the work per clock, so expect a
20 to 30x gap: 3 to 5 s for the same phrase. The medium LibriTTS-R voice (same
speaker ids) is about 4.5x faster. ONNX Runtime's default thread pool is worth
about 2x over one thread, so a busy second core (UI, mixer, worker start) shows
up directly as slower speech.

## Diagnostics that already ship

All run from the parent menu's Terminal (or tty2 on the debug ISO, see
`debug-shell-escape.md`).

- `purple-speech-probe [extra .onnx ...]`: CPU model, SIMD flags, current and
  max clock, thermal, whether the speech worker process is alive, cache state,
  then per-voice timings split into phonemize, inference and post-processing,
  for the shipped voice and any voices passed on the command line, plus a
  one-thread run for comparison. Photograph the SUMMARY block or bring back
  `/var/log/purple/speech-probe-*.log`. Script: `scripts/purple-speech-probe.py`.
  To compare voices, put the `.onnx` and `.onnx.json` pairs on a USB stick,
  `sudo mount /dev/sdb1 /mnt`, then `purple-speech-probe /mnt/*.onnx`.
- `/tmp/purple-tts-debug.log`: every speak call, with millisecond timestamps:
  clip vs cache hit vs synthesis, `synth via worker|in-process: X.XXs`,
  `piper worker: waiting for ready`, mixer warm-up, play start and finish.
  Read it right after a slow utterance to attribute the seconds.
- `/tmp/purple-boot.log`: `piper worker: ready in Xs` (model load in the
  worker process) and mixer lines. `grep -iE 'piper|mixer' /tmp/purple-boot.log`.
- `dump-purple`: dumps every thread's stack into the boot log. Run it while a
  word is "stuck" to see whether the app is waiting on the worker pipe, the
  mixer lock, or something else.
- `purple-audio-probe`: the loudness probe, which also times model load and
  three synthesis calls (coarser than the speech probe, but on older images
  it's what is there).

## On an image without purple-speech-probe

Copy `scripts/purple-speech-probe.py` onto a USB stick and run:

```bash
sudo mount /dev/sdb1 /mnt
PYTHONPATH=/opt/purple python3 /mnt/purple-speech-probe.py /mnt/*.onnx
```

## Reading the results

- `simd: avx2=NO`: ONNX Runtime is on SSE kernels; expect 3 to 4x slower per
  clock than an AVX2 machine. Model size is the main lever.
- `freq` far below max while the probe runs: power or thermal limiting.
- `speech worker alive: NO` while the app runs: speech synthesizes in the UI
  process (blocking keystrokes) and pays model load again. Check the boot log
  for `piper worker: failed to start`.
- `cache: writable=False` or a clip count that never grows: every repeat of a
  word re-synthesizes. Cache dir is `~/.purple/cache/tts`.
- Word timings much larger in the app's speech log than in the probe: the
  app is contending for the CPU (look at what else runs) or waiting on the
  mixer, not on the model.
- Still too slow after all of the above: Parent Menu, Sound & Display, Voice,
  pick Quick. That swaps Piper for flite (`cmu_us_lnh`, no ML runtime), about
  0.1 s per phrase on any of these machines. The speech log then says
  `synth via quick`.
