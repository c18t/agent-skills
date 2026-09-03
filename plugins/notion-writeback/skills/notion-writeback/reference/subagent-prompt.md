# サブエージェントへの依頼文（テンプレート）

Claude Code は `Agent` ツールで `subagent_type: "notion-writeback:notion-fetcher"` を指定する。
Codex は `spawn_agent` を使い、下の本文の `<…>` を埋めてそのまま渡す。
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
# macOS / Linux
sh "<CLAUDE_PLUGIN_ROOT>/scripts/python.sh" "<CLAUDE_PLUGIN_ROOT>/scripts/notion_mirror.py" diff --page <ID> --file <ローカル正本> > <出力ディレクトリ>/<ID>.diff.txt 2>&1
# Windows
& "<CLAUDE_PLUGIN_ROOT>\scripts\python.cmd" "<CLAUDE_PLUGIN_ROOT>\scripts\notion_mirror.py" diff --page <ID> --file <ローカル正本> > <出力ディレクトリ>\<ID>.diff.txt 2>&1
```

⚠️ **依頼文に載せるのは実行する環境の 1 行だけ。** 両方渡すとどちらを実行するか迷う。

## pull（ローカル正本の作成）

```text
次のページを notion-fetch してから、ページごとに pull を実行して報告せよ。

ページ:
- <ページ ID or URL> … 書き出し先 <path/to/page.md>

コマンド（作業ディレクトリは <プロジェクトルート>）:
# macOS / Linux
sh "<CLAUDE_PLUGIN_ROOT>/scripts/python.sh" "<CLAUDE_PLUGIN_ROOT>/scripts/notion_mirror.py" pull --page <ID> --out <書き出し先> > <出力ディレクトリ>/<ID>.pull.txt 2>&1
# Windows
& "<CLAUDE_PLUGIN_ROOT>\scripts\python.cmd" "<CLAUDE_PLUGIN_ROOT>\scripts\notion_mirror.py" pull --page <ID> --out <書き出し先> > <出力ディレクトリ>\<ID>.pull.txt 2>&1
```

⚠️ `pull` は既存のローカル正本を**上書きする**。未書き戻しの編集があるページには投げない。

## 受け取ったあと本体がすること

| | 期待値 | 本体が見るもの |
| --- | --- | --- |
| 書き戻し**前** | 編集済みなら `DIRTY` が正常 | 出力ファイルを Read し、**`⚠️消える(Notionのみ)` と `⚠️食い違い` の文脈**（＝消える側）。自分がやっていない変更が混じっていないか。`追記(ローカルのみ)` は自分の編集 |
| 書き戻し**後** | **`CLEAN` の一択** | 報告の一語だけ。`DIRTY` が出たときだけ出力ファイルを読む |
| `ERROR` が返った | — | 🔴 **`CLEAN` と読まない。** 出力ファイルを Read する。空＝スクリプトが起動していない。照合は**未了**なので書き戻さない |

⚠️ **報告行の前後に文章が付いていても読まない**（状況説明・前置きが出ることがある）。
🔴 **報告行だけを抜き出す。** `ERROR` の理由は出力ファイルから取る（→ #33）。

## 依頼文を組むときに実パスへ展開するもの

`<CLAUDE_PLUGIN_ROOT>` は依頼文を組む時点で実パスに展開しておく（サブエージェントの環境で変数が展開される保証がない）。

📌 **`<出力ディレクトリ>` も同じく実パスで渡す。`/tmp` と書かない。**
`/tmp` はシェルによって別の実体に解決される（実測）。

| 実行側 | 着地先 |
| --- | --- |
| PowerShell | ドライブ直下に `C:\tmp\` を**新規作成** |
| Bash (Git Bash) | `C:\Users\<user>\AppData\Local\Temp` |

⚠️ **どちらに落ちたかで報告のパスが変わる**ので、本体が出力ファイルを読もうとして見失う。
`$TEMP` / `$env:TEMP` かプロジェクト内のスクラッチ用ディレクトリを、**実パスに展開して**渡す。
ディレクトリが無いとリダイレクト自体が失敗して出力が空になり、`ERROR` として返る。

## Windows で `sh` を渡さない理由

⚠️ **Windows は `.sh` を直接実行できない。** それでも `sh "…/python.sh"` を渡すと、
PowerShell 側のサブエージェントが先頭の `sh` を呼び出し演算子 `&` に「移植」することがある（実測 → #38）。
そうなると外部プロセスが 1 つも走らず、出力は 0 バイト・`exit` は**空文字**になる。

📌 だから**環境に合う入口をこちらで選んで渡す。** エージェント側の規律に頼らない。
