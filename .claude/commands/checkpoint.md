---
description: Create a lane-local checkpoint commit for the current Claude Code worktree.
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Create a checkpoint commit in the current lane.

Message: $ARGUMENTS

Run:
.claude/skills/swarm-monitor/scripts/checkpoint.sh "$ARGUMENTS"

Rules:
- Commit only in the current worktree.
- Do not push to GitHub.
- Do not merge.
- Do not amend previous commits.
- Do not squash.
- If there are no changes, say so.
- If the working tree has conflicts, stop and report them.
- After committing, show the latest 5 commits for this lane.
