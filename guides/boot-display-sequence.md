# Boot Display Sequence

What the user sees from power-on to the TUI, what controls each stage, and what we learned getting here.

**Debugging a hang during live boot?** See `boot-hang-debugging.md` for the always-on boot log (`/var/log/purple/boot.log`) and the Python startup watchdog that dumps thread stacks on stuck starts.

---

## The Boot Stages

### 1. UEFI Firmware (0-2s)

Laptop vendor splash (Dell logo, ThinkPad logo, Apple logo, etc.). We don't control this. Duration varies by hardware.

### 2. GRUB (instant, invisible)

GRUB loads from the USB's EFI partition, runs its embedded config, finds our `grub.cfg`, and boots the kernel.

**What the user sees:** Nothing (timeout=0, no gfxterm, no menu).

**Key files:**
- `build-scripts/01-remaster-iso.sh` (GRUB config, EFI partition patch)
- `grubx64.efi` comes from the stock Ubuntu Server 24.04.1 ISO (not modified)

**EFI partition patch:** Ubuntu's `grubx64.efi` has an embedded config that checks if `$prefix` (default: `/boot/grub` on the EFI partition) exists. On our ISO, the EFI partition only has `/EFI/boot/`, so this check prints `error: file '/boot/' not found` before falling back to a search. We fix this by adding `/boot/grub/grub.cfg` to the EFI FAT partition during the ISO build. That file chains to the real config:

```grub
search --file --set=root /.disk/info
set prefix=($root)/boot/grub
source $prefix/grub.cfg
```

### 3. Kernel + Initramfs (1-3s)

Kernel decompresses and starts. The VT palette is set to purple via kernel command line params (`vt.default_red`, etc.), so any console output would appear on a purple background. Console output goes to tty2 (`console=tty2`), keeping tty1 clean.

**init-top splash:** The earliest script we can run. Redefines VT color 0 to purple (#2d1b4e), clears tty1, and shows "Welcome to Purple Computer! / Starting up..." in white text. This is what the user sees for most of the boot.

**casper-bottom hook:** Runs after the live root is mounted. Repaints the same splash (refresh), restores dotfiles, and sets up debug mode if `purple.debug=1` is on the kernel cmdline.

**What the user sees:** Purple screen with "Welcome to Purple Computer! / Starting up..."

**Key files:**
- `build-scripts/01-remaster-iso.sh` (init-top splash, casper-bottom hook, kernel params)

### 4. Systemd Boot (2-5s)

Systemd takes over. `purple-splash.service` runs early (after `vconsole-setup`) and repaints the same purple splash. This is needed because `vconsole-setup` resets the console font, which can cause a brief size jump. The service also silences kernel console messages (`dmesg -n 1`) so driver probes don't overwrite the splash.

On shutdown, `ExecStop` repaints the splash so systemd teardown messages aren't visible.

**What the user sees:** Same purple "Starting up..." screen (seamless refresh).

**Key files:**
- `build-scripts/00-build-golden-image.sh` (`purple-splash` script and service)

### 5. GPU Readiness + X11 (1-15s)

`purple-x11.service` starts. `ExecStartPre` runs `purple-wait-display`, which polls `/sys/class/drm/card*-*/status` for a connected display. This handles i915's async initialization on older hardware (MacBook 2014 took several seconds to report a connected display).

Once a display is found (or 15s timeout), X11 starts. The xinitrc clears the VT buffer under X (so nothing scary shows if X exits later), starts PulseAudio, launches Alacritty, and runs the Purple TUI.

**What the user sees:** Purple "Starting up..." screen holds until the TUI appears.

**Key files:**
- `scripts/purple-wait-display.sh`
- `config/systemd/purple-x11.service`
- `config/xinit/xinitrc`

### 6. If X11 Fails

`purple-x11-failed` (`ExecStopPost`) paints tty1 purple and shows either a kid-friendly message ("Please turn off and on again") or debug details (log paths, tty2 shell hint). Restart is attempted 3 times within 60s.

---

## What the User Sees (Summary)

| Duration | Screen |
|----------|--------|
| 0-2s | Laptop vendor logo (firmware) |
| instant | Nothing (GRUB, invisible) |
| 3-10s | Purple with "Welcome to Purple Computer! / Starting up..." |
| 0s | TUI appears |

One transition: vendor logo to purple. Purple holds steady until the TUI is ready.

---

## The Purple Color

`#2d1b4e` (RGB 45, 27, 78) everywhere. Applied via:

- **VT palette trick:** `\033]P02d1b4e` redefines VT color 0 (normally black) to purple. Clearing the screen then fills it with "black" = purple. Works on all Linux framebuffer consoles. 24-bit RGB escapes (`\033[48;2;...`) do NOT work on VT consoles.
- **Kernel params:** `vt.default_red=0x2d,...` sets the palette before any scripts run.
- **X11:** `xsetroot -solid '#2d1b4e'` sets the root window. Alacritty background matches.

---

## What Didn't Work

### Plymouth

Attempted 4+ times. Issues: Plymouth fights with Casper for tty1 control, requires framebuffer driver timing to be right, adds complexity for a simple purple screen. The VT palette escape approach is simpler and more reliable.

### GRUB gfxterm for purple background

`loadfont unicode` + `insmod gfxterm` + `terminal_output gfxterm` + `background_color 45,27,78`. This switches GRUB to graphics mode and sets a purple background. Problem: gfxterm initialization shows a gray flash (default framebuffer color before background_color takes effect). Since GRUB's visible time is near-zero with timeout=0, there's no benefit to making it purple. Removed.

### GRUB timeout for technical access

Previously had a 3-second hidden timeout where pressing any key would reveal the GRUB menu (for technical users). Removed in favor of just using the debug ISO when needed. The 3 seconds of blank/GRUB screen before the kernel was wasted time for every normal boot.

### init-top splash without text

Originally init-top only painted the purple background, with text added later by `purple-splash.service` (to avoid a font-size jump from `vconsole-setup`). But the delay between purple-only and purple-with-text was noticeable. Now init-top shows the full message immediately. The font-size jump is less important than showing the user something meaningful as early as possible.

### Writing to /run in init-top

Files written to `/run` during init-top are lost during `switch_root`. Casper-bottom runs after the real `/run` is mounted, so that's where persistent runtime state goes (debug flags, dotfile restore).

---

## Debugging Boot Issues

### Available locally

Built ISOs: `/opt/purple-installer/output/`
Source Ubuntu ISO: `/opt/purple-installer/build/ubuntu-24.04.1-live-server-amd64.iso`

Use xorriso to extract files without needing a live-booted machine:
```bash
# Extract a file from an ISO
xorriso -osirrox on -indev /path/to/iso -extract /path/in/iso /local/path

# List boot records
xorriso -indev /path/to/iso -report_el_torito plain

# Extract EFI partition image (for inspecting grubx64.efi, etc.)
# Get LBA and sector count from -report_el_torito, then:
dd if=/path/to/iso of=efi.img bs=512 skip=$((LBA * 4)) count=SECTORS
```

### On the live machine

```bash
# Check what GRUB config is active
cat /cdrom/boot/grub/grub.cfg

# Check EFI partition contents
ls /cdrom/EFI/boot/

# See kernel command line
cat /proc/cmdline

# Check display connector status (GPU readiness)
cat /sys/class/drm/card*-*/status

# Boot logs
journalctl -b          # full boot log
cat /tmp/purple-boot.log   # purple-specific boot log (debug mode)
cat /tmp/xinitrc.log       # X11 startup log

# Switch to debug shell
# Ctrl+Alt+F2 (tty2 has a login prompt)
```

### Embedded GRUB config

The signed `grubx64.efi` has an embedded config baked in. To inspect it:
```bash
# Extract from ISO
xorriso -osirrox on -indev /path/to/iso -extract /EFI/boot/grubx64.efi ./grubx64.efi

# The config is in xz-compressed memdisk layers. Quick extraction:
python3 -c "
import lzma
data = open('grubx64.efi', 'rb').read()
for i in range(len(data)):
    if data[i:i+6] == b'\xfd7zXZ\x00':
        try:
            d = lzma.decompress(data[i:i+0x200000])
            text = d.decode('ascii', errors='replace')
            if 'search' in text and 'prefix' in text:
                for line in text.split('\n'):
                    if any(k in line for k in ['search','configfile','set ','prefix','source','if ','fi']):
                        print(line.strip())
                break
        except: pass
"
```

Ubuntu Server 24.04.1's embedded config:
```grub
if [ -z "$prefix" -o ! -e "$prefix" ]; then
    if ! search --file --set=root /.disk/info; then
        search --file --set=root /.disk/mini-info
    fi
    set prefix=($root)/boot/grub
fi
if [ -e $prefix/x86_64-efi/grub.cfg ]; then
    source $prefix/x86_64-efi/grub.cfg
elif [ -e $prefix/grub.cfg ]; then
    source $prefix/grub.cfg
fi
```
