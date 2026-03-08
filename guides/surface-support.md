# Microsoft Surface Support

Microsoft Surface devices (especially the Surface Laptop 2) are a good hardware target for Purple Computer: widely available used, good build quality, and solid Linux support with minor tweaks.

This guide covers what's needed to get full functionality on Surface hardware.

---

## Tested Devices

| Device | Status | Notes |
|---|---|---|
| Surface Laptop 2 | Works with tweaks | Needs `i915.enable_dpcd_backlight=1` for backlight control |

Other Surface devices (Laptop 3/4/5, Pro, Go, Book) likely need similar fixes. Update this table as devices are tested.

---

## Display Brightness Control

### The problem

On Surface Laptop 2, the display output shows as `None-1` in xrandr with no CRTC (CRT Controller) associated. This means:

- `xrandr --brightness` and `--gamma` silently fail ("need crtc to set gamma on")
- `/sys/class/backlight/` is empty (no kernel backlight interface)
- `xgamma` runs without errors but has no visible effect
- The "Adjust Display" menu in Purple Computer does nothing

The root cause: the i915 (Intel graphics) driver defaults to PWM backlight control, which doesn't work on the Surface's eDP panel. The driver needs to be told to use DPCD (DisplayPort Configuration Data) backlight control over the AUX channel instead.

### The fix

Add this kernel parameter:

```
i915.enable_dpcd_backlight=1
```

This tells the i915 driver to use DPCD registers for backlight control, which:

- Populates `/sys/class/backlight/intel_backlight/`
- Makes xrandr brightness/gamma work properly
- Gives the "Adjust Display" menu in Purple Computer working controls

### Where to add it

**In the golden image GRUB config** (`build-scripts/00-build-golden-image.sh`), append to the kernel command line:

```
linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet splash console=tty0 console=ttyS0,115200n8 i915.enable_dpcd_backlight=1
```

This parameter is safe on non-Surface hardware: if the display doesn't support DPCD backlight, the driver falls back to its default behavior.

**On a running system** (temporary test): edit `/boot/grub/grub.cfg` and add the parameter to the `linux` line, then reboot.

### Graceful degradation

If the kernel parameter isn't set (or on hardware where xrandr can't control the display), Purple Computer detects this at startup and hides the "Adjust Display" option from the parent menu. The detection works by running a no-op xrandr brightness command and checking for "need crtc" errors.

See `purple_tui/rooms/parent_menu.py`: `display_control_available()`.

---

## linux-surface Kernel

The [linux-surface](https://github.com/linux-surface/linux-surface) project provides a patched kernel with better Surface support. For Purple Computer, the stock Ubuntu kernel with the right kernel parameters may be sufficient, but the linux-surface kernel is worth considering if:

- Touchscreen support is needed (Purple Computer doesn't currently use it)
- Battery reporting is unreliable
- Other hardware-specific issues arise

The linux-surface kernel provides:
- Better power management for Surface devices
- Surface Aggregator Module (SAM) support for newer Surface models (4th gen+)
- Improved display, battery, and thermal handling

For Surface Laptop 2 specifically, the stock kernel with `i915.enable_dpcd_backlight=1` appears to be enough for Purple Computer's needs (keyboard via evdev, audio, display).

---

## Known Issues

### xrandr output name `None-1`

Without the DPCD backlight fix, xrandr reports the display as `None-1` rather than a standard name like `eDP-1`. This is cosmetic when the DPCD fix is applied and xrandr works properly. If it persists after the fix, it doesn't affect functionality.

---

## References

- [linux-surface project](https://github.com/linux-surface/linux-surface)
- [i915 DPCD backlight issue](https://gitlab.freedesktop.org/drm/i915/kernel/-/issues/3400)
- [Arch Wiki: Backlight](https://wiki.archlinux.org/title/Backlight) (general Linux backlight troubleshooting)
- [Intel backlight kernel docs](https://docs.kernel.org/gpu/backlight.html)
