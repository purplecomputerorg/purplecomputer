# Kid-Proofing Purple Computer

Purple Computer must be resilient to kids (ages 2–8+) mashing random key combinations. This document explains the hardening measures and how they work together.

---

## The Problem

Kids press random keys. Sometimes they hold keys, sometimes they mash combinations. On a normal Linux system, this can:

- Kill the X server (Ctrl+Alt+Backspace)
- Switch to a scary terminal (Ctrl+Alt+F1)
- Trigger instant reboot (Alt+SysRq+B)
- Enable sticky keys (hold Shift 5 seconds)
- Reboot the system (Ctrl+Alt+Del)

Purple Computer disables all of these.

---

## Hardening Layers

| Layer | What it blocks | Config file |
|-------|---------------|-------------|
| X11 ServerFlags | VT switching, X kill | `config/xorg/10-modesetting.conf` |
| Kernel sysctl | SysRq magic keys | `/etc/sysctl.d/99-purple-sysrq.conf` |
| Systemd mask | Ctrl+Alt+Del reboot | `ctrl-alt-del.target` masked |
| XKB AccessX | Sticky keys, slow keys | `xkbset -a` in xinitrc |
| Evdev grab | Terminal signals (Ctrl+C) | `input.py` grabs keyboard exclusively |
| Logind | Power button behavior | `/etc/systemd/logind.conf.d/purple-power.conf` |

---

## X11 Level: DontZap

**File:** `config/xorg/10-modesetting.conf`

```
Section "ServerFlags"
    Option "DontZap" "true"
EndSection
```

| Shortcut | Normal behavior | With hardening |
|----------|-----------------|----------------|
| Ctrl+Alt+Backspace | Kills X server instantly | Ignored |

**`DontVTSwitch` is intentionally NOT set.** Ctrl+Alt+F2 reaches an autologin bash shell on tty2 (enabled on both ISOs). 4-7 year olds won't accidentally chord three keys, and if they did they'd land on a harmless unprivileged shell — Ctrl+Alt+F1 returns to Purple. Keeping the escape hatch is worth more than the theoretical accidental-press risk.

---

## Kernel Level: SysRq Disabled

**File:** `/etc/sysctl.d/99-purple-sysrq.conf`

```
kernel.sysrq = 0
```

| Shortcut | Normal behavior | With hardening |
|----------|-----------------|----------------|
| Alt+SysRq+B | Instant reboot (no sync) | Ignored |
| Alt+SysRq+O | Instant poweroff | Ignored |
| Alt+SysRq+K | Kill all processes on TTY | Ignored |

SysRq (PrintScreen on most keyboards) combined with Alt triggers "magic" system commands. Value 0 disables all of them.

**Exception:** The shutdown watchdog (`PowerManager.shutdown()`) and post-install reboot watcher re-enable sysrq dynamically (`echo 1 > /proc/sys/kernel/sysrq`) immediately before triggering poweroff/reboot via sysrq. This is the nuclear fallback that works even when overlayfs is dead (USB removed during live boot). Kids cannot trigger it: it requires root and only fires from code paths that have already confirmed shutdown intent.

---

## Systemd Level: Ctrl+Alt+Del Masked

**Applied in:** `build-scripts/00-build-golden-image.sh`

```bash
systemctl mask ctrl-alt-del.target
```

By default, Ctrl+Alt+Del triggers a system reboot via systemd. Masking the target makes it do nothing.

---

## XKB Level: AccessX Disabled

**File:** `config/xinit/xinitrc`

```bash
xkbset -a  # Disable all AccessX features
```

| Trigger | Normal behavior | With hardening |
|---------|-----------------|----------------|
| Hold Shift 5 seconds | Enable sticky keys | Ignored |
| Hold Shift 8 seconds | Enable slow keys | Ignored |

AccessX accessibility features are well-intentioned but confuse kids. Sticky keys makes Shift "stick" so the next key is shifted. Slow keys requires holding each key for a full second.

---

## Evdev Level: Keyboard Grabbed

**File:** `purple_tui/input.py`

```python
class EvdevReader:
    def __init__(self, callback, device_path=None, grab=True):
        ...
        self._device.grab()  # Exclusive access
```

The evdev reader grabs the keyboard exclusively. This means:

- X11/Alacritty never see keyboard events
- Ctrl+C doesn't reach the terminal (can't send SIGINT)
- All keyboard input goes through Purple's handler

This is the deepest layer of protection. Even if other layers fail, the terminal can't receive dangerous signals.

---

## Power Management: Kid-Friendly Power Button and Lid

**Files:**
- `/etc/systemd/logind.conf.d/purple-power.conf` (logind ignores all buttons)
- `purple_tui/input.py`: `PowerButtonReader` monitors power button via evdev
- `purple_tui/rooms/sleep_screen.py`: `SleepScreen`, `ByeScreen`, `LiveBootSplash`
- `purple_tui/power_manager.py`: idle tracking, charger detection, and shutdown

```ini
[Login]
HandlePowerKey=ignore
HandlePowerKeyLongPress=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleSuspendKey=ignore
HandleHibernateKey=ignore
```

logind ignores all power actions so the TUI has full control over the UX.

Two power states: awake and sleep face. Timers adapt to charger and lid:

| Action | What happens |
|--------|-------------|
| Power button tap | Shows shutdown confirm. Second tap shuts down. Any other key cancels. |
| Power button hold (3s) | Shows "Bye!" screen and shuts down immediately. |
| Power button hold (10s) | Hardware forced off (ACPI, cannot be changed). |
| Lid close | Sleep face immediately. Shuts down after 10 min. Lid reopen resets everything. |
| Idle (on charger) | 5 min: sleep face. 60 min: shutdown. |
| Idle (on battery) | 2 min: sleep face. 10 min: shutdown. |

Charger detection scans `/sys/class/power_supply/` for `type == "Mains"` with smoothing (2 consecutive reads). Falls back to battery timers if charger state is unknown.

**Why this design:** A 3-year-old mashing the power button sees a cute sleeping face (not scary) and can press any key to get back. A parent who wants to turn it off holds power for 3 seconds (phone-like, intuitive). No suspend/hibernate (unreliable on old laptops). Closing the lid to carry the laptop is safe for 10 minutes. Plugged in machines get more time (60 min) but nothing runs forever.

The 10-second forced power-off is a **hardware feature** (ACPI) that bypasses the OS. This cannot be changed and serves as the ultimate escape hatch.

**Live boot:** On first launch from USB, a splash screen explains that Purple is running from USB and will need the USB again after shutdown. The sleep face and parent menu also show reminders during live boot.

---

## What's NOT Blocked

These are deliberately allowed:

| Action | Why allowed |
|--------|-------------|
| Fn+Brightness | Annoying but harmless |
| Fn+Volume | Annoying but harmless |
| Power button tap | Shows sleep screen (harmless, any key wakes) |
| Lid close | Delayed shutdown with 2-minute grace period |

---

## Applying to Existing Installations

For machines already installed (without rebuilding the image):

```bash
# 1. X11 hardening (edit existing file or create new)
sudo tee /usr/share/X11/xorg.conf.d/99-purple-kidproof.conf << 'EOF'
Section "ServerFlags"
    Option "DontZap" "true"
    Option "DontVTSwitch" "true"
EndSection
EOF

# 2. Disable SysRq
echo 'kernel.sysrq = 0' | sudo tee /etc/sysctl.d/99-purple-sysrq.conf
sudo sysctl -p /etc/sysctl.d/99-purple-sysrq.conf

# 3. Mask Ctrl+Alt+Del
sudo systemctl mask ctrl-alt-del.target

# 4. Power button and lid: TUI handles everything
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/purple-power.conf << 'EOF'
[Login]
HandlePowerKey=ignore
HandlePowerKeyLongPress=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
HandleSuspendKey=ignore
HandleHibernateKey=ignore
EOF
sudo systemctl restart systemd-logind

# 5. Install xkbset (for AccessX disabling in xinitrc)
sudo apt install xkbset

# 6. Reboot to apply all changes
sudo reboot
```

---

## Testing

To verify hardening is working:

```bash
# Check SysRq is disabled
cat /proc/sys/kernel/sysrq  # Should be 0

# Check Ctrl+Alt+Del is masked
systemctl status ctrl-alt-del.target  # Should show "masked"

# Check X config is loaded (in X session)
grep -i dontzap /var/log/Xorg.0.log

# Test keyboard grab (should see "grabbed keyboard exclusively")
grep -i "grabbed" /tmp/xinitrc.log
```

---

## Summary

Purple Computer uses defense in depth:

1. **X11** blocks VT switching and X kill shortcuts
2. **Kernel** blocks SysRq magic keys
3. **Systemd** blocks Ctrl+Alt+Del reboot
4. **XKB** blocks accessibility toggles
5. **Evdev** grabs keyboard so terminal never sees signals
6. **Logind** ignores power/lid so TUI controls the UX (tap=sleep, hold=shutdown, lid=delayed shutdown)

No single layer is sufficient. Together, they make the system resilient to any key combination a kid can produce.
