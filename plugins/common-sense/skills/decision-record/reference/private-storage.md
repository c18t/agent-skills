# 非公開 ADR の保存先

非公開の判断は、公開リポジトリごとに 1 つの companion repository へ保存する。companion repository の
名前は `<repository>-decisions` とし、可視性は private にする。

## 配置と解決方法

ローカルの clone は 1 つだけ、次の場所へ配置する。

```text
<main checkout>/.claude/decisions/<repository>-decisions/
```

`.claude/decisions/` は `.claude/worktrees/` と並列に置く。各 worktree の中へ clone するのではない。
linked worktree から Git の absolute common directory を経由して main checkout を求めるため、main と
すべての worktree が同じ clone を使える。ユーザー固有の絶対パスを tracked file に書かず、worktree
ごとに clone を作らない。

同梱 helper で保存先を解決・検証する。

```bash
sh "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/python.sh" \
  "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/decision_store.py" check --repository "$PWD"
```

Windows では同じ Python script を `scripts/python.cmd` から呼ぶ。成功すると `docs/decisions/` の絶対パスを
出力する。clone が無い、独立した Git repository ではない、または書き込めない場合は安全側に停止する。

Claude Code で worktree に入っている間、共有 clone はその worktree の外にある。読み書きが拒否されたら
worktree 内へ複製せず、`ExitWorktree` の `action: "keep"` で一度出てから共有 clone を操作する。Codex では
共有 clone の絶対パスを `workdir` に指定し、必要ならそのパスへの権限を明示して承認を取る。

## 初回セットアップ

1. 公開リポジトリの既存内容を残したまま `.gitignore` へ `.claude/decisions/` を追記し、この公開設定の変更を
   commit する。
2. リポジトリの既存指示を残したまま、次の規約を `AGENTS.md` へ追記する。

   ```markdown
   ## Architecture decisions

   公開 ADR は `docs/decisions/`、非公開 ADR は private な `<repository>-decisions` companion repository
   へ保存する。共有するローカル clone は common-sense の `decision_store.py check` helper で解決し、
   worktree ごとに複製したり絶対パスを記録したりしない。新しい ADR を書く前に既存 ADR を検索し、
   非公開 ADR は companion repository からだけ commit する。
   ```

3. `decision_store.py setup --repository <checkout>` を実行する。companion repository が存在しなければ、
   helper は GitHub を変更する前に停止する。作成する private repository の名前をユーザーに示し、実行直前に
   承認を得てから `--approve-create` を付けて再実行する。この flag は今回の実行について承認済みであることを
   表す。推測で付けたり、以前の承認を再利用したりしない。
4. main checkout と使用中の各 worktree から `check` を再実行し、すべてが同じパスを出力することを確かめる。

helper は clone 前に private visibility を確認する。repository が存在するがアクセスできない場合は、外部で
存在しないことを確認してから作成する。同名の代替 repository を作らない。

## 安全な利用と復旧

ADR を読み書きする前に `check` を実行する。返された directory で同じ論点と supersede 済みの ADR を探す。
`git -C <返された docs directory> ...` で書き込みと commit を行う。commit 前に公開 checkout の
`git status --short` と `git diff --cached` を確認し、ADR の内容が一切現れないことを確かめる。

`check` が clone 不在を報告したら setup をやり直す。アクセス不能を報告したら filesystem の権限を直すか、
clone を規定の場所へ戻す。public tree、別の worktree、未追跡の一時 directory へフォールバックしない。
フォールバックすると非公開の判断が漏れたり、worktree 間で判断が分岐したりする。
