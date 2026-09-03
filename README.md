# agent-skills

Personal agent skills and plugin marketplace for Claude Code and Codex.

## Install

Claude Code:

```text
/plugin marketplace add c18t/agent-skills
/plugin install notion-writeback@c18t
```

Codex plugins use the `.codex-plugin/plugin.json` manifest bundled in each supported plugin.
After installing `notion-writeback`, review and trust its hook with `/hooks`, then invoke it with
`$notion-writeback:notion-writeback`.

## Plugins

| Name | Summary |
| --- | --- |
| [notion-writeback](plugins/notion-writeback/README.md) | Hooks and a skill for using the Notion MCP reliably. Injects page bodies straight from files via the `@@FILE:` sentinel and blocks repeated `update_content` calls |
| [issue-flow](plugins/issue-flow/README.md) | The life of a GitHub issue. Drafts one for review before filing it, turns its number into a dedicated worktree with runtime-appropriate boundaries, and works it through to a PR, a squash merge, and cleanup. Integrates PRs that conflict with each other on a `release/<plugin>-<version>` branch when they cannot land one at a time |

## Development

```bash
claude --plugin-dir ./plugins/notion-writeback
```

```bash
claude plugin validate ./plugins/notion-writeback
```

Validate the Codex manifest with the bundled `plugin-creator` validator.

Lint Markdown with `markdownlint-cli2 "**/*.md"`.
