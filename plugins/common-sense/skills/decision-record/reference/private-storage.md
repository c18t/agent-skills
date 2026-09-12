# Private ADR storage

Private decisions live in one companion repository per public repository. The companion is named
`<repository>-decisions` and must have private visibility.

## Layout and resolution

The single local clone is stored at:

```text
<main checkout>/.claude/decisions/<repository>-decisions/
```

Linked worktrees resolve the main checkout through Git's absolute common directory, so they all use the same clone.
Never put a user-specific absolute path in a tracked file and never create one clone per worktree.

Resolve and validate the store with the bundled helper:

```bash
sh "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/python.sh" \
  "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/decision_store.py" check --repository "$PWD"
```

On Windows, call the same Python script through `scripts/python.cmd`. A successful command prints the absolute
`docs/decisions/` path. It fails closed when the clone is absent, is not an independent Git repository, or is not
writable.

## One-time setup

1. Append `.claude/decisions/` to the public repository's `.gitignore` without replacing existing content, and commit
   that public configuration change.
2. Add the following policy to the repository's `AGENTS.md`, preserving its existing instructions:

   ```markdown
   ## Architecture decisions

   Public ADRs live in `docs/decisions/`. Private ADRs live in the private `<repository>-decisions` companion
   repository. Resolve the shared local clone with the common-sense `decision_store.py check` helper; do not copy it
   into individual worktrees or record its absolute path. Search existing ADRs before writing a new one, and commit a
   private ADR only from the companion repository.
   ```

3. Run `decision_store.py setup --repository <checkout>`. If the companion does not exist, the helper stops before
   changing GitHub. Show the user the exact private repository name and obtain approval immediately before rerunning
   with `--approve-create`. That flag records approval for this invocation; never infer or reuse it.
4. Re-run `check` from the main checkout and every active worktree. All invocations must print the same path.

The helper verifies private visibility before cloning. If the repository exists but is inaccessible, distinguish that
from confirmed absence outside the helper before creating anything; never create a similarly named fallback.

## Safe use and recovery

Before reading or writing an ADR, run `check`. Search the returned directory for the same topic and superseding ADRs.
Write and commit with `git -C <returned docs directory> ...`; verify the public checkout remains absent from
`git status --short` and `git diff --cached` before committing.

If `check` reports a missing clone, rerun setup. If it reports an inaccessible path, restore filesystem permissions or
move the clone back to the canonical location. Do not fall back to the public tree, another worktree, or an untracked
temporary directory, because each can leak or fork private decisions.
