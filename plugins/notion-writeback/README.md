# notion-writeback

Notion MCP（`notion-update-page`）で日本語ページを安定して更新するためのプラグイン。

## 何を解決するか

Notion MCP でページ本文をツール引数に打ち直すと、呼び出しごとに小さな確率で日本語が別の字に化ける。
化けの露出は**呼び出し回数**にほぼ比例し、「長い引数は危ないから分割する」は逆効果だった。

このプラグインは本文がモデルの出力を一切経由しない経路を作る。

- **PreToolUse フック** `scripts/notion_write_guard.py`
  - `replace_content` の `new_str` に `@@FILE:<プロジェクト相対パス>@@` と書くと、ファイル実体を読んで引数に差し替える
  - `update_content` の連打（1 ページ 3 回超・複数置換の同梱・未 fetch ページへの適用）を deny する
- **補助スクリプト** `scripts/notion_mirror.py`
  - `pull` … セッションのトランスクリプトに逐語で残った `notion-fetch` 結果からローカル正本を作る
  - `diff` … ローカル正本と fetch 結果を正規化して照合する（`CLEAN` / `DIRTY` / `STALE`）
- **エージェント** `notion-writeback:notion-fetcher` … fetch とスクリプト実行だけを担う軽量（haiku）サブエージェント。判断はしない
- **スキル** `/notion-writeback:notion-writeback` … fetch → pull → 編集 → diff → `replace_content`（センチネル）→ 再 fetch → `CLEAN` の手順

## 前提

- Notion MCP サーバーが接続済みであること（このプラグインには同梱しない。`.mcp.json` に `{"type":"http","url":"https://mcp.notion.com/mcp"}` を追加する）
- `python3` が PATH にあること
- フックはプラグインが読み込まれたセッションで動く（Claude Code、および Customize → Plugins から入れた Cowork）。プロジェクトの `.claude/settings.json` に書いたフックは Cowork では読まれない。読み戻しで `@@FILE:...@@` が残っていたらフック未作動

## 使い方

```text
/notion-writeback:notion-writeback <ページ URL> を docs/page.md から書き戻して
```

手順の詳細は [skills/notion-writeback/SKILL.md](skills/notion-writeback/SKILL.md)。
