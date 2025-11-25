#!/bin/bash
# Purple Computer First Boot Script
# This runs automatically on first boot after autoinstall
# It performs final configuration and optimization

LOG_FILE="/var/log/purple-firstboot.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "Purple Computer First Boot Configuration"
echo "========================================"
date

# Ensure all Purple Computer files have correct permissions
echo "Setting file permissions..."
chown -R kiduser:kiduser /home/kiduser/.purple
chown -R kiduser:kiduser /home/kiduser/.config
chmod +x /home/kiduser/.xinitrc
chmod +x /home/kiduser/.purple/repl.py 2>/dev/null || true

# Test text-to-speech
echo "Testing text-to-speech..."
if command -v espeak-ng &> /dev/null; then
    echo "espeak-ng is installed"
else
    echo "WARNING: espeak-ng not found"
fi

# Test Python environment
echo "Testing Python environment..."
python3 -c "import sys; print(f'Python {sys.version}')"
python3 -c "import IPython; print(f'IPython {IPython.__version__}')" 2>/dev/null || echo "WARNING: IPython not found"

# Verify audio devices
echo "Checking audio devices..."
aplay -l || echo "WARNING: No audio devices found"

# Optimize boot time
echo "Optimizing boot configuration..."
# Disable Plymouth splash if installed
systemctl mask plymouth-start.service 2>/dev/null || true
systemctl mask plymouth-quit-wait.service 2>/dev/null || true

# Disable apt-daily timers (no auto-updates)
systemctl disable apt-daily.timer 2>/dev/null || true
systemctl disable apt-daily-upgrade.timer 2>/dev/null || true

# Ensure getty auto-login is active
systemctl enable getty@tty1.service

# Create success marker
touch /var/lib/purple-configured

echo "========================================"
echo "First boot configuration complete!"
echo "System ready for Purple Computer use."
date

# Disable this script from running again
systemctl disable purple-firstboot.service 2>/dev/null || true
