# issue-work で落ちる原因（既知）と例外時の扱い

`issue-work` スキルの各手順から参照する。手順番号は `SKILL.md` のもの。

## マージせずに中断するとき

手順 12 まで進まなかった場合、worktree は残す。レビュー対応や作業の再開がそこで続くため。
`*.code-workspace` の記載もそのまま残す（消すのは worktree を実際に削除するときだけ）。

ユーザーが「戻って」と言ったときは `ExitWorktree` があれば `action: "keep"` を渡す。
worktree のディレクトリは残るので、`EnterWorktree` に同じ `path` を渡せば再び入れる。Codex では
移動操作をせず、再開時も絶対 `workdir` と preflight を使う。

`action: "remove"` は使わない。このスキルの worktree は手動の `git worktree add` で作るため
`ExitWorktree` の管理外にあり、削除は `git worktree remove` で行う（手順 12-c）。

## worktree の作成・移動まわり

- **`EnterWorktree` が `path` を拒む** … `git worktree list` に出ていないパスは入れない。
  手順 3-b が実際に成功したか確認する。パスは repo ルートからの相対で解決される点にも注意
- **`fatal: '<パス>' already exists`** … 以前の worktree が残っている。
  `git worktree list` で確認し、再利用するか、ユーザーに確認してから片付ける。**黙って消さない**
- **ブランチが既に別の worktree で checkout 済み** … `git worktree add <パス> <ブランチ>` は
  同じブランチを二重に checkout できない。既存の worktree のパスへ `EnterWorktree` で入る
- **`cd` で代用する** … Claude Code では cwd は動いても書き込み権限・`CLAUDE.md`・設定はメイン側の
  ままなので `EnterWorktree` を使う。Codex では `cd` の持続を仮定せず、すべての操作へ絶対
  `workdir` を指定し、`pwd` / top-level / branch の preflight を行う
- **移動後にメイン側のファイルを編集しようとする** … ハーネスが弾く。これは事故の防止であって
  不具合ではない。メイン側を触る必要が本当にあるなら、何をなぜ触るのかユーザーに確認する
- **`*.code-workspace` の編集がハーネスに弾かれる** … このファイルはメインチェックアウト側にある。
  追記は移動前（手順 4）、削除は `ExitWorktree` の後（手順 12-d）に行う。
  順序を守っていれば起きない

## `*.code-workspace` の編集

- ファイルは JSONC で、**末尾カンマやコメントが書かれていることがある。** JSON として読み直して
  書き戻すとそれらが消えるので、**Edit で要素を挿入・削除する**（ファイル全体を書き直さない）。
  既存ファイルの整形スタイル（インデント幅、末尾カンマの有無）に合わせる
- 既にファイルがあり、メイン自身の要素に `name` が無い場合は**そのまま触らない。**
  足すのは今回の worktree の要素だけ
- 同じ `path` が既に `folders` にあれば何もしない（再開時の二重登録を防ぐ）
- 手順 4 でファイルを新規作成した場合も、12-d では**ファイルごと消さずに `folders` の要素だけ消す**
  （メイン自身の要素が残った状態にする）。ユーザーがその後に設定を足している可能性があるため

## `gh` まわり

- **`gh` が未認証** … 手順 1 で落ちる。`gh auth status` を案内する。認証を代行しない。
  GitHub MCP のツールが使えるならそちらの経路で続けられる
  （[github-mcp.md](github-mcp.md) の判定順）
- **`gh` が無い（Cowork など）** … `gh auth status` の案内は解決策にならない。
  GitHub MCP サーバーのセットアップを案内する（プラグイン README の前提）。
  MCP も無ければ止まる
- **issue が存在しない・権限が無い** … 手順 1 で止まる。番号の推測で続けない

## マージまわり

- **worktree の中から `gh pr merge` を実行する** … GitHub 側のマージは成功するのに `gh` の
  ローカル後処理が `fatal: '<デフォルトブランチ>' is already checked out at '<メインのパス>'` で
  失敗する。**コマンドは非ゼロ終了するがマージは完了している**ため、失敗と読んで再実行すると
  マージ済みの PR を操作することになる。12-a で先に出る
- **`gh pr merge` が失敗した** … 再実行の前に `gh pr view <PR番号> --json state,mergedAt` で
  マージ済みかどうかを確かめる（`state: MERGED` なら完了している）
- **`--subject` / `--body-file` を省く** … GitHub が各コミットのメッセージを連結した本文を
  既定にし、あとから UI で直す必要が出る。これを避けるのが手順 12-b の目的なので必ず渡す
- **`--subject` の末尾に半角スペース＋`(#<PR番号>)` を付け忘れる** … `--subject` を渡すと GitHub が
  既定で付ける番号が消える。`main` の履歴から PR を引けなくなるので自分で書く
- **`--delete-branch` を付ける** … リモートとローカルの両方を消そうとするが、ローカル側は
  worktree が checkout したままなので必ず失敗する
  （`Cannot delete branch '<ブランチ名>' checked out at '<worktree のパス>'`）。削除は 12-c で行う
- **リポジトリで squash merge が無効** … `gh pr merge --squash` が拒まれる。
  設定を変えずにユーザーへ伝える。**`--merge` や `--rebase` に勝手に切り替えない**

## 片付けまわり

- **`git worktree remove` が拒む** … 未コミットの変更が残っている。
  `--force` を付けずに止まり、内容をユーザーに伝える
- **worktree の中から `git worktree remove` を実行する** … 自分がいるディレクトリは消せない。
  手順 12-a の `ExitWorktree` で先にメイン側へ戻る。Codex では main checkout の絶対パスを
  `workdir` に指定する
- **cleanup 時に未追跡ファイルがある** … ユーザー所有として残し、`--force` や手動削除を使わず止まる。
  main と worktree の両方で `git status --short` を取り、対象を混同しない
- **`git branch -d` が「マージされていない」と拒む** … squash merge は元のコミットとは別の
  新しいコミットを作るため、`-d` は拒む。12-b のマージ成功を確認したうえで `-D` を使う
- **`git push origin --delete` が「remote ref does not exist」で失敗する** … リポジトリが
  「マージ後にブランチを自動削除」する設定。正常なので無視してよい
