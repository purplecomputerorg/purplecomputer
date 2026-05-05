---
description: Monitor all local Claude Code lanes and summarize overlap, risk, and integration readiness.
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Run:
- .claude/skills/swarm-monitor/scripts/status.sh main
- .claude/skills/swarm-monitor/scripts/overlap.sh main

Then summarize:
1. active lanes
2. branch and worktree path for each lane
3. changed files against main
4. uncommitted changes
5. latest commits
6. handoff status if present
7. exact file overlaps
8. directory overlaps
9. integration risk
10. suggested integration order
11. next action

Do not modify files.
Do not push to GitHub.
Do not merge anything.
