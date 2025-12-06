# Purple Computer Installation Guide

Complete guide for installing Purple Computer from the FAI-based installer.

## What You Get

Purple Computer provides:
- Minimal Debian/Ubuntu base system
- Lightweight X11 environment with Openbox
- Modern terminal (Alacritty) with vim/tmux
- Complete offline installation capability
- LVM disk layout for flexibility
- Auto-login to graphical environment

## Before You Begin

### Hardware Requirements

**Minimum:**
- 64-bit x86 CPU (Intel/AMD)
- 2GB RAM
- 20GB disk space
- BIOS or UEFI firmware

**Recommended:**
- 4GB+ RAM
- 60GB+ disk space
- WiFi/Ethernet for post-install updates

**Tested on:**
- 2010-2015 era laptops
- ThinkPad T series
- Dell Latitude/XPS
- HP EliteBook
- Modern desktops

### What You Need

1. Purple Computer installer ISO or USB
2. Target computer for installation
3. **BACKUP YOUR DATA** - installation will erase entire disk!

## Installation Methods

### Method 1: USB Drive (Recommended)

**Advantages:**
- Faster than CD/DVD
- Reusable
- Works on machines without optical drive

**See**: `/opt/purple-installer/output/WRITE_TO_USB.txt` for detailed USB writing instructions.

### Method 2: CD/DVD

**Advantages:**
- Write-protected (cannot be modified)
- Good for archival purposes

Burn ISO to DVD using your OS's disc burning utility.

### Method 3: Virtual Machine (Testing)

Good for testing before installing on real hardware.

**QEMU:**
```bash
qemu-system-x86_64 -cdrom purple-computer-installer.iso -boot d -m 2048
```

**VirtualBox:**
1. Create new VM (Linux, Debian 64-bit)
2. Allocate 2GB+ RAM
3. Create 20GB+ virtual disk
4. Attach ISO to optical drive
5. Boot VM

## Installation Process

### Step 1: Boot from Installer

1. **Insert USB/CD**
   - Insert installer media into target computer

2. **Access Boot Menu**
   - Restart computer
   - Press boot menu key during startup:
     - Dell: F12
     - HP: F9 or Esc
     - Lenovo: F12 or F1
     - ASUS: F8 or Esc
     - Generic: F12, F8, Esc, or Del

3. **Select Boot Device**
   - Choose USB drive or CD/DVD from menu
   - System should boot to Purple Computer boot screen

### Step 2: Installation Menu

You'll see a boot menu with these options:

**Purple Computer - Automated Installation** (default)
- Fully automated installation
- Quiet mode (minimal output)
- Reboots automatically when done
- **This is what most users want**

**Purple Computer - Installation (Verbose)**
- Same as above but shows detailed progress
- Useful for troubleshooting
- Shows all FAI actions

**Purple Computer - Rescue Shell**
- Boots to a shell without installing
- For recovery or manual operations
- Advanced users only

**Default behavior:** After 5 seconds, automated installation starts.

### Step 3: Automated Installation

Once installation starts, the system will automatically:

1. **Detect Hardware** (~30 seconds)
   - Identify CPU, RAM, disk, firmware type
   - Determine UEFI vs BIOS
   - Assign FAI classes

2. **Partition Disk** (~1-2 minutes)
   - **WARNING: This erases the entire disk!**
   - Creates GPT or MBR partition table
   - Sets up boot partition
   - Creates LVM physical volume
   - Creates logical volumes (root, home, var, tmp, swap)
   - Formats filesystems

3. **Install Base System** (~3-5 minutes)
   - Installs minimal Debian/Ubuntu base
   - Configures APT for local repository
   - Sets up essential system tools

4. **Install Packages** (~5-10 minutes)
   - Installs all packages from embedded repository
   - Includes kernel, drivers, X11, applications
   - Progress shown in verbose mode

5. **Configure System** (~2-3 minutes)
   - Sets hostname, timezone, locale
   - Creates user account
   - Configures X11 and Openbox
   - Applies dotfiles and configurations
   - Sets up auto-login

6. **Install Bootloader** (~1 minute)
   - Installs GRUB (UEFI or BIOS)
   - Configures boot parameters
   - Updates initramfs

7. **Finalize** (~1 minute)
   - Cleans package cache
   - Sets permissions
   - Unmounts filesystems

8. **Reboot**
   - System automatically reboots
   - Remove installation media when prompted

**Total time:** 10-20 minutes (depending on hardware)

### Step 4: First Boot

After reboot:

1. **GRUB Menu**
   - Default: Purple Computer
   - Timeout: 5 seconds

2. **System Boots**
   - Systemd initialization
   - Services start (takes ~15-30 seconds)

3. **LightDM Auto-Login**
   - Automatically logs in as user "purple"
   - Starts Openbox window manager

4. **Welcome Screen**
   - Terminal opens with welcome message
   - Shows quick tips and default credentials
   - Press Enter to dismiss

5. **Desktop Environment**
   - Minimal Openbox desktop
   - Purple/dark wallpaper
   - Terminal ready for use

## Post-Installation Setup

### Immediate Actions

#### 1. Change Default Password

**CRITICAL SECURITY STEP!**

```bash
passwd
```

Current password: `purple`
Enter new password twice.

#### 2. Connect to Network

**WiFi:**
```bash
sudo nmtui
# Or use the helper:
sudo purple-setup
# Select option 2
```

**Ethernet:**
Should work automatically with DHCP.

#### 3. Set Timezone

```bash
sudo purple-setup
# Select option 3

# Or manually:
sudo dpkg-reconfigure tzdata
```

#### 4. Update System (if online)

```bash
# Enable online repositories first
sudo vim /etc/apt/sources.list
# Uncomment the online repository lines

sudo apt update
sudo apt upgrade
```

### Optional Configuration

#### Configure Keyboard Layout

```bash
sudo dpkg-reconfigure keyboard-configuration
sudo systemctl restart keyboard-setup
```

#### Add More Users

```bash
sudo useradd -m -s /bin/bash -G sudo,audio,video newuser
sudo passwd newuser
```

#### Install Additional Software

```bash
sudo apt update
sudo apt install package-name
```

#### Disable Auto-Login

```bash
sudo rm /etc/lightdm/lightdm.conf.d/50-purple-autologin.conf
sudo systemctl restart lightdm
```

## Using Purple Computer

### Keyboard Shortcuts

**Window Manager (Openbox):**
- `Alt+Enter`: Open terminal
- `Alt+Space`: Application launcher (Rofi)
- `Alt+Q`: Close window
- Right-click desktop: Menu

**Terminal (Alacritty):**
- `Ctrl+Shift+C`: Copy
- `Ctrl+Shift+V`: Paste
- `Ctrl++`: Increase font size
- `Ctrl+-`: Decrease font size
- `Ctrl+0`: Reset font size

**Tmux (if running):**
- `Ctrl+A`: Prefix key (changed from default Ctrl+B)
- `Prefix |`: Split vertically
- `Prefix -`: Split horizontally
- `Prefix arrow`: Switch panes

### Applications

**Terminal:** `alacritty` (or `xterm`)
**File Manager:** `pcmanfm` or `ranger` (CLI)
**Text Editor:** `vim` or `nano`
**Browser:** `firefox-esr`
**PDF Viewer:** `zathura`
**System Monitor:** `htop` or `btop`

### Configuration Files

All in `/home/purple/`:
- `.bashrc`: Bash shell configuration
- `.vimrc`: Vim editor configuration
- `.tmux.conf`: Tmux configuration
- `.config/alacritty/alacritty.yml`: Terminal config
- `.config/openbox/`: Window manager config
- `.Xresources`: X11 color/font settings

## Disk Layout

### Partitions

**UEFI Systems:**
```
/dev/sda1: 512MB  /boot/efi  (ESP)
/dev/sda2: 512MB  /boot      (kernel)
/dev/sda3: Rest   LVM PV
```

**BIOS Systems:**
```
/dev/sda1: 512MB  /boot      (bootable)
/dev/sda2: Rest   LVM PV
```

### LVM Layout

```
Volume Group: vg_system

Logical Volumes:
  root: 20GB   mounted at /
  home: 10GB   mounted at /home
  var:  10GB   mounted at /var
  tmp:  2GB    mounted at /tmp
  swap: 4GB    swap space

Unallocated: Remaining space (for future use)
```

### Managing LVM

**View layout:**
```bash
sudo lvs
sudo vgs
sudo pvs
```

**Extend home volume:**
```bash
sudo lvextend -L +10G /dev/vg_system/home
sudo resize2fs /dev/vg_system/home
```

**Create new volume:**
```bash
sudo lvcreate -L 20G -n data vg_system
sudo mkfs.ext4 /dev/vg_system/data
sudo mkdir /data
sudo mount /dev/vg_system/data /data
```

## Troubleshooting

### Installation Issues

**Installation hangs or fails:**
1. Reboot and select "Installation (Verbose)"
2. Press Alt+F2 for shell access
3. Check `/tmp/fai/` for logs
4. Look for error messages

**Cannot boot after installation:**
1. Boot from installer media
2. Select "Rescue Shell"
3. Mount system:
   ```bash
   vgchange -ay
   mount /dev/vg_system/root /target
   mount /dev/sda1 /target/boot  # or /boot/efi for UEFI
   ```
4. Chroot and reinstall GRUB:
   ```bash
   chroot /target
   grub-install /dev/sda  # or with --efi for UEFI
   update-grub
   ```

**Packages not found:**
- Repository may not be mounted
- Check ISO/USB integrity
- Verify checksums match

### Boot Issues

**GRUB rescue prompt:**
- Bootloader installation failed
- Re-install using rescue mode (see above)

**Kernel panic:**
- Hardware incompatibility
- Try different kernel parameters
- Check hardware support

**Black screen after boot:**
- X11 may have failed to start
- Press Ctrl+Alt+F2 for console
- Check logs: `journalctl -xb`

### Display Issues

**Wrong resolution:**
```bash
xrandr
xrandr --output OUTPUT_NAME --mode 1920x1080
```

**No display output:**
- Graphics driver issue
- Try `nomodeset` kernel parameter
- May need proprietary drivers

### Network Issues

**WiFi not working:**
```bash
# Check if device is detected
ip link

# May need firmware
lspci | grep -i network
# Search for firmware-* package

sudo apt install firmware-iwlwifi  # Example for Intel
sudo reboot
```

**No network at all:**
- Check if NetworkManager is running
- Try manual configuration with `ip` commands

### Getting Help

**System logs:**
```bash
journalctl -xb          # Boot logs
journalctl -u lightdm   # Display manager
journalctl -f           # Follow logs
```

**Hardware info:**
```bash
lscpu                   # CPU info
lsblk                   # Block devices
lspci                   # PCI devices
lsusb                   # USB devices
free -h                 # Memory
df -h                   # Disk usage
```

## Advanced Topics

### Manual Installation

If you need manual control:

1. Boot to Rescue Shell
2. Partition disk manually
3. Create filesystems
4. Mount to `/target`
5. Run FAI manually:
   ```bash
   fai -v -N install
   ```

### Customizing Installation

To customize before installing:
1. Boot to Rescue Shell
2. Mount CD: `mount /dev/sr0 /mnt`
3. Edit configs in `/mnt/...`
4. Unmount and run installation

### Offline Operation

Purple Computer works fully offline:
- All packages embedded in ISO
- No internet required for installation
- Local repository at `/media/purple-repo`

To use local repository after installation:
```bash
# Repository already configured in /etc/apt/sources.list
# Point to the ISO/USB if still mounted
```

### Backup and Recovery

**Backup home directory:**
```bash
tar czf /external/backup-home.tar.gz /home/purple
```

**Backup system config:**
```bash
tar czf /external/backup-etc.tar.gz /etc
```

**Clone LVM volume:**
```bash
lvcreate -L 20G -s -n root_backup /dev/vg_system/root
```

## FAQ

**Q: Can I dual-boot with Windows?**
A: Not with the automated installer - it uses the entire disk. For dual-boot, use manual installation and partition beforehand.

**Q: How do I change the desktop environment?**
A: Install another DE (e.g., `sudo apt install xfce4`) and select it from LightDM login screen.

**Q: Is this suitable for production servers?**
A: Purple Computer is designed for desktop/laptop use. For servers, consider a minimal install without X11.

**Q: Can I reinstall without losing data?**
A: No - reinstallation erases the disk. Backup `/home` first.

**Q: How do I update packages offline?**
A: You'll need to create an updated repository and rebuild the ISO, or temporarily connect online.

**Q: What's the difference from standard Debian/Ubuntu?**
A: Purple Computer is pre-configured with a minimal X11 environment, optimized for terminal use, with sensible defaults for older laptops.

## Credits

Purple Computer uses:
- FAI (Fully Automatic Installation)
- Debian/Ubuntu base
- Openbox window manager
- Alacritty terminal
- Various open source software

## License

Purple Computer configuration and scripts are open source.
All included software retains its original licenses.
