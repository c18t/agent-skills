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

次の節のセンチネルは承認ゲートと直交する。**チャットで本文の承認を取る →
その本文をファイルに保存する → センチネルで渡す**の順で、承認したものがそのまま届く。

## 本文とファイル内容は `@@FILE:` センチネルで渡す

本文をファイルに保存し、ツール引数には `@@FILE:<基準ディレクトリからの相対パス>@@`
**だけ**を書く（他の文字を混ぜない。文中に埋め込むと展開されない）。
同梱の PreToolUse フックがファイル実体を読んで引数に差し替えるので、内容は
ディスク → フック → API と流れ、**モデルの転記を一切経由しない。**

| ツール | センチネルを書くフィールド |
| --- | --- |
| `push_files` | `files[].content`（要素ごとに独立。一部だけセンチネルでもよい） |
| `create_or_update_file` | `content` |
| `issue_write` | `body` |
| `create_pull_request` | `body` |
| `add_issue_comment` | `body` |
| `merge_pull_request` | `commit_message` |

タイトル（`commit_title` など 1 行のもの）は文字列でそのまま渡してよい。

**なぜ必要か。** MCP はツール引数に本文をそのまま渡せる——が、その「そのまま」を
作るのはモデルの転記であり、`--body-file` が持っていた「ファイル実体がモデルの出力を
一切経由しない」という性質は失われている。実際に PR #28 で、10 ファイルの `push_files` の
うち 3 ファイルで「続けて**進めて**よい」が「続けて**進んで**よい」に置き換わった。
意味の近い自然な言い回しへ無意識に "補正" する壊れ方で、**目視レビューでは検出できない。**

**注入できなければ止まる（フェイルクローズ）。** ファイルが無い・基準ディレクトリの外を
指した・UTF-8 で読めない場合、フックは注入せず**呼び出しごと deny する**。
`@@FILE:...@@` という文字列がそのまま push されコミットに乗るのが最悪ケースなので、
注入できないなら止める。deny の理由にはどのフィールド（`files[2].content` など）かが出る。

**パスの基準ディレクトリ**は `CLAUDE_PROJECT_DIR` → フック入力の `cwd` → カレントの順に
決まる。Claude Code では起動位置に依らずリポジトリルート、Cowork ではセッションの `cwd`。
基準の外は `../` でも symlink 経由でも指せない。

### フックが動かない環境

判定は環境の推測ではなく**結果の読み戻しで行う**。呼び出したあと本文やファイル内容に
`@@FILE:...@@` が残っていたら、フックが動いていない。そのときは:

1. プラグインが有効か確認する。Codex ではユーザーに `/hooks` の Source / Matcher / Trust を
   確認してもらい、Matcher が UI に出る**実際の MCP ツール名**へ一致するかを見る。Trusted 表示だけでは
   適用済みと判断しない。Claude Code のハイフン区切りと Codex のアンダースコア区切りなど、
   ランタイム間で名前が異なる場合がある。Python 3（`python3` / `python` / `py`）が `PATH` に
   無い場合もフックは起動しない
2. `updatedInput` / `systemMessage` が確認できるなら今回のセンチネルが展開されたかを見る。
   見えない環境では書き込み後に再取得し、今回送った一意なセンチネルだけを検査する。過去の本文に
   元から含まれる `@@FILE:` は判定対象にしない
3. それでも動かないなら、**直前にファイル全文を Read してから**その内容を文字列で渡す。
   🔴 **記憶から書かない**
4. 下の照合を必ず取る

本文ファイルを `.codex/tmp` などへ置く場合は sandbox の writable root を先に確認する。書き込みが
拒否されたら、書き込み可能な worktree 内へ保存するか、必要な権限を明示して承認を取る。

### `push_files` の後は必ず照合する

フックの有無に関わらず行う。🔴 **フックを入れたあとも外さない**——フックが起動しない
環境ではセンチネルも効かないので、これが最後の防波堤になる。

```bash
git fetch origin
git diff HEAD origin/<ブランチ>
```

**diff が空であること**を確認する。空でなければ、リモートに乗った内容がローカルと違う
＝引数がどこかで書き換わっている。差分の出たファイルを `push_files` で送り直し、
もう一度照合する。

📌 PR #28 の転記ミス（3 ファイルの「進めて」→「進んで」）を実際に検出したのがこの照合。
CI もレビューも通り抜けた。

## MCP 経路の注意

- 🔴 **本文とファイル内容は `@@FILE:` センチネルで渡す。これが既定。**
  対象フィールドとフェイルクローズの扱いは上の「本文とファイル内容は `@@FILE:`
  センチネルで渡す」節にまとめてある
- **`merge_pull_request` には `commit_title` / `commit_message` を必ず渡す。**
  `--subject` / `--body-file` と同じ理由（省くと GitHub が各コミットのメッセージを連結した
  本文を既定にする）。❗ **`commit_title` の末尾には半角スペース＋`(#<PR番号>)` を付ける**
  （渡した時点で GitHub の既定の番号が消えるため）
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
