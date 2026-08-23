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

## 手順

### 1. issue を読む

```bash
gh issue view <番号>
```

タイトル・本文・ラベル・コメントまで読む。**ここで読んだ内容が手順 6 の判断材料になる**ので、
番号とタイトルだけ取って先に進まない。

issue が存在しない・権限が無い等で失敗したら**そこで止まる**。番号の推測で続けない。

### 2. ブランチ名と worktree パスを決める

ブランチ名は [Conventional Branch](https://conventionalbranch.org/) に従う。

- ブランチ名 … `<接頭辞>/<番号>-<英語スラッグ>`
  スラッグは issue タイトルから起こした小文字ケバブケース（例 `feature/123-add-login-form`）
- worktree パス … `../<リポジトリ名>-<ブランチ名のスラッシュをハイフンに置換>`

接頭辞は **issue のラベルを起点に**選ぶ（`bug` が付いていれば `bugfix/`）。

| 接頭辞 | 使うとき |
| --- | --- |
| `feature/` | 新機能、および不具合ではない機能改善 |
| `bugfix/` | バグ修正 |
| `hotfix/` | 緊急の修正 |
| `release/` | リリース準備 |
| `chore/` | 依存更新・ドキュメントなどコード以外の作業 |

**仕様は `fix/` も `bugfix/` の別名として認めているが、`bugfix/` を採る。**
`fix` は「直す」全般に読めてしまい、不具合ではない小さな改善を前にすると
`feature/` との境界が毎回曖昧になる。`bugfix/` なら判断が「これはバグか」の一問で済む。

命名の制約は 2 つ。

- 使えるのは**小文字英数字とハイフンのみ**。アンダースコアは使えず、
  ハイフンの連続・先頭・末尾も不可
- issue 番号は `issue-123-` ではなく **`123-` と数字だけ**にする
  （接頭辞・リポジトリ名に続く 3 つ目の修飾語が増えると、worktree のパスと
  VSCode の表示が読みにくくなるため）

⚠️ **ブランチ名の接頭辞と Conventional Commits の type は別物。**
Conventional Commits 側に `bugfix` は無いので、`bugfix/` ブランチでも
コミットは `fix:` で打つ（手順 8）。

```bash
basename "$(git rev-parse --show-toplevel)"
```

例：リポジトリ `agent-skills`／ブランチ `feature/123-add-login-form`
→ `../agent-skills-feature-123-add-login-form`

### 3. worktree を作る

- **3-a** ブランチの有無を確認する

  ```bash
  git show-ref --verify --quiet "refs/heads/<ブランチ名>" && echo exists || echo "not exists"
  ```

- **3-b** worktree を作る

  | ブランチ | コマンド |
  | --- | --- |
  | 無い | `git worktree add -b <ブランチ名> <パス>` |
  | ある | `git worktree add <パス> <ブランチ名>` |

- **3-c** `git worktree list` で登録を確認する

### 4. `*.code-workspace` に worktree を登録する

**この手順は移動する前に行う。** 対象ファイルはメインチェックアウト側にあり、
移動後は編集がハーネスに弾かれるため。

リポジトリルートの `*.code-workspace` を探し、次のように分岐する。

| 状態 | やること |
| --- | --- |
| ある | `folders` 配列に要素を追記する。**既存の要素と設定は残す** |
| 無い | `<リポジトリ名>.code-workspace` を新規作成する（メインブランチのパス＝リポジトリルート直下） |

追記する要素は `name` と `path` の 2 つを持たせる。**`name` にはブランチ名をそのまま入れる**
（スラッシュはハイフンに置換しない。VSCode 上でどのブランチの worktree か判別できるようにするため）。

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

新規作成する場合は上の形をそのまま作る。メイン自身の要素は `name` を `"main"`、`path` を `"."` に
する。`folders` 以外の設定は足さない。

既にファイルがあり、メイン自身の要素に `name` が無い場合は**そのまま触らない**。
足すのは今回の worktree の要素だけ。

追記の場合は、**同じ `path` が既に `folders` にあれば何もしない**（再開時の二重登録を防ぐ）。

⚠️ `.code-workspace` は JSONC で、**末尾カンマやコメントが書かれていることがある。**
JSON として読み直して書き戻すとそれらが消えるので、**Edit で要素を挿入する**（ファイル全体を
書き直さない）。既存ファイルの整形スタイル（インデント幅、末尾カンマの有無）に合わせる。

### 5. worktree へ移動する

`EnterWorktree` ツールに `path: "<パス>"` を渡してセッションを移す。
`.claude/worktrees/` の外なので初回は承認プロンプトが出る。これは正常なので承認を待つ。
移動できたことを `pwd` で確かめてから次へ進む。

`git worktree add` はディレクトリを作るだけでセッションはメインチェックアウトに残るため、
移動せずに編集すると変更がメイン側に積まれ、切ったブランチは空のまま残る。
`cd` では代用にならない（cwd は動くが、書き込み権限・`CLAUDE.md`・設定はメイン側のまま）。
移動後は Edit / Write / Bash がこの worktree の中だけで通り、メイン側への書き込みはハーネスが弾く。

### 6. issue を解決する

手順 1 で読んだ内容をもとに、この worktree の中で実装する。
**着手前に方針を 2〜3 行で示す。** issue の記述が曖昧で方針が複数に割れるなら、そこでユーザーに聞く。

### 7. リンター・型チェックを通す

コミット前に必ず実行する。**実行コマンドはプロジェクトから判断する。**

| 見る場所 | 例 |
| --- | --- |
| `.mise.toml` | `mise run lint` / `mise run typecheck` |
| `package.json` の `scripts` | `npm run typecheck`（`packageManager` の指定に従う。pnpm/npm を取り違えない） |
| `.pre-commit-config.yaml` | `pre-commit run --all-files` |
| Go | `staticcheck ./...` |
| Markdown を触った | `markdownlint-cli2 "**/*.md"` |

失敗したら直す。**通らないままコミットへ進まない。**

### 8. コミットする

Conventional Commits に従う。タイトルは `type(scope): description` の英文（80 字程度、
description は小文字始まり・命令形・末尾ピリオドなし）、本文は日本語の箇条書き。

マージ時に squash で 1 つにまとまるので、作業の区切りごとに分けて構わない。

### 9. PR の内容をチャットに書き出す

リポジトリの `.github/pull_request_template.md` を読み、テンプレートの見出しを埋めた本文を
チャットに全文書き出す。`resolves: #<番号>` を忘れない。

そのうえでユーザーのレビューを待つ。この手順では `gh pr create` を実行せず、
承認されるまで push も PR 作成もしない。

### 10. 承認されたら PR を作る

```bash
git push -u origin <ブランチ名>
gh pr create --title "<タイトル>" --body-file <本文ファイル>
```

PR 本文は手順 9 で承認されたものをそのまま使う。作成後、PR の URL を伝える。

コミットはここまでで分かれたままでよい。1 つにまとめるのは手順 12 の squash merge が行う。

### 11. CI を待ち、マージの確認を取る

まず現状を見る。**already 完了していることがあるので、待つ前に確認する。**

```bash
gh pr checks <PR番号> --json name,bucket --jq '.[] | "\(.name): \(.bucket)"'
gh pr view <PR番号> --json mergeable,mergeStateStatus
```

`pending` が残っていれば `Monitor` ツールで待つ。`gh pr checks --watch` は**セッションを
ブロックする**ので使わない。Monitor なら結果が届くまで他の作業を続けられる。

**ループを自分で組まない。** プラグイン同梱のスクリプトを Monitor の `command` に渡す。

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr.sh" <PR番号>
```

完了したチェックを 1 件ずつ出し、全部終わったら
`MERGE STATE: <mergeable> / <mergeStateStatus>` を出して終了する。
ポーリング間隔は第 2 引数で変えられる（既定 30 秒）。

🔴 **監視ループを Monitor の `command` に直接書かない。** worktree に滞在中は
コマンド置換とパイプの連結が「worktree の外に出ないと確認できない」と判定され、
ハーネスに弾かれる
（`this command is too complex to verify that it stays inside the worktree`）。
スクリプト経由なら通る。

⚠️ 弾かれるのはプロセス置換（`<(...)`）だけではない。**コマンド置換とパイプの
組み合わせ程度でも起きる。** 弾かれたら書き換えて粘らず、スクリプトへ逃がす。

スクリプトが引き受けている判断は 3 つある。**自分で書き直すときも落とさない。**

- `bucket` は `pass` / `fail` / `pending` / `skipping` / `cancel` を取る。
  **成功だけを拾う書き方にしない**（落ちたことに気づけなくなる）
- 完了済みを毎回出すと**通知が重複する**ので、前回との差分だけを出す
- jq の `all` は `all(.[]; <条件>)` の形で書く。`all(<条件>)` だと配列自身に条件が
  適用されて常に真になり、**CI を待たずに素通りする**

CI が落ちたら直してコミットし直す。**落ちたままマージへ進まない。**

CI が通ったら、次の 3 点をチャットに出してユーザーの承認を待つ。

- CI の結果と、マージ可能かどうか（`mergeStateStatus`）
- squash merge 後のコミットタイトル … 手順 9 で承認された PR タイトルと同じ英文
- squash merge 後のコミット本文 … 日本語の箇条書き（PR 本文の「なにをやったか」が土台）

**承認されるまでマージしない。** マージは巻き戻しにくい外向きの操作なので、
CI が通っただけでは進めない。ユーザーが GitHub の UI で自分でマージする場合もあるため、
「マージしておいて」と明示的に言われたときだけ手順 12 へ進む。

### 12. squash merge して片付ける

- **12-a** worktree を出る

  `ExitWorktree` ツールに `action: "keep"` を渡す。ここでは `remove` を使わない
  （このスキルの worktree は `.claude/worktrees/` の外にあり `ExitWorktree` の管理外なので、
  実際に消すのは 12-c）。

  🔴 **マージより先に出る。** worktree の中から `gh pr merge` を実行すると、GitHub 側の
  マージは成功するのに `gh` のローカル後処理が
  `fatal: '<デフォルトブランチ>' is already checked out at '<メインのパス>'` で失敗する。
  **コマンドは非ゼロ終了するがマージは完了している**ため、失敗と読んで再実行すると
  マージ済みの PR を操作することになる

- **12-b** マージする

  ```bash
  gh pr merge <PR番号> --squash \
    --subject "<承認されたタイトル>" \
    --body-file <本文ファイル>
  ```

  `--subject` と `--body-file` を渡すのは、**省略すると GitHub が各コミットのメッセージを
  連結した本文を既定にしてしまい、あとから UI で直す必要が出るため。**

  🔴 **`--delete-branch` を付けない。** このフラグはリモートとローカルの両方を消そうとするが、
  ローカル側はこの時点で worktree が checkout したままなので必ず失敗する
  （`Cannot delete branch '<ブランチ名>' checked out at '<worktree のパス>'`）。
  ブランチの削除は 12-c でまとめて行う。

  失敗したときは、**再実行の前に `gh pr view <PR番号> --json state,mergedAt` で
  マージ済みかどうかを確かめる**（`state: MERGED` なら完了している）

- **12-c** worktree とローカルブランチを片付ける

  ```bash
  git worktree remove <パス>
  git branch -D <ブランチ名>
  git push origin --delete <ブランチ名>
  git fetch --prune
  ```

  **順序が要る。** `git worktree remove` を先に済ませないと、ブランチは checkout 中の扱いで
  消せない。

  `git worktree remove` が未コミットの変更を理由に拒んだら、**`--force` を付けずに止まる。**
  何が残っているかをユーザーに伝えて判断を仰ぐ。

  ローカルブランチの削除に `-D` を使うのは、**squash merge が元のコミットとは別の新しい
  コミットを作るため、`-d` が「マージされていない」と判断して拒むから。**
  12-b のマージ成功を確認したうえで実行する。

  リポジトリが「マージ後にブランチを自動削除」する設定なら `git push origin --delete` は
  「remote ref does not exist」で失敗する。**それは正常なので無視してよい。**

- **12-d** `*.code-workspace` から worktree の記載を消す

  手順 4 で追記・作成した `folders` の要素を取り除く。**この worktree の `path` を持つ要素だけを
  消し、メイン自身の要素・他の worktree の要素・`settings` などの設定は残す。**

  手順 4 でファイルを新規作成した場合も、**ファイルごと消さずに `folders` の要素だけ消す**
  （メイン自身の要素が残った状態にする）。ユーザーがその後に設定を足している可能性があるため。

  ⚠️ `.code-workspace` は JSONC で、**末尾カンマやコメントが書かれていることがある。**
  JSON として読み直して書き戻すとそれらが消えるので、**Edit で該当要素の行だけを取り除く。**

  この編集はメインチェックアウト側への書き込みなので、**12-a で worktree を出た後に行う。**

- **12-e** マージ済みであることを確認して報告する

  ```bash
  git log --oneline -1 origin/<デフォルトブランチ>
  ```

## ブランチ名を変えるとき

規約を変えたときや接頭辞を選び違えたときは、**切り直さずに改名する。**
追随させるものが 3 つある（ブランチ・worktree のディレクトリ名・`*.code-workspace` の記載）ので、
順序どおりに進める。

1. worktree の中でブランチを改名する

   ```bash
   git branch -m <新しいブランチ名>
   ```

2. `ExitWorktree` に `action: "keep"` を渡してメイン側へ戻る

   **滞在中のディレクトリは動かせない**ため、次の `git worktree move` より先に出る。

3. worktree のディレクトリを移す

   ```bash
   git worktree move <旧パス> <新パス>
   ```

   🔴 **`mv` を使わない。** git 内部のメタデータ
   （`.git/worktrees/<名前>/gitdir` とリンク先）が古いパスを指したまま壊れる。

4. `*.code-workspace` の該当要素の `name` と `path` を新しいものに直す

   メイン側にいるこのタイミングで行う（手順 4・12-d と同じ理由）。
   JSONC なので **Edit で該当行だけを直す。**

5. `EnterWorktree` に**新しいパス**を渡して入り直す

## マージせずに中断するとき

手順 12 まで進まなかった場合、worktree は残す。レビュー対応や作業の再開がそこで続くため。
`*.code-workspace` の記載もそのまま残す（消すのは worktree を実際に削除するときだけ）。

ユーザーが「戻って」と言ったときは `ExitWorktree` に `action: "keep"` を渡す。
worktree のディレクトリは残るので、`EnterWorktree` に同じ `path` を渡せば再び入れる。

`action: "remove"` は使わない。このスキルの worktree はメインの外に `git worktree add` で
作ったものなので `ExitWorktree` の管理外にあり、削除は `git worktree remove` で行う（手順 12-c）。

## 落ちる原因（既知）

- **`EnterWorktree` が `path` を拒む** … `git worktree list` に出ていないパスは入れない。
  手順 3-b が実際に成功したか確認する。パスは repo ルートからの相対で解決される点にも注意
- **`fatal: '<パス>' already exists`** … 以前の worktree が残っている。
  `git worktree list` で確認し、再利用するか、ユーザーに確認してから片付ける。**黙って消さない**
- **ブランチが既に別の worktree で checkout 済み** … `git worktree add <パス> <ブランチ>` は
  同じブランチを二重に checkout できない。既存の worktree のパスへ `EnterWorktree` で入る
- **移動後にメイン側のファイルを編集しようとする** … ハーネスが弾く。これは事故の防止であって
  不具合ではない。メイン側を触る必要が本当にあるなら、何をなぜ触るのかユーザーに確認する
- **`gh` が未認証** … 手順 1 で落ちる。`gh auth status` を案内する。認証を代行しない
- **リポジトリで squash merge が無効** … `gh pr merge --squash` が拒まれる。
  設定を変えずにユーザーへ伝える。**`--merge` や `--rebase` に勝手に切り替えない**
- **`--subject` / `--body-file` を省く** … GitHub が各コミットのメッセージを連結した本文を
  既定にする。これを避けるのが手順 12-b の目的なので必ず渡す
- **`*.code-workspace` の編集がハーネスに弾かれる** … このファイルはメインチェックアウト側にある。
  追記は移動前（手順 4）、削除は `ExitWorktree` の後（手順 12-d）に行う。
  順序を守っていれば起きない
- **`git worktree remove` が拒む** … 未コミットの変更が残っている。
  `--force` を付けずに止まり、内容をユーザーに伝える
- **worktree の中から `git worktree remove` を実行する** … 自分がいるディレクトリは消せない。
  手順 12-a の `ExitWorktree` で先にメイン側へ戻る
