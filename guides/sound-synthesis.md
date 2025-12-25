# Sound Synthesis for Purple Computer Play Mode

This document captures learnings from developing the musical tones for Play Mode (F2).

## Design Goals

- **For kids**: Playful, engaging, fun to press repeatedly
- **For parents**: Beautiful enough to listen to without annoyance
- **Full and rich**: Not thin or tinny
- **Organic**: Should feel like a real instrument, not a synthesizer
- **Clean mixing**: No clipping/static when many keys pressed rapidly

## Current Implementation: Marimba

We chose marimba because it's:
- Warm and woody (not harsh)
- Full-bodied (resonator tubes add richness)
- Playful (percussive attack is fun)
- Universally appealing

### Key Components

#### 1. Bar Partials (Wooden Bar Physics)
Real marimba bars have **inharmonic partials** - not perfect integer ratios:
```python
bar_partials = [
    (1.0, 1.0, 1.5),      # fundamental
    (3.9, 0.15, 4.0),     # ~4x (not exactly 4)
    (9.2, 0.05, 8.0),     # ~9x (not exactly 9)
]
```
Each tuple: `(frequency_ratio, amplitude, decay_rate)`

Higher partials decay faster - this is natural physics.

#### 2. Resonator Tube Modes
This is what makes marimba sound **FULL**. The tube under each bar:
- Resonates at the fundamental frequency
- Builds up after the initial strike
- Sustains longer than the bar itself

```python
tube_modes = [
    (1.0, 0.9, 0.9),      # main resonance - slow decay
    (2.0, 0.35, 1.5),     # 2nd harmonic
    (3.0, 0.15, 2.5),     # 3rd harmonic - presence
]
```

The tube envelope builds up then decays:
```python
tube_env = (1 - math.exp(-t * 25)) * math.exp(-t * decay_rate)
```

#### 3. Sub-Bass Warmth
A half-frequency undertone adds low-end body:
```python
sub_bass = 0.3 * math.exp(-t * 0.8) * math.sin(2 * math.pi * frequency * 0.5 * t)
```

#### 4. Attack Envelope
Soft mallet attack with "bloom" as resonator catches energy:
```python
if t < 0.012:
    attack = t / 0.012  # quick rise
elif t < 0.06:
    attack = 1.0 + 0.2 * math.sin(...)  # slight bloom
```

#### 5. Fade Out
Cosine curve fade (sounds more natural than linear):
```python
fade_progress = (t - fade_out_start) / fade_out_duration
sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))
```

## Preventing Clipping/Static

When many sounds play simultaneously:

1. **Lower peak level in WAV files**: `peak_level=0.5` (was 0.75)
2. **Lower playback volume**: `sound.set_volume(0.3)` (was 0.4)
3. **16 mixer channels**: `pygame.mixer.set_num_channels(16)`

## What We Tried (and Why It Didn't Work)

### Pure Karplus-Strong
- **Problem**: Sounded tinny, lacked body
- **Why**: K-S excels at plucked strings but needs something underneath for fullness

### Ethereal Chorus/Detune
- **Problem**: Too dreamy, not kid-friendly
- **Why**: Wide detuning + slow attack = ambient pad, not playful instrument

### Heavy Vibrato
- **Problem**: Sounded weird/bad
- **Why**: Marimba doesn't naturally have vibrato; felt artificial

### Perfect Harmonic Ratios
- **Problem**: Sounded synthetic/computerized
- **Why**: Real instruments have slightly inharmonic partials

### Too Much High-Frequency Content
- **Problem**: Sounded thin/tinny
- **Why**: Need strong fundamental and low harmonics for fullness

### Too Low Frequencies
- **Problem**: Muddy and blurred
- **Why**: Laptop speakers can't reproduce very low frequencies well

## Frequency Mapping

Current layout (balanced range):
```
Top row (Q-P):    392 - 988 Hz   (bright but not shrill)
Middle row (A-;): 196 - 494 Hz   (warm middle)
Bottom row (Z-/): 98 - 247 Hz    (rich low end)
```

## Available Generator Functions

The codebase has multiple generators for comparison:

1. **`generate_marimba()`** - Current, full resonant marimba (ACTIVE)
2. **`generate_piano_tone()`** - Original bright piano with ADSR
3. **`generate_rich_tone()`** - Xylophone-like, punchy attack

Switch in `main()`:
```python
samples = generate_marimba(freq)  # or generate_piano_tone, generate_rich_tone
```

## Other Instruments Considered

| Instrument | Character | Why/Why Not |
|------------|-----------|-------------|
| **Marimba** | Warm, woody, full | CHOSEN - best balance |
| **Steel Drum** | Bright, tropical, happy | Good alternative |
| **Kalimba** | Crystalline, intimate | Might be too delicate |
| **Balafon** | Buzzy, earthy | Buzz adds organic feel |
| **Xylophone** | Bright, punchy | Less full than marimba |
| **Celesta** | Magical, sparkly | Too ethereal |

## Technical Details

### Sample Rate & Format
- 44100 Hz, 16-bit mono WAV
- Duration: 1.0s per note
- Fade out: 0.15s (cosine curve)

### Playback
- pygame.mixer with 16 channels
- Buffer size: 2048 samples (~46ms latency)
- Volume: 0.3 per sound

## Future Improvements

Ideas to explore:
1. **Stereo width**: Slight L/R variation per note
2. **Velocity layers**: Harder hits = brighter tone
3. **Round-robin**: Multiple samples per note to avoid "machine gun" effect
4. **Room reverb**: Convolution or algorithmic reverb for space
5. **Sample-based hybrid**: Real attack sample + synthesized sustain

## References

- [Modal Synthesis (SuperCollider)](https://sccode.org/1-5ay)
- [Ableton Collision - Physical Modeling](https://www.ableton.com/en/packs/collision/)
- [Physical Modeling Synthesis Guide](https://www.musicradar.com/news/what-is-physical-modelling-synthesis)
- [Freesound - Marimba Samples](https://freesound.org/people/Samulis/packs/15684/)
