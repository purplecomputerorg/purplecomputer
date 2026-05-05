# swarm-monitor

Run multiple Claude Code instances in parallel on the same repo, each in its own git worktree (a **lane**). This skill helps you start, watch, save, and merge them locally. Nothing here pushes to GitHub.

## The one thing to remember

```
cw help
```

That prints the full cheat sheet. Below is the same thing organized by what you're trying to do.

## Lane names: short name vs branch

Refer to a lane by its **short name** — the worktree directory name (e.g. `esc`, `feat-auth`). That's what you type into every command here.

The underlying git branch is `worktree-<name>` (Claude Code's `--worktree` flag picks that prefix; we don't control it). You'll see the branch in `git log` and in `/monitor` output rendered as:

```
Lane: esc    (branch: worktree-esc)
```

Tooling accepts either form, so don't worry about it.

## Workflow at a glance

### 1. Start a lane (from the main worktree, in your shell)

```
cw start feat-auth         # launches Claude Code in worktree "feat-auth"
```

### 2. Work inside the lane (slash commands inside Claude)

| Want to... | Use |
| --- | --- |
| Save progress, you write the message | `/checkpoint added validation` |
| Save progress, Claude writes the message | `/wrap` |
| Update human-readable handoff notes | `/handoff` |

### 3. Look around (works inside Claude or from the shell)

| Want to... | Inside Claude | From shell |
| --- | --- | --- |
| Status + overlap across all lanes | `/monitor` | `cw monitor` |
| Commit history for all lanes | `/log-lanes` | `cw log` |
| Inspect one lane | `/lane feat-auth` | — |
| List worktrees/branches | — | `cw lanes` |

### 4. Bring a lane home

| Want to... | Use |
| --- | --- |
| "Which lane should I merge next?" | `/integrate-next` |
| Actually merge a lane into the current branch | `/merge-lane feat-auth` or `cw merge feat-auth` |

`/merge-lane` uses `--no-ff` so the lane shows up as a unit in history. It refuses if your working tree is dirty. It does not push, squash, or delete the lane.

## When-to-use cheat sheet

- **Just want to save state?** `/wrap` (lazy) or `/checkpoint <msg>` (you write it).
- **About to step away?** `/handoff` writes a markdown summary other lanes can read.
- **Curious what other lanes are doing?** `/monitor`.
- **Ready to integrate?** `/integrate-next` to pick the safest one, then `/merge-lane <name>`.
- **Forgot everything?** `cw help`.

## Files

- `scripts/cw` — shell dispatcher (this is what you type in a terminal).
- `.claude/commands/*.md` — slash commands (what you type inside Claude Code).
- `.claude/skills/swarm-monitor/scripts/*.sh` — the underlying scripts both layers call.
- `.claude/skills/swarm-monitor/SKILL.md` — instructions Claude follows when coordinating lanes.

## Safety

The skill never pushes to GitHub, never squashes, never deletes worktrees or branches without you saying so. Merging is local only.
