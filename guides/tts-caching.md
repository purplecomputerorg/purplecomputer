# TTS Caching

How spoken text gets fast, and why the cache stores raw WAV.

## Playback layers

`speak_sync` in `purple_tui/tts.py` tries three sources in order:

1. **Pre-generated voice clips** (`packs/core-sounds/content/voice/*.wav`): hand-curated phrases like `goodbye.wav`. Instant, shipped on the image.
2. **Disk cache** (`~/.purple/cache/tts/*.wav`): anything Piper has synthesized before on this machine. Instant on repeat.
3. **Piper synthesis**: everything else. Takes a moment; the UI shows a pending indicator (··) until playback starts.

The cache is keyed on normalized text (punctuation and case stripped), so "hello!" and "Hello" share an entry. Capped at 50MB with LRU eviction by access time.

## Why raw WAV, not OGG

The cache originally copied WAVs. A later commit (1d3fc81) switched to OGG via an `ffmpeg` subprocess to shrink cache entries about 10x. But ffmpeg was never installed on the golden image, and `_store_cache` swallows all exceptions, so on real hardware every store silently failed: the cache stayed empty forever and every phrase re-synthesized on every repeat. Dev machines have ffmpeg, so the bug never reproduced locally (the one test that would have caught it was skipped without ffmpeg).

Reverting to WAV fixed it. The tradeoff math:

- Piper output is 22kHz 16-bit mono, about 43 KB per second of speech. A typical utterance is 50-130 KB as WAV, roughly 10x smaller as OGG.
- The 50MB LRU cap bounds disk use either way. Compression only changes capacity: roughly 500-1000 phrases as WAV vs ~5000 as OGG. A kid does not cycle through 500 distinct phrases before eviction becomes harmless.

## Rejected alternatives

- **Install ffmpeg on the image**: 50MB+ dependency tree on an image we actively slim, plus a runtime subprocess spawn per cache store. All to compress a cache that is already size-bounded.
- **vorbis-tools (oggenc)**: much smaller than ffmpeg but still a new system package and subprocess.
- **soundfile pip package**: PulseAudio already pulls in libsndfile, which includes a Vorbis encoder, so this needs no new system packages. Still a new pip dep (plus cffi), lazy-import handling, and a second audio-writing code path. Keep this in mind if cache capacity ever becomes real pressure; not worth it today.

## Shipped sound assets are separate

Compressing the image is a build-time concern, not a runtime one. The 81 shipped WAVs in `packs/` total 2.5MB; converting them to OGG (as the instrument notes already are) would happen at asset-generation time with ffmpeg on a dev machine and save about 2MB on a multi-GB ISO. Not currently worth doing.
