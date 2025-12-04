#!/bin/bash
set -euo pipefail

# Silent Boot Configuration Script for Purple Computer
# Runs during first boot to configure completely silent boot with Plymouth splash
# Part of Purple Computer autoinstall system

# Purple color
PURPLE='\033[0;35m'
BRIGHT_PURPLE='\033[1;35m'
NC='\033[0m'

# Simple progress bar function
show_progress() {
    local current=$1
    local total=$2
    local width=30
    local percent=$((current * 100 / total))
    local filled=$((width * current / total))
    local empty=$((width - filled))

    printf "\r  ${PURPLE}["
    printf "%${filled}s" | tr ' ' '█'
    printf "${NC}%${empty}s${PURPLE}" | tr ' ' '░'
    printf "]${NC} %3d%%" "$percent"
}

echo ""
echo -e "  ${BRIGHT_PURPLE}Welcome to Purple Computer!${NC}"
echo ""
echo "  Setting up your startup screen..."
echo ""

# 1. Configure GRUB for silent boot
show_progress 1 7
cat >> /etc/default/grub <<'EOF'

# Purple Computer silent boot configuration
GRUB_TIMEOUT=2
GRUB_TIMEOUT_STYLE=hidden
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3 rd.systemd.show_status=auto systemd.show_status=auto rd.udev.log_level=3 udev.log_level=3 vt.global_cursor_default=0"
EOF
update-grub >/dev/null 2>&1

# 2. Configure Plymouth for instant display
show_progress 2 7
if [[ -d "/usr/share/plymouth/themes/purplecomputer" ]]; then
    plymouth-set-default-theme purplecomputer >/dev/null 2>&1
elif plymouth-set-default-theme bgrt >/dev/null 2>&1; then
    true
fi

cat >> /etc/plymouth/plymouthd.conf <<'EOF'

# Purple Computer Plymouth configuration
ShowDelay=0
DeviceTimeout=5
EOF

# 3. Silence cloud-init console output
show_progress 3 7
cat > /etc/cloud/cloud.cfg.d/99-silent-boot.cfg <<'EOF'
# Purple Computer: redirect cloud-init output to logs only
output:
  all: '| tee -a /var/log/cloud-init-output.log'
reporting:
  logging:
    type: log
EOF

# 4. Minimize systemd console output
show_progress 4 7
mkdir -p /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/silent-boot.conf <<'EOF'
# Purple Computer: minimal boot status
[Manager]
ShowStatus=auto
LogLevel=warning
LogTarget=journal
EOF

# 5. Reduce kernel console logging
show_progress 5 7
cat > /etc/sysctl.d/99-silent-boot.conf <<'EOF'
# Purple Computer: only show errors/warnings on console
kernel.printk = 3 3 3 3
EOF

# 6. Add graphics drivers to initramfs for early Plymouth display
show_progress 6 7
cat >> /etc/initramfs-tools/modules <<'EOF'

# Purple Computer: early KMS for Plymouth
drm
drm_kms_helper
EOF

if lspci | grep -i vga | grep -iq intel; then
    echo "i915" >> /etc/initramfs-tools/modules
elif lspci | grep -i vga | grep -iq amd; then
    echo "amdgpu" >> /etc/initramfs-tools/modules
fi

cat > /etc/initramfs-tools/conf.d/splash <<'EOF'
# Purple Computer: enable framebuffer for Plymouth
FRAMEBUFFER=y
EOF

# 7. Update initramfs with new modules
show_progress 7 7
update-initramfs -u -k all >/dev/null 2>&1

# Complete
printf "\r  ${PURPLE}[%30s]${NC} 100%%\n" | tr ' ' '█'
echo ""
echo -e "  ${BRIGHT_PURPLE}✓${NC} Done"
echo ""
