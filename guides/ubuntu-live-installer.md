# Ubuntu ISO Remaster - Technical Details

This document describes the technical implementation of the initramfs injection approach.

For the high-level architecture, see [architecture-overview.md](architecture-overview.md).

---

## Overview

We take the official Ubuntu Server 24.04 ISO and make one modification: inject a hook script into the initramfs. This hook runs early in boot, before casper mounts the squashfs.

**What we modify:** initramfs only
**What we don't touch:** kernel, squashfs, casper, GRUB config, boot signatures

---

## Build Process

```
1. Download Ubuntu Server 24.04 ISO
2. Extract ISO contents
3. Extract initramfs (unmkinitramfs)
4. Add hook script to /scripts/init-top/
5. Repack initramfs
6. Add payload files (/purple/install.sh, /purple/purple-os.img.zst)
7. Rebuild ISO with xorriso
```

---

## The Hook Script

Location: `/scripts/init-top/01_purple_installer`

```sh
#!/bin/sh
# Runs early in initramfs, before casper

# Check each block device for our payload
for dev in /dev/sd* /dev/nvme* /dev/vd*; do
    mount -o ro "$dev" /tmp/check
    if [ -x /tmp/check/purple/install.sh ]; then
        # Found our payload - run installer
        /tmp/check/purple/install.sh
        reboot -f
    fi
    umount /tmp/check
done

# No payload found - continue normal boot
exit 0
```

This runs after udev (so devices exist) but before casper (so squashfs isn't mounted yet).

---

## Initramfs Structure

Ubuntu's initramfs is a concatenation of multiple cpio archives:

```
initrd
├── early/     (CPU microcode)
├── early2/    (additional early modules)
├── early3/    (more early modules)
└── main/      (the actual initramfs)
    ├── init
    ├── scripts/
    │   ├── init-top/        ← We add our hook here
    │   │   ├── ORDER
    │   │   ├── udev
    │   │   └── 01_purple_installer  ← Our script
    │   ├── init-premount/
    │   ├── casper           ← We never reach this
    │   └── ...
    └── ...
```

---

## Repacking Initramfs

```bash
# Extract
unmkinitramfs /path/to/initrd /work/initrd-work

# Add hook
cp 01_purple_installer /work/initrd-work/main/scripts/init-top/

# Update ORDER file
sed -i '/udev/a /scripts/init-top/01_purple_installer "$@"' \
    /work/initrd-work/main/scripts/init-top/ORDER

# Repack (maintain concatenated structure)
for dir in early early2 early3; do
    (cd /work/initrd-work/$dir && find . | cpio -o -H newc)
done > new-initrd

(cd /work/initrd-work/main && find . | cpio -o -H newc | zstd) >> new-initrd
```

---

## ISO Structure

```
purple-installer.iso
├── boot/
│   └── grub/           (untouched)
├── casper/
│   ├── vmlinuz         (untouched)
│   ├── initrd          (MODIFIED - has our hook)
│   └── *.squashfs      (untouched - never mounted)
├── EFI/                (untouched)
├── isolinux/           (untouched)
└── purple/             (NEW - our payload)
    ├── install.sh
    └── purple-os.img.zst
```

---

## Why This Works

1. **Secure Boot intact** - We don't modify signed components (shim, GRUB, kernel)
2. **Squashfs irrelevant** - Our code runs before casper mounts it
3. **Layered squashfs irrelevant** - We don't care about squashfs structure
4. **Clean fallback** - If payload missing, normal Ubuntu boot continues
5. **Supported mechanism** - initramfs-tools hooks are a documented feature

---

## Build Scripts

| Script | Purpose |
|--------|---------|
| `00-build-golden-image.sh` | Build the installed system with debootstrap |
| `01-remaster-iso.sh` | Download ISO, inject hook, add payload, rebuild |
| `build-all.sh` | Run both steps |
| `build-in-docker.sh` | Run build in Docker container |
| `install.sh` | The actual installer (runs in initramfs) |

---

## Troubleshooting

**Hook doesn't run**
- Check ORDER file includes our script
- Check script is executable
- Boot with `break=init-top` to debug

**Can't find payload**
- Device enumeration happens after udev
- Check script waits for devices to settle
- Try adding longer sleep

**Installer fails**
- Hook drops to shell on failure
- Check install.sh has all needed tools available in initramfs

---

## Security

- Shim: Microsoft-signed (unchanged)
- GRUB: Canonical-signed (unchanged)
- Kernel: Canonical-signed (unchanged)
- Initramfs: Modified but not signed (Secure Boot still works because kernel verifies it)

The initramfs is embedded in the ISO and loaded by the signed kernel. Secure Boot validates the kernel signature, and the kernel trusts its embedded initramfs.
