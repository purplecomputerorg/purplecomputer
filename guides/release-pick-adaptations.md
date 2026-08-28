# Release Pick Adaptations

Hand-edits made while cherry-picking main commits onto release/1.x, newest first.
These are places where the release branch intentionally differs from the original
commit, usually because the pick depends on a feature that stays on main.
If a later pick conflicts weirdly in one of these spots, look here first.

## 2026-08-28

The audio chain, `ea6c0c7` through `717f6a1` (18 picks: PulseAudio volume, speech
leveling and pacing, the TTS worker, the volume limit, the startup chime and
the 1 to 10 scale). Three spots needed hands:

- `6eef3e2` (volume through PulseAudio) → release `dfdc53e`
  - `purple_tui/room_picker.py`: the import list. Main's side carried `ICON_TIME_TRAVEL` (Time Travel `a14d1e6` stays on main); release keeps `ICON_BROOM, ICON_CODE,` and drops the volume icons the pick removes.
  - `docs/UX_LOG.md`: release's log with the chain's entries inserted at the top, the same rule at `e74b70d` → `e1a4b15`. Only chain commits touched the log on main over this span, so the entries are exactly the chain's.
- `e5fa6e7` (speech leveling, clips regenerated) → release `ee4cce3`
  - `packs/core-sounds/content/voice/`: six clips came up modify/delete because `fa4e203` (demo sounds, main-only) had added them and this pick regenerated them. Took the pick's versions; they are generated clips nothing on release plays. Later picks regenerate them again without conflict.

## 2026-08-13

- `6c79598` (initrd prune v2) → release `5611960`
  - `guides/usb-flash-settle.md`: took main's merged version wholesale. The commit carried a swept-in guide paragraph written against the pre-`e39b3cd` text; main's HEAD already harmonizes both edits, so release converges to it rather than diverging.
- `95899bd` (infiniband prune) → release `fbc3ed5`
  - Dropped `guides/release-pick-adaptations.md` from the pick (delete-resolution). The file rode along via a broad `git add -A`; it is this guide, a main-only process doc from `fcd7be8`, and release deliberately does not carry it.
- `d23ad08` (late power button adoption + power/evdev log persistence + first-boot audio check) → release `cde4645`
  - `scripts/preview.py`: kept only the `first_boot` docstring line, dropped the `time_travel` line that rode along in the conflict (Time Travel `a14d1e6` stays on main; no handler code came over).

## 2026-08-07

- `c795423` (swap install fix + no-accel-while-painting) → release `aa11a65`
  - `art_room.py`: kept release's paint condition (`_space_down or space_held or char_held`) instead of main's `_pen_down` (pen toggle `14dec55` stays on main); adopted the new `step_count` gating on top of it.
  - `tests/test_paint_accelerated.py`: took main's rewritten file, translated pen state to space (`_pen_down` → `_space_down`, `test_pen_down_never_accelerates` → `test_space_paint_never_accelerates`).
  - `docs/UX_LOG.md`: kept only this commit's two entries, dropped Time Travel / pen entries that rode along in the conflict.
  - When `14dec55` (pen toggle) ships in 2.0, these diverge-points collapse: expect conflicts in exactly these spots.

- `1f0d5b5` (appples plural count + drag coats once) → release `acce8d0`
  - `art_room.py`: dropped the hunk patching `restore_timeline_state` (Time Travel `a14d1e6` stays on main; the method doesn't exist on release).
  - `docs/UX_LOG.md`: kept only this commit's two entries.
  - When `a14d1e6` ships, re-apply `canvas._last_paint_pos = None` inside `restore_timeline_state`.
