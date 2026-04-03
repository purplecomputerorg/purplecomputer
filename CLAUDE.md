# Claude Code Notes for Purple Computer

**Keep this file minimal.** When editing CLAUDE.md, also tighten existing sections: remove anything derivable from code, merge overlaps, cut stale info. Aim for <150 lines.

---

## Code Quality (TOP PRIORITY)

**DRY is king.** Never duplicate logic. When you see the same pattern in two places, extract it. Before adding code, check if existing code already handles the case or can be extended to. Reuse relentlessly: every copy-pasted block is a future bug. Prefer one clear code path over branching into similar-but-slightly-different flows. Minimize LOC, if-else sprawl, and surface area for bugs. Keep functions short and single-purpose. No spaghetti: if a function has more than 3 levels of nesting or 5+ early returns, restructure it.

---

## Sensitive Files (DO NOT READ)

Never read `.env` files, `credentials.json`, or `secrets.yaml`.

---

## Hardware Safety (CRITICAL)

Purple Computer runs on kids' laptops. Never make changes that could cause issues on real hardware. VM-specific workarounds must be safe no-ops on real devices.

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
```

Output: PNG at `/tmp/screenshots/`. See `guides/headless-preview.md` for full reference.

**Visual/layout tests:** `app.run_test()` verifies widget sizes and positions headlessly. See `tests/test_code_panel_layout.py`.

**AI UX testing:** `just ux` launches a Claude agent that explores the app as a simulated kid, presses keys, and reports bugs to `AI_UX_BUGS.md`. Config in `scripts/ai_ux_config.py`. See `guides/ai-ux-testing.md`.

---

## Terminal Layout Constants

Single source of truth: `purple_tui/constants.py` (`VIEWPORT_WIDTH=134`, `VIEWPORT_HEIGHT=30`, `REQUIRED_TERMINAL_ROWS=38`). Font size calc in `scripts/calc_font_size.py` imports from there.

---

## Textual Framework Workarounds

### Background Colors (Textual 0.67.0)

`widget.styles.background` on `Static` doesn't repaint. Use `Widget` subclass with `render_line()` returning `Strip([Segment(...)])`.

### Flicker-Free Reflows (MusicGrid pattern)

When widget height changes, Textual renders intermediate sizes causing flicker. Fix: `_layout_ready = False` before change, cache last good dimensions in `_cached_layout`, render with cached values during reflow. `on_resize` debounces 50ms then sets `_layout_ready = True`.

### Keyboard Input (evdev)

Input via evdev (`/dev/input/event*`), bypassing the terminal. Alacritty is display-only.

```
Physical Keyboard → evdev → EvdevReader → KeyboardStateMachine → handle_keyboard_action()
```

**Key files:** `purple_tui/input.py`, `purple_tui/keyboard.py`. See `guides/keyboard-architecture.md`.

**Single code path:** All keyboard logic in `handle_keyboard_action()`. Textual's `_on_key()` suppresses events. All navigation is explicit (no Tab/Shift-Tab focus).

### HoldOrTap Pattern

`HoldOrTap` (keyboard.py) distinguishes quick taps from long holds (space-hold toggles code panel). Always check `on_other_key()` return value to flush buffered space before the next character.

### Code Panel Architecture

**State:** `_code_panel_active` (bool on app) persists across room switches. `ReplPanel.is_open` is per-room runtime state.

**Room switch:** When active, switching to Music/Art auto-opens REPL. Play shows compact indicator. Mode ends on explicit close.

**Canvas sizing:** Space-hold (user-initiated) pins canvas height. Room switch keeps `1fr`. Viewport grows by 4 when code panel opens: 3 from indicator swap (4-row → 1-row) + 1 extra for REPL after hint bar hidden.

**Write mode + space buffering:** Space-down starts hold timer, doesn't type immediately. Repeats suppressed while pending. Tap sends space, `on_other_key()` True flushes before new key.

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

**Post-install reboot:** When install finishes, Python exits Textual and `execv`s into `/run/purple-reboot-mount/purple-reboot` (own tmpfs with `exec,suid` since Ubuntu's `/run` is `nosuid,noexec`). The binary ignores terminal signals (SIGHUP, SIGQUIT, SIGINT, SIGTSTP) so it survives pty hangup when Alacritty dies after USB removal. It calls `reboot(2)` directly, no shared libs. With `--wait` it shows a message and waits for Enter before rebooting.

**Casper shutdown prompt** (`casper-stop`) shows "remove media, press enter" on reboot/poweroff and hangs when USB is removed. Suppressed two ways:
- `touch /run/casper-no-prompt` before reboot (runtime, in `parent_menu.py`)
- `casper-stop` neutered to `exit 0` at image build time (`00-build-golden-image.sh`)

### UEFI Boot (Installed System)

Boot must work on diverse hardware (ThinkPads, Dells, Surface, etc.):
- **UUID over labels** for root partition
- **Signed boot chain:** shim → GRUB → kernel
- **Multiple EFI paths:** `/EFI/BOOT/`, `/EFI/Microsoft/Boot/`, `/EFI/purple/`
- **NVRAM entries are bonus:** create but don't depend on them

Device-specific fixes: comment which device, keep under 10 lines. Run `build-scripts/diagnose-boot.sh` to debug.

---

## Build Image Size Reduction

Uses `--no-install-recommends`. `linux-firmware` must be installed explicitly.

**Kernel modules (`/lib/modules/`): DANGEROUS to prune.** Cross-directory dependencies are invisible. **Only remove networking modules** (`drivers/net`, `drivers/bluetooth`, `net/bluetooth`, `net/wireless`, `drivers/nfc`, `drivers/isdn`). Build runs `modprobe --dry-run` after pruning.

**Firmware (`/lib/firmware/`): Safe to prune aggressively.** Standalone blobs. Keep `i915/`, `amdgpu/`, `nvidia/`, `intel/`.
