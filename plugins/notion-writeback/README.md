# notion-writeback

A plugin for updating Japanese (or any non-ASCII) Notion pages reliably through the Notion MCP (`notion-update-page`).

## Problem

When a page body is retyped into a tool argument, each call has a small chance of corrupting characters.
Exposure scales with the **number of calls**, not the payload size — "split long arguments into small ones" makes it worse.

This plugin creates a path where the page body never passes through the model's output.

- **PreToolUse hook** `scripts/notion_write_guard.py`
  - Write `@@FILE:<path relative to the base directory>@@` as `new_str` of `replace_content`, and the hook replaces it with the file contents. The base directory is `CLAUDE_PROJECT_DIR`, then the hook payload's `cwd`, then the current directory — so it is the repository root under Claude Code regardless of where the session was started, and the session's `cwd` under Cowork (keep the local source inside the container there; connected folders live outside the base and are denied). See [SKILL.md](skills/notion-writeback/SKILL.md) for the per-environment table
  - Denies abuse of `update_content`: more than 3 calls per page per session, multiple replacements in one call, and calls against a page not fetched in this session
- **Helper script** `scripts/notion_mirror.py`
  - `pull` — builds a local source file from the verbatim `notion-fetch` result stored in the session transcript
  - `diff` — compares the local source with the fetch result after normalization (`CLEAN` / `DIRTY` / `STALE`; exit 0 for `CLEAN`, 1 for `DIRTY` / `STALE`, 3 for a real failure). It always prints at least one line, so **empty output means the script never ran — never "no differences"**. Normalization folds Notion's auto-linking of bare filenames and domain-like tokens (`notion_mirror.py` → `notion_[mirror.py](http://mirror.py)`), but only where the link text equals its target, so hand-pasted links still show up as diffs
- **Wrapper** `scripts/python.sh` — runs the Python scripts with whichever of `python3` / `python` / `py -3` exists, so the hook works on Linux, WSL, and Windows (Git Bash) alike. Exits 2 when none is found
- **Agent** `notion-writeback:notion-fetcher` — a lightweight (haiku) subagent that only fetches and runs the script. It makes no judgment: the word it reports comes from the marker at the head of the output file, and is `ERROR` when there is none — including when the file is empty
- **Skill** `/notion-writeback:notion-writeback` — the procedure: fetch → pull → edit → diff → `replace_content` (sentinel) → fetch again → `CLEAN`

## Prerequisites

- A connected Notion MCP server (not bundled; add `{"type":"http","url":"https://mcp.notion.com/mcp"}` to your `.mcp.json`)
- Python 3 on `PATH` — any of `python3`, `python`, or `py` (the hook and the docs go through `scripts/python.sh`, which picks the first one that exists). If none is found the hook exits 2 and blocks the write rather than letting an unexpanded `@@FILE:...@@` reach the page
- The hook runs in any session that loads the plugin (Claude Code, and Cowork when installed via Customize → Plugins). Hooks written in a project's `.claude/settings.json` are not read by Cowork. If `@@FILE:...@@` is still in the page after a read-back, the hook did not run

## Usage

```text
/notion-writeback:notion-writeback write <page URL> back from docs/page.md
```

See [skills/notion-writeback/SKILL.md](skills/notion-writeback/SKILL.md) for the full procedure (Japanese).
