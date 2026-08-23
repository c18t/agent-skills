# Notion MCP の実測メモ

手順書（SKILL.md）の根拠になっている観測。Notion MCP（`https://mcp.notion.com/mcp`）と Claude Code の組み合わせで得たもの。

## fetch

- **`notion-fetch` が 1 回で返る実用上限は約 30,000 字**（約 60,000 字は上限超過で返らなかった）。ページがこれを超えそうなら子ページへ分ける
- **出力上限を超えた結果は失われない。** `~/.claude/projects/<プロジェクト>/<セッション>/tool-results/*.txt` に退避され、`notion_mirror.py` はそこからも読む。`exceeds maximum allowed tokens` は**正常でリトライ不要**——サブエージェントに委譲するときは必ずこれを明記する（書かないとリトライしたり失敗と報告したりする）
- **サブエージェントの fetch 結果は親の JSONL に入らない。** `<セッション>/subagents/agent-*.jsonl` に残る。`notion_mirror.py` は両方を見る
- トランスクリプトの選択は `CLAUDE_CODE_SESSION_ID` を最優先する。mtime で最新を選ぶと**同時に動いている別セッション**を掴み、同じページが CLEAN → 数十秒後に STALE になる
- ツール結果は「JSON 文字列の中の JSON 文字列」で二重にエンコードされている。ページ ID は祖先・子ページのリンクにも出るので、**最初の `<page url=…>` が自ページ**

## 検証

- **書いた直後に必ず `notion-fetch` で読み戻す。** 検出できる手段はこれだけ
- **`notion-search` はインデックスに数分のラグがあり検証には使えない**
- 化けは「漢字が似た別字になる」より「単語が別語に置換される」傾向がある。字面ではなく意味が通るかを読む
- `replace_content` の実績：18,000 字・703 行をバイト単位で一致、1 日で計 42,247 字を化けゼロ

## 本文の書き方

- **Notion は番号付きリストの番号を保存時に正規化する。** 番号を意味として持たせたいなら本文ラベル（`ルール N` など）にする
- **表のセルの中に表の構造タグと同じ字面を書かない。** バッククォートで囲んでもパーサがそこで表を打ち切り、以降の行の右側の列が消えた実測あり。段落に書くぶんには壊れない
- Markdown のパイプ表と `<table>` タグは往復で同一になる。手動変換は不要
- 子ページ参照は `<page url="https://app.notion.com/p/<id>">タイトル</page>` の形で本文に残す。消すと `This operation would delete N child page(s)` で落ちる
- `<database>` タグは fetch 結果を一字も変えずに含めれば `replace_content` で安全（レコード 105 件・ビュー名・フィルタ・スキーマが保たれた）。`allow_deleting_content` は不要
- データベースのレコード本体はページ本文ではないので fetch にも mirror にも出ない。DB の中身は Notion 側で操作する

## フック

- `updatedInput` は部分マージではなく **tool_input 全体を置き換える**。注入フィールドを重ねた完全な dict を返す
- Windows（cp932）では絵文字を `print()` すると `UnicodeEncodeError` でフックが**出力なしで落ち**、Claude Code は「意見なし」として素通しする。stdout/stdin はバイト列で UTF-8 を明示する
- フックの matcher は `mcp__.*notion-update-page`。サーバー名が UUID でも `notion` でも掛かる
- `notion-create-pages` にはフックが掛からない。新規ページは空で作ってから `replace_content`＋センチネルで本文を入れる
