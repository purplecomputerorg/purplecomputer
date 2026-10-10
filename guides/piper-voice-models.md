# Piper Voice Models

Purple Computer uses [Piper](https://github.com/rhasspy/piper) for local text-to-speech. This guide documents the model choice and performance characteristics.

## Current Model

**en_US-libritts_r-medium** (79 MB)

- Speaker 166 (id 6006 in the LibriTTS dataset)
- 22.05 kHz sample rate
- 904 speakers available (multi-speaker model)

## Why Medium Over High

The high-quality model (`en_US-libritts-high`, 137 MB) sounds slightly better but is dramatically slower on low-end CPUs without AVX/AVX2 instructions.

### Benchmark: HP Stream (Celeron N3060, no AVX)

Measured with `purple-speech-probe` on the actual device:

| Phrase | High | Medium | Speedup |
|--------|------|--------|---------|
| "cat" | 3.14s | 0.39s | 8x |
| "big dog" | 3.81s | 0.54s | 7x |
| "seven plus three is ten" | 10.70s | 1.20s | 9x |

The high model made single words take 3+ seconds, which feels broken. The medium model delivers sub-second response for typical words.

### Why the Gap Is So Large

1. **No AVX.** Gemini Lake Celerons (N3060, N4000, N4020) lack AVX and AVX2. ONNX Runtime falls back to SSE, which does roughly a quarter of the work per clock.

2. **Thermal throttling.** The Stream's Celeron runs at 480 MHz under sustained load (vs 2.4 GHz max) due to the 6W power limit.

3. **Smaller network.** The medium model has fewer parameters, so fewer matrix multiplications per phoneme.

On a modern desktop CPU with AVX2, the gap is closer to 4.5x.

## Speaker Consistency

Both models include speaker 166 from the same LibriTTS dataset, so the voice sounds like the same person. The medium model has slightly less detail in the timbre, but kids don't notice.

The pre-baked demo clips (`packs/core-sounds/content/voice/`) should be regenerated when switching models to keep the voice consistent between pre-recorded and dynamic speech:

```bash
.venv/bin/python scripts/generate_voice_clips.py --force
```

## Other Voices Considered

| Model | Size | Notes |
|-------|------|-------|
| lessac-medium | 63 MB | Single speaker, slightly robotic |
| lessac-low | 63 MB | Same network at 16 kHz, no real speedup |
| libritts-high | 137 MB | Best quality, too slow on Celerons |
| libritts_r-medium | 79 MB | **Current choice**: good quality, fast enough |

The "x_low" tier exists but has no LibriTTS voices and sounds noticeably robotic.

## Diagnostics

Run `purple-speech-probe` from the parent menu Terminal to measure synthesis speed on any device:

```bash
purple-speech-probe                     # shipped voice only
purple-speech-probe /mnt/*.onnx         # also test voices on a USB stick
```

The output includes CPU model, SIMD flags, clock speed, thermal state, and per-phrase timing breakdown. See `guides/tts-speed-debugging.md` for interpreting results.

## Changing the Voice

To switch models:

1. Update `VOICE_MODEL` in `purple_tui/tts.py`
2. Update the download URL in `build-scripts/00-build-golden-image.sh`
3. Regenerate pre-baked clips: `scripts/generate_voice_clips.py --force`
4. Clear the TTS cache on test devices: `just clear-tts-cache`

The cache key includes the model name, so stale WAVs from the old voice won't replay.
