# Purple Computer Autoinstall

Automated Ubuntu Server installation with Purple Computer pre-configured.

## Architecture

**Ubuntu Server 24.04 LTS + minimal Xorg (no desktop) + alacritty fullscreen**

No desktop environment. Just a fullscreen terminal that boots directly into Purple Computer.

**Fully offline** - all packages bundled in ISO, no network required during installation.

---

## Build the ISO (Linux only)

```bash
# From project root
make build-iso

# Or directly
./autoinstall/build-iso.sh

# Test mode (auto-installs without confirmation, for VM testing)
./autoinstall/build-iso.sh --test
```

Creates `purple-computer.iso` (~4-5GB).

**Requirements:**
- Linux (use a VM or WSL2 if on macOS/Windows)
- Docker
- ~10GB free disk space

```bash
# Install dependencies (Ubuntu/Debian)
sudo apt install xorriso curl rsync docker.io
sudo usermod -aG docker $USER
newgrp docker
```

**Build time:** 10-15 minutes first time, 2-3 minutes after (packages cached).

---

## Write ISO to USB

**Any OS (recommended):**
1. Download [balenaEtcher](https://www.balena.io/etcher/)
2. Select purple-computer.iso
3. Select USB drive
4. Flash

**Linux:**
```bash
lsblk  # Find USB device
sudo dd if=purple-computer.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

---

## Install

1. Insert USB into target computer
2. Power on, press boot menu key (F12, F2, or ESC)
3. Select USB drive
4. Press Enter to install
5. Wait ~10 minutes
6. Remove USB when done
7. System reboots into Purple Computer

**No network required** - everything is on the USB.

---

## VM Testing

### QEMU/KVM

```bash
# Create disk
qemu-img create -f qcow2 purple-test.qcow2 20G

# Install
qemu-system-x86_64 \
  -cdrom purple-computer.iso \
  -drive file=purple-test.qcow2,format=qcow2 \
  -m 4096 -smp 2 -boot d -enable-kvm

# After install, boot from disk
qemu-system-x86_64 \
  -drive file=purple-test.qcow2,format=qcow2 \
  -m 4096 -smp 2 -enable-kvm
```

### VirtualBox

1. New VM: Linux, Ubuntu 64-bit, 4GB RAM, 20GB disk
2. Attach purple-computer.iso to optical drive
3. Start and wait for install
4. Remove ISO, reboot

---

## Configuration Files

- `autoinstall.yaml` - Ubuntu autoinstall config
- `files/xinit/xinitrc` - X11 startup
- `files/alacritty/alacritty.toml` - Terminal config
- `build-iso.sh` - ISO builder

---

## Troubleshooting

### Build fails

```bash
# Missing deps
sudo apt install xorriso curl rsync docker.io

# Docker not running
sudo systemctl start docker

# Not in docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Installation hangs

- Need 4GB+ RAM
- Check BIOS: try UEFI vs Legacy boot
- Rebuild ISO: `rm -rf autoinstall/build && ./autoinstall/build-iso.sh`

### X11 doesn't start after install

```bash
# Check X11
ps aux | grep Xorg

# Manual start
startx

# View logs
journalctl -u getty@tty1 -b
cat ~/.local/share/xorg/Xorg.0.log
```

---

## Manual Installation (without ISO)

On existing Ubuntu 24.04:

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```
