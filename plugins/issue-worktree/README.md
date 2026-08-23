# issue-worktree

Two skills covering both ends of an issue: `issue-draft` writes one, `issue-worktree` works it through to a squash merge.

## Problem

`git worktree add` creates a directory — it does not move the session.
Editing right after it lands the changes in the main checkout while the new branch stays empty,
and that only becomes visible when the PR turns out to have no diff.

`cd` is not a fix either: the working directory moves, but write access, `CLAUDE.md`, and settings stay with the main checkout.

`issue-worktree` makes the move explicit with the built-in `EnterWorktree` tool, so the isolation is enforced by the harness — edits against the main checkout are blocked for the rest of the session.

Writing the issue has its own recurring decisions: which of the repository's actual labels applies, English title and Japanese body, and leaving the *reasoning* behind each item so picking the work up later does not mean re-deciding it. `issue-draft` fixes those, and holds the body for review before anything is created.

## What it does

### `issue-draft` — writing the issue

Given a free-form topic:

1. `gh repo view` and `gh issue list` — checks for an existing issue on the same topic before adding another
2. Looks for `.github/ISSUE_TEMPLATE/` and prefers the repository's own headings; falls back to 背景 / やること / 影響範囲 / 補足
3. `gh label list` — picks from labels that actually exist, because `--label` on a missing one fails the whole create
4. Titles it in English as `<target>: <english>`, bodies it in Japanese, and records the reasoning behind each item
5. **Writes the full title, labels, and body into the chat for review — it does not call `gh issue create`**
6. Creates the issue once you approve, passing the body via `--body-file`
7. Reports the URL and hands you `/issue-worktree:issue-worktree <number>` — it does not start the work itself

Issue and PR numbers are assigned at creation, so the body is written without them; a cross-reference is added afterwards with `gh issue edit`.

### `issue-worktree` — working it

Given an issue number:

1. `gh issue view` — reads the issue in full (the content is what the implementation step works from)
2. Derives `feature/<number>_<english-slug>` and a sibling worktree path `../<repo>-<branch-slug>`
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

- `gh` on `PATH` and authenticated (`gh auth status`) — neither skill authenticates for you
- A git repository with a remote (`issue-worktree`)
- `EnterWorktree` needs your approval on first entry, because the worktree lives outside `.claude/worktrees/` (`issue-worktree`)

## Usage

```text
/issue-worktree:issue-draft add a skill for creating issues
/issue-worktree:issue-worktree 123
```

See [skills/issue-draft/SKILL.md](skills/issue-draft/SKILL.md) and
[skills/issue-worktree/SKILL.md](skills/issue-worktree/SKILL.md) for the full procedures (Japanese).

## Notes

- The two skills are deliberately separate invocations. `issue-draft` stops at the URL rather than starting the work, because filing an issue and picking it up are different decisions
- Creating an issue is gated on an explicit go-ahead, since the only undo is closing it
- Merging is gated on an explicit go-ahead every time. CI passing is not treated as approval, and neither is the step 8 review of the PR body
- The worktree is removed only as part of a completed merge (step 11). If the run stops earlier, it is kept so the work can be resumed by entering the same path again
- Because the worktree is created outside `.claude/worktrees/`, `ExitWorktree` will not delete it — removal is an explicit `git worktree remove`
- The squash merge needs to be enabled on the repository. The skill reports it and stops rather than falling back to `--merge` or `--rebase`
