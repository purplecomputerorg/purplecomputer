---
description: Inspect one Claude Code lane by branch or worktree name.
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Inspect this lane: $ARGUMENTS

Find the matching git worktree or branch.

Report:
1. branch/worktree path
2. current git status
3. changed files against main
4. uncommitted files
5. latest commits
6. .claude-lane-status.md if present
7. merge risk
8. whether it looks ready to integrate

Do not modify files.
Do not push.
