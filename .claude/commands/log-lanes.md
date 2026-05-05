---
description: Show commit history for all local Claude Code lanes.
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Run:
.claude/skills/swarm-monitor/scripts/log-lanes.sh main

Then summarize:
1. lane name
2. worktree path
3. commits ahead of main
4. latest 5 commits
5. whether the lane has uncommitted changes
6. whether the lane appears ready for integration

Do not modify files.
Do not push.
Do not merge.
