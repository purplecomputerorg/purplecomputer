---
description: Update the current lane handoff file.
allowed-tools: Bash, Read, Grep, Glob, Write
---

Use the swarm-monitor skill.

Write or update .claude-lane-status.md in the current worktree.

Include:
- lane name
- current goal
- current status
- changed files
- commands run
- test results
- blockers
- integration notes
- files likely to overlap with other lanes
- next recommended action

Keep it factual and concise.
Do not push to GitHub.
