# Test VM Setup

Automated Ubuntu Server VM for testing Purple Computer.

This creates a minimal VM with evdev, X11, and Alacritty configured. Not for production: use `build-scripts/` for that.

## Quick Start (UTM on Mac)

### 1. Download Ubuntu Server 24.04 ARM64 ISO

https://ubuntu.com/download/server/arm

### 2. Create VM in UTM

1. Click **Create a New Virtual Machine**
2. Select **Virtualize** (not Emulate)
3. Select **Linux**
4. Browse to the Ubuntu ISO you downloaded
5. On the Hardware screen:
   - **RAM**: 2048 MB (2 GB is enough)
   - **CPU Cores**: 2
6. On the Storage screen:
   - **Size**: 16 GB
7. On the Shared Directory screen:
   - Click **Browse** and select a folder (e.g., your `purplecomputer` repo folder)
   - This becomes `/mnt/share` in the VM
8. On the Summary screen:
   - **Name**: `purple-test` (or whatever you like)
   - Click **Save**

### 3. Configure display resolution

Before first boot, edit the VM settings:

1. Select the VM, click the **slider icon** (or right-click → Edit)
2. Go to **Display**
3. Set resolution: **1920x1080** (or your preferred size)
   - This is fixed; Linux VMs don't support dynamic resizing with Apple Virtualization

### 4. Install Ubuntu Server

Boot the VM and install Ubuntu:
- Select **minimized** install
- Enable **OpenSSH** server
- Create user: `purple` (or any name)
- Password: your choice

### 5. Run setup script

SSH into the VM and run:

```bash
sudo apt update && sudo apt install -y curl
curl -fsSL https://raw.githubusercontent.com/purplecomputerorg/purplecomputer/main/test-vm-setup/setup.sh | bash
```

### 6. Reboot

```bash
sudo reboot
```

### 7. Start X and run Purple

Log into VM console (not SSH), then:

```bash
startx
```

In Alacritty:
```bash
# If you shared the purplecomputer folder directly:
cd /mnt/share

# Or if you shared a parent folder:
cd /mnt/share/purplecomputer

# Or clone fresh:
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer

# Then:
make setup
make run
```

## What setup.sh Does

- Installs packages: git, make, python, X11, Alacritty, SDL/audio
- Installs fonts: JetBrainsMono Nerd Font, Noto Color Emoji
- Adds user to `input` group (evdev access)
- Configures uinput permissions
- Sets up VirtioFS for file sharing (`/mnt/share`)
- Sets up X wrapper permissions
- Creates `.xinitrc` for kiosk-style X session

## Workflow

| Task | Where |
|------|-------|
| Edit code | SSH or Mac (shared folder) |
| Run/test Purple | VM console with `startx` |

SSH gives you terminal input, not evdev. Keyboard testing must happen in the VM console.

## Troubleshooting

**"Permission denied" on keyboard:**
```bash
groups  # Should include 'input'
# If not, the reboot didn't happen. Reboot now.
```

**X exits immediately:**
```bash
# Test with xterm first
echo 'exec xterm' > ~/.xinitrc
startx
# If that works, the issue is Alacritty. Check missing libs.
```

**Alacritty crashes:**
```bash
sudo apt install libxkbcommon-x11-0 libgl1 libegl1 libgles2
```

**Shared folder not mounting:**
```bash
# Check virtiofs module is loaded
lsmod | grep virtiofs

# If not, load it manually
sudo modprobe virtiofs

# Try mounting manually
sudo mount -t virtiofs share /mnt/share
```

If virtiofs fails, make sure you selected "Virtualize" (Apple Virtualization), not "Emulate" (QEMU) when creating the VM.

## Notes

- This setup uses **Apple Virtualization** (native, fast)
- File sharing uses **VirtioFS**
- Resolution is fixed (set in UTM before boot, e.g., 1920x1080)
- Dynamic window resizing is not supported for Linux guests
