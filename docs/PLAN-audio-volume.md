# Plan: Volume That Is Loud Enough, On Every Machine

> **Status: PROPOSED.** Nothing here has shipped. Phase 0 is measurement and is
> safe to land on its own; Phases 2 and 3 are deliberately gated on what Phase 0
> finds.

## Problem

Customers report Purple is too quiet, and more so on some machines than others.
We have volume limits in place that were added to stop hissing and crackling,
so the two complaints pull against each other.

## Root Cause

Four separate attenuations stack, and only one of them was chosen for hiss:

| Stage | Value | Where |
|---|---|---|
| Sample render level | peak-normalized to 0.7 FS (ukulele 0.4, low notes up to 0.95) | `scripts/generate_sounds.py:106` |
| Playback gain per sound | `set_volume(0.4)` | `purple_tui/rooms/music_room.py:670`, `:689` |
| App volume default | 60 of 100 | `purple_tui/constants.py:75` |
| System mixer cap | app volume x 0.85 into ALSA `Master` | `purple_tui/constants.py:76`, `purple_tui/purple_tui.py:3031` |

The dominant one is the last. `amixer sset Master 51%` is not "half volume":
ALSA percentages are linear in the control's raw value, and on typical HDA
codecs those steps are dB-linear over roughly -65 dB to 0 dB, so 51% lands near
-32 dB. Stacked on the -11 dBFS digital level, the shipped default sits about
43 dB below what the hardware can do. At Full it is still about 21 dB down.

Three things make it machine-dependent:

1. **`Master` may not exist.** SOF and Apple `cs8409` codecs often expose `PCM`,
   `Speaker`, or `Digital` instead. The call is a `Popen` with stderr to
   `/dev/null` inside a bare `except` (`purple_tui.py:3030`), so failure is
   completely silent: the badge updates and nothing happens.
2. **No boot-time mixer normalization.** Nothing in the golden image unmutes or
   levels the secondary controls, so `Speaker`, `PCM`, `Headphone`, and
   Auto-Mute Mode sit at whatever that codec defaults to.
3. **Hotplug never re-applies volume.** `_start_audio_hotplug`
   (`purple_tui.py:1295`) reinits the mixer for a new sink but does not call
   `_apply_volume_system()`, so a USB speaker lands at its own default level
   while the badge still shows the old one.

### Why it was built this way

Worth recording, because it changes which decisions are worth revisiting.

- **2026-03-09** (`2b1a12c`): `amixer sset Master` added. At that point
  `purple-x11.service` had no `SDL_AUDIODRIVER` and audio really was going
  straight to ALSA, so this was the correct and only tool.
- **2026-03-14** (`0a540cc`): the 85% cap added for analog amp hiss, measured on
  that same raw-ALSA chain.
- **2026-04-22** (`cd7c815`): audio routed through PulseAudio, for an unrelated
  reason (multi-card machines latching onto HDMI with no monitor). Volume was
  never moved with it.

So the volume layer is one layer too low by accident of history, not by design.
It kept working well enough to never force a revisit, and the Pulse migration
that followed was painful enough (`86c3fd2`, `cd0a206`, `bd37105`) to make
"leave the working amixer line alone" the rational local choice every time.

The hiss cap deserves the same scrutiny: it predates both PulseAudio and the
audio idle-release (`743a8d0`, 2026-07-23), which closes the PCM stream after a
quiet minute and on most laptop codecs mutes the speaker amp along with it. It
may already be solving a problem a later change solved better. Note the Music
room is exempt from idle release (`purple_tui.py:1332`), which is exactly where
silence between notes is most audible.

## Solution Overview

Stop hand-rolling the gain staging. Two tools already in the pipeline do it
properly:

1. **PulseAudio owns runtime volume.** One `pactl` call replaces the mapping,
   the control-name guessing, and the unmute handling, and it follows the
   default sink across hotplug.
2. **Loudness normalization owns asset levels.** Raise average level at a fixed
   peak ceiling, which buys perceived loudness without raising analog gain,
   which is the only way to get louder and less hissy at the same time.

The clipping budget that produced `set_volume(0.4)` is sound and is preserved:
N simultaneous uncorrelated notes sum to about +10*log10(N) dB, so a ten-note
key mash is +10 dB, and -11 dBFS per note is the right order of magnitude. The
loudness gain comes from raising RMS at constant peak, not from raising peak.

---

## Phase 0: Measure first (land independently)

### 0a. `pactl` is probably not in the image

`build-scripts/00-build-golden-image.sh:198` installs `alsa-utils pulseaudio`
under `--no-install-recommends`. `pactl` ships in `pulseaudio-utils`, which
`recording-setup/setup.sh:23` installs explicitly for exactly this reason but
the golden image does not.

If that is right, `scripts/purple-audio-dump.sh:92` and `:95` have been printing
"command not found" on every shipped device since April, and we have no field
data on any customer's audio chain.

Verify against a built image before assuming:

```bash
sudo chroot /path/to/golden-image bash -c "command -v pactl" || echo MISSING
```

Then add `pulseaudio-utils` to the install list and guard it the way the
existing audio pieces are guarded, next to the `AUDIO_MISSING` checks at
`build-scripts/00-build-golden-image.sh:757`:

```bash
chroot "$MOUNT_DIR" bash -c "command -v pactl >/dev/null" || AUDIO_MISSING="$AUDIO_MISSING pulseaudio-utils"
```

This is a prerequisite for Phase 1 regardless.

### 0b. Capture the gain chain in the audio dump

Add to `scripts/purple-audio-dump.sh`, keeping its read-only guarantee (all of
these are queries):

```bash
section "alsa mixer state"
amixer scontents 2>&1

section "alsa Master, raw and mapped"
amixer sget Master 2>&1
amixer -M sget Master 2>&1

section "pactl sink volumes (incl. base volume)"
sudo -u purple XDG_RUNTIME_DIR=/run/user/1000 pactl list sinks 2>&1
```

`base volume` is the interesting field: it tells us where Pulse thinks the
sink's nominal level sits, which is the cleanest signal for "this machine has a
weak amp."

### 0c. Take the measurement

On at least three machines, ideally including one that has been complained
about and one Mac: capture the dump at the shipped default, then walk the volume
steps and record what `Master` and the Pulse sink volume actually do.

**This is what decides Phase 3.** Specifically: does hiss return at 100% on any
machine once the stream is open, and is it audible in the Music room where the
idle release is vetoed.

---

## Phase 1: Move volume onto PulseAudio

### 1a. One helper, two callers

The amixer invocation is currently duplicated at `purple_tui/purple_tui.py:3031`
and `purple_tui/rooms/parent_menu.py:683`. Collapse to a single function; the
parent menu's test-sound path differs only in that it wants a specific level and
a blocking call.

New in `purple_tui/audio.py` (already the audio helper module):

```python
_backend = None  # "pactl" | "amixer", probed once


def _probe_backend() -> str:
    """Pick the volume backend once. pactl maps percentages perceptually and
    picks the right ALSA control per machine; amixer -M is the fallback."""
    global _backend
    if _backend is None:
        _backend = "pactl" if shutil.which("pactl") else "amixer"
    return _backend


def system_volume_argv(level: int) -> list[list[str]]:
    """Commands that set the system volume to `level` (0-100)."""
    if _probe_backend() == "pactl":
        return [
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if level == 0 else "0"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
        ]
    return [["amixer", "-M", "sset", "Master", f"{level}%", "unmute" if level else "mute"]]
```

Splitting argv construction from execution keeps it unit-testable, which matters
because there is currently **no test at all** on this path.

Callers stay non-blocking (`Popen`), which `docs/UX_LOG.md:147` records as
load-bearing: a blocking mixer call used to freeze volume adjustment.

### 1b. Delete the cap and the mapping

In `purple_tui/constants.py`:

- Remove `SYSTEM_VOLUME_MAX` and the `* SYSTEM_VOLUME_MAX / 100` at both call
  sites. The app level goes to Pulse unchanged.
- `VOLUME_LEVELS = [0, 20, 40, 60, 80, 100]`. Pulse's cubic mapping makes
  percentage approximately proportional to perceived loudness, so even spacing
  is now the correct spacing. The 2026-03 respacing to `[0, 15, 35, 60, 85, 100]`
  was compensating for the linear-raw ALSA scale, and under that scale its low
  steps land near -55 dB and -42 dB, effectively inaudible.
- `VOLUME_DEFAULT = 80`.

### 1c. Derive the badge from the levels

`_volume_badge` (`purple_tui/purple_tui.py:175`) hardcodes the old thresholds,
so changing `VOLUME_LEVELS` silently desyncs the bars and labels. Derive the
bars and label from the level's index in `VOLUME_LEVELS` instead, keeping the
existing label set (Sound Off, Whisper, Quiet, Medium, Loud, Full) and icons.

### 1d. Re-apply volume on hotplug

In `_start_audio_hotplug`'s `_on_event` (`purple_tui.py:1298`), after the mixer
reinit succeeds, call `_apply_volume_system()` so a newly plugged sink gets the
level the badge is claiming.

### 1e. Stop swallowing failures

Keep the volume change non-blocking, but record the backend probe result and any
non-zero exit to the boot log via `boot_log.heartbeat`, so the next audio dump
shows whether the volume path is even reaching the hardware. Non-visual and
cheap, so it satisfies the logging policy for the standard ISO.

### Files touched

- `purple_tui/audio.py` (new helper)
- `purple_tui/purple_tui.py` (`_apply_volume_system`, `_volume_badge`, `_on_event`)
- `purple_tui/rooms/parent_menu.py` (`_play_test_sound`)
- `purple_tui/constants.py`
- `build-scripts/00-build-golden-image.sh` (Phase 0a)
- `tests/test_audio_volume.py` (new)
- `docs/UX_LOG.md`

---

## Phase 2: Asset loudness (the louder-without-hiss lever)

Samples are **peak**-normalized today, and a decaying marimba note has a large
peak-to-average ratio, so most of the available loudness is discarded. Speech is
peak-normalized separately to -3 dBFS (`purple_tui/tts.py:247`), which is why it
sits roughly 8 to 13 dB above the instruments.

Replace peak normalization with loudness normalization against a fixed true-peak
ceiling. Same peak budget, same clipping safety, materially more perceived
loudness. Expect 6 to 10 dB.

**Use one shared pure-Python function, not ffmpeg's `loudnorm`.** `loudnorm`
would be the obvious choice for the build-time assets, since
`scripts/generate_sounds.py:69` already shells out to ffmpeg. But runtime TTS
synthesis for uncached phrases post-processes in-process (`_postprocess_wav`),
and it must produce the same level as the pre-generated clips. Adding a
subprocess per spoken phrase is both a latency cost and against the runtime
policy, so a second normalizer would appear. One function keeps a single code
path:

```python
def normalize_loudness(samples, target_rms_dbfs, ceiling_dbfs):
    """Scale to a target RMS, then pull back if the peak would exceed ceiling."""
```

Used by `generate_sounds.py`, `scripts/generate_voice_clips.py`, and
`tts._postprocess_wav`. This deletes the ad-hoc per-instrument `peak_level`
constants (0.7 / 0.4 / 0.7) and the separate -3 dBFS speech target.

Keep `loudness_compensated_peak` (`generate_sounds.py:80`), applied to the RMS
target rather than the peak. Plain RMS is not ear-weighted, so the low-note
compensation is still doing real work.

Re-render assets (`packs/core-sounds/content`, 5.7 MB) and A/B against the
current set. Land as its own commit so it is trivially revertible and so the
before/after is easy to listen to.

---

## Phase 3: Conditional, gated on Phase 0c

Do not do these speculatively.

- **Key-mash headroom.** If Phase 2 lands and pileups clip, scale by active
  channel count (roughly 1/sqrt(N)) so a single note is loud and a mash ducks
  itself. About 10 lines in `music_room.play_sound_with_instrument`, and it
  replaces the empirical tuning behind `scripts/clip_analysis*.py` and
  `find_safe_*.py` with one predictable rule.
- **Extra loud.** Pulse accepts above 100% (software gain). A parent-menu option
  for weak-speaker machines is then a one-line change. It clips above 100%, so
  it stays opt-in, not a default.
- **Boot-time mixer normalization.** If the dumps show secondary controls
  (`Speaker`, `PCM`, Auto-Mute Mode) at low defaults on real machines, add a
  build-time or boot-time pass that levels them and drives loudness from Pulse
  alone. Must skip unrecognized controls rather than guessing, per the hardware
  safety rule.
- **Hiss.** Only if Phase 0c actually reproduces it. The fix is per-machine, or
  extending the idle release into the Music room, not a global cap.

---

## Verification

**Automated** (`tests/test_audio_volume.py`, new):

- `system_volume_argv` returns pactl commands when pactl is present, `amixer -M`
  when it is not, and mutes at 0.
- Every value in `VOLUME_LEVELS` maps to a distinct badge, and the badge is
  derived from the levels rather than hardcoded.
- Build-script guard test for `pulseaudio-utils`, following the existing pattern
  in `tests/test_build_verifications.py`.

**On hardware** (the parts tests cannot cover):

1. Boot on three machines, one of them previously reported as quiet. Walk all
   six steps: every non-zero step is audible and each is clearly louder than the
   last.
2. Compare speech and a music note at the same setting: they should now be close
   in loudness.
3. Plug in a USB speaker mid-session: volume should match the badge without a
   restart.
4. Music room, mash ten keys: no crackle.
5. Sit in the Music room in silence at Full for a minute and listen for hiss.
6. Headphone jack, plug and unplug.

---

## Risks

- **Pulse dead or `pactl` missing.** Falls back to `amixer -M`, which is still
  better than today's linear-raw call. If Pulse is dead there is no sound at
  all, and that path is already handled by `audio_ok`.
- **Louder by default is a real change on machines that were already fine.** The
  step spacing keeps the low end usable, and Volume Lock is unaffected. Worth
  testing on the loudest machine we have, not just the quietest.
- **Phase 2 changes every shipped sound.** Separate commit, easy revert, listen
  before shipping.
- **Release branch.** Phase 0 and Phase 1 read as fixes and are plausible
  `release-pick` candidates. Phase 2 changes shipped assets and should soak on
  main first. Per `CLAUDE.md`, the pick decision is yours to confirm.

## Open Questions

1. **Speech or music?** If complaints are about the voice specifically, Phase 1
   is most of the fix. If about music and sound effects, Phase 2 matters more.
   Worth asking the next customer who reports it.
2. **Which machines?** Model plus the audio dump turns the next report into a
   diagnosis instead of a guess. Blocked on Phase 0a.
3. **Was the original hiss a noise floor, or a specific codec?** If the latter,
   the global cap was always the wrong shape and Phase 3 is a per-machine fix.
