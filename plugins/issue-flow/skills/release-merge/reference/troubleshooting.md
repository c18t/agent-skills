# release-merge で落ちる原因（既知）と例外時の扱い

`release-merge` スキルの各手順から参照する。手順番号は `SKILL.md` のもの。

## 統合をやめるとき

release ブランチを main に入れずに終える場合、**手順 6 の既定（base を張り替えない）に
従っていれば実害はない。** 含まれる PR は OPEN のまま残るので、release ブランチと worktree を
片付ければ元に戻る（12-c / 12-d の手順をそのまま使う）。

base を張り替えていた場合は戻せない。**PR は Merged で固定され、再オープンできない。**
その状態に気づいたら、release ブランチを**破棄せずに** main へ入れる。

## base を張り替えてはいけない理由

🔴 `gh pr edit --base` で PR の base を release ブランチへ張り替えない。
**PR のクローズ条件は「自分の base へマージされること」であって、main への到達ではない。**
張り替えた瞬間からその PR は release を見るので、release へマージした時点で
**Merged になる。まだ main には何も入っていないのに。** ここから 2 つの実害が出る。

1. **PR が再オープンできなくなる。** この時点で release ブランチを破棄すると、
   PR は Merged なのに main には何も無い状態で固定される
2. **`deleteBranchOnMerge` が有効なリポジトリでは feature ブランチが消える。**
   そのコミットを保持しているのが release ブランチだけになり、
   **release ブランチが単一障害点になる。** 多くのリポジトリで autodelete は有効

さらに PR 本文の `resolves:` は「その PR がデフォルトブランチへマージされること」が条件なので、
張り替えた PR の `resolves:` は永久に発火しない（[auto-close.md](auto-close.md)）。

base の張り替えを選んでよいのは、`deleteBranchOnMerge` が無効で、かつ release → main を
必ず通すと決めているときだけ。**既定にしない。**

## メインチェックアウトでリリース作業をしてはいけない理由

手順 6 は `git merge` で実際に衝突を起こすので、メインチェックアウトでやると次の問題が出る。

- リリース作業中ずっと main から離れ、**衝突解消で作業ツリーが汚れる**
- 衝突を抱えたまま放置すると、**メインチェックアウトが人質になる**
- 統合状態の CI をローカルで回すとき、専用の作業場があるほうが確実

## 衝突検出まわり

- **`mergeable` を PR 同士の衝突判定に使う** … 「PR と main」しか答えない。
  [conflict-detection.md](conflict-detection.md)
- **`git merge-tree --write-tree` を古い git で叩く** … `fatal: unknown rev --write-tree`。
  2.38 未満は 3 引数形式
- **3 引数の `git merge-tree` の終了コードで衝突を判定する** … 衝突しても exit 0 を返す。
  `<<<<<<<` マーカーを grep する
- **リネーム PR のあとに旧パスへ新規ファイルを足す PR を入れて、`git status` を見ない** …
  新規ファイルは衝突にならず旧ディレクトリが復活する。lint は全部通る。
  [rename-merge.md](rename-merge.md)

## ブランチ名・version まわり

- **モノレポで `release/<version>` と名付ける** … プラグインごとに version が独立しているため
  識別子にならず、別プラグインが同じ version に達した時点で衝突する。必ずプラグイン名を入れる
- **version のドットをハイフンに潰す** … `0-2-0` となって読みにくく、git tag とも揃わない。
  git はドットを許容する（`refs/heads/release/my-plugin-1.2.0` は有効）
- **統合対象が同じ version を主張しているのに、さらに version を上げる** …
  リリースが 1 回なら version は 1 つ（手順 2）。ユーザーに version を聞くと「さらに上げる」を
  誘発するので聞かない
- **同名の release ブランチが既にある** … 前回の実行が中断した跡。再利用するのか作り直すのかを
  黙って決めず、ユーザーに聞く

## マージ方法まわり

- **PR → release を squash する** … head SHA が変わり、PR が Merged にならない。
  `--no-ff` の merge commit で入れる
- **release → main を squash する** … 同じ理由で含まれる PR が 1 本も自動クローズしない。
  `gh pr merge --merge` を使う
- **release ブランチへのマージで issue が閉じると思い込む** … issue の条件は
  デフォルトブランチへの到達。release へ入れただけでは閉じない。[auto-close.md](auto-close.md)
- **リポジトリで merge commit が無効** … `gh pr merge --merge` が拒まれる。
  設定を変えずにユーザーへ伝える。**`--squash` や `--rebase` に勝手に切り替えない**
- **`--delete-branch` を付ける** … ローカル側は worktree が checkout したままなので必ず失敗する。
  削除は 12-c で行う
- **worktree の中から `gh pr merge` を実行する** … GitHub 側は成功するのに `gh` の
  ローカル後処理が落ちる。非ゼロ終了を失敗と読んで再実行しない。
  再実行の前に `gh pr view <PR番号> --json state,mergedAt` で確かめる（11-a）
- **release ブランチを main に入れずに破棄する** … base を張り替えていた場合、
  PR は Merged なのに main には何も無い状態で固定される

## 整合確認まわり

- **旧名の残留を機械置換する** … 例示のプラグイン名まで壊れる。意味ごとに判断する。
  [rename-merge.md](rename-merge.md)
- **「N スキル」のように数を書く** … 増えるたびに古くなる。数えない表現に改める

## PR 作成・CI まわり

- **`gh pr create --template` でテンプレートを読ませようとする** … 対話エディタの初期値を
  入れるだけで、非対話実行では効かない。読んで埋めて `--body-file` で渡す（手順 9）
- **監視ループを Monitor の `command` に直接書く** … worktree 滞在中はハーネスに弾かれる。
  `scripts/watch-pr.sh` に逃がす。詳細は `issue-work` スキルの
  [reference/ci-watch.md](../../issue-work/reference/ci-watch.md)

## 片付けまわり

- **`git worktree remove` が拒む** … 未コミットの変更が残っている。
  `--force` を付けずに止まり、内容をユーザーに伝える
- **`git branch -d` が拒む** … `-d` は squash やリベースを跨いだブランチを拒む。`-D` を使う
- **`git push origin --delete` が「remote ref does not exist」で失敗する** …
  マージ後にブランチを自動削除する設定。正常なので無視してよい
- **`*.code-workspace` の編集がハーネスに弾かれる** … メインチェックアウト側のファイル。
  追記は移動前（手順 4）、削除は `ExitWorktree` の後（12-d）に行う
