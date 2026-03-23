# Plan: Robust X11 Startup with GPU Readiness

## Problem

X11 starts before the i915 GPU driver finishes display initialization on slower hardware (MacBook 2014 Haswell). The screen goes fully dark (backlight off). The debug recovery shell works because the delay gives the GPU time to finish. The `i915.enable_dpcd_backlight=1` kernel parameter may also cause backlight failure on hardware that doesn't support DPCD backlight (older MacBooks use LVDS/early eDP).

## Root Cause

The current boot chain is: `systemd → getty autologin → .bashrc → startx`. There is no mechanism to wait for the GPU's display pipeline to be ready. The `Type=idle` on the live boot service only waits for systemd jobs to be dispatched, not for the GPU to finish its async internal initialization (connector scanning, EDID reading, backlight setup).

Evidence:
- Same ISO works on 2015 MacBook (Broadwell i915 initializes faster)
- Debug recovery shell (which adds human-scale delay) makes 2014 MacBook work
- Screen goes fully dark (backlight off, not just black pixels) right when X11 would be starting
- The `i915.enable_dpcd_backlight=1` kernel parameter forces DPCD backlight control, which may not be supported on 2014 MacBook panels

## Solution Overview

1. Replace the `.bashrc → startx` chain with a systemd service that has proper GPU device dependencies
2. Add a display-readiness poller script as `ExecStartPre`
3. Remove `i915.enable_dpcd_backlight=1` from ALL kernel command lines (let the kernel auto-detect)
4. Use systemd's built-in restart limits instead of the manual fail counter file

---

## New Files to Create

### 1. `scripts/purple-wait-display.sh`

Installed to `/usr/local/bin/purple-wait-display`. Runs as `ExecStartPre` in the systemd service.

```bash
#!/bin/sh
# Wait for a display to be connected before starting X11.
#
# The i915 GPU driver loads asynchronously: the DRM device node (/dev/dri/card0)
# appears before display connectors are fully initialized. Starting X11 too
# early can result in a black screen or backlight failure, especially on older
# hardware (MacBook 2014 Haswell, some ThinkPads).
#
# This script polls /sys/class/drm/ for a connected display connector.
# It's meant to run as ExecStartPre in the purple-x11 systemd service.

DEBUG_FLAG=/opt/purple/debug
BOOT_LOG=/tmp/purple-boot.log
MAX_WAIT=15

log() {
    local msg="[$(date '+%H:%M:%S')] [wait-display] $1"
    if [ -f "$DEBUG_FLAG" ]; then
        echo "$msg"
        echo "$msg" >> "$BOOT_LOG" 2>/dev/null
    fi
}

# Check if any DRM connector reports "connected"
check_connected() {
    for status_file in /sys/class/drm/card*-*/status; do
        [ -f "$status_file" ] || continue
        if [ "$(cat "$status_file" 2>/dev/null)" = "connected" ]; then
            echo "$status_file"
            return 0
        fi
    done
    return 1
}

log "Waiting for display (up to ${MAX_WAIT}s)..."

waited=0
while [ "$waited" -lt "$MAX_WAIT" ]; do
    found=$(check_connected)
    if [ -n "$found" ]; then
        connector=$(echo "$found" | sed 's|.*/drm/||; s|/status||')
        log "Display ready: $connector (waited ${waited}s)"
        exit 0
    fi
    sleep 0.5
    waited=$((waited + 1))
done

# Timeout: proceed anyway. Some hardware (VMs, unusual panels) may not report
# connector status through sysfs but still work fine with X11.
log "No connected display found after ${MAX_WAIT}s, proceeding anyway"
exit 0
```

### 2. `scripts/purple-x11-failed.sh`

Installed to `/usr/local/bin/purple-x11-failed`. Runs as `ExecStopPost` in the systemd service.

Important: this script is called on EVERY service stop (not just failures). It must check whether the stop was a failure before showing the error. The `$SERVICE_RESULT` environment variable is set by systemd: it's `success` on clean stop, something else on failure.

```bash
#!/bin/sh
# Shown on tty1 when X11 fails to start after multiple attempts.
# Called as ExecStopPost by purple-x11.service.
# Only shows the error screen on failure, not clean shutdown.

# Don't show error on clean stop (e.g. system shutdown)
[ "$SERVICE_RESULT" = "success" ] && exit 0

DEBUG_FLAG=/opt/purple/debug

# Paint tty1 purple background
printf '\033]P02d1b4e\033[H\033[2J' > /dev/tty1 2>/dev/null

if [ -f "$DEBUG_FLAG" ]; then
    # Debug mode: show technical details
    cat > /dev/tty1 2>/dev/null <<'MSG'

  Purple Computer could not start the display.

  Logs:
    /tmp/purple-boot.log      (boot sequence)
    /tmp/startx.log           (X11 output)
    /tmp/xinitrc.log           (xinitrc output)
    /var/log/Xorg.0.log        (X server)

  Switch to tty2 for a shell: Ctrl+Alt+F2

MSG
else
    # Production: kid/parent-friendly message
    cat > /dev/tty1 2>/dev/null <<'MSG'

  Something went wrong starting Purple Computer.

  Please turn off and on again.

  If this keeps happening, contact us at
  support@purplecomputer.org

MSG
fi
```

### 3. `config/systemd/purple-x11.service`

```ini
[Unit]
Description=Purple Computer X11 Session
# Event-driven GPU wait: don't start until the DRM device is registered.
# Wants= (not Requires=) so we still start if the device unit name differs
# on unusual hardware (e.g. card1, renderD128 in VMs).
Wants=dev-dri-card0.device
After=dev-dri-card0.device
After=systemd-user-sessions.service
After=purple-splash.service
# Keep the boot splash visible while we wait for the GPU
Requires=purple-splash.service
# Don't start in installer mode
ConditionKernelCommandLine=!purple.install=1

[Service]
# Poll for a connected display connector (handles i915 async init)
ExecStartPre=/usr/local/bin/purple-wait-display
# Clean stale X lock files from previous crashes
ExecStartPre=-/bin/rm -f /tmp/.X0-lock /tmp/.X11-unix/X0
ExecStart=/usr/bin/startx /home/purple/.xinitrc -- vt1
User=purple
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=tty
StandardError=journal+console
UtmpIdentifier=tty1
TTYReset=no
TTYVHangup=no
TTYVTDisallocate=no
# Restart on failure (replaces manual fail counter)
Restart=on-failure
RestartSec=2
StartLimitIntervalSec=60
StartLimitBurst=3
# Show error on tty1 if we hit the restart limit (or any failure)
ExecStopPost=-/usr/local/bin/purple-x11-failed

[Install]
WantedBy=graphical.target
```

---

## Files to Modify

### 4. `build-scripts/00-build-golden-image.sh`

#### 4a. Replace getty@tty1 autologin with mask (lines 291-297)

REMOVE this block:
```bash
    # Configure auto-login for purple user on tty1
    mkdir -p "$MOUNT_DIR/etc/systemd/system/getty@tty1.service.d"
    cat > "$MOUNT_DIR/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin purple --skip-login --noclear --noissue --nohostname %I $TERM
AUTOLOGIN
```

REPLACE WITH:
```bash
    # Mask getty@tty1: the purple-x11 service owns tty1 directly (no login shell needed)
    chroot "$MOUNT_DIR" systemctl mask getty@tty1.service
```

#### 4b. Install new service and scripts (add after line 402, after the X.Org config copies)

ADD this block after the `40-disable-pointer.conf` copy:
```bash
    # Purple X11 service: systemd-managed, waits for GPU readiness before starting X
    cp /purple-src/config/systemd/purple-x11.service "$MOUNT_DIR/etc/systemd/system/"
    cp /purple-src/scripts/purple-wait-display.sh "$MOUNT_DIR/usr/local/bin/purple-wait-display"
    cp /purple-src/scripts/purple-x11-failed.sh "$MOUNT_DIR/usr/local/bin/purple-x11-failed"
    chmod +x "$MOUNT_DIR/usr/local/bin/purple-wait-display"
    chmod +x "$MOUNT_DIR/usr/local/bin/purple-x11-failed"
    chroot "$MOUNT_DIR" systemctl enable purple-x11.service
```

#### 4c. Remove the entire .bashrc autostart block (lines 413-513)

REMOVE everything from `# Configure auto-start X11 on login (via .bashrc)` through the end of the `AUTOSTART` heredoc (the line `fi` followed by `AUTOSTART`). This is lines 413-513.

The `.bashrc` should just be the default Ubuntu bashrc. The `startx` call, debug banner, fail counter, splash repaint, log saving logic all go away. The systemd service handles all of this now.

#### 4d. Remove bash-autostart.sh creation (lines 516-518)

REMOVE these lines:
```bash
    # Store the autostart snippet in /etc/purple/ for the live boot hook
    # (Everything between the AUTOSTART markers above)
    sed -n '/^# Auto-start X11/,/^fi$/p' "$MOUNT_DIR/home/purple/.bashrc" > "$MOUNT_DIR/etc/purple/bash-autostart.sh"
```

#### 4e. Remove i915.enable_dpcd_backlight=1 from installed GRUB config (lines 536-552)

In the `cat > "$MOUNT_DIR/boot/grub/grub.cfg"` heredoc, remove `i915.enable_dpcd_backlight=1` from BOTH menuentry blocks.

Line 543 currently reads:
```
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet loglevel=0 systemd.show_status=false vt.global_cursor_default=0 console=tty2 console=ttyS0,115200n8 i915.enable_dpcd_backlight=1
```
Change to:
```
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet loglevel=0 systemd.show_status=false vt.global_cursor_default=0 console=tty2 console=ttyS0,115200n8
```

Line 549 currently reads:
```
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro single console=tty0 console=ttyS0,115200n8 i915.enable_dpcd_backlight=1
```
Change to:
```
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro single console=tty0 console=ttyS0,115200n8
```

### 5. `build-scripts/01-remaster-iso.sh`

#### 5a. Remove purple-live.service creation (lines 124-150)

REMOVE the entire block from `# Write our own getty service` through the symlink creation. This is:
```bash
    # Write our own getty service (casper doesn't enable getty@tty1 on Ubuntu Server).
    mkdir -p /root/etc/systemd/system
    cat > /root/etc/systemd/system/purple-live.service << 'SERVICE_EOF'
    ...
    SERVICE_EOF

    mkdir -p /root/etc/systemd/system/multi-user.target.wants
    ln -sf ../purple-live.service /root/etc/systemd/system/multi-user.target.wants/purple-live.service
    purple_log "Created purple-live.service (autologin on tty1)"
```

The golden image's `purple-x11.service` is already in the squashfs and enabled, so it works for live boot too.

#### 5b. Remove .bashrc autostart restoration (line 108)

REMOVE this line:
```bash
    cat /root/etc/purple/bash-autostart.sh >> /root/home/purple/.bashrc
```

Keep the lines around it (xinitrc restoration on lines 105-107, .hushlogin on line 110).

#### 5c. Remove i915.enable_dpcd_backlight=1 from ALL GRUB configs

There are 5 occurrences in this file. Remove `i915.enable_dpcd_backlight=1` (and the space before it) from each:

- **Line 583** (normal live boot menuentry)
- **Line 589** (install menuentry)
- **Line 668** (debug live boot menuentry)
- **Line 674** (debug recovery shell menuentry) -- note: this line doesn't have it currently, double-check
- **Line 680** (debug install menuentry)

### 6. `config/xinit/xinitrc`

#### 6a. Replace the exit logic at the end (lines 140-151)

REMOVE lines 140-151:
```bash
# After Purple exits
if [ -f "$DEBUG_FLAG" ]; then
    # Debug: drop to interactive debug shell
    xlog "Opening debug shell"
    sed -i 's/^size = .*/size = 16.0/' "$ALACRITTY_CONFIG"
    exec alacritty --config-file "$ALACRITTY_CONFIG" \
        -e bash --rcfile /opt/purple/debug-shell.sh
else
    # Production: restart Purple
    xlog "Restarting xinitrc"
    exec "$0"
fi
```

REPLACE WITH:
```bash
# Restart Purple (keeps X running for fast restart without screen flash).
# If X itself crashes, this script exits and systemd restarts the whole service.
xlog "Restarting xinitrc"
exec "$0"
```

This removes the debug shell (tty2 serves that purpose) and always does the fast self-restart. The debug shell via Alacritty was fragile anyway since it depended on X still running.

### 7. `UX_LOG.md`

Add a new entry at the top (after the header line):

```
- Boot now waits for the GPU display to be ready before starting, fixing black screen on older hardware (MacBook 2014, some ThinkPads). Removed forced DPCD backlight parameter that could turn off the screen on unsupported panels.
```

---

## What NOT to Change

- **`purple-splash.service`** (lines 299-331 in golden image): keep as-is. The new service declares `After=purple-splash.service` so the splash is visible during the GPU wait.
- **tty2 autologin** (lines 520-526 in golden image): keep as-is. This is the debug shell access point.
- **xinitrc body** (lines 1-139): keep as-is. All the X setup (PulseAudio, matchbox-wm, xset, cursor hiding, Alacritty launch) stays the same.
- **X.Org configs** (10-modesetting.conf, 40-disable-pointer.conf): keep as-is.
- **`/etc/purple/xinitrc` canonical copy** (line 411 in golden image): keep. The live boot hook still needs to restore it.

---

## Risks and Testing Notes

### PAMName=login + User=purple
The systemd service uses `PAMName=login` to get a proper PAM session, which should create `/run/user/1000` (needed for PulseAudio). If PulseAudio fails to start on testing, add these lines to the `[Service]` section before the `ExecStart`:
```ini
ExecStartPre=+/bin/mkdir -p /run/user/1000
ExecStartPre=+/bin/chown 1000:1000 /run/user/1000
```
(The `+` prefix runs as root regardless of `User=`.)

### startx -- vt1
The `-- vt1` argument forces X to use VT1. If X fails with a VT permission error, try removing `-- vt1` (X should inherit the TTY from the service's `TTYPath=/dev/tty1`).

### Removing i915.enable_dpcd_backlight=1
This parameter was presumably added to fix backlight on some laptop. The kernel's auto-detection should handle it (the parameter just forces one code path). Test on any hardware where backlight control was previously problematic. If a specific laptop regresses, the fix is to use `i915.enable_dpcd_backlight=0` for that machine (explicit opt-out) rather than forcing opt-in for all machines.

### ExecStopPost runs on every stop
The `purple-x11-failed.sh` script checks `$SERVICE_RESULT` (set by systemd) and only shows the error screen when it's not `success`. This means clean shutdowns won't flash an error. Verify this works by testing both: `systemctl stop purple-x11` (should NOT show error) and killing X (should show error after 3 restarts).

### Live boot: purple-x11.service must be in the squashfs
Since we're removing `purple-live.service` from the casper hook, the `purple-x11.service` must already be enabled in the golden image that gets packed into the squashfs. The `systemctl enable` in step 4b handles this. Verify that after building, the service starts on live boot without the casper hook creating any additional services.

### The xinitrc self-restart loop
The `exec "$0"` at the end of xinitrc means: when Alacritty/Purple exits, xinitrc re-runs itself (restarting Alacritty+Purple without tearing down X). This is a fast restart with no screen flash. Only if X itself crashes does the script exit, which causes the systemd service to restart (slower, but handles X server failures). This two-tier restart is intentional.
