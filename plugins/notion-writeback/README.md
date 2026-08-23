# notion-writeback

A plugin for updating Japanese (or any non-ASCII) Notion pages reliably through the Notion MCP (`notion-update-page`).

## Problem

When a page body is retyped into a tool argument, each call has a small chance of corrupting characters.
Exposure scales with the **number of calls**, not the payload size — "split long arguments into small ones" makes it worse.

This plugin creates a path where the page body never passes through the model's output.

- **PreToolUse hook** `scripts/notion_write_guard.py`
  - Write `@@FILE:<path relative to the project root>@@` as `new_str` of `replace_content`, and the hook replaces it with the file contents
  - Denies abuse of `update_content`: more than 3 calls per page per session, multiple replacements in one call, and calls against a page not fetched in this session
- **Helper script** `scripts/notion_mirror.py`
  - `pull` — builds a local source file from the verbatim `notion-fetch` result stored in the session transcript
  - `diff` — compares the local source with the fetch result after normalization (`CLEAN` / `DIRTY` / `STALE`)
- **Agent** `notion-writeback:notion-fetcher` — a lightweight (haiku) subagent that only fetches and runs the script. It makes no judgment
- **Skill** `/notion-writeback:notion-writeback` — the procedure: fetch → pull → edit → diff → `replace_content` (sentinel) → fetch again → `CLEAN`

## Prerequisites

- A connected Notion MCP server (not bundled; add `{"type":"http","url":"https://mcp.notion.com/mcp"}` to your `.mcp.json`)
- `python3` on `PATH`
- The hook runs in any session that loads the plugin (Claude Code, and Cowork when installed via Customize → Plugins). Hooks written in a project's `.claude/settings.json` are not read by Cowork. If `@@FILE:...@@` is still in the page after a read-back, the hook did not run

## Usage

```text
/notion-writeback:notion-writeback write <page URL> back from docs/page.md
```

See [skills/notion-writeback/SKILL.md](skills/notion-writeback/SKILL.md) for the full procedure (Japanese).
