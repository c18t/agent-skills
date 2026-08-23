# ブランチ名を変えるとき

`issue-work` スキルの手順 2 で決めた名前を、あとから変えるときの手順。
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

   メイン側にいるこのタイミングで行う（手順 4・12-d と同じ理由。このファイルは
   メインチェックアウト側にあり、worktree 滞在中はハーネスが編集を弾く）。
   JSONC なので **Edit で該当行だけを直す。**

5. `EnterWorktree` に**新しいパス**を渡して入り直す
