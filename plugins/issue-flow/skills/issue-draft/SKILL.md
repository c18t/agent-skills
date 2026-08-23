---
name: issue-draft
description: "やりたいことを受け取って GitHub issue の本文を起草し、チャットでレビューを受けてから gh issue create で作る。タイトルは英語・本文は日本語、ラベルは実在確認してから選ぶ。issue を作る・issue を立てる・issue を起票する・バグを issue にする・要望を issue にまとめる、と言われたときに使う。"
---

# issue を起草して作る

引数は作りたい issue のテーマ（自由文）。省略されたら何の issue かをユーザーに聞く。

テーマを受け取ったらリポジトリの状況を調べ、タイトル・本文・ラベルを組み立てて、
**チャットに全文を書き出してユーザーのレビューを待つ。** 承認されたら `gh issue create` で作り、
作った issue に着手するための導線を示して終わる。

ユーザーの承認を取るのは 1 箇所（手順 6 の本文レビュー）。それ以外は続けて進めてよい。

GitHub の読み書きは `gh` CLI か GitHub MCP のどちらかで行う。着手前に
[../issue-work/reference/github-mcp.md](../issue-work/reference/github-mcp.md) の判定順で
経路を 1 回だけ決める（`gh auth status` が通れば gh、通らなければ MCP、どちらも無ければ止まる）。
以降の手順は gh のコマンドで書く。MCP 経路では同ファイルの対応表で読み替える。

このスキルは issue を**作る**側。作った issue に着手するのは `issue-work` スキルの担当で、
このスキルからは呼び出さない（手順 8）。

うまくいかないときは [reference/troubleshooting.md](reference/troubleshooting.md) を見る。

## 手順

### 1. リポジトリと既存 issue を確認する

取得するもの: リポジトリの概要と、全 state の既存 issue 一覧。

```bash
gh repo view --json nameWithOwner,description
gh issue list --limit 30 --state all
```

MCP 経路は `search_repositories`（query に `repo:<owner>/<repo>`）と `list_issues`。

同じ話題の issue が既にあれば、新しく作るか既存に足すかをユーザーに聞く。
`gh` が未認証で MCP も使えなければここで止まる
（[../issue-work/reference/github-mcp.md](../issue-work/reference/github-mcp.md) の判定順）。

### 2. issue テンプレートを決める

```bash
ls .github/ISSUE_TEMPLATE/ 2>/dev/null
```

| リポジトリ側 | 使うテンプレート |
| --- | --- |
| ある | その中から適切なものを読み、見出しをそのまま使う |
| 無い | 同梱の既定 [templates/issue.md](templates/issue.md)（背景 / やること / 影響範囲 / 補足） |

リポジトリ側の見出しを優先し、既定形で上書きしない。
どちらを使ったかは手順 6 で本文と一緒に 1 行で伝える。

### 3. ラベルを決める

やること: リポジトリに実在するラベルの確認。

```bash
gh label list
```

MCP 経路に一覧ツールは無いので、`get_label` で候補名（下の目安）を 1 つずつ実在確認する。

**実在するラベルだけを選ぶ。** 目安は次のとおり。

| 内容 | ラベル |
| --- | --- |
| 不具合・壊れている | `bug` |
| 規約の変更・機能追加 | `enhancement` |
| ドキュメントの追加・改善 | `documentation` |

収まらない・決めきれないときはユーザーに聞く。ラベルが未整備なら無しで作ってよい。

### 4. タイトルを決める

**英語。** `<対象>: <英文>` の形。`<対象>` はプラグイン名・コンポーネント名・ファイル名など、
どこの話かが分かる語。description は小文字始まり・命令形・末尾ピリオドなし。

```text
issue-flow: follow Conventional Branch for branch naming
notion-writeback: resolve python3 launcher on Windows
```

### 5. 本文を起草する

**日本語。** 手順 2 で決めたテンプレートの見出しを埋める。既定形の各見出しに書くこと:

| 見出し | 書くこと |
| --- | --- |
| **背景** | 現状どうなっていて何が問題か。なぜ今これを挙げるのか |
| **やること** | 具体的な変更。**判断が要るものは根拠も書く** |
| **影響範囲** | 破壊的変更かどうか、version をどう上げるか、他への波及 |
| **補足** | 分割元の PR、参考リンク、検証済みの事実 |

**「やること」に判断の根拠を残すのがこのスキルの主目的。** 「〜する」だけを並べない。

採番前の自分の番号は本文に書かない（相互参照は手順 8 で追記する）。

### 6. 本文をチャットに書き出してレビューを待つ 🛑

タイトル・ラベル・本文の全文と、使ったテンプレート（リポジトリ側か同梱の既定か）をチャットに出す。
**`gh issue create` はまだ実行しない。**

### 7. 承認されたら作成する

本文をファイルに書いてから渡す（`--body` に直接渡さない）。

```bash
gh issue create --title "<タイトル>" --body-file <本文ファイル> --label <ラベル>
```

MCP 経路は `issue_write`（method: `create`）。**本文は gh 経路と同じくファイルに保存し、
`body` には `@@FILE:<本文ファイルの相対パス>@@` だけを渡す**（フックがファイル実体を
注入するので、承認済みの本文がモデルの転記を経由しない。
[../issue-work/reference/github-mcp.md](../issue-work/reference/github-mcp.md)）。

ラベルを複数付けるときは `--label a --label b` と繰り返す。
失敗したらそのまま再実行せず、エラーメッセージから原因を特定する。

### 8. URL を報告し、着手の導線を示す

作成された issue の URL と番号を伝え、着手するためのコマンドを提示して終わる。

```text
/issue-flow:issue-work <番号>
```

**`issue-work` を自分で呼び出さない。** 続けて着手するかはユーザーが決める。
手順 5 で相互参照を保留していた場合は、ここで `gh issue edit <番号> --body-file <ファイル>`
（MCP 経路は `issue_write` の method: `update`。`body` はセンチネルで渡す）で追記する。

## 例外時の参照先

| ファイル | 内容 |
| --- | --- |
| [reference/troubleshooting.md](reference/troubleshooting.md) | 落ちる原因（既知）と対処 |
| [../issue-work/reference/github-mcp.md](../issue-work/reference/github-mcp.md) | 経路の判定と、gh ↔ GitHub MCP の対応表 |
| [templates/issue.md](templates/issue.md) | リポジトリにテンプレートが無いときの既定 |
