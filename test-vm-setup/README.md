# Test VM Setup

Automated Ubuntu Server VM for testing Purple Computer.

This creates a minimal VM with evdev, X11, and Alacritty configured. Not for production: use `build-scripts/` for that.

## Quick Start (UTM on Mac)

### 1. Download Ubuntu Server 24.04 ARM64 ISO

https://ubuntu.com/download/server/arm

### 2. Create VM in UTM

- Click "Create a New Virtual Machine"
- Select **Virtualize** (not Emulate)
- Select **Linux**
- Browse to the Ubuntu ISO
- Configure:
  - RAM: 2-4 GB
  - Disk: 16 GB
  - **Display**: Set resolution (e.g., 1920x1080). Note: Linux VMs have fixed resolution with Apple Virtualization.

### 3. (Optional) Set up file sharing

Before first boot, in VM settings:
- Go to **Sharing** tab
- Click **Browse** and select a folder on your Mac (e.g., your code directory)

After Ubuntu install, the shared folder will be at `/mnt/share`.

### 4. Install Ubuntu Server

Boot the VM and install Ubuntu:
- Minimized install is fine
- Enable OpenSSH
- Create user (e.g., `purple`)

### 5. Run setup script

SSH into the VM (or use the console) and run:

```bash
curl -fsSL https://raw.githubusercontent.com/purplecomputerorg/purplecomputer/main/test-vm-setup/setup.sh | bash
```

Or if you have the repo:
```bash
bash test-vm-setup/setup.sh
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
# If using shared folder:
cd /mnt/share/purplecomputer

# Or clone fresh:
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer

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
