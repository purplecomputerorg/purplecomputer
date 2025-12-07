# FAI Configuration Reference

Quick reference for Purple Computer FAI configuration structure.

## Directory Layout

```
fai-config/
├── class/10-base-classes          # Hardware detection & class assignment
├── disk_config/
│   ├── LAPTOP                     # Base LVM layout
│   ├── UEFI                       # UEFI-specific ESP partition
│   └── BIOS                       # BIOS/legacy MBR layout
├── package_config/
│   ├── FAIBASE                    # Essential: kernel, bootloader, LVM
│   ├── PURPLECOMPUTER             # Core: system tools, editors, laptop tools
│   └── MINIMAL_X                  # GUI: X11, lightdm, openbox, alacritty
├── scripts/
│   ├── PURPLECOMPUTER/
│   │   ├── 10-configure-system    # Hostname, locale, timezone, sudo
│   │   ├── 20-create-user         # Create 'purple' user + dotfiles
│   │   ├── 40-custom-config       # Alacritty, vim, git, tmux configs
│   │   └── 50-finalize            # Bootloader, cleanup, helpers
│   └── MINIMAL_X/
│       └── 30-configure-x11       # LightDM, Openbox, auto-login
├── hooks/
│   └── instsoft.PURPLECOMPUTER    # APT offline repository config
└── nfsroot.conf                    # Nfsroot build settings
```

## Classes

**Assigned by `class/10-base-classes`:**
- `FAIBASE` - Always applied
- `DEBIAN` or `UBUNTU` - Distribution type
- `AMD64` - Architecture
- `BOOKWORM`, `JAMMY`, etc. - Release name
- `PURPLECOMPUTER` - Purple Computer config
- `LAPTOP` - Laptop-specific settings
- `MINIMAL_X` - Install X11 environment
- `UEFI` or `BIOS` - Auto-detected firmware type
- `DISK_SMALL/MEDIUM/LARGE` - Based on disk size
- `MEM_LOW/MEDIUM/HIGH` - Based on RAM

## Disk Layouts

**LAPTOP class (LVM):**
```
/boot:  512MB ext4
LVM PV: Rest of disk
  ├─ root:  20GB /
  ├─ swap:   4GB swap
  ├─ home:  10GB /home
  ├─ var:   10GB /var
  ├─ tmp:    2GB /tmp
  └─ (unallocated for expansion)
```

**UEFI adds:**
```
/boot/efi: 512MB vfat (ESP)
/boot:     512MB ext4
LVM PV:    Rest
```

**BIOS uses:**
```
/boot: 512MB ext4 (bootable flag)
LVM PV: Rest
```

## FAI Variables

Available in scripts:

- `$target` - Target system mount point (e.g., `/target`)
- `$ROOTCMD` - Run command in chroot (e.g., `chroot $target`)
- `$classes` - Space-separated class list
- `$LOGDIR` - FAI log directory
- `$FAI` - FAI config directory

**Examples:**
```bash
# Write to target system
echo "content" > $target/etc/file

# Run command in chroot
$ROOTCMD systemctl enable service

# Conditional on class
if ifclass MINIMAL_X; then
    echo "X11 detected"
fi
```

## Execution Order

1. **Boot** - Kernel + initramfs from ISO
2. **Class assignment** - `class/10-base-classes` runs
3. **Partitioning** - `disk_config/` for assigned classes
4. **debootstrap** - Install base system
5. **Package install** - From `package_config/`
   - `hooks/instsoft.*` run here
6. **Scripts** - `scripts/CLASSNAME/` in numerical order
7. **Finalize** - Bootloader, cleanup
8. **Reboot**

## Script Template

```bash
#!/bin/bash
# Description of what this script does
# Runs in FAI chroot environment

set -e
error=0 ; trap 'error=$(($?>$error?$?:$error))' ERR

echo "Doing something..."

# Write to target system
cat > $target/etc/config <<'EOF'
config content
EOF

# Run command in chroot
$ROOTCMD systemctl enable service

# Fix ownership
$ROOTCMD chown user:user /path/to/file

echo "Done."
exit $error
```

## Common Tasks

**Add package:**
1. Edit `fai-config/package_config/PURPLECOMPUTER`
2. Add package name
3. Rebuild: `sudo ./01-create-local-repo.sh`

**Change disk layout:**
1. Edit `fai-config/disk_config/LAPTOP`
2. Modify partition/LVM sizes
3. Next install uses new layout

**Add script:**
1. Create `fai-config/scripts/PURPLECOMPUTER/NN-name`
2. Make executable: `chmod +x`
3. Use `$target` and `$ROOTCMD`

**Debug install:**
- Boot menu → "Installation (Verbose)"
- Press Alt+F2 for shell during install
- Check `/tmp/fai/` for logs
- View classes: `cat /tmp/fai/FAI_CLASSES`

## Repository Structure

Created by `01-create-local-repo.sh`:

```
/opt/purple-installer/local-repo/mirror/
├── dists/bookworm/
│   ├── Release                         # Metadata with checksums
│   ├── main/binary-amd64/
│   │   ├── Packages                    # Package index
│   │   ├── Packages.gz                 # Compressed
│   │   └── Packages.xz
│   ├── contrib/binary-amd64/...
│   └── non-free/binary-amd64/...
└── pool/
    ├── main/a/alacritty/alacritty_*.deb
    ├── main/v/vim/vim_*.deb
    └── ...
```

APT configuration:
```
deb [trusted=yes] file:///media/purple-repo bookworm main contrib non-free
```

## Files Reference

| File | Purpose |
|------|---------|
| `class/10-base-classes` | Detect hardware, assign classes |
| `disk_config/LAPTOP` | LVM partition layout |
| `package_config/FAIBASE` | Essential system packages |
| `package_config/PURPLECOMPUTER` | Core packages |
| `package_config/MINIMAL_X` | X11 packages |
| `scripts/*/10-configure-system` | Hostname, locale, services |
| `scripts/*/20-create-user` | User creation, dotfiles |
| `scripts/*/30-configure-x11` | X11, auto-login |
| `scripts/*/40-custom-config` | App configs |
| `scripts/*/50-finalize` | Bootloader, cleanup |
| `hooks/instsoft.PURPLECOMPUTER` | APT offline config |
| `nfsroot.conf` | Nfsroot build settings |

## See Also

- [MANUAL.md](../MANUAL.md) - Complete build & customization guide
- [offline_apt_guide.md](offline_apt_guide.md) - How offline repository works
- FAI docs: https://fai-project.org/doc/
