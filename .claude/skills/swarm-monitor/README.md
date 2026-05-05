# swarm-monitor

Coordinate multiple independent Claude Code instances running in the same repo, usually on separate git worktrees.

A **lane** is one Claude Code instance working in one worktree/branch. Each lane has its own commits, status, and optional `.claude-lane-status.md` handoff file. GitHub is publication, not coordination — everything here is local.

## Start a lane

```
./scripts/cw feat-auth
```

Launches `claude --worktree feat-auth` (extra args forwarded to `claude`).

## Slash commands

Run inside any lane:

| Command | Purpose |
| --- | --- |
| `/handoff` | Write/update `.claude-lane-status.md` in the current worktree. |
| `/checkpoint <msg>` | Lane-local commit prefixed `lane(BRANCH): <msg>`. No push, no amend, no squash. |

Run from any lane (read-only across all lanes):

| Command | Purpose |
| --- | --- |
| `/monitor` | Status + overlap summary across all lanes. |
| `/lane <name>` | Inspect one lane (status, diff vs main, handoff, merge risk). |
| `/log-lanes` | Commit history for every lane. |
| `/integrate-next` | Recommend the safest next lane to integrate into `ai/integration`. |

## Underlying scripts

In `.claude/skills/swarm-monitor/scripts/`:

- `lanes.sh [base]` — list worktrees and lane-like branches.
- `status.sh [base]` — per-lane status, diff vs base, recent commits, handoff.
- `overlap.sh [base]` — exact file and directory overlaps between lanes.
- `log-lanes.sh [base]` — commits ahead of base for each lane.
- `checkpoint.sh "<msg>"` — safe commit in the current worktree.

Default base branch is `main`.

## Safety

The skill never pushes, merges, or deletes worktrees/branches without explicit instruction.
