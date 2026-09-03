# Codex で issue-work の作業境界を守る

`EnterWorktree` / `ExitWorktree` が公開されていない Codex では、チャット全体の cwd や全ツールの
書き込み境界を worktree へ移す API があると仮定しない。固定配置、絶対 `workdir`、操作直前の
preflight で Claude Code の隔離に相当する境界を作る。

## worktree へ入る代わりの規約

worktree は `<main-root>/.claude/worktrees/<branch-slug>` に作り、その絶対パスをチャットに示す。
`.claude/worktrees/` は Claude Code の既定配置でもあり、`EnterWorktree` 利用時の都度承認を避けられる。
手動の `git worktree add` で作った worktree は Claude Code の自動掃除対象ではない。

Codex では Git、テスト、検索、ファイル読み書きの**すべて**に worktree の絶対パスを `workdir` として
渡す。相対パスだけで境界を推測せず、main checkout を作業用 `workdir` にしない。

各操作の直前に、同じ `workdir` で次を検査する。

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
```

`pwd` と top-level が予定した worktree の絶対パスに一致し、ブランチが予定名に一致したときだけ
続ける。main、別ブランチ、別 top-level のどれかを指したら編集や Git 書き込みを止め、`workdir` を
直す。main と worktree の `git status --short` を節目ごとに確認し、変更の混在を早期に検出する。

## merge と cleanup

Codex では `ExitWorktree` の代わりに、メイン checkout の絶対パスを `workdir` として明示する。
`gh pr merge`、`git worktree remove`、ローカルブランチ削除、workspace 登録解除は worktree 外から行う。

cleanup 前に main と worktree の両方で `git status --short` を取り、worktree 側が clean であることを
確認する。main の既存変更と未追跡ファイルはユーザー所有として扱い、復元・上書き・削除しない。
worktree に未コミット変更や未追跡ファイルがあれば `git worktree remove --force` を使わず止まる。

## plugin 開発中の cache 更新

plugin 自身を変更する issue では、読み込まれている cache と作業中 worktree を同一視しない。
再インストール前に marketplace の local source が main ではなく、今回の worktree 内の plugin を
指していることを確認する。違っていれば marketplace を手編集せず、plugin 管理手順に従って直す。

source の一致を確認したあと、plugin-creator の helper で cachebuster を更新して再インストールする。
cachebuster は作業中 worktree の manifest に対して実行する。新しい skill / hook は現在の thread へ
後付けされたとは見なさず、再インストール後に新しい thread を開いて読み直す。

## hook が実際に適用されたか検証する

plugin から Codex UI の `/hooks` に表示される Trusted 状態を直接取得できるとは仮定しない。
ユーザーに `/hooks` の Source、Matcher、Trust を確認してもらう。ツール名はランタイムで異なり得る。
たとえば Claude Code の `notion-update-page` に対し、Codex では `notion_update_page` になり得るため、
Trusted だけでなく Matcher が**実際のツール名**へ一致するかを確認する。

最終判断は表示ではなく実行結果で行う。PreToolUse の `updatedInput` / `systemMessage`、または書き込み後の
再 fetch で今回渡した内容が反映されたことを確かめる。`@@FILE:` を使う検証では、今回送った一意な
センチネルだけを追跡する。過去のページ本文に元から含まれる `@@FILE:` を未展開の証拠にしない。

## sandbox の保存先

`.codex/tmp` などへ本文ファイルを保存するときは、そのパスが現在の sandbox の writable root に
含まれるか先に確認する。permission denied や sandbox deny を内容の不具合として扱わず、書き込み可能な
worktree 内の保存先へ切り替える。権限拡張が必要なら暗黙に回避せず、理由と対象を示して承認を取る。
