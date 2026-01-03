# Linux VM Development Setup

A complete guide to setting up a Linux VM for Purple Computer development with correct keyboard (evdev) behavior.

This guide covers both macOS developers using a VM and Linux-native developers running directly on hardware.

---

## 1. Purpose and Constraints

### Why This Setup Exists

Purple Computer requires precise keyboard semantics that macOS terminals cannot provide:

| Requirement | macOS Terminal | Linux evdev |
|-------------|----------------|-------------|
| Separate key down / key up events | No | Yes |
| Precise timing (ms resolution) | No | Yes |
| Long-press detection | Unreliable | Accurate |
| Modifier state tracking | Approximate | Exact |
| Scancodes | Not available | Available |
| Key repeat vs hold distinction | No | Yes |

The keyboard handling in Purple Computer (sticky shift, double-tap, long-press Escape) depends on these semantics. Without them, you cannot accurately test keyboard UX.

### Why SSH Is Insufficient

When you SSH into a Linux machine:

```
Your Mac keyboard
       ↓
SSH encrypts keystrokes
       ↓
Linux PTY receives characters
       ↓
Your application
```

The Linux PTY receives cooked terminal input, not raw evdev events. You get the same limitations as a Mac terminal, plus network latency.

**SSH is for editing and setup only. Keyboard testing must happen in the VM console or X session.**

### The Solution

Run a Linux VM with:
- Direct console access (UTM window) or X11 session
- evdev for keyboard input
- Alacritty as the terminal

Your keyboard input goes directly through the VM's virtual keyboard device, which Linux exposes via evdev.

---

## 2. Base OS Choice

### Recommended Configuration

| Setting | Value |
|---------|-------|
| VM Software | UTM (macOS) |
| Virtualization | Apple Virtualization (not emulation) |
| Guest OS | Ubuntu Server 24.04 LTS (ARM64) |
| Architecture | aarch64 |
| RAM | 2-4 GB |
| Disk | 16 GB |
| Install Type | Minimized (acceptable) |
| OpenSSH | Enabled |

### Architecture Verification

After installation, verify the architecture:

```bash
uname -m
```

Expected output:
```
aarch64
```

If you see `x86_64`, you accidentally enabled Rosetta or x86 emulation. Reinstall with correct settings.

### Why "Minimized" Install Works

Ubuntu's minimized install omits many packages but keeps the kernel and evdev intact. You will need to install additional packages manually (covered below), but the smaller image boots faster and uses less disk.

---

## 3. Required Base Packages

The minimized Ubuntu Server install does NOT include common development tools. Install them explicitly.

### Essential Packages

```bash
sudo apt update
sudo apt install -y \
    git \
    make \
    unzip \
    fontconfig \
    python3.12 \
    python3.12-venv \
    python3-pip \
    build-essential \
    curl
```

### Why Each Package Is Needed

| Package | Purpose |
|---------|---------|
| `git` | Clone the Purple Computer repository |
| `make` | Run `make setup`, `make run`, etc. |
| `unzip` | Extract font archives during setup |
| `fontconfig` | Font discovery (`fc-cache`, `fc-list`) |
| `python3.12` | Python runtime |
| `python3.12-venv` | Create virtual environments |
| `python3-pip` | Install Python packages |
| `build-essential` | Compile native extensions (some pip packages need this) |
| `curl` | Download fonts and voice models |

### Verify Python

```bash
python3 --version
```

Expected: `Python 3.12.x` (or similar)

---

## 4. Installing Xorg + Matchbox + Alacritty (Kiosk Stack)

We use a minimal X11 stack instead of a full desktop environment. This is faster, simpler, and closer to how Purple Computer runs on real hardware.

### Required Packages

```bash
sudo apt install -y \
    xorg \
    xinit \
    xauth \
    x11-xserver-utils \
    xserver-xorg-video-virtio \
    matchbox-window-manager \
    alacritty \
    xterm
```

### Why Each Package Is Needed

| Package | Purpose |
|---------|---------|
| `xorg` | X server and core components |
| `xinit` | Start X sessions with `startx` |
| `xauth` | X authentication (required by xinit) |
| `x11-xserver-utils` | Utilities like `xset`, `xrandr` |
| `xserver-xorg-video-virtio` | Video driver for VMs |
| `matchbox-window-manager` | Minimal window manager for kiosk mode |
| `alacritty` | GPU-accelerated terminal (Purple's target terminal) |
| `xterm` | Fallback terminal for debugging |

### Important Notes

- Installing Xorg does NOT start it automatically
- There is no desktop environment
- We use `xinit` + `matchbox` to create a minimal kiosk-style session
- `xterm` is critical for debugging: if Alacritty fails, xterm will still work

---

## 5. Fixing Xorg Permission Errors on Ubuntu Server

### The Problem

When you run `startx`, you may see:

```
parse_vt_settings: Cannot open /dev/tty0 (Permission denied)
```

This happens because Ubuntu Server restricts X server access by default.

### The Fix

Edit `/etc/X11/Xwrapper.config`:

```bash
sudo nano /etc/X11/Xwrapper.config
```

Set the contents to:

```
allowed_users=anybody
needs_root_rights=yes
```

Save and exit.

### Apply the Change

Reboot the VM (or at minimum, log out and log back in):

```bash
sudo reboot
```

After reboot, `startx` should work without permission errors.

---

## 6. xinit and .xinitrc

This section is critical. Most "X starts then immediately exits" problems are caused by incorrect `.xinitrc` configuration.

### The Lifecycle Rule

**When the last foreground process in `.xinitrc` exits, X exits.**

This means:
- If your `.xinitrc` runs only background processes, X exits immediately
- If your main application crashes, X exits
- The last command must be a foreground process (usually with `exec`)

### Incremental Debugging Approach

#### Step 1: Known-Good Baseline

Create a minimal `.xinitrc` that proves X works:

```bash
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
exec xterm
EOF
chmod +x ~/.xinitrc
```

Run `startx`. You should see:
- An xterm window
- X stays running until you close xterm

If this fails, the problem is with X configuration, not your application.

#### Step 2: Add Matchbox

Once xterm works, add the window manager:

```bash
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
matchbox-window-manager &
exec xterm
EOF
```

Run `startx`. You should see:
- An xterm window (now managed by matchbox)
- X stays running until you close xterm

#### Step 3: Replace xterm with Alacritty

```bash
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
matchbox-window-manager &
exec alacritty
EOF
```

Run `startx`. You should see:
- An Alacritty window
- X stays running until you close Alacritty

### Why This Structure Works

| Line | Explanation |
|------|-------------|
| `matchbox-window-manager &` | Start window manager in background (the `&` is critical) |
| `exec alacritty` | Replace shell with Alacritty; when Alacritty exits, X exits |

If you forget the `&` after matchbox, it will block and Alacritty will never start.

If you forget `exec`, the shell will wait for Alacritty to exit, then continue to the next line (which doesn't exist), and exit.

---

## 7. Alacritty Debugging on Minimized Systems

### The Problem

Alacritty may crash with:

```
Alacritty panicked with:
Library libxkbcommon-x11.so could not be loaded
```

Or similar errors about missing libraries.

### Why This Happens

Minimized/server installs don't include X11 client libraries. Desktop installs pull these automatically as dependencies of GUI applications. Server installs don't have GUI applications, so these libraries are missing.

### The Fix

```bash
sudo apt install -y libxkbcommon-x11-0
```

Other libraries that may be missing:

```bash
sudo apt install -y \
    libxkbcommon-x11-0 \
    libgl1 \
    libegl1 \
    libgles2
```

### Testing Alacritty

You must test Alacritty from inside a running X session:

```bash
# First, start X with xterm
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
exec xterm
EOF
startx
```

Then, inside the xterm:

```bash
alacritty &
```

If Alacritty opens, it works. If it crashes, read the error message and install missing libraries.

**Do NOT try to run Alacritty from a TTY (before starting X).** It will always fail because there's no display.

---

## 8. Verifying X Is Running

### Check DISPLAY Variable

Inside the X session:

```bash
echo $DISPLAY
```

Expected output:
```
:0
```

If empty or unset, X is not running or you're in a different session.

### Check X Process

From SSH (outside X):

```bash
ps aux | grep Xorg
```

You should see an Xorg process running.

### Visual Confirmation

- The UTM VM window should show a graphical display, not a text console
- Alacritty or xterm should be visible
- X stays running until the main application exits

---

## 9. evdev Still Works Under X

This is important to understand: **evdev works under Xorg.**

X does not "break" evdev. The X server reads from evdev devices and translates events for X clients, but the raw evdev devices are still available at `/dev/input/`.

### Verification

Inside the X session, open a terminal and run:

```bash
sudo evtest /dev/input/by-id/usb-Apple_Inc._Virtual_USB_Keyboard-event-kbd
```

You should see:
- `EV_KEY` events with `value=1` (press), `value=0` (release), `value=2` (repeat)
- Timestamps
- Key codes

This confirms evdev is working correctly.

### How Purple Computer Uses This

`keyboard_normalizer.py` reads directly from evdev, not from Alacritty's stdin. This is why the keyboard UX works correctly:

```
Physical/Virtual Keyboard
       ↓
evdev (/dev/input/...)
       ↓
keyboard_normalizer.py (grabs device, processes events)
       ↓
Virtual keyboard (uinput)
       ↓
X server
       ↓
Alacritty (display only)
       ↓
Purple TUI
```

The TUI receives already-processed events. The timing-sensitive logic happens in keyboard_normalizer.py using evdev.

### Device Grabbing

In production, keyboard_normalizer.py grabs the keyboard device exclusively (`EVIOCGRAB`). This prevents keystrokes from reaching the shell or other applications.

During development, you may want to disable grabbing so you can still use the keyboard for other things. Check the keyboard_normalizer.py source for options.

---

## 10. Recommended Workflow

### Daily Development Loop

| Task | Where |
|------|-------|
| Edit code | SSH or shared folder from Mac |
| Git operations | SSH |
| Install packages | SSH |
| Run Purple Computer | VM console / X session |
| Test keyboard UX | VM console / X session |

### Typical Session

1. **SSH in** from your Mac for editing:
   ```bash
   ssh user@vm-ip
   cd purplecomputer
   # edit code, git pull, etc.
   ```

2. **Switch to VM console** (UTM window) for testing:
   ```bash
   # Log in at the console
   cd purplecomputer
   startx
   ```

3. **Inside X**, Alacritty opens with your `.xinitrc`. Run Purple:
   ```bash
   source .venv/bin/activate
   make run
   ```

4. **Test keyboard features**:
   - Long-press Escape (1 sec) → parent mode
   - Tap shift, then type `a` → `A` (sticky shift)
   - Type `a` twice quickly → `A` (double-tap)
   - F1/F2/F3 → mode switching

5. **Exit** Alacritty to close X, then SSH back in to edit.

### File Syncing Options

| Method | Pros | Cons |
|--------|------|------|
| Git push/pull | Simple, version controlled | Requires commits |
| rsync over SSH | Fast, no commits needed | Manual sync |
| UTM shared folder | Automatic, instant | Requires UTM configuration |

For rapid iteration, UTM shared folders or rsync are recommended.

---

## 11. Troubleshooting Appendix

### Quick Checklist

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| X starts then immediately exits | `.xinitrc` has no foreground process | Use `exec alacritty` as last line |
| `DISPLAY` not set | X not running | Run `startx` first |
| `Cannot open /dev/tty0` | X permission denied | Edit `/etc/X11/Xwrapper.config` |
| Alacritty panic / library error | Missing X11 libraries | `apt install libxkbcommon-x11-0` |
| Black screen, nothing visible | Window manager or app crashed | Fall back to `exec xterm` in `.xinitrc` |
| evdev permission denied | Not in input group | `sudo usermod -aG input $USER` then reboot |
| No `/dev/input/by-id/*` entries | Keyboard not detected | Check UTM VM settings |
| Keyboard works in X but not evdev | Device grabbed by another process | Check for other evdev readers |

### Debugging .xinitrc

If X exits immediately:

1. Add logging:
   ```bash
   cat > ~/.xinitrc << 'EOF'
   #!/bin/sh
   echo "Starting matchbox" >> /tmp/xinit.log
   matchbox-window-manager &
   echo "Starting alacritty" >> /tmp/xinit.log
   exec alacritty
   EOF
   ```

2. Run `startx`, let it fail

3. Check `/tmp/xinit.log` to see how far it got

4. If log is empty, the problem is before your `.xinitrc` runs (X server issue)

### Debugging Alacritty

Run Alacritty with verbose output:

```bash
RUST_BACKTRACE=1 alacritty
```

This shows the full error trace, including missing libraries.

### Debugging evdev

List available input devices:

```bash
ls -la /dev/input/by-id/
```

Test a specific device:

```bash
sudo evtest /dev/input/by-id/usb-Apple_Inc._Virtual_USB_Keyboard-event-kbd
```

Check permissions:

```bash
groups  # Should include 'input'
ls -la /dev/input/event*  # Check group ownership
```

---

## 12. Complete Setup Script

For convenience, here's a script that installs everything after a fresh Ubuntu Server install:

```bash
#!/bin/bash
# Purple Computer VM Setup
# Run this after fresh Ubuntu Server (minimized) install

set -e

echo "=== Purple Computer VM Setup ==="

# Base packages
echo "Installing base packages..."
sudo apt update
sudo apt install -y \
    git make unzip curl fontconfig \
    python3.12 python3.12-venv python3-pip \
    build-essential

# X11 stack
echo "Installing X11 + Alacritty..."
sudo apt install -y \
    xorg xinit xauth x11-xserver-utils \
    xserver-xorg-video-virtio \
    matchbox-window-manager \
    alacritty xterm \
    libxkbcommon-x11-0

# Fix X permissions
echo "Configuring X permissions..."
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

# Add user to input group
echo "Adding user to input group..."
sudo usermod -aG input $USER

# Create .xinitrc
echo "Creating .xinitrc..."
cat > ~/.xinitrc << 'EOF'
#!/bin/sh
matchbox-window-manager &
exec alacritty
EOF
chmod +x ~/.xinitrc

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Reboot: sudo reboot"
echo "2. Log in at VM console (not SSH)"
echo "3. Clone Purple Computer: git clone https://github.com/..."
echo "4. Run: cd purplecomputer && make setup"
echo "5. Start X: startx"
echo "6. In Alacritty: make run"
echo ""
```

Save this as `vm-setup.sh`, run with `bash vm-setup.sh`, then reboot.

---

## Summary

| Component | Purpose |
|-----------|---------|
| Ubuntu Server (ARM64) | Base OS with evdev support |
| Xorg + xinit | Minimal X11 server |
| Matchbox | Lightweight window manager |
| Alacritty | GPU-accelerated terminal |
| evdev | Raw keyboard input |
| keyboard_normalizer.py | Processes keyboard events |

The key insight: this setup gives you real Linux keyboard behavior (evdev) in a VM, allowing rapid iteration without flashing hardware. SSH is for editing; the VM console/X session is for testing.
