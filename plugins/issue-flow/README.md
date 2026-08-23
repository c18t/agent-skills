# issue-flow

Three skills covering the life of an issue: `issue-draft` writes one, `issue-work` works it through to a squash merge, and `release-merge` integrates the PRs that cannot land one at a time.

## Problem

`git worktree add` creates a directory — it does not move the session.
Editing right after it lands the changes in the main checkout while the new branch stays empty,
and that only becomes visible when the PR turns out to have no diff.

`cd` is not a fix either: the working directory moves, but write access, `CLAUDE.md`, and settings stay with the main checkout.

`issue-work` makes the move explicit with the built-in `EnterWorktree` tool, so the isolation is enforced by the harness — edits against the main checkout are blocked for the rest of the session.

Writing the issue has its own recurring decisions: which of the repository's actual labels applies, English title and Japanese body, and leaving the *reasoning* behind each item so picking the work up later does not mean re-deciding it. `issue-draft` fixes those, and holds the body for review before anything is created.

Merging has a blind spot of its own. GitHub judges each PR against the default branch alone, so two PRs that break each other are both reported `MERGEABLE` — the collision only surfaces once one of them has landed. `release-merge` checks for it up front with `git merge-tree`, and integrates the pair on a release branch instead of discovering the conflict on main.

## What it does

### `issue-draft` — writing the issue

Given a free-form topic:

1. `gh repo view` and `gh issue list` — checks for an existing issue on the same topic before adding another
2. Looks for `.github/ISSUE_TEMPLATE/` and prefers the repository's own headings; otherwise uses the bundled default [skills/issue-draft/templates/issue.md](skills/issue-draft/templates/issue.md) (背景 / やること / 影響範囲 / 補足) and says which one it used
3. `gh label list` — picks from labels that actually exist, because `--label` on a missing one fails the whole create
4. Titles it in English as `<target>: <english>`, bodies it in Japanese, and records the reasoning behind each item
5. **Writes the full title, labels, and body into the chat for review — it does not call `gh issue create`**
6. Creates the issue once you approve, passing the body via `--body-file`
7. Reports the URL and hands you `/issue-flow:issue-work <number>` — it does not start the work itself

Issue and PR numbers are assigned at creation, so the body is written without them; a cross-reference is added afterwards with `gh issue edit`.

### `issue-work` — working it

Given an issue number:

1. `gh issue view` — reads the issue in full (the content is what the implementation step works from)
2. Derives a [Conventional Branch](https://conventionalbranch.org/) name `<prefix>/<number>-<english-slug>` — the prefix (`feature` / `bugfix` / `hotfix` / `release` / `chore`) is chosen from the issue's labels — and a sibling worktree path `../<repo>-<branch-slug>`
3. `git worktree add`
4. Registers the worktree in `folders` of the repo's `*.code-workspace` — named after the branch, so VSCode shows which worktree is which — creating `<repo>.code-workspace` if none exists
5. **`EnterWorktree`** to move the session in
6. Implements the fix inside the worktree
7. Runs the project's linters and type checks (`.mise.toml` / `package.json` / `.pre-commit-config.yaml` / `markdownlint-cli2`)
8. Commits using Conventional Commits (freely, in as many commits as the work needs)
9. **Writes the PR body into the chat for review — it does not call `gh pr create`** — filled from `.github/pull_request_template.md`, or from the bundled default [skills/issue-work/templates/pull_request.md](skills/issue-work/templates/pull_request.md) when the repository has none
10. Pushes and opens the PR once you approve
11. Waits for CI via `scripts/watch-pr.sh` under the Monitor tool, then asks for merge approval
    with the squash commit message it intends to use
12. Squash-merges with `--subject`/`--body-file`, leaves the worktree, removes it, and drops its `folders` entry

Step 12 passes an explicit subject and body because GitHub otherwise defaults the squash commit
body to every branch commit message concatenated, which then has to be edited in the web UI.

The `*.code-workspace` edits sit on either side of the move on purpose: that file lives in the main
checkout, which the harness makes read-only for the session while it is inside the worktree. So the
entry is added before `EnterWorktree` (step 4) and removed after `ExitWorktree` (step 12).

### `release-merge` — integrating the ones that collide

Given the numbers of PRs that cannot land one at a time:

1. `gh pr view` on each — and `git merge-tree` between them, because `mergeable` answers "this PR vs the default branch", never "this PR vs that PR". If no pair conflicts, it says so and stops rather than manufacturing a release branch
2. Derives `release/<plugin>-<version>` — the plugin name is mandatory in a monorepo where each plugin versions independently, and the version's dots are kept so the branch matches the tag
3. `git worktree add` from `origin/<default>`, registers it in `*.code-workspace`, and **`EnterWorktree`** — conflict resolution belongs in its own tree, not in the main checkout it would otherwise hold hostage
4. Merges each PR in with `git merge --no-ff`, recording what was resolved and why for the PR body. When a PR renames a directory it goes first, and `git status` is checked after each merge for new files that landed under the old path — git cannot track a rename for files absent from the merge base, so they are not reported as conflicts
5. Runs the project's checks against the *integrated* tree, then checks the versions, READMEs, directory layout, and leftover old names for the inconsistencies a clean merge still leaves behind
6. **Writes the release PR body into the chat for review** — filled from `.github/PULL_REQUEST_TEMPLATE/release.md`, or from the bundled default [skills/release-merge/templates/release.md](skills/release-merge/templates/release.md) when the repository has none. It reads and fills the template itself, since `gh pr create --template` only seeds the interactive editor
7. Opens the PR once you approve, waits for CI via the same `scripts/watch-pr.sh`, and asks before merging
8. `gh pr merge --merge` — never `--squash`, which would rewrite the head SHAs and leave every included PR to be closed by hand
9. Verifies the auto-closes landed, closes by hand whatever did not, and cleans up

The bases of the included PRs are left pointing at the default branch throughout. Retargeting them to
the release branch marks them Merged the moment they land there — while the default branch still has
nothing — and `Merged` cannot be reopened. With `deleteBranchOnMerge` on, their branches are then
deleted too, leaving the release branch as the only copy of those commits.

### PreToolUse hook — `scripts/github_write_guard.py`

On the MCP path, bodies and file contents are *transcribed by the model* into tool arguments,
which loses the one property `--body-file` had on the `gh` path: the bytes never pass through the
model's output. In PR #28 that cost three of ten pushed files a silent rewording — 「続けて**進めて**よい」
became 「続けて**進んで**よい」 — the kind of plausible "correction" a review reads straight past.

So write `@@FILE:<path relative to the base directory>@@` as the whole argument, and the hook
substitutes the file's contents before the call leaves the machine. It covers `push_files`
(`files[].content`, per element), `create_or_update_file` (`content`), `issue_write` /
`create_pull_request` / `add_issue_comment` (`body`), and `merge_pull_request` (`commit_message`).
The base directory is `CLAUDE_PROJECT_DIR`, then the hook payload's `cwd`, then the current
directory — the repository root under Claude Code, the session's `cwd` under Cowork.

If the file is missing, unreadable, or outside the base directory, the hook **denies the call**
rather than injecting nothing: a literal `@@FILE:...@@` reaching a commit is the worst outcome.
Writing no sentinel keeps the old behavior, so this is backward compatible. The hook is scoped to
GitHub MCP tools specifically — `issue_write` and `create_pull_request` are not GitHub-only names,
and a fail-closed hook must not interrupt some other server's calls.

Regardless of the hook, verify after `push_files`: `git fetch origin` then
`git diff HEAD origin/<branch>` must be empty. That check is what caught #28, and it still works
where the hook does not run.

## Prerequisites

- A way to read and write GitHub — either `gh` on `PATH` and authenticated (`gh auth status`), or a GitHub MCP server whose tools are visible to the session. The skills check in that order, once per run, and stop if neither is available — none of them authenticates for you. Every `gh` operation has its MCP counterpart in [skills/issue-work/reference/github-mcp.md](skills/issue-work/reference/github-mcp.md)
- A git repository with a remote (`issue-work`, `release-merge`)
- `EnterWorktree` needs your approval on first entry, because the worktree lives outside `.claude/worktrees/` (`issue-work`, `release-merge`)
- Python 3 on `PATH` — any of `python3`, `python`, or `py` (the hook goes through `scripts/python.sh`, which picks the first one that exists). Only the MCP path needs it; the `gh` path never invokes the hook. If none is found the hook exits 2 and blocks the write rather than letting an unexpanded `@@FILE:...@@` reach GitHub

### Cowork

Cowork tasks run in a cloud VM that has no `gh` and no `gh` credentials, so the MCP path is the
only one available: set up a GitHub MCP server on the desktop side so its tools are proxied into
the session. Two more Cowork-specific notes:

- `release-merge` additionally needs working `git push` credentials for its release branch. The
  MCP `push_files` cannot substitute there — an API push creates new commits, the merged PR head
  SHAs never reach the remote, and none of the included PRs auto-close. Without push credentials
  the skill stops before pushing
- The `*.code-workspace` registration steps exist for VSCode and are skipped in Cowork; the
  worktree steps themselves (`git worktree add` + `EnterWorktree`) work as-is

## Usage

```text
/issue-flow:issue-draft add a skill for creating issues
/issue-flow:issue-work 123
/issue-flow:release-merge 11 12
```

See [skills/issue-draft/SKILL.md](skills/issue-draft/SKILL.md),
[skills/issue-work/SKILL.md](skills/issue-work/SKILL.md), and
[skills/release-merge/SKILL.md](skills/release-merge/SKILL.md) for the full procedures (Japanese).

## Notes

- Each `SKILL.md` is the happy path only. Failure modes, recovery steps, and the reasoning behind each prohibition live in the skill's `reference/` directory and are linked from the step they apply to
- The step-by-step procedures are written with `gh` commands, which stay the shorter path where `gh` works; the shared mapping table ([skills/issue-work/reference/github-mcp.md](skills/issue-work/reference/github-mcp.md)) translates each operation to GitHub MCP tools. The approval gates (🛑) sit in the same places on both paths — MCP tools may execute without a harness-side confirmation, so the skill-side gate is what stands in for it
- Templates are resolved project-first: the repository's own `.github/` template wins, and the bundled default under the skill's `templates/` is used only when there is none. The skill states which one it used when it presents the body
- The three skills are deliberately separate invocations. `issue-draft` stops at the URL rather than starting the work, because filing an issue and picking it up are different decisions. `release-merge` starts from PR numbers, not an issue, so it carries its own worktree steps rather than calling `issue-work`
- Creating an issue is gated on an explicit go-ahead, since the only undo is closing it
- Merging is gated on an explicit go-ahead every time. CI passing is not treated as approval, and neither is the review of the PR body (step 9 in `issue-work`, step 9 in `release-merge`)
- `release-merge` gates once more, before anything is created: the PR list, merge order, branch name, and version go to review at step 2, because a release branch named wrong is only cheap to fix before it is pushed
- The worktree is removed only as part of a completed merge (step 12). If the run stops earlier, it is kept so the work can be resumed by entering the same path again
- Because the worktree is created outside `.claude/worktrees/`, `ExitWorktree` will not delete it — removal is an explicit `git worktree remove`
- The merge method is not interchangeable and neither skill falls back. `issue-work` squashes; `release-merge` uses a merge commit in **both** directions, because a squash rewrites the head SHA and the included PRs then never register as merged. If the repository has the required method disabled, the skill reports it and stops
- Renaming a branch mid-run is a rename, not a re-cut: `git branch -m`, then `git worktree move` after leaving the worktree, then the matching `folders` entry. `mv` would leave the worktree's git metadata pointing at the old path
