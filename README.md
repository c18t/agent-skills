# agent-skills

Personal agent skills and Claude Code plugin marketplace.

## Install

```text
/plugin marketplace add c18t/agent-skills
/plugin install notion-writeback@c18t
```

## Plugins

| Name | Summary |
| --- | --- |
| [notion-writeback](plugins/notion-writeback/README.md) | Hooks and a skill for using the Notion MCP reliably. Injects page bodies straight from files via the `@@FILE:` sentinel and blocks repeated `update_content` calls |
| [issue-flow](plugins/issue-flow/README.md) | Both ends of a GitHub issue. Drafts one for review before filing it, then turns its number into a dedicated worktree — moving the session in with `EnterWorktree` — and works it through to a PR, a squash merge, and cleanup |

## Development

```bash
claude --plugin-dir ./plugins/notion-writeback
```

```bash
claude plugin validate ./plugins/notion-writeback
```

Lint Markdown with `markdownlint-cli2 "**/*.md"`.
