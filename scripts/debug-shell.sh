#!/bin/bash
# Debug shell RC file for Purple Computer
# Loaded when Purple exits and drops to a debug terminal.

# Source normal bashrc if it exists
[ -f /etc/bash.bashrc ] && . /etc/bash.bashrc
[ -f ~/.bashrc ] && . ~/.bashrc

# Show diagnostics on entry
echo "============================================"
echo "  Purple Computer - Debug Shell"
echo "============================================"
echo ""
echo "--- Display ---"
echo "Terminal: $(tput cols)x$(tput lines)"
echo ""
echo "--- Scaling ---"
xrdb -query 2>/dev/null | grep -i dpi || echo "  Xft.dpi: (not set)"
xdpyinfo 2>/dev/null | grep "resolution:" || echo "  xdpyinfo: (not available)"
echo "  WINIT_X11_SCALE_FACTOR=$WINIT_X11_SCALE_FACTOR"
echo ""
echo "--- Boot log ---"
tail -30 /tmp/xinitrc.log 2>/dev/null || echo "  (no log found)"
echo ""
echo "============================================"
echo "  Commands: 'purple' to restart, 'reboot'"
echo "============================================"
echo ""

# Handy aliases
alias purple='/usr/local/bin/purple'
alias bootlog='cat /tmp/xinitrc.log'

PS1='\[\e[35m\]purple-debug\[\e[0m\]:\w\$ '
