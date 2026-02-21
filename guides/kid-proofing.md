# Kid-Proofing Purple Computer

Purple Computer must be resilient to kids (ages 2-8+) mashing random key combinations. This document explains the hardening measures and how they work together.

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

## X11 Level: DontZap and DontVTSwitch

**File:** `config/xorg/10-modesetting.conf`

```
Section "ServerFlags"
    Option "DontZap" "true"
    Option "DontVTSwitch" "true"
EndSection
```

| Shortcut | Normal behavior | With hardening |
|----------|-----------------|----------------|
| Ctrl+Alt+Backspace | Kills X server instantly | Ignored |
| Ctrl+Alt+F1-F12 | Switch to different TTY | Ignored |

These are the most common accidental escapes. DontVTSwitch is critical because switching TTYs leaves kids at a login prompt or blank screen.

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

## Power Management: Clean Shutdown

**File:** `/etc/systemd/logind.conf.d/purple-power.conf`

```ini
[Login]
HandlePowerKey=poweroff
HandlePowerKeyLongPress=poweroff
HandleLidSwitch=poweroff
HandleSuspendKey=poweroff
HandleHibernateKey=poweroff
```

All power actions trigger clean shutdown. No suspend/hibernate (unreliable on old laptops).

The 10-second forced power-off is a **hardware feature** (ACPI) that bypasses the OS. This cannot be changed and serves as the ultimate escape hatch.

---

## What's NOT Blocked

These are deliberately allowed:

| Action | Why allowed |
|--------|-------------|
| Fn+Brightness | Annoying but harmless |
| Fn+Volume | Annoying but harmless |
| Power button | Clean shutdown (configured above) |
| Lid close | Clean shutdown (configured above) |

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

# 4. Power button (add to existing file)
sudo tee -a /etc/systemd/logind.conf.d/purple-power.conf << 'EOF'
HandlePowerKey=poweroff
HandlePowerKeyLongPress=poweroff
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
6. **Logind** makes power button do clean shutdown

No single layer is sufficient. Together, they make the system resilient to any key combination a kid can produce.
