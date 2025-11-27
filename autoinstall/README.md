# Purple Computer Autoinstall

Automated Ubuntu Server installation with Purple Computer pre-configured.

## Architecture

**Ubuntu Server 24.04 LTS + minimal Xorg (no desktop) + kitty fullscreen**

No GUI, no window manager, no desktop environment. Just a fullscreen terminal that boots directly into Purple Computer.

---

## Quick Start

### Build the ISO

```bash
# From project root
make build-iso

# Or directly
./autoinstall/build-iso.sh
```

This creates `purple-computer.iso` (~2.5GB) - a bootable Ubuntu Server ISO with Purple Computer embedded.

**Requirements:**
- ~6GB free disk space (during build; ~5GB after cleanup)
- Internet connection (downloads Ubuntu Server ISO)
- The script will check for required tools and show install commands for your distro

**Build time:** 5-10 minutes (first time), 2-3 minutes (subsequent builds with cached ISO)

---

## VM Testing with Live Code Editing

The ISO is configured to support **virtio-fs shared folders** for VM development. This lets you edit code on your host machine and test instantly in the VM.

### Setup (QEMU/KVM)

**1. Build the ISO**
```bash
make build-iso
```

**2. Create a disk image**
```bash
qemu-img create -f qcow2 purple-test.qcow2 20G
```

**3. Boot the VM with shared folder**
```bash
qemu-system-x86_64 \
  -cdrom purple-computer.iso \
  -drive file=purple-test.qcow2,format=qcow2 \
  -m 4096 \
  -smp 2 \
  -boot d \
  -enable-kvm \
  -object memory-backend-file,id=mem,size=4G,mem-path=/dev/shm,share=on \
  -numa node,memdev=mem \
  -chardev socket,id=char0,path=/tmp/purple-vm.sock \
  -device vhost-user-fs-pci,queue-size=1024,chardev=char0,tag=purple \
  -fsdev local,security_model=passthrough,id=fsdev0,path=/path/to/purplecomputer \
  -device virtio-9p-pci,id=fsdev0,fsdev=fsdev0,mount_tag=purple
```

**Note:** The simpler approach is to use virtio-9p (last two lines). The ISO's autoinstall config will automatically mount it at `/mnt/purple`.

**Simpler command (virtio-9p only):**
```bash
qemu-system-x86_64 \
  -cdrom purple-computer.iso \
  -drive file=purple-test.qcow2,format=qcow2 \
  -m 4096 \
  -smp 2 \
  -boot d \
  -enable-kvm \
  -fsdev local,security_model=passthrough,id=fsdev0,path=$(pwd) \
  -device virtio-9p-pci,id=fs0,fsdev=fsdev0,mount_tag=purple
```

Replace `$(pwd)` with the path to your purplecomputer repository.

**4. Installation runs automatically**
- Wait 10-15 minutes for installation
- VM will reboot when done
- After reboot, change boot to disk (remove `-boot d` flag)

**5. Testing with live code**

After installation, boot the VM normally:
```bash
qemu-system-x86_64 \
  -drive file=purple-test.qcow2,format=qcow2 \
  -m 4096 \
  -smp 2 \
  -enable-kvm \
  -fsdev local,security_model=passthrough,id=fsdev0,path=$(pwd) \
  -device virtio-9p-pci,id=fs0,fsdev=fsdev0,mount_tag=purple
```

Inside the VM, your repo is available at `/mnt/purple`:
```bash
ls /mnt/purple  # See your host files
```

To test code changes:
```bash
# On host: edit purple_repl/repl.py
# In VM:
cp /mnt/purple/purple_repl/* ~/.purple/
# Restart Purple Computer to see changes
```

### Setup (UTM - macOS)

**1. Build the ISO**
```bash
make build-iso
```

**2. Create new VM in UTM**
- System: Linux
- Architecture: x86_64
- Boot ISO: purple-computer.iso
- Memory: 4096 MB
- CPU cores: 2
- Disk: 20 GB

**3. Add shared directory**
- VM Settings → Sharing
- Add Directory: `/path/to/purplecomputer`
- Tag: `purple`

**4. Install**
- Start VM
- Installation runs automatically (10-15 minutes)
- VM reboots when done

**5. Mount shared folder**

After installation, the shared folder should be auto-mounted at `/mnt/purple`. If not:
```bash
sudo mount -t virtiofs purple /mnt/purple
```

### Setup (VirtualBox)

**1. Build the ISO**
```bash
make build-iso
```

**2. Create new VM**
- Type: Linux, Version: Ubuntu (64-bit)
- Memory: 4096 MB
- Create virtual hard disk: 20 GB, VDI
- Attach purple-computer.iso to optical drive

**3. Add shared folder**
- VM Settings → Shared Folders
- Add: Name=`purple`, Path=`/path/to/purplecomputer`, Auto-mount=✅

**4. Install**
- Start VM
- Installation runs automatically
- VM reboots when done

**5. Install Guest Additions (for shared folders)**
```bash
sudo apt install virtualbox-guest-utils virtualbox-guest-dkms
sudo usermod -aG vboxsf purple
sudo reboot
```

After reboot, shared folder is at `/media/sf_purple` or `/mnt/purple`.

---

## Development Workflow

**1. Edit code on host**
```bash
cd /path/to/purplecomputer
vim purple_repl/repl.py
```

**2. Sync to VM**
```bash
# In VM
cp /mnt/purple/purple_repl/* ~/.purple/
```

**3. Test**
```bash
# Restart Purple Computer (Ctrl+C to exit, then relaunch)
~/.purple/repl.py
```

**Pro tip:** Create a sync script in the VM:
```bash
#!/bin/bash
# ~/sync-purple.sh
echo "Syncing from /mnt/purple..."
cp -r /mnt/purple/purple_repl/* ~/.purple/
echo "✓ Synced! Restart Purple Computer to test."
```

---

## Hardware Installation

### Write ISO to USB

**macOS/Windows:**
1. Download [balenaEtcher](https://www.balena.io/etcher/)
2. Select purple-computer.iso
3. Select USB drive
4. Flash!

**Linux:**
```bash
# Find USB device
lsblk

# Write ISO (replace /dev/sdX with your USB device)
sudo dd if=purple-computer.iso of=/dev/sdX bs=4M status=progress oflag=sync

# Eject
sudo eject /dev/sdX
```

### Boot from USB

1. Insert USB into target computer
2. Power on, press boot menu key (usually F12, F2, or ESC)
3. Select USB drive
4. Installation runs automatically (10-15 minutes)
5. Remove USB when prompted
6. System reboots into Purple Computer

---

## Configuration Files

- **autoinstall.yaml** - Ubuntu Server autoinstall config
- **files/xinit/xinitrc** - X11 startup (launches kitty fullscreen)
- **files/kitty/kitty.conf** - Kitty terminal configuration
- **files/systemd/** - Systemd service for auto-login
- **build-iso.sh** - ISO builder script

---

## Troubleshooting

### ISO build fails

**Missing dependencies:**
```bash
sudo apt install xorriso curl wget rsync
```

**Permission errors:**
```bash
# Don't run as root
./autoinstall/build-iso.sh  # Run as normal user
```

**Disk space:**
```bash
df -h  # Check you have 2GB+ free
```

### Shared folder not mounting in VM

**QEMU/KVM:**
```bash
# Check if virtio-9p module is loaded
lsmod | grep 9p

# Manually mount
sudo mount -t 9p -o trans=virtio,version=9p2000.L purple /mnt/purple
```

**UTM:**
```bash
# Check spice services
ps aux | grep spice

# Manually mount
sudo mount -t virtiofs purple /mnt/purple
```

**VirtualBox:**
```bash
# Check guest additions
dpkg -l | grep virtualbox-guest

# Check group membership
groups | grep vboxsf

# Add user to group
sudo usermod -aG vboxsf purple
sudo reboot
```

### Installation hangs

- Check minimum requirements (4GB RAM recommended, 2GB minimum)
- Verify ISO integrity: `md5sum purple-computer.iso`
- Try rebuilding: `make clean-iso && make build-iso`
- Check BIOS settings (UEFI vs Legacy)

### Can't access Purple Computer after install

**Check X11 started:**
```bash
echo $DISPLAY  # Should show :0 or similar
ps aux | grep Xorg
```

**Check kitty:**
```bash
which kitty
kitty --version
```

**Manually start Purple Computer:**
```bash
cd ~/.purple
python3 repl.py
```

**View logs:**
```bash
journalctl -u getty@tty1 -b
```

---

## Advanced

### Custom Autoinstall

Edit `autoinstall.yaml` before building:
- Change hostname
- Modify packages
- Add custom commands
- Configure network settings

### Manual Installation (without ISO)

On existing Ubuntu 24.04 Server:
```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```

### Network Configuration

Network is disabled by default for safety. To enable:

**Option 1: Parent mode**
1. Boot Purple Computer
2. Press Ctrl+C (parent mode)
3. Option 7: Network settings

**Option 2: Manual**
```bash
# Enable NetworkManager
sudo systemctl unmask NetworkManager.service
sudo systemctl enable NetworkManager.service
sudo systemctl start NetworkManager.service

# Use nmtui to configure
sudo nmtui
```

---

## Build Process Details

The build script:
1. Downloads Ubuntu Server 24.04.3 ISO (~2.5GB)
2. Verifies SHA256 checksum for integrity
3. Extracts ISO contents
4. Injects autoinstall.yaml (cloud-init config)
5. Copies Purple Computer files
6. Configures GRUB for hybrid BIOS/UEFI boot (Ubuntu 24.04 uses GRUB for both)
7. Rebuilds ISO with xorriso

First build: 5-10 minutes
Subsequent builds: 2-3 minutes (reuses cached Ubuntu ISO)

---

## See Also

- [MANUAL.md](../MANUAL.md) - Complete Purple Computer documentation
- [README.md](../README.md) - Getting started guide
- Ubuntu autoinstall docs: https://ubuntu.com/server/docs/install/autoinstall

---

Made with 💜 for curious little minds
