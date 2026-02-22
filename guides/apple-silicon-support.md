# Apple Silicon Support

Running Purple Computer on Apple Silicon Macs (M1, M2) via Asahi Linux.

This is the companion to `t2-mac-support.md` (Intel Macs with T2 chip). Apple Silicon is a completely different architecture (ARM64 vs x86_64) with a completely different boot chain.

---

## Supported Hardware

### Ready (M1 series, late 2020-2022)

| Model | Notes |
|-------|-------|
| MacBook Air 13" (M1, 2020) | Best candidate: light, cheap on used market, good speakers, Retina |
| MacBook Pro 13" (M1, 2020) | Same as Air but heavier, Touch Bar shows F-keys by default on Linux |
| MacBook Pro 14" (M1 Pro, 2021) | Larger display (3024x1964), better speakers |
| MacBook Pro 16" (M1 Pro/Max, 2021) | Same but bigger |
| Mac mini (M1, 2020) | Desktop, needs external display/keyboard |

### Ready (M2 series, 2022-2023)

| Model | Notes |
|-------|-------|
| MacBook Air 13" (M2, 2022) | Redesigned, MagSafe charging |
| MacBook Air 15" (M2, 2023) | Larger display |
| MacBook Pro 13" (M2, 2022) | Last Touch Bar model |
| MacBook Pro 14"/16" (M2 Pro/Max) | Higher-end |
| Mac mini (M2/M2 Pro, 2023) | Desktop |

### Not ready

**M3 (late 2023):** First boot achieved January 2026. Keyboard, touchpad, WiFi, NVMe, USB3 working with local patches but no official installer and no GPU driver. Not usable for end users.

**M4 (late 2024):** Very early stage. Introduces additional boot restrictions. Years away.

**Apple Silicon != Apple Silicon.** Each generation requires substantial reverse-engineering because Apple publishes no hardware documentation. M1 and M2 are similar enough that M1 work carried over. M3 has a different GPU architecture and coprocessor layout.

---

## Key Difference from Intel: No USB Boot

**Apple Silicon cannot boot from USB storage.** This is a hardware restriction in the SecureROM (burned into silicon, immutable). There is no workaround. You cannot make a live USB drive that boots on Apple Silicon.

On Intel Macs and PCs, the deployment model is:
```
Burn USB → Plug in → Press boot key → Running
```

On Apple Silicon, the deployment model is:
```
Run installer script from macOS → Reboot to Recovery → Authenticate →
Complete OS setup → Set as default boot → Running
```

This is a fundamental architectural difference, not a software limitation that can be solved.

---

## Boot Chain

The Apple Silicon boot chain is unlike any PC or Intel Mac:

```
SecureROM (immutable, in silicon)
  → iBoot Stage 1 (NOR flash, Apple-signed)
    → iBoot Stage 2 (from disk, per-OS container)
      → m1n1 Stage 1 (Asahi's bootloader, machine-signed)
        → m1n1 Stage 2 (from Linux ESP, handles hardware init)
          → U-Boot (provides UEFI services to GRUB)
            → GRUB (standard ARM64 EFI bootloader)
              → Linux kernel
```

Every stage starts with Apple firmware. There is no way to bypass this chain. A ~2.5GB macOS stub partition must remain on disk permanently (contains Apple's bootloader, firmware, and Recovery image).

### OS Selection at Power-On

Hold the **Power button** for ~15 seconds at startup to enter the Mac Startup Manager. Select macOS or Asahi Linux. You can set Asahi as the default boot target so it boots automatically without holding anything.

### Role of macOS

macOS is required for:
- **Initial installation** (the Asahi installer runs from macOS Terminal)
- **Recovery** (if Linux boot breaks, Recovery mode is the escape hatch)
- **Authorizing the kernel** (Recovery mode step during install)
- **Firmware updates** (Apple firmware is updated through macOS)

macOS cannot be fully removed. The stub partition is permanent.

---

## Hardware Support for Purple Computer

Purple Computer needs four things: keyboard via evdev, display, audio output, and power management. Here's where each stands.

### Keyboard via evdev: Works

The internal keyboard appears as a standard `/dev/input/event*` device. The existing `EvdevReader → KeyboardStateMachine → handle_keyboard_action()` pipeline should work unchanged.

**How the keyboard connects (M1):**
The keyboard is a passive switch matrix connected to the trackpad controller (Broadcom BCM5976 + STM32). This connects to the SoC via SPI. The `hid_apple` kernel driver presents it as a standard HID device, which Linux's input subsystem exposes through evdev.

**How the keyboard connects (M2):**
Redesigned. The trackpad controller logic moved into the SoC as a coprocessor. Communication uses DockChannel (Apple's FIFO protocol) with custom HID transport. Still appears as a standard evdev device to userspace.

**F-key behavior:** configurable via `/sys/module/hid_apple/parameters/fnmode` (default is 3 on Asahi, which makes F1-F12 the primary function and media keys require Fn). This matches Purple Computer's expectations.

**Important caveat:** the internal keyboard does NOT work in U-Boot/GRUB (no driver at that boot stage). An external USB keyboard is needed to interact with the bootloader menu. Once Linux boots, the internal keyboard works fine. For Purple Computer, this is acceptable since GRUB auto-boots with no user interaction needed.

### Display: Works

Internal displays work on M1 and M2 Macs via the DCP (Display Coprocessor) driver.

| Model | Resolution | Effective at 200% scaling |
|-------|-----------|--------------------------|
| MacBook Air 13" (M1) | 2560x1600 | 1280x800 |
| MacBook Air 13" (M2) | 2560x1664 | 1280x832 |
| MacBook Air 15" (M2) | 2880x1864 | 1440x932 |
| MacBook Pro 14" | 3024x1964 | 1512x982 |
| MacBook Pro 16" | 3456x2234 | 1728x1117 |

These are all HiDPI Retina panels. At 100% scaling, everything is tiny. At 200% scaling, you get the "effective" resolution, which is still well above Purple Computer's 114x39 terminal minimum (`REQUIRED_TERMINAL_COLS` x `REQUIRED_TERMINAL_ROWS`).

The DCP driver is not yet upstream in mainline Linux. Asahi's patched kernel includes it.

### Audio: Works, with caveats

Speakers work on M1 and M2 via Asahi's custom audio stack:

```
Application → PipeWire → WirePlumber → lsp-plugins DSP → Speaker hardware
```

The DSP chain is critical. Apple's speakers are driven hard and rely on software limiters to prevent damage. Asahi reverse-engineered the safety parameters and implements them via `lsp-plugins` (an open-source audio DSP plugin suite).

**What this means for Purple Computer:**
- Sound synthesis (marimba, percussion) plays through PipeWire, which is the standard Linux audio API
- Fedora Asahi Remix configures the DSP chain correctly out of the box
- Other distros need manual configuration of the speaker safety profiles

**Risks:**
- `lsp-plugins` version must be 1.0.20 or later, or the DSP can produce artifacts that may **physically damage the speakers**
- Not all Mac models have validated speaker safety profiles. Using speakers on untested models is explicitly warned against by the Asahi project
- PipeWire replaces PulseAudio. Purple Computer's audio code needs to work with PipeWire (it should, since PipeWire provides a PulseAudio compatibility layer)

**Action item:** test audio output on each specific Mac model before considering it supported. Verify `lsp-plugins` version and DSP configuration.

### Power Management: Weak spot

**Lid close:** triggers s2idle (freeze). Battery drain during sleep is approximately 2% per hour (50% overnight). Compare to macOS at 1-2% over 8 hours. This is because the hardware isn't properly powered down during suspend.

**Purple Computer's workaround:** Purple already configures `HandleLidSwitch=poweroff` in logind (see `00-build-golden-image.sh` lines 204-220). Lid close triggers a full shutdown, not suspend. This sidesteps the battery drain problem entirely. The same configuration would apply on Apple Silicon.

**Power button:** short press triggers shutdown (via logind configuration). Same as on Intel Purple Computer systems.

**Battery life during use:** noticeably shorter than macOS. Expect 5-7 hours on an M1 Air vs 10+ on macOS. Adequate for a kid's computing session.

---

## Purple Computer's Software on ARM64

### Architecture-Generic Components (no changes needed)

The Python TUI code is 100% architecture-independent:

| Component | Why it's portable |
|-----------|------------------|
| `purple_tui/` (all Python code) | Pure Python, no native extensions |
| Textual / Rich | Pure Python |
| evdev (Python package) | Small C extension, works on all Linux architectures. Pre-built in Fedora aarch64 repos. |
| NumPy | Official aarch64 wheels on PyPI. Pre-built in Fedora aarch64 repos. |
| espeak-ng | Pre-built in Fedora aarch64 repos |
| Alacritty | Pre-built in Fedora aarch64 repos |

### Components That Need Attention

**Piper TTS:** uses ONNX Runtime for neural network inference. ONNX Runtime has aarch64 builds, but performance and compatibility should be verified. The `piper-tts` pip package includes a native `espeakbridge.so` that would need to be compiled for aarch64. Alternatively, fall back to `espeak-ng` directly (lower quality but zero porting effort).

**pygame:** has pre-built aarch64 wheels on PyPI. Should work. SDL2 libraries (`libsdl2-2.0-0`, etc.) are available in Fedora aarch64 repos.

**simpleaudio** (if used): unmaintained since 2019, no aarch64 wheels. Can compile from source (depends on ALSA). Consider replacing with `sounddevice` (actively maintained, uses PortAudio via CFFI).

### Build System Changes

The build scripts are hardcoded to x86_64. An ARM64 build would need these changes:

**`build-scripts/config.sh`:**
```bash
# Current (x86_64)
ARCH="amd64"
UBUNTU_ISO_URL="...ubuntu-24.04.1-live-server-amd64.iso"
GOLDEN_PACKAGES="linux-image-generic grub-efi-amd64 systemd sudo"

# ARM64 variant
ARCH="arm64"
UBUNTU_ISO_URL="...ubuntu-24.04.1-live-server-arm64.iso"  # or Fedora
GOLDEN_PACKAGES="linux-image-generic grub-efi-arm64 systemd sudo"
```

**`build-scripts/00-build-golden-image.sh`:**
```bash
# Current
debootstrap --arch=amd64 ...
grub-mkstandalone --format=x86_64-efi --output=".../BOOTX64.EFI" ...

# ARM64 variant
debootstrap --arch=arm64 ...
grub-mkstandalone --format=arm64-efi --output=".../BOOTAA64.EFI" ...
```

**`build-scripts/install.sh`:**
```bash
# Current EFI paths
/EFI/BOOT/BOOTX64.EFI
/EFI/Microsoft/Boot/bootmgfw.efi
/EFI/purple/grubx64.efi

# ARM64 EFI paths
/EFI/BOOT/BOOTAA64.EFI
/EFI/purple/grubaa64.efi
# Microsoft path not relevant on Apple Silicon
```

**Note:** the live boot USB model (`01-remaster-iso.sh`) does not apply to Apple Silicon since USB boot is impossible. A different installation mechanism is needed (see "Installation Path" below).

### Distro Choice: Fedora vs Ubuntu

The current build uses Ubuntu 24.04 (Noble). For Apple Silicon, the options are:

**Fedora Asahi Remix (recommended for Apple Silicon):**
- Official Asahi distribution, best hardware support
- Speaker DSP preconfigured
- Upstream Fedora aarch64 package repos
- Uses `dnf` instead of `apt`, `rpm` instead of `deb`
- The build scripts would need significant changes (debootstrap → Fedora's equivalent, apt → dnf, systemd unit paths may differ)

**Ubuntu Asahi (community project):**
- Closer to current build system (same package manager, same base)
- Less polished than Fedora Asahi, speaker DSP may need manual setup
- Not officially supported by either Canonical or the Asahi project
- Available at [ubuntuasahi.org](https://ubuntuasahi.org/)

**Practical recommendation:** use Fedora Asahi Remix for Apple Silicon and keep Ubuntu for Intel. Maintaining two build paths (one per distro) is more work, but each path uses the best-supported distro for its hardware.

---

## Installation Path

Since USB live boot is impossible on Apple Silicon, Purple Computer needs a different installation mechanism.

### How Asahi Installation Works Today

1. User opens Terminal in macOS
2. Runs `curl https://alx.sh | sh`
3. Script asks for macOS password
4. Script shrinks macOS partition, creates Linux partitions
5. System reboots to Recovery Mode (hold power button)
6. User runs commands in Recovery to authorize the kernel
7. System boots into Fedora installer
8. User completes standard setup (create user, set password)
9. System reboots, user sets Asahi as default boot target

### Adaptation for Purple Computer

A custom installer script could wrap the Asahi installer and automate the Purple-specific setup:

```
curl https://[purple-install-url] | sh
    ↓
Wraps Asahi installer (partitioning, m1n1 bootloader)
    ↓
Reboots to Recovery Mode (user holds power button, authenticates)
    ↓
Boots into minimal Fedora → Purple setup script runs automatically:
  - Installs Purple Computer packages
  - Configures auto-login, lid-close shutdown, kid-proofing
  - Sets Asahi as default boot target
    ↓
Reboots into Purple Computer
```

The Recovery Mode step (step 5 above) **cannot be automated**. It requires physical interaction: holding the power button and clicking through Apple's security prompts. This is the irreducible complexity of Apple Silicon installation. Clear instructions (or a short video) are needed for this step.

### Pre-loaded Approach

The installation complexity mostly disappears if Purple Computer is pre-installed before it reaches the user:
1. Install Fedora Asahi Remix on the Mac
2. Install Purple Computer
3. Set Asahi as default boot target
4. Configure lid-close shutdown, kid-proofing, etc.

The user turns on the Mac and it boots straight to Purple Computer. No setup, no boot keys, no installation steps.

---

## What Doesn't Apply from Intel Purple Computer

Several pieces of the Intel build are irrelevant on Apple Silicon:

| Intel concept | Apple Silicon equivalent |
|---------------|------------------------|
| USB live boot (casper, squashfs) | Not possible. No USB boot on Apple Silicon. |
| `BOOTX64.EFI` / `BOOTAA64.EFI` | Asahi's m1n1 → U-Boot → GRUB handles boot. Standard GRUB grub.cfg still applies. |
| Multiple EFI fallback paths (Microsoft, vendor) | Not needed. Only one boot path through m1n1. |
| NVRAM boot entries (efibootmgr) | Not applicable. Boot selection is through Apple's Startup Manager, not UEFI NVRAM. |
| Secure Boot disable (T2 Macs) | Handled by Asahi installer automatically. |
| F12 / boot key instructions | Power button (hold) enters Startup Manager. But usually not needed after setup. |
| X.Org modesetting driver | Asahi uses its own DCP-based display driver. X.Org config may differ. |
| PulseAudio | Fedora Asahi uses PipeWire exclusively. |

---

## Kernel and Driver Maintenance

Purple Computer on Apple Silicon depends on Asahi's kernel patches, which are not yet in mainline Linux.

### Current State (February 2026)

The Asahi project has upstreamed a significant portion of their patches. Downstream patches are below 1,000 for the first time. Major components NOT yet upstream:
- GPU driver (DCP, display controller)
- `apple-bce` / keyboard+trackpad coprocessor drivers
- Audio DSP integration
- Some power management code

### Project Status

The Asahi Linux founder and lead developer (Hector Martin) resigned in February 2025, citing burnout. The project transitioned to a seven-person collective governance model and continues via Open Collective funding. Development pace has slowed but the project is active and publishing regular kernel progress reports (most recent: Linux 6.19, February 2026).

### Options for Kernel

1. **Use Fedora Asahi Remix's kernel** (recommended): they track upstream Fedora kernels with Asahi patches applied. Maintained by the Asahi project.
2. **Use Ubuntu Asahi's kernel**: community-maintained, less guaranteed.
3. **Build from Asahi's kernel source**: more control, more maintenance burden.

### Risk

If the Asahi project stalls, Apple Silicon support would be difficult to maintain independently. The reverse-engineering effort is substantial and requires specialized expertise. This is a dependency risk that doesn't exist on Intel hardware (where mainline Linux kernels work without patches).

---

## Validation Checklist

Before considering Apple Silicon supported, verify each item on actual hardware:

### Phase 1: Can it boot and run?

- [ ] Install Fedora Asahi Remix on M1 MacBook Air
- [ ] Verify internal keyboard appears in `/dev/input/event*`
- [ ] Verify `evtest` shows key-down and key-up events from internal keyboard
- [ ] Verify scancodes from F1-F12 match expectations (run `keyboard_normalizer.py --calibrate`)
- [ ] Verify Alacritty launches fullscreen at correct resolution
- [ ] Verify Purple TUI starts and renders correctly

### Phase 2: Does everything work?

- [ ] Explore mode: type characters, verify visual output
- [ ] Play mode: verify sound output through speakers
- [ ] Doodle mode: verify painting works
- [ ] TTS: verify text-to-speech audio output (Piper or espeak-ng)
- [ ] Audio quality: are marimba/percussion sounds acceptable through the built-in speakers?
- [ ] Lid close: verify full shutdown (not suspend)
- [ ] Power button: verify clean shutdown
- [ ] Kid-proofing: verify Ctrl+Alt+Del, SysRq, TTY switching are all disabled

### Phase 3: Edge cases

- [ ] Boot after full shutdown (not just restart)
- [ ] Boot with lid closed, then open (does display wake?)
- [ ] Keyboard behavior after lid-close-then-open without shutdown
- [ ] Battery life: how long does a session last?
- [ ] Verify `lsp-plugins` version is 1.0.20+ (speaker safety)
- [ ] Test on M2 MacBook Air (verify M2-specific keyboard path works)

---

## References

- [Asahi Linux](https://asahilinux.org/)
- [Fedora Asahi Remix](https://asahilinux.org/fedora/)
- [Asahi feature support (M1)](https://asahilinux.org/docs/platform/feature-support/m1/)
- [Asahi feature support (M2)](https://asahilinux.org/docs/platform/feature-support/m2/)
- [Asahi boot process](https://asahilinux.org/docs/fw/boot/)
- [Asahi FAQ](https://asahilinux.org/docs/project/faq/)
- [Asahi audio (GitHub)](https://github.com/AsahiLinux/asahi-audio)
- [Ubuntu Asahi](https://ubuntuasahi.org/)
- [lsp-plugins](https://lsp-plug.in/) (speaker safety DSP)
- [Kernel progress reports](https://asahilinux.org/blog/) (regular updates on upstream status)
- Purple Computer companion guide: `guides/t2-mac-support.md` (Intel T2 Macs)
- Purple Computer boot reference: `guides/usb-boot-reference.md` (Intel PCs and Macs)
