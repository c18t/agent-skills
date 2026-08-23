# サブエージェントへの依頼文（テンプレート）

`Agent` ツールで `subagent_type: "notion-writeback:notion-fetcher"` を指定し、下の本文の `<…>` を埋めてそのまま渡す。
エージェント側の振る舞い（リトライ禁止・要約禁止・報告形式）は `agents/notion-fetcher.md` に固定してあるので、
依頼文に書くのは**対象と引数だけ**でよい。

複数ページをまとめて 1 回の依頼にしてよい（9 ページを 1 回で回した実績）。

## diff（書き戻し前・後の照合）

```text
次のページを notion-fetch してから、ページごとに diff を実行して報告せよ。

ページ:
- <ページ ID or URL 1> … ローカル正本 <path/to/page1.md>
- <ページ ID or URL 2> … ローカル正本 <path/to/page2.md>

コマンド（ページごと、作業ディレクトリは <プロジェクトルート>）:
sh "<CLAUDE_PLUGIN_ROOT>/scripts/python.sh" "<CLAUDE_PLUGIN_ROOT>/scripts/notion_mirror.py" diff --page <ID> --file <ローカル正本> > <出力ディレクトリ>/<ID>.diff.txt 2>&1
```

## pull（ローカル正本の作成）

```text
次のページを notion-fetch してから、ページごとに pull を実行して報告せよ。

ページ:
- <ページ ID or URL> … 書き出し先 <path/to/page.md>

コマンド（作業ディレクトリは <プロジェクトルート>）:
sh "<CLAUDE_PLUGIN_ROOT>/scripts/python.sh" "<CLAUDE_PLUGIN_ROOT>/scripts/notion_mirror.py" pull --page <ID> --out <書き出し先> > <出力ディレクトリ>/<ID>.pull.txt 2>&1
```

⚠️ `pull` は既存のローカル正本を**上書きする**。未書き戻しの編集があるページには投げない。

## 受け取ったあと本体がすること

| | 期待値 | 本体が見るもの |
| --- | --- | --- |
| 書き戻し**前** | 編集済みなら `DIRTY` が正常 | 出力ファイルを Read し、**`delete` の文脈だけ**（＝消える側）。自分がやっていない変更が混じっていないか |
| 書き戻し**後** | **`CLEAN` の一択** | 報告の一語だけ。`DIRTY` が出たときだけ出力ファイルを読む |

`<CLAUDE_PLUGIN_ROOT>` は依頼文を組む時点で実パスに展開しておく（サブエージェントの環境で変数が展開される保証がない）。
