# Purple Computer FAI Configuration Structure

Complete reference for the FAI configuration directory layout.

## Overview

The FAI configuration follows the standard FAI directory structure with Purple Computer-specific customizations.

## Directory Tree

```
fai-config/
├── README.md                    # Overview and quick start
├── BUILDING.md                  # Build instructions
├── STRUCTURE.md                 # This file - complete structure reference
├── nfsroot.conf                 # Nfsroot build configuration
│
├── class/                       # Class definition scripts
│   └── 10-base-classes          # Main class assignment script
│
├── disk_config/                 # Disk partitioning layouts
│   ├── LAPTOP                   # LVM layout for laptops (BIOS/UEFI generic)
│   ├── UEFI                     # UEFI-specific boot configuration
│   └── BIOS                     # BIOS/legacy boot configuration
│
├── package_config/              # Package installation lists
│   ├── FAIBASE                  # Essential base system packages
│   ├── PURPLECOMPUTER           # Purple Computer core packages
│   └── MINIMAL_X                # X11 + terminal environment packages
│
├── scripts/                     # Post-install scripts (run in order)
│   ├── PURPLECOMPUTER/
│   │   ├── 10-configure-system  # System configuration (hostname, locale, etc.)
│   │   ├── 20-create-user       # Create default user account
│   │   ├── 40-custom-config     # Custom dotfiles and configurations
│   │   └── 50-finalize          # Bootloader, cleanup, final tasks
│   └── MINIMAL_X/
│       └── 30-configure-x11     # X11, LightDM, Openbox setup
│
├── hooks/                       # FAI hooks for various stages
│   └── instsoft.PURPLECOMPUTER  # Configure APT for local repository
│
├── files/                       # Files to copy to target system
│   └── (currently empty - config done in scripts)
│
└── basefiles/                   # Base system overlay files
    └── (currently empty)
```

## File Descriptions

### Class Definitions (class/)

#### 10-base-classes
- **Type**: Shell script
- **When it runs**: During class assignment (early in FAI)
- **Purpose**: Determines which FAI classes apply to this installation
- **Output**: Prints class names (one per line) to stdout

**Classes defined:**
- `FAIBASE`: Always applied - base FAI functionality
- `DEBIAN`: Distribution type (change to UBUNTU if needed)
- `AMD64`: Architecture
- `BOOKWORM`: Debian release (JAMMY/NOBLE for Ubuntu)
- `PURPLECOMPUTER`: Purple Computer-specific config
- `LAPTOP`: Laptop-optimized setup
- `MINIMAL_X`: Minimal X11 environment
- `UEFI` or `BIOS`: Detected based on firmware
- `DISK_SMALL/MEDIUM/LARGE`: Based on disk size
- `MEM_LOW/MEDIUM/HIGH`: Based on RAM

### Disk Configurations (disk_config/)

#### LAPTOP
- **Type**: FAI disk_config format
- **Applied to**: Systems with LAPTOP class
- **Partition scheme**: GPT with LVM
- **Layout**:
  - `/boot`: 512MB ext4 (for kernel/initrd)
  - LVM PV: Remaining space
  - LVM volumes:
    - `root`: 20GB for `/`
    - `swap`: 4GB swap
    - `home`: 10GB for `/home`
    - `var`: 10GB for `/var`
    - `tmp`: 2GB for `/tmp`
  - Remaining space: Unallocated (for future expansion)

#### UEFI
- **Type**: FAI disk_config format
- **Applied to**: UEFI systems
- **Extends**: LAPTOP config
- **Additional**:
  - `/boot/efi`: 512MB VFAT (ESP - EFI System Partition)
  - `/boot`: 512MB ext4 (separate boot partition)

#### BIOS
- **Type**: FAI disk_config format
- **Applied to**: BIOS/legacy systems
- **Partition scheme**: MSDOS (MBR)
- **Similar to LAPTOP** but uses legacy bootable flag

### Package Lists (package_config/)

Format: FAI package_config format
```
PACKAGES install
package1
package2
...
```

#### FAIBASE
Essential packages for any FAI installation:
- Kernel: `linux-image-amd64`
- Bootloaders: `grub-pc`, `grub-efi-amd64`
- LVM: `lvm2`
- Basic tools: `sudo`, `vim-tiny`, `wget`, `curl`
- Hardware support: `firmware-linux-free`

#### PURPLECOMPUTER
Purple Computer core system:
- System: `systemd`, `dbus`, `udev`
- Filesystems: `e2fsprogs`, `btrfs-progs`, `ntfs-3g`
- Compression: `gzip`, `bzip2`, `xz-utils`, `zip`
- Editors: `vim`, `nano`
- Tools: `htop`, `tmux`, `tree`, `rsync`
- Laptop: `laptop-mode-tools`, `tlp`, `acpi`
- Wireless: `wpasupplicant`, `wireless-tools`
- Bluetooth: `bluez`, `bluez-tools`
- Development: `build-essential`, `git`, `python3`

#### MINIMAL_X
Minimal graphical environment:
- X.org: `xserver-xorg-core`, `xserver-xorg-input-all`
- Display manager: `lightdm`, `lightdm-gtk-greeter`
- Window manager: `openbox`
- Terminals: `alacritty`, `xterm`, `rxvt-unicode`
- Fonts: `fonts-dejavu-core`, `fonts-liberation`, `fonts-noto-*`
- Audio: `alsa-utils`, `pulseaudio`, `pavucontrol`
- Utilities: `feh`, `pcmanfm`, `rofi`, `dmenu`, `ranger`
- Applications: `firefox-esr`, `zathura`

### Installation Scripts (scripts/)

Scripts run in numerical order within each class directory.

#### PURPLECOMPUTER/10-configure-system
- **When**: After package installation
- **Purpose**: Basic system configuration
- **Actions**:
  - Set hostname to "purplecomputer"
  - Configure `/etc/hosts`
  - Set timezone to UTC
  - Generate locale (en_US.UTF-8)
  - Configure keyboard layout (US)
  - Enable systemd services (journald, acpid, tlp)
  - Configure sudo for sudo group

#### PURPLECOMPUTER/20-create-user
- **When**: After system configuration
- **Purpose**: Create default user account
- **Actions**:
  - Create user "purple" with groups: sudo, audio, video, plugdev, netdev, bluetooth
  - Set default password: "purple"
  - Create home directories (Documents, Downloads, etc.)
  - Configure `.bashrc` with colors and aliases
  - Configure `.profile` for PATH
  - Set proper permissions

#### MINIMAL_X/30-configure-x11
- **When**: After user creation (if MINIMAL_X class)
- **Purpose**: Configure graphical environment
- **Actions**:
  - Enable LightDM display manager
  - Configure auto-login for user "purple"
  - Create Openbox configuration (autostart, menu, keybindings)
  - Configure `.xinitrc` for manual X startup
  - Create `.Xresources` for terminal colors
  - Generate purple background image
  - Fix ownership of all config files

#### PURPLECOMPUTER/40-custom-config
- **When**: After X11 configuration
- **Purpose**: Apply custom dotfiles and configurations
- **Actions**:
  - Configure Alacritty terminal (colors, fonts, keybindings)
  - Configure Vim (settings, colors, keybindings)
  - Configure Git (user, aliases)
  - Configure Tmux (keybindings, status bar)
  - Create first-boot welcome script
  - Fix ownership

#### PURPLECOMPUTER/50-finalize
- **When**: Last script to run
- **Purpose**: Finalize installation
- **Actions**:
  - Update initramfs
  - Install GRUB bootloader (UEFI or BIOS)
  - Clean package cache
  - Create installation info file
  - Set up MOTD (message of the day)
  - Create `purple-setup` helper script
  - Set proper permissions on system files

### Hooks (hooks/)

Hooks run at specific FAI stages (named: `stage.CLASSNAME`).

#### instsoft.PURPLECOMPUTER
- **Stage**: `instsoft` (after package installation begins)
- **Purpose**: Configure APT for offline repository
- **Actions**:
  - Create `/etc/apt/sources.list` pointing to `/media/purple-repo`
  - Set APT preferences to prefer local repository
  - Disable recommended/suggested packages
  - Configure dpkg for non-interactive mode

### Configuration Files

#### nfsroot.conf
- **Purpose**: Configure FAI nfsroot creation
- **Settings**:
  - Distribution: Debian Bookworm (or Ubuntu variant)
  - Architecture: amd64
  - Nfsroot packages: Kernel, live-boot, LVM tools, partitioning utilities

## FAI Execution Flow

1. **Boot from ISO/USB**
   - Kernel and initramfs load
   - Live environment boots
   - FAI starts automatically

2. **Class Assignment** (`class/`)
   - `10-base-classes` runs
   - Determines applicable classes
   - Classes stored in `$LOGDIR/FAI_CLASSES`

3. **Disk Partitioning** (`disk_config/`)
   - Reads disk_config for detected classes
   - Creates partitions and LVM volumes
   - Formats filesystems
   - Mounts to `$target` (usually `/target`)

4. **Package Installation** (`package_config/`)
   - Reads package lists for all classes
   - Installs base system with debootstrap
   - Installs packages from lists
   - **instsoft hooks run here**

5. **Configuration Scripts** (`scripts/`)
   - Scripts run in order (10, 20, 30, 40, 50)
   - Executed in chroot of target system
   - `$target` points to new system root
   - `$ROOTCMD` prefix for commands in chroot

6. **Finalization**
   - Bootloader installation
   - Cleanup
   - Unmount filesystems

7. **Reboot**
   - System reboots into installed OS

## Variables Available in Scripts

### FAI Environment Variables
- `$target`: Mount point of target system (e.g., `/target`)
- `$ROOTCMD`: Prefix for running commands in chroot (e.g., `chroot $target`)
- `$classes`: Space-separated list of classes
- `$LOGDIR`: FAI log directory
- `$FAI`: FAI configuration directory

### Usage Examples

```bash
# Create file in target system
cat > $target/etc/hostname <<EOF
purplecomputer
EOF

# Run command in chroot
$ROOTCMD systemctl enable lightdm

# Check if class is defined
if ifclass MINIMAL_X; then
    echo "Installing X11..."
fi
```

## Customization Points

### Add New Package
1. Edit appropriate file in `package_config/`
2. Add package name
3. Rebuild local repository
4. Rebuild ISO

### Add New Script
1. Create script in `scripts/CLASSNAME/`
2. Use numbering (10, 20, 30...) for order
3. Make executable: `chmod +x script`
4. Use `$target` and `$ROOTCMD` for target system operations

### Add New Class
1. Create new class output in `class/` script
2. Create corresponding files:
   - `disk_config/NEWCLASS` (if custom partitioning)
   - `package_config/NEWCLASS` (if custom packages)
   - `scripts/NEWCLASS/` (if custom configuration)

### Modify Disk Layout
1. Edit `disk_config/LAPTOP` (or UEFI/BIOS)
2. Adjust partition sizes, filesystems, mount options
3. Changes take effect on next installation

## Debugging

### Enable Verbose Mode
Boot with "Installation (Verbose)" option from boot menu.

### View Logs During Installation
- Press `Alt+F2` for shell
- Press `Alt+F3` for FAI logs
- Press `Alt+F1` to return to main screen

### Log Files
After installation, logs are in:
- `/var/log/fai/` on target system
- `/tmp/fai/` during installation

### Common Issues

**Script fails:**
- Check `error` variable handling
- Ensure `set -e` is at top
- Use `|| true` for non-critical commands

**Package not found:**
- Verify package in local repository
- Check spelling in package_config
- Rebuild repository if package added

**Permission denied:**
- Use `$ROOTCMD` for commands in target
- Check script is executable
- Verify file paths use `$target`

## References

- FAI Documentation: https://fai-project.org/doc/
- FAI Guide: https://fai-project.org/fai-guide/
- Disk config syntax: https://fai-project.org/doc/man/fai-disk-config.html
- Debian packaging: https://www.debian.org/doc/manuals/debian-reference/

## See Also

- `README.md` - Overview and quick start
- `BUILDING.md` - Build instructions
- `/home/tavi/purplecomputer/build-scripts/` - Build automation scripts
