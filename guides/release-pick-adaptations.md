# Release Pick Adaptations

Hand-edits made while cherry-picking main commits onto release/1.x, newest first.
These are places where the release branch intentionally differs from the original
commit, usually because the pick depends on a feature that stays on main.
If a later pick conflicts weirdly in one of these spots, look here first.

## 2026-08-13

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
