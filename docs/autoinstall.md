# Purple Computer: Autoinstall Guide

This guide covers building the Purple Computer ISO and installing it on a machine.

## Overview

Purple Computer uses Ubuntu's autoinstall system to create a completely automated installation. You:
1. Build the ISO
2. Write it to a USB drive
3. Boot from USB
4. Walk away—installation is automatic

## Prerequisites

### For Building the ISO
- Ubuntu 22.04 LTS or similar Linux system
- 10GB free disk space
- `xorriso`, `isolinux`, `curl` packages
- Root/sudo access

### For Installing Purple Computer
- Target machine with:
  - x86_64 processor (Intel or AMD)
  - 2GB RAM minimum (4GB recommended)
  - 8GB storage minimum (16GB recommended)
  - USB port for installation media

## Building the ISO

### Step 1: Clone Repository
```bash
git clone https://github.com/yourusername/purplecomputer.git
cd purplecomputer
```

### Step 2: Install Build Dependencies
```bash
sudo apt update
sudo apt install -y xorriso isolinux curl wget p7zip-full
```

### Step 3: Run Build Script
```bash
cd autoinstall
./build-iso.sh
```

This script will:
1. Download the Ubuntu 22.04 Server ISO
2. Extract the ISO contents
3. Inject our autoinstall configuration
4. Add Purple Computer files
5. Rebuild the ISO with our customizations
6. Create `purple-computer.iso`

Build time: 5-15 minutes depending on your internet connection.

### Step 4: Verify ISO
```bash
ls -lh purple-computer.iso
# Should be around 1.4GB
```

## Creating Installation Media

### On Linux
```bash
# Identify your USB drive
lsblk

# Write ISO to USB (replace /dev/sdX with your drive)
sudo dd if=purple-computer.iso of=/dev/sdX bs=4M status=progress
sudo sync
```

### On macOS
```bash
# Identify your USB drive
diskutil list

# Unmount the drive (replace diskN with your drive)
diskutil unmountDisk /dev/diskN

# Write ISO to USB
sudo dd if=purple-computer.iso of=/dev/rdiskN bs=4m
```

### On Windows
Use [Rufus](https://rufus.ie/) or [balenaEtcher](https://www.balena.io/etcher/):
1. Open the tool
2. Select the `purple-computer.iso`
3. Select your USB drive
4. Click "Flash" or "Start"

## Installing Purple Computer

### Step 1: Boot from USB
1. Insert the USB drive into the target computer
2. Power on and enter boot menu (usually F12, F2, or ESC)
3. Select the USB drive
4. Ubuntu installer will start

### Step 2: Automatic Installation
The installation is completely automated. You'll see:
1. Language selection (defaults to English)
2. Autoinstall begins
3. Partitioning (entire disk)
4. Package installation
5. Purple Computer setup
6. System configuration
7. Reboot prompt

**Do not interrupt**. The process takes 10-20 minutes.

### Step 3: First Boot
After reboot:
1. Remove the USB drive
2. Computer boots into Purple Computer automatically
3. Large purple welcome screen appears
4. Kid environment is ready!

## What the Autoinstall Does

### Partitioning
- Uses entire disk with LVM
- Creates: `/boot`, `/`, swap
- No separate `/home` partition

### Base System
Installs minimal Ubuntu Server packages:
- Linux kernel
- systemd
- network tools (disabled by default)

### Additional Packages
```
- xorg                # Minimal X11 server
- kitty               # Terminal emulator
- python3             # Python runtime
- python3-pip         # Package manager
- ipython3            # Interactive Python
- piper-tts           # Speech synthesis
- fonts-noto-color-emoji  # Emoji support
```

### User Configuration
Creates:
- User: `kiduser` (auto-login)
- Password: `purplecomputer` (for parent access via Ctrl+Alt+P)
- Home: `/home/kiduser`

### System Configuration
- Disables automatic updates (stable experience)
- Configures auto-login via getty
- Sets up systemd kiosk service
- Installs Purple REPL
- Configures Kitty terminal
- Sets up X11 auto-start

### Purple Computer Files
Copies into system:
```
/home/kiduser/.purple/     # REPL and modules
/home/kiduser/.xinitrc     # X11 startup
/home/kiduser/.config/     # Kitty config
/etc/systemd/system/       # Service files
/usr/share/purple/         # Shared resources
```

## Post-Installation Configuration

### Accessing Parent Mode
Press **Ctrl+Alt+P** to access the parent menu.

From there you can:
- Open a root terminal
- Change kiduser password
- Configure network (if needed)
- Customize settings
- Return to kid mode

### Changing Default Password
```bash
# Via parent menu or:
sudo passwd kiduser
```

### Enabling Network (Optional)
Purple Computer works offline by default. To enable network:
```bash
# Via parent menu, or:
sudo nmtui  # NetworkManager TUI
```

### Customizing Appearance
Edit `/home/kiduser/.config/kitty/kitty.conf`:
```conf
background #800080         # Purple background
foreground #ffffff         # White text
font_size 18.0            # Large text
cursor_blink_interval 0    # No blink (less distraction)
```

### Adding Custom Modes
Add Python files to `/home/kiduser/.purple/modes/`

See [dev.md](dev.md) for mode development guide.

## Troubleshooting

### Installation hangs
- Check if target machine meets minimum requirements
- Verify ISO integrity: `md5sum purple-computer.iso`
- Try rebuilding the ISO
- Check BIOS settings (UEFI vs Legacy)

### System boots to command line instead of Purple Computer
```bash
# Check systemd service
systemctl status getty@tty1

# View logs
journalctl -u getty@tty1 -b

# Manually start (for testing)
startx
```

### Kitty won't start
```bash
# Check if X11 is running
echo $DISPLAY

# Check Kitty installation
which kitty

# Try running manually
kitty
```

### Purple REPL crashes
```bash
# Check Python installation
python3 --version
ipython3 --version

# Test REPL manually
cd /home/kiduser/.purple
python3 repl.py
```

### No speech output
```bash
# Check audio devices
aplay -l

# Test Piper TTS
piper --help

# Fallback to espeak
espeak "test"

# Check volume
alsamixer
```

### Screen resolution wrong
```bash
# Via parent menu, or:
xrandr  # List available resolutions
xrandr --output HDMI-1 --mode 1920x1080  # Set resolution
```

## Advanced Customization

### Modify Autoinstall Config
Edit `autoinstall/autoinstall.yaml` before building ISO.

Key sections:
```yaml
identity:       # Change default username/password
packages:       # Add/remove packages
user-data:      # Cloud-init customization
late-commands:  # Post-install scripts
```

### Custom Kernel Parameters
Edit `autoinstall/build-iso.sh`:
```bash
# Add kernel parameters to GRUB config
# e.g., quiet splash nosplash
```

### Include Additional Files
Place files in `autoinstall/files/` and they'll be copied during installation.

### Pre-seed Emoji or Content
Add to `autoinstall/files/ipython/` to include in startup.

## Rebuilding After Changes

After modifying configuration:
```bash
cd autoinstall
rm -f purple-computer.iso  # Remove old ISO
./build-iso.sh              # Rebuild
```

## Network Installation (Advanced)

For installing on multiple machines, you can:
1. Set up a PXE boot server
2. Host the autoinstall.yaml via HTTP
3. Boot machines via network

See Ubuntu's [netboot documentation](https://ubuntu.com/server/docs/install/netboot).

## Automated Testing

Test the ISO in a VM before burning to USB:

```bash
cd purplecomputer
./scripts/test-iso.sh
```

This launches QEMU with the ISO and simulates installation.

## Upgrading Purple Computer

To upgrade an existing installation:
```bash
# Access parent mode (Ctrl+Alt+P)
# Open terminal
cd /home/kiduser/.purple
git pull  # If installed via git
# Or manually copy new files
```

For major upgrades, a fresh install is recommended.

## Backup and Recovery

### Backup Kid Data
Purple Computer doesn't persist kid data by default (ephemeral session). If you've modified it to save files:
```bash
tar czf kiduser-backup.tar.gz /home/kiduser/.purple
```

### Recovery Mode
If Purple Computer won't boot:
1. Boot from USB again
2. Choose "Rescue mode"
3. Mount existing installation
4. Fix configuration

## Security Considerations

### Default Password
The default password is `purplecomputer`. Change it post-install for security:
```bash
sudo passwd kiduser
```

### Network Isolation
Purple Computer has no network by default. Keep it that way unless you specifically need updates.

### Physical Access
Purple Computer assumes physical security. Anyone with physical access can boot from USB and access the system.

## Resources

- [Ubuntu Autoinstall Documentation](https://ubuntu.com/server/docs/install/autoinstall)
- [Cloud-init Documentation](https://cloudinit.readthedocs.io/)
- [Systemd Documentation](https://www.freedesktop.org/software/systemd/man/)

## Getting Help

- Check [dev.md](dev.md) for technical details
- Check [parents.md](parents.md) for usage help
- File issues on GitHub
- Review autoinstall logs: `/var/log/installer/`

---

Happy building! 💜
