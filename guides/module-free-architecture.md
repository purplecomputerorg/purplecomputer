# Module-Free Architecture - Technical Deep-Dive

This guide provides technical details on PurpleOS's module-free installer architecture. For general usage, see [MANUAL.md](../MANUAL.md).

---

## Architecture Rationale

### Why Module-Free?

The previous module-based approach used Ubuntu kernel modules loaded at runtime via `insmod`. This failed repeatedly due to:

1. **ABI Mismatches**
   - Kernel compiled with one set of compiler flags
   - Modules downloaded separately, different build environment
   - Result: `unknown symbol` errors, modules refused to load

2. **Dependency Hell**
   - Complex chains: `usb-storage` → `scsi_mod` → `sd_mod`
   - Wrong load order caused failures
   - Missing transitive dependencies

3. **Compression Issues**
   - Ubuntu ships `.ko.zst` (zstandard compressed)
   - Requires decompression before loading
   - initramfs complexity and failure points

4. **VM-Specific Design**
   - Expected `/dev/sr0` (CD-ROM device)
   - Real laptops booting from USB don't have CD-ROM
   - Detection logic worked in QEMU but failed on hardware

### Solution: Built-In Drivers

Compile all essential drivers directly into kernel (`CONFIG_*=y`):

**Benefits:**
- No ABI mismatches (single compile)
- No dependency resolution needed
- No decompression needed
- 98% smaller initramfs (1-2 MB vs 50-100 MB)
- Deterministic boot across hardware

**Trade-off:**
- Larger kernel (~8-12 MB vs ~6 MB)
- Longer initial build (10-30 min)
- But: Kernel cached, subsequent builds fast

---

## Technical Implementation

### Kernel Build Process

**Source:** `build-scripts/00-build-custom-kernel.sh`

1. Download upstream kernel from kernel.org (not Ubuntu packages)
2. Start with `defconfig` (minimal base)
3. Apply `kernel-config-fragment.config` (PurpleOS additions)
4. Compile with `make -j$(nproc) bzImage`

**Why upstream kernel?**
- Ubuntu packages are binary blobs with separate modules
- We need control over CONFIG options
- Source compilation ensures all built-in drivers use same flags

### Initramfs Internals

**Source:** `build-scripts/02-build-initramfs.sh`

**Contents:**
```
initramfs-root/
├── bin/busybox          # Statically-compiled (~1 MB)
├── sbin/                # Symlinks to busybox
├── init                 # Boot script (~200 lines)
└── dev/, proc/, sys/    # Mount points
```

**NO kernel modules, NO libraries.**

**Init script logic:**
```bash
# 1. Mount pseudo-filesystems
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev

# 2. Wait for device enumeration (USB takes ~3 sec)
sleep 3

# 3. Find installer partition
for dev in /dev/sd* /dev/nvme* /dev/vd*; do
    LABEL=$(blkid -s LABEL -o value "$dev")
    if [ "$LABEL" = "PURPLE_INSTALLER" ]; then
        INSTALLER_DEV="$dev"
        break
    fi
done

# 4. Mount and switch root
mount "$INSTALLER_DEV" /mnt
mount -o loop /mnt/boot/installer.ext4 /newroot
exec switch_root /newroot /install.sh
```

### Installation Logic

**Source:** `build-scripts/install.sh`

```bash
# 1. Find target disk (first non-USB)
lsblk -dno NAME,TYPE,TRAN | awk '$2=="disk" && $3!="usb" {print $1; exit}'

# 2. Wipe and partition (GPT)
sgdisk -Z /dev/$TARGET
sgdisk -n 1:0:+512M -t 1:ef00 /dev/$TARGET  # EFI
sgdisk -n 2:0:0 -t 2:8300 /dev/$TARGET      # Root

# 3. Write golden image
zstd -dc /purple-os.img.zst | dd of=/dev/${TARGET}2 bs=4M

# 4. Install GRUB
mount /dev/${TARGET}2 /target
mount /dev/${TARGET}1 /target/boot/efi
grub-install --target=x86_64-efi --efi-directory=/target/boot/efi /dev/$TARGET
```

---

## Kernel Configuration Details

### Complete Driver Set

**USB Controllers (3 generations):**
```makefile
CONFIG_USB=y                    # USB core
CONFIG_USB_XHCI_HCD=y          # USB 3.0+ (2012+ laptops)
CONFIG_USB_XHCI_PCI=y          # PCI binding
CONFIG_USB_EHCI_HCD=y          # USB 2.0 (2002+)
CONFIG_USB_EHCI_PCI=y          # PCI binding
CONFIG_USB_OHCI_HCD=y          # USB 1.1 (fallback)
CONFIG_USB_UHCI_HCD=y          # USB 1.1 Intel/VIA
```

**USB Storage:**
```makefile
CONFIG_USB_STORAGE=y           # Mass storage (flash drives)
CONFIG_USB_UAS=y               # USB Attached SCSI (faster USB 3.0)
```

**SATA Controllers:**
```makefile
CONFIG_SATA_AHCI=y             # Modern AHCI (2007+)
CONFIG_ATA_PIIX=y              # Older Intel PATA/SATA (ThinkPads)
```

**NVMe:**
```makefile
CONFIG_NVME_CORE=y             # NVMe core
CONFIG_BLK_DEV_NVME=y          # NVMe block device
```

**SCSI Subsystem (required even for SATA):**
```makefile
CONFIG_SCSI=y                  # SCSI core
CONFIG_BLK_DEV_SD=y            # SCSI disk (sd_mod)
```

**Filesystems:**
```makefile
CONFIG_EXT4_FS=y               # Installer rootfs, target system
CONFIG_VFAT_FS=y               # USB boot, EFI partitions
CONFIG_FAT_FS=y                # FAT core
CONFIG_NLS_CODEPAGE_437=y      # DOS codepage (for FAT)
CONFIG_NLS_ISO8859_1=y         # Latin-1 (for FAT)
```

**Block Layer:**
```makefile
CONFIG_BLOCK=y                 # Block device support
CONFIG_BLK_DEV_LOOP=y          # Loop devices (mount installer.ext4)
CONFIG_PARTITION_ADVANCED=y    # Partition support
CONFIG_MSDOS_PARTITION=y       # MBR
CONFIG_EFI_PARTITION=y         # GPT
```

### Verification

After kernel build:
```bash
grep "=y" /opt/purple-installer/build/kernel-config-purple | grep -E "(USB|SATA|NVME|EXT4)"
```

Should show all drivers as built-in (no `=m` modules).

---

## Device Detection Logic

### USB Partition Detection

**Method 1: Label-based (preferred)**
```bash
for dev in /dev/sd* /dev/nvme* /dev/vd*; do
    [ -b "$dev" ] || continue
    LABEL=$(blkid -s LABEL -o value "$dev" 2>/dev/null || true)
    if [ "$LABEL" = "PURPLE_INSTALLER" ]; then
        INSTALLER_DEV="$dev"
        break
    fi
done
```

**Why loop all devices?**
- USB stick could be `/dev/sdb1`, `/dev/sdc1`, etc.
- Depends on other USB devices plugged in
- NVMe uses `/dev/nvme0n1p1` naming
- VirtIO uses `/dev/vda1` (QEMU)

**Method 2: Content scan (fallback)**
```bash
for dev in /dev/sd* /dev/nvme* /dev/vd*; do
    [ -b "$dev" ] || continue
    mount -o ro "$dev" /mnt 2>/dev/null || continue
    if [ -f /mnt/boot/installer.ext4 ]; then
        INSTALLER_DEV="$dev"
        umount /mnt
        break
    fi
    umount /mnt 2>/dev/null || true
done
```

**Why fallback?**
- Label may be lost if ISO manually modified
- Some tools strip labels during write
- Provides redundancy

### Target Disk Detection

```bash
lsblk -dno NAME,TYPE,TRAN | awk '$2=="disk" && $3!="usb" {print $1; exit}'
```

**Logic:**
- `TYPE=="disk"` excludes partitions and loops
- `TRAN!="usb"` excludes USB drives
- Takes first match (usually `/dev/sda`)

**Edge cases:**
- Multiple internal disks: Picks first (usually correct)
- USB disk labeled as non-USB: Manual override needed
- NVMe naming: Works (`nvme0n1` returned correctly)

---

## Debugging and Development

### Enable Serial Console

Edit `build-scripts/04-build-iso.sh`:

```bash
# ISOLINUX config (line 84)
APPEND initrd=/boot/initrd.img console=ttyS0,115200n8 console=tty0

# GRUB config (line 94)
linux /boot/vmlinuz console=ttyS0,115200n8 console=tty0
```

**Test with QEMU:**
```bash
qemu-system-x86_64 \
    -drive file=purple-installer.iso,format=raw \
    -boot c -m 2048 \
    -serial stdio  # Serial output to stdout
```

### Initramfs Debug Mode

Edit `build-scripts/02-build-initramfs.sh`, add to init script:

```bash
# After line 82 (set -e)
set -x  # Enable command tracing

# Before error exit (line 150)
echo "Debug shell - type 'exit' to continue"
/bin/busybox sh  # Drop to shell for inspection
```

### Kernel Module Verification

```bash
# Check if driver is built-in
grep CONFIG_USB_XHCI_HCD= /opt/purple-installer/build/kernel-config-purple
# Should show: CONFIG_USB_XHCI_HCD=y (not =m)

# Verify in running kernel (boot live USB)
zcat /proc/config.gz | grep CONFIG_USB_XHCI_HCD
```

### QEMU Testing

**USB boot simulation:**
```bash
qemu-system-x86_64 \
    -drive file=purple-installer.iso,format=raw,if=none,id=usb-drive \
    -device nec-usb-xhci,id=xhci \
    -device usb-storage,drive=usb-drive,bus=xhci.0 \
    -m 2048 -enable-kvm
```

**NVMe testing:**
```bash
qemu-system-x86_64 \
    -drive file=purple-installer.iso,format=raw,if=none,id=installer \
    -drive file=test-disk.img,format=raw,if=none,id=nvme-disk \
    -device nvme,drive=nvme-disk,serial=1234 \
    -device usb-storage,drive=installer \
    -m 2048 -enable-kvm
```

### Common Development Tasks

**Add new driver:**
1. Edit `kernel-config-fragment.config`
2. Add `CONFIG_NEW_DRIVER=y` with comment
3. Rebuild: `./build-in-docker.sh 0 && ./build-in-docker.sh 4`

**Test initramfs changes:**
1. Edit `02-build-initramfs.sh`
2. Rebuild: `./build-in-docker.sh 2 && ./build-in-docker.sh 4`
3. Test in QEMU

**Modify golden image:**
1. Edit `01-build-golden-image.sh`
2. Rebuild: `./build-in-docker.sh 1`
3. Complete build: `./build-in-docker.sh 3 && ./build-in-docker.sh 4`

### Performance Profiling

**Measure boot time:**
```bash
# Add to init script
echo "Boot start: $(date +%s)" > /boot-time.log

# At end of install.sh
echo "Install complete: $(date +%s)" >> /target/boot-time.log
```

**Identify bottlenecks:**
- Kernel load: ~1-2 sec
- Initramfs unpack: ~0.5 sec
- Device enumeration: ~3 sec (USB settle time)
- Partition detection: ~0.5 sec
- Disk write: ~5-15 min (depends on disk speed)
- GRUB install: ~30 sec

**Optimization opportunities:**
- Reduce USB wait time (currently 3 sec, may be overkill)
- Parallel disk write + GRUB preparation
- Use `dd bs=4M` for faster write (already implemented)

---

## Hardware-Specific Notes

### ThinkPad T/X Series

**Quirks:**
- Older models (pre-2012) use `ata_piix` instead of `ahci`
- Config already includes both
- BIOS may need "AHCI mode" enabled

### MacBook Air/Pro

**Quirks:**
- 2016+ models with T2 chip: Not supported (requires proprietary drivers)
- 2013-2015 Intel models: Work with standard NVMe
- May need `nomodeset` kernel parameter for graphics

### Dell/HP Laptops

**Generally compatible:**
- Standard AHCI controllers
- Intel WiFi (requires firmware, not included in installer kernel)
- UEFI boot works reliably

---

## Future Enhancements

### Short-Term

1. **Add WiFi firmware**
   - Include common firmware in installer.ext4
   - Copy to /lib/firmware during install
   - Enables immediate network connectivity

2. **Progress indicator**
   - Show disk write progress (currently silent for 10-15 min)
   - Use `pv` or `dd status=progress` with output parsing

3. **Error recovery**
   - Automatic retry on disk write failure
   - Checksum verification of written image

### Long-Term

1. **Secure Boot support**
   - Sign kernel with MOK (Machine Owner Key)
   - Requires shim bootloader

2. **Encryption support**
   - Add dm-crypt/LUKS to kernel
   - Prompt for passphrase during install

3. **Multi-disk support**
   - Detect multiple disks, let user choose
   - TUI menu in initramfs (requires dialog/whiptail)

---

## Reference Implementation

### Minimal Working Example

**Smallest possible installer kernel config:**
```makefile
# Absolute minimum for USB boot + ext4 write
CONFIG_USB_XHCI_HCD=y
CONFIG_USB_STORAGE=y
CONFIG_SCSI=y
CONFIG_BLK_DEV_SD=y
CONFIG_EXT4_FS=y
CONFIG_VFAT_FS=y  # For EFI
```

**Smallest possible initramfs:**
```bash
# Just BusyBox + init script (no modules)
# Size: ~1 MB compressed
```

**This is the theoretical minimum.** PurpleOS adds SATA, NVMe, and compatibility drivers for broader hardware support.

---

**Document Version:** 1.0
**Last Updated:** 2025-12-07
**Kernel Version:** 6.8.12
**Ubuntu Base:** 24.04.3 LTS (Noble Numbat)
