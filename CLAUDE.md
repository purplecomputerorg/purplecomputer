# Claude Code Notes for Purple Computer

**Keep this file minimal.** When editing CLAUDE.md, also tighten existing sections: remove anything derivable from code, merge overlaps, cut stale info. Aim for <150 lines.

---

## Code Quality (TOP PRIORITY)

**DRY is king.** Never duplicate logic. When you see the same pattern in two places, extract it. Before adding code, check if existing code already handles the case or can be extended to. Reuse relentlessly: every copy-pasted block is a future bug. Prefer one clear code path over branching into similar-but-slightly-different flows. Minimize LOC, if-else sprawl, and surface area for bugs. Keep functions short and single-purpose. No spaghetti: if a function has more than 3 levels of nesting or 5+ early returns, restructure it.

**Comments: brief or absent.** Default is NO comment. Add one only when the WHY is non-obvious (hidden constraint, subtle invariant, workaround for a specific bug). Never explain WHAT the code does — well-named identifiers already do that. Never narrate the change, the task, or the caller. One line, not a paragraph. Multi-paragraph docstrings are almost always wrong. If you're tempted to write a design-decision essay, put it in a guide under `guides/` and link to it.

**Imports: no heavy work at module scope.** A new pip dep whose cold `import` takes >100ms must be lazy-loaded. Runtime-type-check packages (`typeguard`, `beartype`, etc.) do AST rewriting at decoration time — audit them carefully. Rule + case study: `guides/boot-hang-debugging.md#rule-dont-do-heavy-work-at-module-import-time`.

---

## Two UIs, keep them in sync (until Textual is gone)

`main` carries both UIs. The shipping Textual UX (`purple_tui/purple_tui.py`, the top-level `purple_tui/rooms/`, `modal.py`, `repl_panel.py`, `loop_panel.py`, `time_travel.py`, `config/alacritty/`, and their tests at the top of `tests/`) is frozen: fixes only, and it must never diverge from `release/1.x` unpicked. A change to those files is fine when it is picked onto `release/1.x` too (as the mixer consolidation was); a change that stays on main only would make every later `release-pick` conflict. The TUI never imports canvas modules. The canvas UX lives under `purple_tui/canvas/` with its tests in `tests/canvas/`; it is the default, `PURPLE_UX=tui` runs the Textual UI.

- **Bug fixes and tweaks to behavior that ships today land in BOTH.** Prefer fixing a shared module: `constants.py` tunables (hold thresholds, volume steps), `audio.py`, `tts.py`, `settings.py`, `keyboard.py`, `play_eval.py`, `mixer.py`, `palette.py`. One edit serves both and cherry-picks cleanly.
- **When the fix is in UI logic that exists twice, make two commits:** the TUI-only commit first, touching only original TUI paths (so `release-pick` is clean), then the canvas commit.
- **The rule is NOT "everything twice".** Features that will only ever ship with the next major release are canvas-only, need no Textual counterpart, and wait on `main` (`release-status` marks them `~`). Anything that is more than a clear bug fix: ask the user whether it needs a TUI counterpart before assuming either way.
- **DRY does not apply across the two UIs.** Duplicated logic between the frozen TUI and the canvas is deliberate; don't clean it up.

---

## Git Commits

Never run `git commit` directly. Always commit via `/checkpoint <msg>` (you supply the message) or `/wrap` (you draft a 1-2 sentence message from the diff). These come from the [`lanes`](https://github.com/tavinathanson/lanes) tool installed at `~/.claude/`.

Commit messages: **one line, max two short sentences.** No bullet-list body. No `Co-Authored-By` trailer. No `lane(...)` prefix — the script handles whatever prefixing is needed. Never use the default verbose Claude Code commit format.

Commit messages are public and customer-readable, and they are the record of UX changes (`docs/UX_LOG.md` is frozen): describe what changed, never the messaging strategy or tone intent behind it (no "warmer", "apologetic", "less blame-y").

If you're unsure what message to use, propose one and ask the user to confirm before committing.

## Shipping Branch

Customer ISOs build from `release/1.x`, a fixes-only branch checked out at `~/purplecomputer-release`. Never commit or merge there directly: fixes land on main first, then flow over via `just release-pick`. Full workflow: `guides/release-guide.md`, Release Branch section.

Cherry-pick decisions (fix vs feature) are the user's to confirm: propose picks, and after every `release-pick`, show the `just release-status` output with a one-line reason per commit for why it ships or waits.

---

## No Claude Memories

Do not save anything to Claude's persistent memory system. Durable notes and project state go in the repo under `docs/`. Tasks, bugs, and ideas go in Linear (see below), not a markdown backlog.

## Linear (task source of truth)

Tasks, bugs, and ideas for the Purple repos live in Linear (team `Purple Computer`, prefix `PUR`), not markdown backlogs. Check Linear yourself for a relevant issue before asking. When you finish or materially change tracked work, update or close the matching issue automatically; no need to ask first. Don't open and immediately close an issue for work you just did, but do close an existing open issue when its work lands. Without access, reference any `PUR-` id the user gives you; plan docs under `docs/` stay the technical reasoning of record, without restating issue status.

## Sensitive Files (DO NOT READ)

Never read `.env` files, `credentials.json`, or `secrets.yaml`.

---

## Hardware Safety (CRITICAL)

Purple Computer runs on kids' laptops. Never make changes that could cause issues on real hardware. VM-specific workarounds must be safe no-ops on real devices.

---

## Logging Policy

**Instrumentation can ship in the standard (+debug) ISO only if it's non-visual, non-expensive, and non-interfering.** Otherwise it's debug-only (gated on `/opt/purple/debug`).

- **Non-visual** = file descriptors only. Never write to stdout/stderr: under the canvas UI they land in the xinitrc log (fine for diagnostics, wrong for per-keystroke chatter); under the Textual UI, Textual owns stderr and any stray write corrupts the screen (`stderr_guard.hide_native_stderr()` points fd 2 at `/tmp/purple-stderr.log` for C-level noise). Use `boot_log`, `_power_log`, or `tts._dbg`.
- **Non-expensive** = cheap appends, no subprocess spawns at runtime, no fsync/flush cascades.
- **Non-interfering** = no EVIOCGRAB, no terminal mode changes, no signal handlers that paint.

**Exception:** user-facing error/diagnostic screens (e.g. `purple-x11-failed` scroll) ship in standard even though they're visual, because diagnosing failures matters more than hiding them.

Boot hang diagnostics: see `guides/boot-hang-debugging.md`. `purple_tui/boot_log.py` is the always-on heartbeat + watchdog; log lives at `/tmp/purple-boot.log` and persistently at `/var/log/purple/boot.log` on the debug ISO (casper writable partition).

---

## Target Audience

**Kids 3-10** (from learning letters to writing code) and their **non-technical parents**.

User-facing messages: simple, friendly, no jargon. Clear next steps, not error explanations. Add `(Technical: ...)` for known root causes. Use `SUPPORT_EMAIL` from `purple_tui/constants.py`.

**Writing style:** No em-dashes or spaced dashes. Use colons, commas, or periods instead.

---

## Python Environment

**Use `just` commands** (pre-approved, no confirmation needed):

```bash
just test    just run    just lint    just setup    just python foo.py
```

Always `just python` instead of `.venv/bin/python`.

---

## Headless UI Preview

```bash
just preview play                              # Default Play room
just preview art code_panel                    # Art with code panel open
just preview play type:5+3 key:enter           # Type and submit in Play
just preview play parent_menu                  # Parent menu modal
just preview play room_picker                  # Room picker modal
```

Output: PNG at `/tmp/screenshots/` (override with `PURPLE_SCREENSHOT_DIR`). `PURPLE_UX=tui just preview ...` previews the Textual UI. See `guides/headless-preview.md` for full reference.

**Visual/layout tests:** canvas tests drive a headless app from `purple_tui.canvas.harness` (`tests/canvas/`); Textual tests use `app.run_test()` (e.g. `tests/test_code_panel_layout.py`).

**AI UX testing:** `just ux` launches a Claude agent that explores the app as a simulated kid, presses keys, and reports bugs to `docs/AI_UX_BUGS.md`. Config in `scripts/ai_ux_config.py`. See `guides/ai-ux-testing.md`.

---

## Canvas UI (default)

The screen is a pygame window the app paints itself (`purple_tui/canvas/gfx.py`, `purple_tui/canvas/app.py`). Read `guides/canvas-architecture.md` before touching drawing or input. Rules that matter most: sizes come from `g.vh()`/`g.vw()`, every state change calls `app.invalidate()`, nothing animates on an idle screen, and text goes through `Gfx.text`/`Gfx.draw_markup` so ALL CAPS and emoji fallbacks apply everywhere.

## Textual UI (`PURPLE_UX=tui`, frozen)

`purple_tui/purple_tui.py` plus the top-level `purple_tui/rooms/`, `modal.py`, `repl_panel.py`, `loop_panel.py`, `time_travel.py`; runs in Alacritty (`config/alacritty/`). Fixes only, picked onto `release/1.x` (see Two UIs above). Notes kept for those fixes:

- **Layout constants:** `purple_tui/constants.py` (`VIEWPORT_WIDTH=134`, `VIEWPORT_HEIGHT=29`, `REQUIRED_TERMINAL_ROWS=37`); `scripts/calc_font_size.py` imports from there.
- **CSS scoping:** `CSS` is scoped to the defining class; use `DEFAULT_CSS` for inheritable styles. All modals inherit `PurpleModal` (`purple_tui/modal.py`) with the standard `#modal-dialog`, `#modal-title`, `#modal-hint` IDs.
- **Background colors:** `widget.styles.background` on `Static` doesn't repaint; use a `Widget` with `render_line()` returning `Strip([Segment(...)])`.
- **Flicker-free reflows (MusicGrid):** set `_layout_ready = False` before a height change, render from `_cached_layout` meanwhile, `on_resize` debounces 50ms then flips it back.
- **Code panel:** `_code_panel_active` (app-level, persists across rooms) vs `ReplPanel.is_open` (per-room). Space-hold pins canvas height; viewport grows by 4 on open. Textual's `_on_key()` suppresses events; all keyboard logic goes through `handle_keyboard_action()`.

## Keyboard Input (evdev + keyd, both UIs)

Input is read from evdev (`/dev/input/event*`), never from the terminal or the window. `keyd` (`config/keyd/default.conf`, built in `00-build-golden-image.sh`) remaps grave/tilde to Escape and RightAlt to F2 at the kernel level; do NOT add application-level remaps. `purple_tui/input.py` feeds `KeyboardStateMachine` (`purple_tui/keyboard.py`), which both UIs dispatch from. `HoldOrTap` distinguishes taps from holds; always check `on_other_key()` to flush a buffered space before the next character. Full rationale: `guides/keyboard-architecture.md`.

## Python Gotchas

**Environment variable checks:** Compare to `"1"`, never use truthiness (`"0"` is truthy).

**Dataclass constructors:** Check actual definitions. `NavigationAction` has `direction`, not `is_down`. `ControlAction` has `action` and `is_down`.

---

## Installer and Boot

**Debugging boot files:** Built ISOs are at `/opt/purple-installer/output/` and the source Ubuntu ISO at `/opt/purple-installer/build/`. Use `xorriso` to extract files (e.g., EFI binaries, grub.cfg) locally instead of needing a live-booted machine.

### Live USB Boot (Casper)

Both ISOs boot via Casper (Ubuntu's live boot framework). The normal ISO hides the GRUB menu and auto-boots. The debug ISO shows a GRUB menu with verbose boot options.

Installation is triggered through the live boot, not a GRUB menu entry. The install flow is:
1. Live boot starts Purple Computer normally
2. Parent menu → Install option → user confirms
3. `install.sh` runs (called from `parent_menu.py`)
4. Success screen: "Press ENTER to restart"
5. The app shows "All done" and on Enter `execv`s into `/run/purple-reboot-mount/purple-reboot` (static binary on tmpfs; the Textual UI exits first and passes `--wait`)

**Shutdown architecture:** All shutdown paths use `sudo systemctl poweroff --force` (sudo required even though purple user exists, because non-sudo systemctl lacks permission on live USB). Two-stage watchdog: stage 1 (5s) retries systemctl, stage 2 (8s) uses sysrq `echo o > /proc/sysrq-trigger`. Logged to `/tmp/purple-power.log`.

**Post-install reboot:** `purple-reboot` static binary on its own `exec,suid` tmpfs (Ubuntu's `/run` is `nosuid,noexec`). Ignores pty signals so it survives Alacritty dying after USB removal. Calls `reboot(2)` directly.

**Casper shutdown prompt** suppressed by touching `/run/casper-no-prompt` (runtime) + neutering `casper-stop` to `exit 0` at image build time.

### UEFI Boot (Installed System)

Boot must work on diverse hardware (ThinkPads, Dells, Surface, etc.):
- **UUID over labels** for root partition
- **Signed boot chain:** shim → GRUB → kernel (+ mmx64.efi MOK Manager alongside shim)
- **Multiple EFI paths:** `/EFI/BOOT/`, `/EFI/Microsoft/Boot/`, `/EFI/purple/`
- **NVRAM entries are bonus:** create but don't depend on them

Device-specific fixes: comment which device, keep under 10 lines. Run `build-scripts/diagnose-boot.sh` to debug.

---

## Build Image Size Reduction

Uses `--no-install-recommends`. `linux-firmware` must be installed explicitly.

**Kernel modules (`/lib/modules/`): DANGEROUS to prune.** Cross-directory dependencies are invisible. **Only remove networking modules** (`drivers/net`, `drivers/bluetooth`, `net/bluetooth`, `net/wireless`, `drivers/nfc`, `drivers/isdn`). Build runs `modprobe --dry-run` after pruning.

**Firmware (`/lib/firmware/`): Safe to prune aggressively.** Standalone blobs. Keep `i915/`, `amdgpu/`, `nvidia/`, `intel/`.
