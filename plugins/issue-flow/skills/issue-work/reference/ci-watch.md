# CI の監視と worktree 滞在中の制約

`issue-work` スキルの手順 11（`release-merge` スキルでは手順 10）から参照する。
このページの `gh` / `watch-pr.sh` は gh 経路のもの。`gh` が無い環境（Cowork など）は
最後の「`gh` が無い環境では都度確認に倒す」を読む。

## `gh pr checks --watch` を使わない

セッションをブロックする。`Monitor` ツールなら結果が届くまで他の作業を続けられる。

## 監視ループを Monitor の `command` に直接書かない

🔴 worktree に滞在中は、コマンド置換とパイプの連結が「worktree の外に出ないと確認できない」と
判定され、ハーネスに弾かれる。

```text
this command is too complex to verify that it stays inside the worktree
```

弾かれるのはプロセス置換（`<(...)`）だけではない。**コマンド置換とパイプの組み合わせ程度でも
起きる。** 弾かれたら書き換えて粘らず、プラグイン同梱のスクリプトへ逃がす。

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr.sh" <PR番号>
```

完了したチェックを 1 件ずつ出し、全部終わったら
`MERGE STATE: <mergeable> / <mergeStateStatus>` を出して終了する。
ポーリング間隔は第 2 引数で変えられる（既定 30 秒）。

## スクリプトが引き受けている 3 つの判断

自分で書き直すときも落とさない。

- `bucket` は `pass` / `fail` / `pending` / `skipping` / `cancel` を取る。
  **成功だけを拾う書き方にしない**（落ちたことに気づけなくなる）
- 完了済みを毎回出すと**通知が重複する**ので、前回との差分だけを出す
- jq の `all` は `all(.[]; <条件>)` の形で書く。`all(<条件>)` だと配列自身に条件が
  適用されて常に真になり、**CI を待たずに素通りする**

## 待つ前に現状を見る

既に完了していることがある。

```bash
gh pr checks <PR番号> --json name,bucket --jq '.[] | "\(.name): \(.bucket)"'
gh pr view <PR番号> --json mergeable,mergeStateStatus
```

`pending` が残っているときだけ Monitor で待つ。

## `gh` が無い環境では都度確認に倒す

`watch-pr.sh` は `gh pr checks` 前提なので、`gh` が無い環境（Cowork など。経路の判定は
[github-mcp.md](github-mcp.md)）では動かない。そして `Monitor` の `command` はシェルしか
実行できず、MCP ツールを呼ぶ手段が無い。つまり **MCP 経路ではポーリング監視をしない。**
代わりに都度確認する。

- `pull_request_read`（method: `get_check_runs`）で check run を**全件**見る。
  **成功だけを拾わない**のはスクリプトと同じ。conclusion の `failure` / `cancelled` /
  `timed_out` も終端で、見落とすと落ちた CI に気づけない
- `queued` / `in_progress` が残っていたら、どれくらい待つかを伝えてから時間を置き、
  同じ呼び出しを繰り返す。完了通知は来ない
- 全部終わったら `pull_request_read`（method: `get`）の mergeable 系フィールドで
  マージ可能かを見る（`gh pr view --json mergeable,mergeStateStatus` 相当）

スクリプトが引き受けている 3 つの判断のうち「成功だけを拾わない」はここでも守る。
「差分だけを出す」「jq の `all`」はポーリングしないので関係しない。

## Windows（PowerShell）では動かない

`gh` があっても `watch-pr.sh` は起動しない。**上の都度確認と同じ扱いにする**
（`gh` はあるので、コマンドは `gh pr checks` / `gh pr view` をそのまま使う）。

- issue-flow の `scripts/` は **POSIX シェル前提**で、notion-writeback の `python.cmd` に
  相当するラッパーが無い。`hooks.json` にも `commandWindows` が無い
- PowerShell は先頭の `sh` を `&` に書き換えるため、**外部プロセスが 1 つも起動しない**。
  終了コードが数字ですらなく空文字で返るのがその合図（→ #38）

Codex / Windows 対応は**未実装で、既知の制約**。🔴 **回避のためにスクリプトを書き直さない。**
