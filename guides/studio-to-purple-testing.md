# Studio to Purple testing

What a family does, tested end to end: make something in Studio, download it, carry it to Purple on a USB drive, add it, play with it, and copy saved work back to the drive. Four tiers, cheapest first. Every tier hands its pack to the same checker, `tests/canvas/pack_journey.py`, which reads whatever a `.purplepack` holds and looks for each part where a kid meets it: Play's answer, Art's Open, Music, the family room, the screen's colors.

| Tier | Run | What it drives | Cost |
| --- | --- | --- | --- |
| 1 | `just python -m pytest tests/canvas/test_studio_to_purple.py` | Packs built by Studio's own SDK (`studio/scripts/fixture-packs.ts`), the USB updater, the Add flow, export to a FAT image | seconds; skips without node or mtools |
| 2 | `just e2e-studio [--url URL]` | Studio's real UI in headless Chromium: a word, a recording, a photo, a starter room, Download; then the file through tier 1's checker | about a minute |
| 3 | `just e2e-vm [PACK] [--ref COMMIT]` | A built ISO in QEMU: the drive plugged in, Add, a kid's keys, Copy Saved Work to USB, the drive read back | minutes; needs KVM and `just build` |
| 4 | `just e2e-ai [--budget 10] [--goal ...]` | An AI parent in Studio, an AI kid on Purple, an Opus judge; real findings go to `docs/AI_UX_BUGS.md` | the budget, $10 by default |

`just e2e-pack FILE.purplepack [--shots DIR] [--expect TEXT]` runs the checker on any pack, a family's included. `--expect` fails when a check that should have passed is missing, which is how tier 2 catches Studio leaving something out of the download.

**Tier 3 presses keys blind.** They live in `tests/canvas/real_purple.py`, and tier 1 replays the same keys on a headless Purple, so a change that moves a menu item breaks a fast test instead of a VM run. Held keys go through `_handle_raw_key_event`, where Esc-hold timing lives. Its two hard checks need no OCR: the screen turns the pack's theme color, and the Art page copied to the drive has the pack picture's colors.

**Tier 4 finds bugs; tiers 1 and 2 keep them fixed.** Turn every real finding into a test there. The parent's browser is `studio/scripts/browser-bridge.ts`, the same `browser.mjs` tier 2 uses.

Browsers and QEMU need a real machine: Claude Code's sandbox blocks Chromium's sockets and hides `/dev/kvm`.
