# issue-worktree

A skill that turns a GitHub issue number into a dedicated worktree, moves the session into it, and works the issue through to a PR.

## Problem

`git worktree add` creates a directory — it does not move the session.
Editing right after it lands the changes in the main checkout while the new branch stays empty,
and that only becomes visible when the PR turns out to have no diff.

`cd` is not a fix either: the working directory moves, but write access, `CLAUDE.md`, and settings stay with the main checkout.

This skill makes the move explicit with the built-in `EnterWorktree` tool, so the isolation is enforced by the harness — edits against the main checkout are blocked for the rest of the session.

## What it does

Given an issue number:

1. `gh issue view` — reads the issue in full (the content is what the implementation step works from)
2. Derives a [Conventional Branch](https://conventionalbranch.org/) name `<prefix>/<number>-<english-slug>` — the prefix (`feature` / `bugfix` / `hotfix` / `release` / `chore`) is chosen from the issue's labels — and a sibling worktree path `../<repo>-<branch-slug>`
3. `git worktree add`
4. Registers the worktree in `folders` of the repo's `*.code-workspace` — named after the branch, so VSCode shows which worktree is which — creating `<repo>.code-workspace` if none exists
5. **`EnterWorktree`** to move the session in
6. Implements the fix inside the worktree
7. Runs the project's linters and type checks (`.mise.toml` / `package.json` / `.pre-commit-config.yaml` / `markdownlint-cli2`)
8. Commits using Conventional Commits (freely, in as many commits as the work needs)
9. **Writes the PR body into the chat for review — it does not call `gh pr create`**
10. Pushes and opens the PR once you approve
11. Waits for CI via `scripts/watch-pr.sh` under the Monitor tool, then asks for merge approval
    with the squash commit message it intends to use
12. Squash-merges with `--subject`/`--body-file`, leaves the worktree, removes it, and drops its `folders` entry

Step 12 passes an explicit subject and body because GitHub otherwise defaults the squash commit
body to every branch commit message concatenated, which then has to be edited in the web UI.

The `*.code-workspace` edits sit on either side of the move on purpose: that file lives in the main
checkout, which the harness makes read-only for the session while it is inside the worktree. So the
entry is added before `EnterWorktree` (step 4) and removed after `ExitWorktree` (step 12).

## Prerequisites

- `gh` on `PATH` and authenticated (`gh auth status`)
- A git repository with a remote
- `EnterWorktree` needs your approval on first entry, because the worktree lives outside `.claude/worktrees/`

## Usage

```text
/issue-worktree:issue-worktree 123
```

See [skills/issue-worktree/SKILL.md](skills/issue-worktree/SKILL.md) for the full procedure (Japanese).

## Notes

- Merging is gated on an explicit go-ahead every time. CI passing is not treated as approval, and neither is the step 8 review of the PR body
- The worktree is removed only as part of a completed merge (step 11). If the run stops earlier, it is kept so the work can be resumed by entering the same path again
- Because the worktree is created outside `.claude/worktrees/`, `ExitWorktree` will not delete it — removal is an explicit `git worktree remove`
- The squash merge needs to be enabled on the repository. The skill reports it and stops rather than falling back to `--merge` or `--rebase`
- Renaming a branch mid-run is a rename, not a re-cut: `git branch -m`, then `git worktree move` after leaving the worktree, then the matching `folders` entry. `mv` would leave the worktree's git metadata pointing at the old path
