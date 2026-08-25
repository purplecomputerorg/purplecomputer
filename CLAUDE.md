# Claude Code Notes for Purple Computer

**Keep this file minimal.** When editing CLAUDE.md, also tighten existing sections: remove anything derivable from code, merge overlaps, cut stale info. Aim for <150 lines.

---

## Code Quality (TOP PRIORITY)

**DRY is king.** Never duplicate logic. When you see the same pattern in two places, extract it. Before adding code, check if existing code already handles the case or can be extended to. Reuse relentlessly: every copy-pasted block is a future bug. Prefer one clear code path over branching into similar-but-slightly-different flows. Minimize LOC, if-else sprawl, and surface area for bugs. Keep functions short and single-purpose. No spaghetti: if a function has more than 3 levels of nesting or 5+ early returns, restructure it.

**Comments: brief or absent.** Default is NO comment. Add one only when the WHY is non-obvious (hidden constraint, subtle invariant, workaround for a specific bug). Never explain WHAT the code does — well-named identifiers already do that. Never narrate the change, the task, or the caller. One line, not a paragraph. Multi-paragraph docstrings are almost always wrong. If you're tempted to write a design-decision essay, put it in a guide under `guides/` and link to it.

**Imports: no heavy work at module scope.** A new pip dep whose cold `import` takes >100ms must be lazy-loaded. Runtime-type-check packages (`typeguard`, `beartype`, etc.) do AST rewriting at decoration time — audit them carefully. Rule + case study: `guides/boot-hang-debugging.md#rule-dont-do-heavy-work-at-module-import-time`.

---

## Git Commits

Never run `git commit` directly. Always commit via `/checkpoint <msg>` (you supply the message) or `/wrap` (you draft a 1-2 sentence message from the diff). These come from the [`lanes`](https://github.com/tavinathanson/lanes) tool installed at `~/.claude/`.

Commit messages: **one line, max two short sentences.** No bullet-list body. No `Co-Authored-By` trailer. No `lane(...)` prefix — the script handles whatever prefixing is needed. Never use the default verbose Claude Code commit format.

Commit messages and `docs/UX_LOG.md` are public and customer-readable: describe what changed, never the messaging strategy or tone intent behind it (no "warmer", "apologetic", "less blame-y").

If you're unsure what message to use, propose one and ask the user to confirm before committing.

## Shipping Branch

Customer ISOs build from `release/1.x`, a fixes-only branch checked out at `~/purplecomputer-release`. Never commit or merge there directly: fixes land on main first, then flow over via `just release-pick`. Full workflow: `guides/release-guide.md`, Release Branch section.

Cherry-pick decisions (fix vs feature) are the user's to confirm: propose picks, and after every `release-pick`, show the `just release-status` output with a one-line reason per commit for why it ships or waits.

---

## No Claude Memories

Do not save anything to Claude's persistent memory system. All notes, TODOs, and project state go in the repo (e.g. `docs/TODO.md`).

## Sensitive Files (DO NOT READ)

Never read `.env` files, `credentials.json`, or `secrets.yaml`.

---

## Hardware Safety (CRITICAL)

Purple Computer runs on kids' laptops. Never make changes that could cause issues on real hardware. VM-specific workarounds must be safe no-ops on real devices.

---

## Logging Policy

**Instrumentation can ship in the standard (+debug) ISO only if it's non-visual, non-expensive, and non-interfering.** Otherwise it's debug-only (gated on `/opt/purple/debug`).

- **Non-visual** = file descriptors only. Never write to stdout/stderr from hot paths: they land in the xinitrc log, fine for diagnostics, wrong for per-keystroke chatter. Use `boot_log`, `_power_log`, or `tts._dbg`.
- **Non-expensive** = cheap appends, no subprocess spawns at runtime, no fsync/flush cascades.
- **Non-interfering** = no EVIOCGRAB, no terminal mode changes, no signal handlers that paint.

**Exception:** user-facing error/diagnostic screens (e.g. `purple-x11-failed` scroll) ship in standard even though they're visual, because diagnosing failures matters more than hiding them.

Boot hang diagnostics: see `guides/boot-hang-debugging.md`. `purple_tui/boot_log.py` is the always-on heartbeat + watchdog; log lives at `/tmp/purple-boot.log` and persistently at `/var/log/purple/boot.log` on the debug ISO (casper writable partition).

---

## Target Audience

**Kids 3-10** (from learning letters to writing code) and their **non-technical parents**.

User-facing messages: simple, friendly, no jargon. Clear next steps, not error explanations. Add `(Technical: ...)` for known root causes. Use `SUPPORT_EMAIL` from `purple_tui/constants.py`.

**Writing style:** No em-dashes or spaced dashes. Use colons, commas, or periods instead.

**UX changes:** Add a one-line description to `docs/UX_LOG.md`.

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

**AI UX testing:** `just ux` launches a Claude agent that explores the app as a simulated kid, presses keys, and reports bugs to `docs/AI_UX_BUGS.md`. Config in `scripts/ai_ux_config.py`. See `guides/ai-ux-testing.md`.

---

## Terminal Layout Constants

Single source of truth: `purple_tui/constants.py` (`VIEWPORT_WIDTH=134`, `VIEWPORT_HEIGHT=29`, `REQUIRED_TERMINAL_ROWS=37`). Font size calc in `scripts/calc_font_size.py` imports from there.

---

## Canvas UI

The screen is a pygame window the app paints itself (`purple_tui/gfx.py`, `purple_tui/app.py`). Read `guides/canvas-architecture.md` before touching drawing or input. Rules that matter most: sizes come from `g.vh()`/`g.vw()`, every state change calls `app.invalidate()`, nothing animates on an idle screen, and text goes through `Gfx.text`/`Gfx.draw_markup` so ALL CAPS and emoji fallbacks apply everywhere.

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
5. The app shows "All done" and on Enter `execv`s into `/run/purple-reboot-mount/purple-reboot` (static binary on tmpfs)

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
