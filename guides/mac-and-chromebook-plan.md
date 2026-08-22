# Macs and Chromebooks: Every Way In

One place for the machines our USB stick can't boot as-is: Apple Silicon Macs (M1 through M4), T2 Intel Macs, and Chromebooks. Researched August 2026. Claims marked **unverified** were not checked on hardware.

The premise throughout: the kid owns the machine. Purple owns the whole visible surface. What Apple or Google keep underneath is our concern, never the kid's.

Companion guides with background detail: `t2-mac-support.md`, `apple-silicon-support.md`, `chromebook-support.md`. Where they disagree with this one, this one is newer. The x86 kernel plan (T2 kernel, 32-bit EFI, 32-bit CPUs) is in `hardware-coverage-plan.md`.

---

## The map

| Machine | Path | What the kid sees at power-on | What Apple/Google keep |
|---|---|---|---|
| Intel Mac 2006-2017, PCs | USB stick, wipe and install (today) | Purple | Nothing |
| T2 Intel Mac (2018-2020) | USB stick after two one-time steps | Purple | Nothing |
| M1/M2 | Asahi native, arm64 build | Purple | 2.5GB macOS stub and boot chain |
| M3/M4 and future Macs | Purple running natively on macOS, hidden admin | Apple logo, then Purple | macOS itself, hidden |
| x86 Chromebook, retail, case opened | MrChromebox Full ROM, then USB stick | Purple | Nothing |
| x86 Chromebook, retail, case closed | RW_LEGACY plus `dev_default_boot=legacy` | Warning screen, 30s, beep, Purple | ChromeOS, dormant |
| ARM Chromebook | Cadmium (Ctrl+U kernel partition) | Not worth it | Everything |
| School-enrolled Chromebook | Web page only, if the school allows it | A browser tab | Everything |

Three pieces of work unlock most rows and are reused across them:

1. **arm64 build** (Asahi native, and the arm64 half of anything VM-based).
2. **A second input backend** behind `RawKeyEvent` (native macOS, browser). Today `EvdevReader` in `purple_tui/input.py` is the only producer; `KeyboardStateMachine` and `handle_keyboard_action()` never need to change.
3. **A companion app / script per platform** that does everything the firmware lets a script do and turns each firmware-enforced step into one screen with a photo and a check.

---

## Apple Silicon boot, the real rule

Apple Silicon Macs always start from the internal SSD's iBoot. "External boot" means a LocalPolicy record on the internal SSD authorizes a volume somewhere else; a DFU restore erases those records. Background: https://mjtsai.com/blog/2025/04/04/how-external-bootable-disks-work-with-apple-silicon-macs/

Consequences:

- Nothing boots that Apple's chain hasn't authorized. Asahi works by having the owner authorize m1n1 once from recoveryOS (Permissive Security). That authorization step is the one thing no script can do; it needs a human with the owner password.
- A permanent ~2.5GB macOS stub (iBoot, recoveryOS) stays on disk. Not shrinkable.
- **USB boot is possible after a one-time internal install.** The Asahi installer's "UEFI environment only" option (m1n1 + U-Boot + a 500MB ESP, ~3GB total with the stub) leaves a machine whose U-Boot will boot `EFI/BOOT/BOOTAA64.EFI` from a USB stick. NixOS installs exactly this way. `apple-silicon-support.md` said "no USB boot, no workaround"; that is too strong.
- Internal keyboard at the U-Boot/GRUB stage: works on M1 laptops (upstream U-Boot SPI keyboard driver). M2 and later: **unverified, likely absent**. Irrelevant when GRUB auto-boots with no menu, which is our design.

Asahi in 2026: healthy (seven-person board since Hector Martin left in Feb 2025, Fedora Asahi Remix 44 in April 2026, kernel 7.1.x, downstream patch count falling). M1 and M2 families supported. **M3 is bring-up only with the installer disabled and no display driver. M4 has nothing and no ETA.** Apple Silicon generations do not carry over; each is a new reverse-engineering effort.

The installer is built for third parties: host your own `installer_data.json` and OS zip, set `INSTALLER_DATA` / `REPO_BASE`, ship `curl https://purple.../install | sh`. Ubuntu Asahi, Debian's Bananas team, and Arch all do this. Speaker safety is mandatory: `speakersafetyd` plus the asahi-audio PipeWire DSP chain, both packaged in Debian trixie and Ubuntu now. Without them the speakers can be physically damaged. Our audio path (pygame, SDL, PulseAudio) works through PipeWire's pulse shim.

---

## T2 Intel Macs: the two manual steps

Verified against wiki.t2linux.org. Both are enforced by the T2 chip and survive a disk wipe.

1. **Startup Security Utility, once.** Recovery (Cmd+R), Utilities > Startup Security Utility: Secure Boot = **No Security**, Allow Boot Media = **Allow booting from external media**. Needs a macOS admin password; Internet Recovery (Cmd+Option+R) works if macOS is already gone.
2. **Make Purple the default startup disk, once, after install.** Apple firmware ignores `efibootmgr` NVRAM entries, and t2linux warns against touching NVRAM on T2 at all (`install.sh` Layer 4 should be skipped on Apple hardware). Instead: hold Option at power-on, then hold **Control** while selecting the EFI Boot entry. That persists.

For a laptop we pre-configure, the parent sees neither. The rest of the T2 story (unsigned t2linux kernel chosen by GRUB via SMBIOS) is in `hardware-coverage-plan.md`.

---

## Native Purple on macOS: the M3/M4 answer, and maybe the Mac answer

macOS is Unix underneath, and everything Purple needs runs on it natively on arm64 and Intel: Python, Textual, Alacritty, pygame, piper-tts. No VM, no Asahi dependency, no Secure Boot steps, and it works on every Mac Apple will ever ship. The trade: macOS stays on disk and the Apple logo shows at boot. The kid never sees anything else.

### Runtime

- **Input: a CGEventTap instead of evdev.** A session-level Quartz event tap (PyObjC, in-process) sees every key down and key up before any app, including Cmd+Tab, Cmd+Q, Cmd+Space, and swallows them by returning null. It replaces `EvdevReader` and the kid-proofing that keyd and logind provide on Linux. keyd's two remaps (grave/tilde to Esc, RightAlt to F2) become two lines in the tap. Needs Accessibility permission once. Not interceptable: the power/Touch ID button and Cmd+Ctrl+Q (lock screen); both recover into Purple, neither escapes.
- **Display: Alacritty for Mac**, `window.startup_mode = "SimpleFullscreen"` (hides menu bar and dock). `font_sizer.py` works unchanged since `alacritty msg` exists on Mac.
- **Audio and TTS:** CoreAudio via pygame and piper-tts wheels (arm64 and x86_64). `audio_hotplug.py` (PulseAudio-specific) becomes a no-op.
- **Power:** macOS handles lid and power button itself; `power_manager.py` (logind-specific) is bypassed.

Linux-specific code is confined to `input.py`, `power_manager.py`, `audio_hotplug.py`, `diagnostics.py`, and bits of `constants.py` and `purple_tui.py`. The real work is a `MacKeyReader` producing `RawKeyEvent`s plus a Mac-to-Linux keycode table: roughly 300-400 lines. Same seam later serves a browser backend.

### Lockdown, kid-owns-it version

- Wipe, then set up as Purple and nothing else: one hidden admin account (macOS requires one; `dscl ... IsHidden 1` removes it from the login window) and one auto-login standard "Purple" account with Purple as its LaunchAgent.
- Wi-Fi off and admin-locked: `networksetup -setairportpower off`; the "require administrator to turn Wi-Fi on or change networks" switches (System Settings > Wi-Fi > Advanced; scriptable via `airportd prefs RequireAdminPowerToggles=YES RequireAdminNetworkChange=YES`, **unverified on current macOS**). Bluetooth off. Software update checks, notifications, Siri, Spotlight off for the account.
- Screen Time on the Purple account blocking all apps except Alacritty and all websites, as a second layer behind the event tap.

What you cannot do that Linux allows: remove the Apple logo, remove macOS from disk, stop Apple from existing under there (updates, Recovery, Find My). All invisible to the kid.

---

## Purple for Mac.app: the companion

One signed, notarized `.app` (Developer ID, $99/yr) that doubles as the runtime: first launch is setup mode, later launches on the Purple account are kiosk mode. Privileged work goes through a helper with one admin password prompt. SwiftUI shell, Python inside, sharing the arm64 and amd64 builds the other paths need.

What it automates, per path:

| Path | App does | Parent does (firmware-enforced) |
|---|---|---|
| Detect | `sysctl hw.model` / `system_profiler`: Intel, T2, M1/M2, M3+. Shows one path, not a decision tree. | Nothing |
| Native (M3/M4) | Accounts, auto-login, deps, LaunchAgent, Wi-Fi lock, update/notification silencing, optional deletion of other accounts | One toggle: Accessibility permission. App opens the exact pane, waits, detects via `AXIsProcessTrusted()`. TCC cannot be granted by script without MDM. |
| T2 | Flash the USB (`dd` with authorization, replaces Etcher); verify the security setting was actually changed before saying "reboot" (T2 secure boot policy is readable from macOS via an `nvram` variable, `AppleSecureBootPolicy`; **exact name and values unverified**) | Startup Security Utility in Recovery; Option then Control once after install |
| M1/M2 | GUI around the Asahi installer with our `installer_data.json`; partition, write image, reboot straight into recoveryOS via `nvram recovery-boot-mode=unused` (no 15s power-button hold) | Type `yes` and the owner password in recoveryOS |
| Pre-T2 Intel | Flash the USB. Stretch: skip the USB. Shrink APFS (`diskutil apfs resizeContainer`), write the golden image to a new partition, `bless` its ESP, reboot; Purple's first boot reclaims the macOS partition. Boot Camp in reverse; handle with care. | Nothing |

Every manual step is one screen with a photo, and the app checks the result before moving on.

Sequencing: native runtime first (what M3/M4 require, all Python, testable on any Mac today), then the app shell with routing and T2 flashing, then the Asahi GUI last (most external dependencies).

Why not a VM: Apple's Virtualization.framework plus macOS kiosk presentation options (`NSApplication.PresentationOptions`: `disableProcessSwitching`, `disableForceQuit`, hidden dock and menu bar) would run our unchanged Linux image fullscreen with the existing amd64 ISO on Intel Macs today, attaching the ISO as a USB mass-storage device. It is a valid fallback and a fast prototype. Native is preferred because it has no VM layer, better battery, and the same coverage. UTM specifically is out: it is a window in someone else's app.

---

## Chromebooks

### x86, retail: MrChromebox

Still at https://mrchromebox.tech (`firmware-util.sh`); docs.chrultrabook.com is a companion site, not a move. Full UEFI ROM covers Sandy Bridge through Alder Lake-N and Meteor Lake, plus AMD Cezanne and Mendocino. RW_LEGACY is EOL for Sandy Bridge through Skylake (Full ROM only there) and still offered from Apollo Lake onward. Nothing newer than Meteor Lake is supported yet.

Two tiers:

- **Full ROM** needs write protect disabled: open the case and unplug the battery on most Apollo-Lake-and-newer boards (no SuzyQ cable needed on those). Afterwards the machine is a normal PC with no Secure Boot; our stick boots like anywhere else. No warning screen.
- **RW_LEGACY** needs no screwdriver and keeps ChromeOS. `crossystem dev_default_boot=legacy` makes the developer screen auto-boot our stick after its timer, no Ctrl+L. But the **30-second wait and the beep cannot be shortened with write protect on**: the short-delay and default-target flags live in the read-only GBB region. So the case-closed tier is: power on, scary screen, 30 seconds, beep, Purple. Every boot. Fine for testing, marginal for a kid.

What our image needs for Chromebooks, all bakeable offline as no-ops elsewhere:

- **Audio:** WeirdTreeThing's `chromebook-linux-audio` (https://github.com/WeirdTreeThing/chromebook-linux-audio) is file copies: UCM2 configs from `alsa-ucm-conf-cros` into `/usr/share/alsa/ucm2`, SOF topology and firmware blobs into `/lib/firmware/{intel,amd}`, driver-selection files into `/etc/modprobe.d`. Its one runtime `git clone` gets vendored at build time. Covers Baytrail through Meteor Lake and AMD Stoney through Mendocino. It also deletes `max98357a-tplg.bin` on purpose to prevent unlimited-volume speaker damage.
- **Keyboard:** standard evdev (`cros_ec` or i8042). The top row emits media keycodes, not F-keys; WeirdTreeThing's `cros-keyboard-map` generates a **keyd** config from `/sys/.../function_row_physmap`, which drops straight into our keyd layer. Search key is LeftMeta. No physical Delete or CapsLock.
- **Kernel:** we ship `linux-image-generic` on 24.04 (6.8). chrultrabook wants 6.19+ (AMD Stoney audio requires it). Since `hardware-coverage-plan.md` already adds a second, unsigned kernel for T2, a newer Chromebook-capable kernel is the same slot; MrChromebox firmware has no Secure Boot so signing doesn't matter there.
- **Storage:** cheap AUE-expired boards (Dell 3100 "fleex", Lenovo 100e "robo", HP 11 G8 "vorticon") all support both tiers but have 4GB RAM and 16-32GB eMMC. Our 16GB minimum is tight on the 16GB ones.

Ctrl+U boot of a vboot-signed kernel partition on USB (no firmware change at all) is technically real on x86 and ARM, but the tooling is dead (eupnea/depthboot discontinued 2023 with a compromised GitHub; PrawnOS last touched 2021), the kernel command line is baked into the signed blob, and shim/GRUB are bypassed entirely. Not worth maintaining.

### The Chromebook companion

ChromeOS runs no apps of ours before Developer Mode, so the companion is a web page plus one script, not an app:

1. **Before buying:** the login screen says "managed by" for enrolled devices. That is the whole pre-purchase check. No tool can do it remotely.
2. **Enable Developer Mode** (wipes local data). Photo-guided, unavoidable.
3. **Run `curl https://purple.../chromebook | bash` in the VT2 shell.** Our wrapper: reads `crossystem wpsw_cur` to say whether the case must be opened, runs `firmware-util.sh` non-interactively for RW_LEGACY (or Full ROM once write protect is off), sets `dev_boot_altfw=1` and `dev_default_boot=legacy`, reports the board name so we know which audio profile applies.
4. **Boot the stick.** Purple's installer sees a Chromebook board, and the baked audio files and keyd map do the rest.

Everything after step 3 is the normal stick experience.

### ARM Chromebooks (MediaTek Kompanio, Snapdragon 7c)

No coreboot, so the only route is Cadmium (https://github.com/Maccraft123/Cadmium): Ctrl+U kernel-partition boot with a mainline arm64 kernel, open-source drivers only, manual audio fiddling on some boards. A separate project with the arm64 build as a prerequisite. Skip.

### School-enrolled Chromebooks

Enrolled means Google Admin policy owns the device: Developer Mode blocked, Forced Re-Enrollment re-applies policy on any network check-in, and most schools also disable Linux (Crostini). The exploits (sh1mmer, badrecovery) are version-gated, patched continuously, and not something to build a product on. Under our premise this one is settled: the kid does not own a school Chromebook; the school does. There are two honest positions:

- **After the school lets it go.** Schools sell or give away fleets at AUE. If the school deprovisioned the device in the admin console, it is a retail Chromebook and the x86 path above applies. If they did not, FRE keeps it enrolled forever; tell people to ask the school to deprovision before taking it home.
- **While the school owns it: a web page.** The only thing that runs on an enrolled Chromebook is what the admin's allowlist permits. A "Purple Web" that a teacher can allow is the sole route, and it is a different product: browser keydown/keyup give real key-up events, so the input seam works, but rendering has to come from a server (textual-serve) or an in-browser Python (Pyodide plus a custom xterm.js driver, **unverified**), TTS moves to the browser (Web Speech API, or Piper via onnxruntime-web), and sound to Web Audio. That same web build is also what a parent-owned, unflashed Chromebook could run under Family Link with Purple as the only allowed site, or as a Chrome kiosk app on a parent-enrolled device ($50/device Kiosk Upgrade). Worth knowing, not worth building before the Mac work; it rides on the same input seam.

---

## Sequencing across both platforms

1. Input-backend seam in `input.py`, then the macOS `MacKeyReader`. Testable on a Mac today, unlocks M3/M4.
2. Purple for Mac.app shell: routing, native setup, T2 USB flashing and verification.
3. Chromebook: vendor the audio files and keyd map into the golden image, the VT2 wrapper script, the newer kernel alongside the T2 kernel work.
4. arm64 build: Asahi native on M1/M2 via hosted installer data, and ARM anything later.
5. Purple Web, only if locked Chromebooks turn out to be a real population.

---

## Sources

- Apple Silicon external boot: https://mjtsai.com/blog/2025/04/04/how-external-bootable-disks-work-with-apple-silicon-macs/
- Asahi boot process and U-Boot: https://asahilinux.org/docs/alt/boot-process-guide/ , https://asahilinux.org/docs/sw/u-boot/
- Asahi installer data (UEFI-only entry): https://github.com/AsahiLinux/asahi-installer-data
- Asahi installer for downstreams: https://github.com/AsahiLinux/asahi-installer
- NixOS UEFI-standalone install: https://github.com/tpwrules/nixos-apple-silicon/blob/main/docs/uefi-standalone.md
- Asahi progress reports (M3/M4 state, upstream status): https://asahilinux.org/2026/02/progress-report-6-19/ , https://asahilinux.org/2026/04/progress-report-7-0/
- Debian Bananas: https://wiki.debian.org/Teams/Bananas ; Ubuntu Asahi: https://github.com/UbuntuAsahi/ubuntu-asahi
- t2linux pre-install and rEFInd guides: https://wiki.t2linux.org/guides/preinstall/ , https://wiki.t2linux.org/guides/refind/
- MrChromebox: https://docs.mrchromebox.tech/docs/supported-devices.html , https://docs.mrchromebox.tech/docs/boot-modes/developer.html , https://docs.mrchromebox.tech/docs/boot-modes/legacy.html
- ChromiumOS developer mode (`dev_default_boot`): https://www.chromium.org/chromium-os/developer-library/guides/device/developer-mode/
- Chromebook audio and keyboard: https://github.com/WeirdTreeThing/chromebook-linux-audio , https://github.com/WeirdTreeThing/cros-keyboard-map
- chrultrabook: https://docs.chrultrabook.com/docs/installing/known-issues.html
- Cadmium (ARM): https://github.com/Maccraft123/Cadmium
