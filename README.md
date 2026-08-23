# agent-skills

Personal agent skills and Claude Code plugin marketplace.

## マーケットプレイスの追加とインストール

```text
/plugin marketplace add c18t/agent-skills
/plugin install notion-writeback@agent-skills
```

## プラグイン

| 名前 | 概要 |
| --- | --- |
| [notion-writeback](plugins/notion-writeback/README.md) | Notion MCP を安定して使うためのフックとスキル。`@@FILE:` センチネルで本文をファイルから直接注入し、`update_content` の連打を止める |

## 開発

```bash
claude --plugin-dir ./plugins/notion-writeback
```

```bash
claude plugin validate ./plugins/notion-writeback
```

Markdown は `markdownlint-cli2 "**/*.md"` で検査する。
