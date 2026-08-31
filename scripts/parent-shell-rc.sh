#!/bin/bash
# Interactive rc for the Parent Menu terminal (opened on the same screen as
# Purple via xterm). Typing exit returns to Purple.

[ -f /etc/bash.bashrc ] && . /etc/bash.bashrc
[ -f ~/.bashrc ] && . ~/.bashrc

echo ""
echo "  Purple Computer terminal"
echo "  Type exit and press Enter to go back to Purple."
echo ""

alias purple='/usr/local/bin/purple'
PS1='\[\e[35m\]purple\[\e[0m\]:\w\$ '
