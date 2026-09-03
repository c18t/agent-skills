---
name: issue-work
description: "GitHub issue 番号を受け取り、専用の worktree を作ってセッションごと移動し、そこで issue を解決して PR を出し、承認を得てから squash merge して worktree を片付ける。issue に着手する・issue の対応を始める・issue 用のブランチを切る・worktree を作って作業する、と言われたときに使う。"
---

# issue から worktree を作って解決する

引数は issue 番号（`123` でも `#123` でも可）。

issue を読み、専用の worktree を作ってセッションごと移動し、その中で実装・検証・コミットまで進めて、
PR 本文をユーザーにレビューしてもらってから PR を作る。
マージの承認を得たら squash merge し、worktree を片付ける。

ユーザーの承認を取るのは 2 箇所（手順 9 の PR 本文と手順 11 のマージ）。それ以外は続けて進めてよい。

GitHub の読み書きは `gh` CLI か GitHub MCP のどちらかで行う。着手前に
[reference/github-mcp.md](reference/github-mcp.md) の判定順で経路を 1 回だけ決める
（`gh auth status` が通れば gh、通らなければ MCP、どちらも無ければ止まる）。
以降の手順は gh のコマンドで書く。MCP 経路では同ファイルの対応表で読み替える。

うまくいかないときは [reference/troubleshooting.md](reference/troubleshooting.md) を見る。
途中で止めるときの扱いも同じファイルにある。

## 手順

### 1. issue を読む

取得するもの: issue のタイトル・本文・ラベル・コメント全部。

```bash
gh issue view <番号>
gh issue view <番号> --comments
```

MCP 経路は `issue_read`（method: `get` と `get_comments`）。

**ここで読んだ内容が手順 6 の判断材料になる**ので、
番号とタイトルだけ取って先に進まない（`--comments` を付けると本文が出ないので、2 回に分けて読む）。

issue が存在しない・権限が無い等で失敗したら**そこで止まる。**

### 2. ブランチ名と worktree パスを決める

ブランチ名は [Conventional Branch](https://conventionalbranch.org/) に従う。

- ブランチ名 … `<接頭辞>/<番号>-<英語スラッグ>`（例 `feature/123-add-login-form`）
- worktree パス … `../<リポジトリ名>-<ブランチ名のスラッシュをハイフンに置換>`
  （例 `../agent-skills-feature-123-add-login-form`）

```bash
basename "$(git rev-parse --show-toplevel)"
```

接頭辞は **issue のラベルを起点に**選ぶ。

| 接頭辞 | 使うとき |
| --- | --- |
| `feature/` | 新機能、および不具合ではない機能改善 |
| `bugfix/` | バグ修正（`fix/` は使わない。「これはバグか」の一問で決まるようにするため） |
| `hotfix/` | 緊急の修正 |
| `release/` | リリース準備 |
| `chore/` | 依存更新・ドキュメントなどコード以外の作業 |

命名の制約は 2 つ。

- 使えるのは**小文字英数字とハイフンのみ**。アンダースコア、ハイフンの連続・先頭・末尾は不可
- issue 番号は `issue-123-` ではなく **`123-` と数字だけ**（パスと VSCode の表示を短く保つため）

ブランチ名の接頭辞と Conventional Commits の type は別物。`bugfix/` ブランチでもコミットは
`fix:` で打つ（手順 8）。あとから名前を変えるときは
[reference/rename-branch.md](reference/rename-branch.md)。

### 3. worktree を作る

```bash
git show-ref --verify --quiet "refs/heads/<ブランチ名>" && echo exists || echo "not exists"
```

| ブランチ | コマンド |
| --- | --- |
| 無い | `git worktree add -b <ブランチ名> <パス>` |
| ある | `git worktree add <パス> <ブランチ名>` |

`git worktree list` で登録を確認する。

### 4. `*.code-workspace` に worktree を登録する

**ローカル限定**（VSCode に worktree を見せるための手順）。Cowork などエディタが
リポジトリを開いていない環境ではスキップしてよい（その場合は 12-d もスキップする）。

**移動する前に行う。** このファイルはメインチェックアウト側にあり、移動後は編集が弾かれる。

リポジトリルートの `*.code-workspace` の `folders` に、`name` にブランチ名をそのまま、
`path` に worktree パスを入れた要素を **Edit で**追記する（JSONC なので全体を書き直さない）。
無ければ `<リポジトリ名>.code-workspace` を新規作成する。

```json
{
  "folders": [
    { "name": "main", "path": "." },
    {
      "name": "feature/123-add-login-form",
      "path": "../agent-skills-feature-123-add-login-form"
    }
  ]
}
```

同じ `path` が既にあれば何もしない。細かい分岐は
[reference/troubleshooting.md](reference/troubleshooting.md) の「`*.code-workspace` の編集」。

### 5. worktree へ移動する

`EnterWorktree` ツールに `path: "<パス>"` を渡してセッションを移す。
初回は承認プロンプトが出るので待つ。移動できたことを `pwd` で確かめてから次へ進む。

`git worktree add` はディレクトリを作るだけでセッションは動かない。**`cd` では代用にならない。**
移動後は Edit / Write / Bash がこの worktree の中だけで通る。

### 6. issue を解決する

手順 1 で読んだ内容をもとに、この worktree の中で実装する。
**着手前に方針を 2〜3 行で示す。** issue の記述が曖昧で方針が複数に割れるなら、そこでユーザーに聞く。

### 7. リンター・型チェックを通す

実行コマンドはプロジェクトから判断する。

| 見る場所 | 例 |
| --- | --- |
| `.mise.toml` | `mise run lint` / `mise run typecheck` |
| `package.json` の `scripts` | `npm run typecheck`（`packageManager` の指定に従う） |
| `.pre-commit-config.yaml` | `pre-commit run --all-files` |
| Go | `staticcheck ./...` |
| Markdown を触った | `markdownlint-cli2 "**/*.md"` |

失敗したら直す。**通らないままコミットへ進まない。**

### 8. コミットする

Conventional Commits に従う。タイトルは `type(scope): description` の英文（80 字程度、
description は小文字始まり・命令形・末尾ピリオドなし）、本文は日本語の箇条書き。

マージ時に squash で 1 つにまとまるので、作業の区切りごとに分けて構わない。

### 9. PR の内容をチャットに書き出す 🛑

PR テンプレートを決めて、見出しを埋めた本文をチャットに全文書き出す。`resolves: #<番号>` を忘れない。

| リポジトリ側 | 使うテンプレート |
| --- | --- |
| `.github/pull_request_template.md` がある | それ |
| 無い | 同梱の既定 [templates/pull_request.md](templates/pull_request.md) |

どちらを使ったかを本文と一緒に 1 行で伝える。
**この手順では push も `gh pr create` も実行しない。** 承認されるまで待つ。

### 10. 承認されたら PR を作る

やること: ブランチを push し、承認された本文で PR を作る。

```bash
git push -u origin <ブランチ名>
gh pr create --title "<タイトル>" --body-file <本文ファイル>
```

MCP 経路は `create_branch` → `push_files` → `create_pull_request`（`git push` の認証が
無い環境向け）。**`push_files` の各 `files[].content` と `create_pull_request` の `body` は
`@@FILE:<相対パス>@@` で渡す**（フックがファイル実体を注入する）。
❗ **push したら `git fetch origin` + `git diff HEAD origin/<ブランチ名>` が空であることを
必ず確認する。** 1 コミットに畳まれる注意と照合手順は
[reference/github-mcp.md](reference/github-mcp.md)。

PR 本文は手順 9 で承認されたものをそのまま使う。作成後、PR の URL を伝える。

### 11. CI を待ち、マージの確認を取る 🛑

まず現状を見る（既に完了していることがある）。見るのは CI チェックの結果全件とマージ可否。

```bash
gh pr checks <PR番号> --json name,bucket --jq '.[] | "\(.name): \(.bucket)"'
gh pr view <PR番号> --json mergeable,mergeStateStatus
```

MCP 経路は `pull_request_read`（method: `get_check_runs` と `get`）。

`pending` が残っていれば、同梱スクリプトを `Monitor` ツールの `command` に渡して待つ。

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr.sh" <PR番号>
```

🔴 `gh pr checks --watch` は使わない。監視ループを Monitor に直接書かない
（worktree 滞在中はハーネスに弾かれる）。理由とスクリプトが担う判断は
[reference/ci-watch.md](reference/ci-watch.md)。
`gh` が無い環境ではスクリプトも動かないので、ポーリングせず都度確認に倒す
（同ファイルの「`gh` が無い環境では都度確認に倒す」）。
❗ **Windows（PowerShell）からも動かない。** `watch-pr.sh` は POSIX シェル前提で、
issue-flow には `.cmd` ラッパーも `commandWindows` も無い。`gh` が無い環境と同じく
**都度確認に倒す**（同ファイルの「Windows（PowerShell）では動かない」）。

CI が落ちたら直してコミットし直す。**落ちたままマージへ進まない。**

CI が通ったら、次の 3 点をチャットに出してユーザーの承認を待つ。

- CI の結果と、マージ可能かどうか（`mergeStateStatus`）
- squash merge 後のコミットタイトル … 手順 9 で承認された PR タイトル＋**末尾に半角スペース＋`(#<PR番号>)`**
  （例 `fix(scope): drop the stale flag (#34)`。GitHub の既定と揃え、`main` の履歴から
  PR を引けるようにする）
- squash merge 後のコミット本文 … 日本語の箇条書き（PR 本文の「なにをやったか」が土台）

**「マージしておいて」と明示的に言われたときだけ手順 12 へ進む。** CI が通っただけでは進めない。

### 12. squash merge して片付ける

- **12-a** worktree を出る

  `ExitWorktree` ツールに `action: "keep"` を渡す（`remove` は使わない。実際に消すのは 12-c）。

  🔴 **マージより先に出る。** worktree の中から `gh pr merge` を実行すると、マージは
  成功するのに `gh` のローカル後処理が失敗して非ゼロ終了する。

- **12-b** マージする

  ```bash
  gh pr merge <PR番号> --squash \
    --subject "<承認されたタイトル> (#<PR番号>)" \
    --body-file <本文ファイル>
  ```

  ❗ **`--subject` の末尾に半角スペース＋`(#<PR番号>)` を付ける。** `--subject` を渡すと GitHub が
  既定で付ける番号が消えるので、自分で書かないと `main` の履歴から PR を引けなくなる。

  MCP 経路は `merge_pull_request`（`merge_method: squash`）。承認されたタイトルは
  `commit_title` に文字列で（**ここでも末尾に半角スペース＋`(#<PR番号>)` を付ける**）、
  **本文はファイルに保存して `commit_message` に `@@FILE:<相対パス>@@`** を渡す。

  `--subject` と `--body-file`（MCP なら `commit_title` / `commit_message`）は必ず渡す
  （省くと GitHub が各コミットのメッセージを連結した本文を既定にする）。
  🔴 **`--delete-branch` は付けない**（ローカル側が worktree に
  checkout されたままなので失敗する。削除は 12-c）。

  失敗したときは、再実行の前に `gh pr view <PR番号> --json state,mergedAt` でマージ済みか確かめる。

- **12-c** worktree とローカルブランチを片付ける

  ```bash
  git worktree remove <パス>
  git branch -D <ブランチ名>
  git push origin --delete <ブランチ名>
  git fetch --prune
  ```

  この順序で行う（worktree を先に消さないとブランチは checkout 中の扱いで消せない）。
  `git worktree remove` が未コミットの変更を理由に拒んだら、**`--force` を付けずに止まり**
  ユーザーに伝える。`git push origin --delete` が「remote ref does not exist」で失敗するのは
  自動削除の設定によるもので正常。MCP 経路にリモートブランチの削除ツールは無い
  （自動削除設定に任せ、残ったら伝える）。

- **12-d** `*.code-workspace` から worktree の記載を消す

  手順 4 をスキップした環境（Cowork など）ではここもスキップする。
  手順 4 で追記した `folders` の要素だけを **Edit で**取り除く。メイン自身の要素・
  他の worktree の要素・`settings` などは残し、新規作成していた場合もファイルごとは消さない。
  メインチェックアウト側への書き込みなので **12-a で出た後に**行う。

- **12-e** マージ済みであることを確認して報告する

  ```bash
  git log --oneline -1 origin/<デフォルトブランチ>
  ```

## 例外時の参照先

| ファイル | 内容 |
| --- | --- |
| [reference/troubleshooting.md](reference/troubleshooting.md) | 落ちる原因（既知）、中断時の扱い、`*.code-workspace` 編集の分岐 |
| [reference/rename-branch.md](reference/rename-branch.md) | 作業途中でブランチ名を変える手順 |
| [reference/ci-watch.md](reference/ci-watch.md) | CI 監視の制約と `watch-pr.sh` が担う判断、`gh` が無い環境での都度確認 |
| [reference/github-mcp.md](reference/github-mcp.md) | 経路の判定と、gh ↔ GitHub MCP の対応表 |
| [templates/pull_request.md](templates/pull_request.md) | リポジトリに PR テンプレートが無いときの既定 |
