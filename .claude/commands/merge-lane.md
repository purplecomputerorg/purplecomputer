---
description: Merge a finished lane into the current branch (no push, no squash, no auto-cleanup).
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Merge this lane into the current branch: $ARGUMENTS

Steps:

1. Confirm the current branch (target) and that the working tree is clean.
2. Show the user:
   - target branch
   - lane being merged
   - lane commits about to land (`git log --oneline TARGET..LANE`)
   - files changed
3. Run:
   `.claude/skills/swarm-monitor/scripts/merge-lane.sh $ARGUMENTS`
4. After the script finishes, show the resulting `git log --oneline -5`.
5. Suggest the test command appropriate for this repo (`just test`).

Rules:
- Do not push.
- Do not squash. The script uses `--no-ff` so the lane stays visible in history.
- Do not delete the lane's branch or worktree. The user removes those by hand when ready.
- If the script refuses (dirty tree, missing branch, no new commits), report exactly what it said and stop.
