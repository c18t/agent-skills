# gh と GitHub MCP の対応

3 スキル（issue-draft / issue-work / release-merge）の各手順から参照する。
GitHub の読み書きの経路は `gh` CLI と GitHub MCP サーバーの 2 つで、この表で対応させる。
どちらの経路でも、各手順の 🛑（承認）の位置は変わらない。

## 経路の判定

作業を始める前に 1 回だけ判定し、以降はその経路で通す。

1. `gh auth status` が通る → **gh 経路**。各 SKILL.md のコマンドをそのまま使う
2. 通らない・`gh` が無い → GitHub MCP のツール（`issue_read` など）が使えるか確認する。
   使えれば **MCP 経路**。この表で読み替える
3. どちらも無い → **止まる。** 暗黙のフォールバックや認証の代行はしない。
   Cowork なら GitHub MCP サーバーのセットアップを案内する（プラグイン README の前提を参照）

MCP 経路でも git そのものはローカルの clone に対して使う（worktree・merge・`merge-tree` に
MCP の対応は無い）。リポジトリの clone を作れない環境では `issue-work` / `release-merge` は
完走できないので、そこで止まってユーザーに伝える。

## 対応表

ツール名は [github/github-mcp-server](https://github.com/github/github-mcp-server) のもの。
ハーネスによって `mcp__github__...` や `mcp__remote-devices__github__...` のような接頭辞が付く。
旧版のサーバーでは `get_issue` のようにツールが分かれていることがあるので、
実際に見えているツール名で読み替える。

| やること | gh | GitHub MCP |
| --- | --- | --- |
| リポジトリ概要を見る | `gh repo view` | `search_repositories`（query に `repo:<owner>/<repo>`） |
| issue を一覧する | `gh issue list` | `list_issues` / `search_issues` |
| issue 本文を読む | `gh issue view` | `issue_read`（method: `get`） |
| issue コメントを読む | `gh issue view --comments` | `issue_read`（method: `get_comments`） |
| ラベルの実在を確かめる | `gh label list` | `get_label`（一覧ツールは無い。候補名を 1 つずつ引く） |
| issue を作る 🛑 | `gh issue create` | `issue_write`（method: `create`） |
| issue を編集する | `gh issue edit` | `issue_write`（method: `update`） |
| issue を閉じる | `gh issue close --comment` | `add_issue_comment` → `issue_write`（method: `update`、`state: closed`） |
| ブランチを push する | `git push -u origin <ブランチ>` | `create_branch` → `push_files`（下の注意） |
| PR を作る 🛑 | `gh pr create` | `create_pull_request` |
| PR の状態を見る | `gh pr view --json ...` | `pull_request_read`（method: `get`） |
| PR のコミットを見る | `gh pr view --json commits` | `pull_request_read`（method: `get_commits`） |
| CI チェックを見る | `gh pr checks` | `pull_request_read`（method: `get_check_runs`） |
| PR をマージする 🛑 | `gh pr merge --squash` / `--merge` | `merge_pull_request`（`merge_method` で指定） |
| リモートブランチを消す | `git push origin --delete` | 対応ツール無し（下の注意） |

## 書き込み系でも 🛑 の位置を動かさない

`issue_write`（create）・`create_pull_request`・`merge_pull_request` は、gh 経路と同じ場所で
承認を取ってから呼ぶ。MCP ツールの実行前確認はハーネス依存で、確認なしに通る環境もある。
スキル側の承認ゲートがその代わりなので、経路が MCP でも位置を変えない。

## MCP 経路の注意

- **本文はファイルでなく文字列で渡す。** `--body-file` は gh 経路のシェル事故
  （引用符・改行・バッククォート）を避けるための手当てで、MCP はツール引数に本文を
  そのまま渡せる。承認済みの本文を一字も変えずに渡す
- **`merge_pull_request` には `commit_title` / `commit_message` を必ず渡す。**
  `--subject` / `--body-file` と同じ理由（省くと GitHub が各コミットのメッセージを連結した
  本文を既定にする）
- **`push_files` は 1 回の呼び出しが 1 コミット。** ローカルの複数コミットをそのまま送る手段は
  無い。`create_branch`（起点はデフォルトブランチ）でリモートに同名ブランチを作り、変更した
  全ファイルを 1 回の `push_files` で積む。`issue-work` は squash merge 前提なので、
  コミット粒度が失われても結果は変わらない
- **`push_files` で積んだあとのローカルブランチはリモートと履歴が分かれる。** 以降の修正も
  「ローカルで編集 → 変更ファイルを `push_files`」で通す。リモート履歴との同期を取り直そうと
  しない
- 🔴 **`release-merge` の release ブランチは `push_files` で代用できない。** API 経由の push は
  新しいコミットを作るため、ローカル merge で積んだ各 PR の head SHA がリモートに乗らず、
  含まれる PR が 1 本も自動クローズしなくなる（`release-merge` スキルの
  [auto-close.md](../../release-merge/reference/auto-close.md) と同じ理屈）。
  `git push` できる認証が無い環境では、`release-merge` は push の前で止まって
  ユーザーに伝える
- **リモートブランチの削除ツールは無い。** マージ後の削除はリポジトリの自動削除設定
  （`deleteBranchOnMerge`）に任せ、残った場合はその旨をユーザーに伝えるだけにする
