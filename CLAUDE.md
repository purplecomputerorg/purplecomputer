# Claude Code Notes for Purple Computer

**Keep this file minimal.** When editing CLAUDE.md, also tighten existing sections: remove anything derivable from code, merge overlaps, cut stale info. Aim for <150 lines.

---

## Code Quality (TOP PRIORITY)

**DRY is king.** Never duplicate logic. When you see the same pattern in two places, extract it. Before adding code, check if existing code already handles the case or can be extended to. Reuse relentlessly: every copy-pasted block is a future bug. Prefer one clear code path over branching into similar-but-slightly-different flows. Minimize LOC, if-else sprawl, and surface area for bugs. Keep functions short and single-purpose. No spaghetti: if a function has more than 3 levels of nesting or 5+ early returns, restructure it.

**Comments: brief or absent.** Default is NO comment. Add one only when the WHY is non-obvious (hidden constraint, subtle invariant, workaround for a specific bug). Never explain WHAT the code does — well-named identifiers already do that. Never narrate the change, the task, or the caller. One line, not a paragraph. Multi-paragraph docstrings are almost always wrong. If you're tempted to write a design-decision essay, put it in a guide under `guides/` and link to it.

**Imports: no heavy work at module scope.** A new pip dep whose cold `import` takes >100ms must be lazy-loaded. Runtime-type-check packages (`typeguard`, `beartype`, etc.) do AST rewriting at decoration time — audit them carefully. Rule + case study: `guides/boot-hang-debugging.md#rule-dont-do-heavy-work-at-module-import-time`.

---

## Git Commits

Never run `git commit` directly. Always commit via `/checkpoint <msg>` (you supply the message) or `/wrap` (you draft a 1-2 sentence message from the diff). These use `.claude/skills/swarm-monitor/scripts/checkpoint.sh`.

Commit messages: **one line, max two short sentences.** No bullet-list body. No `Co-Authored-By` trailer. No `lane(...)` prefix — the script handles whatever prefixing is needed. Never use the default verbose Claude Code commit format.

If you're unsure what message to use, propose one and ask the user to confirm before committing.

---

## Sensitive Files (DO NOT READ)

Never read `.env` files, `credentials.json`, or `secrets.yaml`.

---

## Hardware Safety (CRITICAL)

Purple Computer runs on kids' laptops. Never make changes that could cause issues on real hardware. VM-specific workarounds must be safe no-ops on real devices.

---

## Logging Policy

**Instrumentation can ship in the standard (+debug) ISO only if it's non-visual, non-expensive, and non-interfering.** Otherwise it's debug-only (gated on `/opt/purple/debug`).

- **Non-visual** = file descriptors only. Never write to stdout/stderr — Textual owns stderr for its UI, so any stray write corrupts the screen.
- **Non-expensive** = cheap appends, no subprocess spawns at runtime, no fsync/flush cascades.
- **Non-interfering** = no EVIOCGRAB, no terminal mode changes, no signal handlers that paint.

**Exception:** user-facing error/diagnostic screens (e.g. `purple-x11-failed` scroll) ship in standard even though they're visual, because diagnosing failures matters more than hiding them.

Boot hang diagnostics: see `guides/boot-hang-debugging.md`. `purple_tui/boot_log.py` is the always-on heartbeat + watchdog; log lives at `/tmp/purple-boot.log` and persistently at `/var/log/purple/boot.log` on the debug ISO (casper writable partition).

---

## Target Audience

**Kids 4-7** (fun for 2-8+) and their **non-technical parents**.

User-facing messages: simple, friendly, no jargon. Clear next steps, not error explanations. Add `(Technical: ...)` for known root causes. Use `SUPPORT_EMAIL` from `purple_tui/constants.py`.

**Writing style:** No em-dashes or spaced dashes. Use colons, commas, or periods instead.

**UX changes:** Add a one-line description to `UX_LOG.md`.

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

Output: PNG at `/tmp/screenshots/` (override with `PURPLE_SCREENSHOT_DIR`). See `guides/headless-preview.md` for full reference.

**Visual/layout tests:** `app.run_test()` verifies widget sizes and positions headlessly. See `tests/test_code_panel_layout.py`.

**AI UX testing:** `just ux` launches a Claude agent that explores the app as a simulated kid, presses keys, and reports bugs to `AI_UX_BUGS.md`. Config in `scripts/ai_ux_config.py`. See `guides/ai-ux-testing.md`.

---

## Terminal Layout Constants

Single source of truth: `purple_tui/constants.py` (`VIEWPORT_WIDTH=134`, `VIEWPORT_HEIGHT=30`, `REQUIRED_TERMINAL_ROWS=38`). Font size calc in `scripts/calc_font_size.py` imports from there.

---

## Textual Framework Workarounds

### CSS Scoping (IMPORTANT)

`CSS` is **scoped** to the defining class. A base class's `CSS` rules won't apply inside subclass instances. Use `DEFAULT_CSS` for inheritable styles (lower specificity, subclass `CSS` overrides cleanly).

### Modal Dialogs

All modals inherit from `PurpleModal` (`purple_tui/modal.py`), which provides shared `DEFAULT_CSS` for centering, dialog background, title, and hint styling. Use standard IDs: `#modal-dialog`, `#modal-title`, `#modal-hint`. Content-specific widgets use their own IDs. Each subclass sets its own width, padding, and border via `CSS`.

### Background Colors (Textual 0.67.0)

`widget.styles.background` on `Static` doesn't repaint. Use `Widget` subclass with `render_line()` returning `Strip([Segment(...)])`.

### Flicker-Free Reflows (MusicGrid pattern)

When widget height changes, Textual renders intermediate sizes causing flicker. Fix: `_layout_ready = False` before change, cache last good dimensions in `_cached_layout`, render with cached values during reflow. `on_resize` debounces 50ms then sets `_layout_ready = True`.

### Keyboard Input (evdev + keyd)

Input via evdev (`/dev/input/event*`), bypassing the terminal. Alacritty is display-only.

```
Physical Keyboard → keyd (EVIOCGRAB + uinput) → keyd virtual keyboard
                                               → EvdevReader → KeyboardStateMachine → handle_keyboard_action()
```

**keyd** (`config/keyd/default.conf`, built from source in `00-build-golden-image.sh`) runs as a systemd service on the golden image and does the grave/tilde→Escape and RightAlt→F2 remaps at the kernel level, so they work before Purple starts and at rescue shells. `purple_tui/input.py` uses keyd's virtual device alongside any physicals keyd didn't grab. Do NOT add application-level grave/tilde remaps — they'd duplicate keyd and only work while Purple is running. Full rationale (why keyd not systemd-hwdb, Apple SPI driver constraint): `guides/keyboard-architecture.md#remap-layer-choice`.

**Key files:** `purple_tui/input.py`, `purple_tui/keyboard.py`. See `guides/keyboard-architecture.md`.

**Single code path:** All keyboard logic in `handle_keyboard_action()`. Textual's `_on_key()` suppresses events. All navigation is explicit (no Tab/Shift-Tab focus).

### HoldOrTap Pattern

`HoldOrTap` (keyboard.py) distinguishes quick taps from long holds (space-hold toggles code panel). Always check `on_other_key()` return value to flush buffered space before the next character.

### Code Panel Architecture

`_code_panel_active` (app-level, persists across rooms) vs `ReplPanel.is_open` (per-room). Space-hold pins canvas height; viewport grows by 4 on open. Write-mode space is buffered by `HoldOrTap`: tap flushes the space before the next key via `on_other_key()` returning True.

---

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
5. Textual exits, Python `execv`s into `/run/purple-reboot-mount/purple-reboot --wait` (static binary on tmpfs)

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
