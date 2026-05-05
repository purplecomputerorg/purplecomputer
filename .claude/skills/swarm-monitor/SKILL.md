---
name: swarm-monitor
description: Use when monitoring multiple independent Claude Code instances running in git worktrees for the same repository, especially to summarize lane status, detect overlap, and recommend local integration order before GitHub.
---

# Swarm Monitor

The user runs multiple independent Claude Code sessions in the same repository, usually via git worktrees.

This skill observes and coordinates those sessions locally.

GitHub is publication, not coordination.

Do not push, create PRs, merge remotely, delete branches, or delete worktrees unless explicitly requested.

## Concepts

A lane is one Claude Code instance working in one worktree or branch.

A lane may have:
- a git worktree
- a branch
- uncommitted changes
- commits ahead of main
- a .claude-lane-status.md handoff file

## Monitoring workflow

When asked to monitor:

1. Identify the repo root.
2. Determine the base branch, defaulting to main.
3. List git worktrees.
4. Identify likely lanes from git worktree list.
5. For each lane, inspect:
   - branch name
   - worktree path
   - git status --short
   - git diff --name-status BASE...HEAD
   - latest commits
   - .claude-lane-status.md if present
6. Compute overlap:
   - same files changed by multiple lanes
   - same directories changed by multiple lanes
   - shared test/setup/config files
   - migration/schema/model files
7. Classify integration risk:
   - low: docs, tests, isolated leaf files
   - medium: shared utilities, common components, related tests
   - high: models, schema, API contracts, auth, routing, package config, broad refactors
8. Recommend an integration order:
   - low-risk independent changes first
   - tests/support changes before feature changes if they unblock validation
   - broad or overlapping work last
9. Never assume a clean git merge means semantic compatibility.

## Output format

Use concise sections:

- Active lanes
- Overlap map
- Risks
- Suggested integration order
- Next action

Prefer exact git evidence over guessing.

## Handoff file

Each lane should maintain .claude-lane-status.md with:

# Claude lane status

## Lane

## Goal

## Status

## Changed files

## Commands run

## Test result

## Blockers

## Integration notes

## Likely overlap

## Lane commit history

Each lane should keep its own git history.

Use checkpoint commits to preserve useful intermediate states.

Rules:
- Commit within the lane branch.
- Do not squash lane commits during active work.
- Do not amend lane commits unless explicitly requested.
- Prefer small commits with clear messages.
- Prefix checkpoint commits with lane(BRANCH):.
- Before integration, inspect commits ahead of main.
- During integration, preserve history with merge --no-ff or cherry-pick -x when useful.
- If two lanes touch the same files, keep their commits separate until integration.
- A clean git merge does not prove semantic compatibility.

When integrating:
- Use merge --no-ff to preserve the lane as a branch-level unit.
- Use cherry-pick -x to pull selected commits while retaining original commit references.
- Avoid squashing unless the user explicitly asks.

## Safety

Never push to GitHub unless explicitly asked.
Never merge multiple lanes at once.
Never delete worktrees or branches unless explicitly asked.
Stop before destructive git operations.
