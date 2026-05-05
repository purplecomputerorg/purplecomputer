---
description: Auto-write a 1-2 sentence commit message from the current diff and checkpoint the lane.
allowed-tools: Bash, Read, Grep, Glob
---

Use the swarm-monitor skill.

Goal: commit the current lane's changes with a message you generate from the diff. The user does not want to write the message themselves.

Steps:

1. Run `git status --short` and `git diff --stat` to see the scope.
2. If there are no changes, say so and stop.
3. Run `git diff` (and `git diff --cached` if anything is staged) to read the actual changes. For huge diffs, sample the most informative hunks.
4. Draft a 1-2 sentence commit message:
   - One line, max two short sentences. No bullet-list body.
   - Focus on the WHY or the user-visible effect, not a file list.
   - Imperative mood ("add X", "fix Y").
   - Do NOT prefix with `lane(...)`. Do NOT add `Co-Authored-By`.
5. Show the proposed message to the user and ask them to confirm or edit it.
6. Once confirmed, call:
   `.claude/skills/swarm-monitor/scripts/checkpoint.sh "<final message>"`
7. Print the resulting `git log --oneline -5`.

Rules:
- Do not push.
- Do not amend.
- Do not merge.
- Do not squash.
- If conflicts or whitespace errors are present, the script will refuse — report what it said.
