#!/bin/bash
# Purple Computer ISO Tester
# Test the built ISO in QEMU virtual machine

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Purple Computer ISO Tester${NC}"
echo "============================"
echo ""

# Check if QEMU is installed
if ! command -v qemu-system-x86_64 &> /dev/null; then
    echo -e "${RED}Error: QEMU not installed${NC}"
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt install qemu-system-x86"
    echo "  macOS: brew install qemu"
    exit 1
fi

# Check if ISO exists
ISO_FILE="autoinstall/purple-computer.iso"
if [ ! -f "$ISO_FILE" ]; then
    echo -e "${RED}Error: ISO file not found${NC}"
    echo "Expected: $ISO_FILE"
    echo ""
    echo "Build the ISO first:"
    echo "  cd autoinstall && ./build-iso.sh"
    exit 1
fi

echo -e "${GREEN}ISO found:${NC} $ISO_FILE"
echo "Size: $(du -h $ISO_FILE | cut -f1)"
echo ""

# VM configuration
VM_NAME="purple-test"
VM_DISK="${VM_NAME}.qcow2"
VM_MEMORY="2048"
VM_CORES="2"
DISK_SIZE="8G"

# Create or use existing disk
if [ ! -f "$VM_DISK" ]; then
    echo -e "${YELLOW}Creating virtual disk...${NC}"
    qemu-img create -f qcow2 "$VM_DISK" "$DISK_SIZE"
    FRESH_INSTALL=1
else
    echo -e "${YELLOW}Using existing virtual disk: $VM_DISK${NC}"
    echo -e "${YELLOW}Delete it to do a fresh install${NC}"
    FRESH_INSTALL=0
fi

echo ""
echo "VM Configuration:"
echo "  Memory: ${VM_MEMORY}M"
echo "  CPU cores: $VM_CORES"
echo "  Disk: $DISK_SIZE"
echo ""

if [ $FRESH_INSTALL -eq 1 ]; then
    echo -e "${GREEN}Starting VM for installation...${NC}"
    echo ""
    echo "The Ubuntu autoinstaller will run automatically."
    echo "Installation takes 10-20 minutes."
    echo "The VM will reboot when done."
    echo ""
    echo "Press Enter to continue..."
    read
fi

# QEMU arguments
QEMU_ARGS=(
    -name "$VM_NAME"
    -m "$VM_MEMORY"
    -smp "$VM_CORES"
    -hda "$VM_DISK"
    -boot d
    -enable-kvm  # Remove if not on Linux
    -cpu host
    -vga virtio
    -display sdl
)

# Add ISO for fresh install
if [ $FRESH_INSTALL -eq 1 ]; then
    QEMU_ARGS+=(-cdrom "$ISO_FILE")
fi

# Add audio if available
if [ -f /dev/snd/seq ]; then
    QEMU_ARGS+=(-audiodev pa,id=snd0 -device AC97,audiodev=snd0)
fi

# Detect OS for KVM support
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - remove KVM, use hvf
    QEMU_ARGS=("${QEMU_ARGS[@]//-enable-kvm/}")
    QEMU_ARGS+=(-accel hvf)
elif [[ "$OSTYPE" != "linux-gnu"* ]]; then
    # Other OS - remove KVM
    QEMU_ARGS=("${QEMU_ARGS[@]//-enable-kvm/}")
fi

echo "Starting QEMU..."
echo ""
echo "To exit QEMU:"
echo "  • Press Ctrl+Alt+G to release mouse"
echo "  • Close the window or press Ctrl+C in this terminal"
echo ""

# Run QEMU
qemu-system-x86_64 "${QEMU_ARGS[@]}"

echo ""
echo -e "${GREEN}VM stopped${NC}"
echo ""
echo "To test again: ./scripts/test-iso.sh"
echo "To delete VM: rm $VM_DISK"
