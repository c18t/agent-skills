---
name: release-merge
description: "破壊的変更が重なって 1 本ずつマージできない複数の PR を、release ブランチの worktree でローカル merge して統合し、統合状態で CI を回してから release → main を merge commit で入れる。PR をまとめてリリースする・複数 PR を統合する・release ブランチを切る・PR 同士が衝突する・リリース PR を作る、と言われたときに使う。"
---

# 衝突する複数 PR を release ブランチで統合する

引数は統合したい PR 番号（`11 12` でも `#11 #12` でも可）。省略されたらどの PR を統合するかを聞く。

PR 同士が衝突するかを事前に確かめ、`release/<プラグイン名>-<version>` の worktree を作って
セッションごと移動し、その中で PR を 1 本ずつローカル merge して衝突を解消する。
統合状態で CI を回してからリリース PR を出し、承認を得て release → main を merge commit で入れ、
自動クローズを確認して worktree を片付ける。

ユーザーの承認を取るのは 3 箇所（手順 2 の統合方針、手順 9 の PR 本文、手順 11 のマージ）。
それ以外は続けて進めてよい。

このスキルは複数 PR を**まとめて出す**側。1 本で完結する PR は `issue-worktree` スキルの担当で、
このスキルからは呼び出さない。**入口が違うため手順も共有しない**
（`issue-worktree` は issue 番号から始まるが、リリースには対応する issue が無い）。
重なるのは worktree 作成 → `EnterWorktree` → 片付けの 3 点セットだけで、それも自前で持つ。

## 手順

### 1. 対象 PR を読み、衝突を事前に検出する

まず各 PR を読む。

```bash
gh pr view <番号> --json number,title,headRefName,baseRefName,state,mergeable,body
```

head ブランチ名と、`resolves:` が **PR 本文だけにあるのか、コミットメッセージにもあるのか**を
記録する。これが手順 12 の判断材料になる。コミットメッセージ側は次で見る。

```bash
gh pr view <番号> --json commits --jq '.commits[].messageBody'
```

🔴 **`mergeable` を PR 同士の衝突判定に使わない。** これが答えているのは「その PR と main」で
あって「PR と PR」ではない。**互いを壊す 2 本が、どちらも `MERGEABLE` と表示される。**
衝突に気づけるのは片方をマージしたあとになる。

そのうえで `git merge-tree` でペアごとに突き合わせる。**git のバージョンで書式が違う。**

```bash
git --version
git fetch origin
```

| git | コマンド |
| --- | --- |
| 2.38 以降 | `git merge-tree --write-tree origin/<A> origin/<B>` |
| 2.38 未満 | `git merge-tree $(git merge-base origin/<A> origin/<B>) origin/<A> origin/<B>` |

⚠️ **判定の仕方も 2 つで違う。取り違えると「衝突なし」と誤読する。**

- `--write-tree`（2.38 以降）は**衝突すると exit 1**、衝突したパスを出力する
- 3 引数形式（2.38 未満）は**衝突しても exit 0** を返す。しかも**きれいに自動マージできる場合でも**
  `changed in both` と diff を出力する。つまり**終了コードも出力の有無も使えない。**
  材料は `<<<<<<<` マーカーだけなので、出力を `grep '<<<<<<<'` して判定する

どのペアも衝突しないなら、**release ブランチは要らない。** その旨を伝えて、
1 本ずつ通常どおりマージすればよいと言って止まる。ここで手順を続けない。

### 2. リリースブランチ名と統合方針を決める（承認 1）

対象 PR が触っているパスからプラグイン名を、`plugin.json` の差分から version を割り出す。
**ユーザーに version を聞かない**（聞くと「さらに上げる」を誘発する。下の版の決め方を参照）。

ブランチ名は **`release/<プラグイン名>-<version>`**（例 `release/issue-worktree-0.2.0`）。
`release/` は [Conventional Branch](https://conventionalbranch.org/) の Purpose Prefixes にある。

🔴 **プラグイン名を必ず入れる。** このリポジトリは 1 つの中に複数のプラグインがあり、
**それぞれが独立に version を持つ。** `release/<version>` だけでは識別子にならず、
別のプラグインが同じ version に達した時点でブランチ名が衝突する。

**issue 番号は付けない。** 統合対象は複数あって 1 つに決まらない。

⚠️ **version のドットはそのまま使う。** `issue-worktree` 手順 2 の「小文字英数字とハイフンのみ」は
issue 由来のブランチを想定した制約で、release ブランチは別カテゴリとして扱う。
git はドットを許容し（`refs/heads/release/issue-worktree-0.2.0` は有効）、semver 表記のままの
ほうが git tag とも揃う。ハイフンに潰すと `0-2-0` となって読みにくい。

**複数プラグインを同時にリリースする場合は、プラグインごとに release ブランチを分ける。**
version が別々である以上、1 本にまとめると命名が破綻する。

version の決め方 … **統合対象が同じ minor を主張していたら、それ以上上げない。**
破壊的変更が重なっても、リリースが 1 回なら version は 1 つ。

worktree パスは `../<リポジトリ名>-<ブランチ名のスラッシュをハイフンに置換>`
（例 `../agent-skills-release-issue-worktree-0.2.0`）。

```bash
basename "$(git rev-parse --show-toplevel)"
```

次をチャットに出してユーザーの承認を待つ。**この手順ではまだブランチを作らない。**

- 対象 PR の一覧と**マージ順**（衝突が小さいほうを先に入れる。あとの 1 本で解消をまとめる）
- ブランチ名と worktree パス
- version と、それ以上上げない根拠
- 手順 1 で見つかった衝突（ファイルと内容）

### 3. worktree を作る

release ブランチは**必ず新規**なので、`issue-worktree` 手順 3 のような有無の分岐は要らない。

```bash
git fetch origin
git worktree add -b release/<プラグイン名>-<version> <パス> origin/<デフォルトブランチ>
git worktree list
```

⚠️ **起点を `origin/<デフォルトブランチ>` と明示する。** `issue-worktree` 手順 3 と違って
現在の HEAD からは切らない。手元の main が遅れていると、統合結果が古い土台の上に乗る。

同名のブランチが既にあれば**止まってユーザーに聞く。** 前回の実行が中断した跡なので、
再利用するのか作り直すのかを黙って決めない。

### 4. `*.code-workspace` に worktree を登録する

**この手順は移動する前に行う。** 対象ファイルはメインチェックアウト側にあり、
移動後は編集がハーネスに弾かれるため。

リポジトリルートの `*.code-workspace` を探し、`folders` 配列に `name` と `path` を持つ要素を
追記する（無ければ `<リポジトリ名>.code-workspace` を新規作成し、メイン自身の要素を
`name: "main"` / `path: "."` で作る）。**`name` にはブランチ名をそのまま入れる**
（スラッシュはハイフンに置換しない）。同じ `path` が既にあれば何もしない。

⚠️ `.code-workspace` は JSONC で、**末尾カンマやコメントが書かれていることがある。**
JSON として読み直して書き戻すとそれらが消えるので、**Edit で要素を挿入する。**

形式と細かい分岐は `issue-worktree` スキルの手順 4 と同じ。

### 5. worktree へ移動する

`EnterWorktree` ツールに `path: "<パス>"` を渡してセッションを移す。
`.claude/worktrees/` の外なので初回は承認プロンプトが出る。これは正常なので承認を待つ。
移動できたことを `pwd` で確かめてから次へ進む。

🔴 **リリース作業をメインチェックアウトでやらない。** 手順 6 は `git merge` で実際に衝突を
起こすので、メインチェックアウトでやると次の問題が出る。

- リリース作業中ずっと main から離れ、**衝突解消で作業ツリーが汚れる**
- 衝突を抱えたまま放置すると、**メインチェックアウトが人質になる**
- 統合状態の CI をローカルで回すとき、専用の作業場があるほうが確実

### 6. PR を 1 本ずつローカル merge する

手順 2 で決めた順に、worktree の中で入れていく。

```bash
git fetch origin
git merge --no-ff origin/<PR のブランチ>   # 衝突があればここで解消
git push -u origin release/<プラグイン名>-<version>
```

🔴 **`gh pr edit --base` で PR の base を release ブランチへ張り替えない。**
**PR のクローズ条件は「自分の base へマージされること」であって、main への到達ではない。**
張り替えた瞬間からその PR は release を見るので、release へマージした時点で
**Merged になる。まだ main には何も入っていないのに。** ここから 2 つの実害が出る。

1. **PR が再オープンできなくなる。** この時点で release ブランチを破棄すると、
   PR は Merged なのに main には何も無い状態で固定される
2. **`deleteBranchOnMerge` が有効なリポジトリでは feature ブランチが消える。**
   そのコミットを保持しているのが release ブランチだけになり、
   **release ブランチが単一障害点になる。** 多くのリポジトリで autodelete は有効

**PR の base は main のままにしておく。** こうすると PR は OPEN のまま残り、
release → main が入った時点で「head が base に到達した」と判定されて Merged になる。

🔴 **PR → release も merge commit にする（`--no-ff`）。** squash すると head SHA が変わり、
PR が Merged と判定されなくなる。`.github/PULL_REQUEST_TEMPLATE/release.md` の
「必ず merge commit で」は release → main を指したものだが、**この向きにも同じ理由で要る。**

衝突を解消したら、**どのファイルを・どちら側で・なぜ**を都度記録する。
そのまま手順 9 のリリース PR の「競合解消」欄になる。
version の衝突は、片方に寄せるのではなく**手順 2 で決めた値**に揃える。

base の張り替えを選んでよいのは、`deleteBranchOnMerge` が無効で、かつ release → main を
必ず通すと決めているときだけ。**既定にしない。**

### 7. 統合状態で CI を回す

**各 PR が個別に緑でも、統合状態は別物。** リリース PR を出す前にローカルで回す。
実行コマンドはプロジェクトから判断する（`issue-worktree` 手順 7 と同じ表の見方）。

このリポジトリでは次の 4 つ。

```bash
npx --yes markdownlint-cli2 "**/*.md"
claude plugin validate .
claude plugin validate ./plugins/<プラグイン名>
python3 .github/scripts/check_manifests.py
```

出力は控えておく。手順 9 のリリース PR の「補足」欄になる。
失敗したら直してコミットし直す。**通らないまま PR へ進まない。**

### 8. version と README の整合を確認する

**衝突が出なくても整合は壊れる。** 各 PR が自分の機能だけを見て説明文を書いていると、
テキストが重ならないので merge は成功するのに、**統合後の説明がどちらの実態とも合わない。**
これは lint では拾えないので目で見る。

- `plugin.json` の `version` が手順 2 で決めた値になっているか
- `plugin.json` と `marketplace.json` の `description` が一致し、統合後の実態と合っているか
- README が機能を数え違えていないか（「2 スキル」のまま 3 つ入っている、など）

直したら通常どおりコミットする（Conventional Commits）。

### 9. リリース PR の内容をチャットに書き出す（承認 2）

`.github/PULL_REQUEST_TEMPLATE/release.md` を読み、見出しを埋めた本文をチャットに全文書き出す。

| 見出し | 埋めるもの |
| --- | --- |
| リリース対象 | 対象 PR が解決する **issue** の番号 |
| 含まれる PR | 手順 6 のマージ順に列挙する |
| 競合解消 | 手順 6 で記録した「どのファイルを・どちら側で・なぜ」。無ければ「なし」 |
| マージ方法 | テンプレートの `> [!IMPORTANT]` をそのまま残す |
| マージ後の確認 | 手順 12 で見るもの（自動クローズ、main の CI） |
| 補足 | 手順 7 の検証結果と、version をそれ以上上げない根拠 |

⚠️ **`gh pr create --template` を使わない。** このフラグは対話エディタの初期値を入れるだけで、
非対話実行では何もしない。**テンプレートを読んで自分で埋め、`--body-file` で渡す。**

そのうえでユーザーのレビューを待つ。この手順では `gh pr create` を実行しない。

### 10. 承認されたら PR を作り、CI を待つ

```bash
git push
gh pr create --base <デフォルトブランチ> --title "release: <プラグイン名> <version>" --body-file <本文ファイル>
```

タイトルは `release: <プラグイン名> <version>` の形にする（例 `release: issue-worktree 0.2.0`）。

CI はプラグイン同梱のスクリプトを `Monitor` ツールに渡して待つ。
`gh pr checks --watch` は**セッションをブロックする**ので使わない。

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr.sh" <PR番号>
```

🔴 **監視ループを Monitor の `command` に直接書かない。** worktree に滞在中は
コマンド置換とパイプの連結が「worktree の外に出ないと確認できない」と判定され、
ハーネスに弾かれる
（`this command is too complex to verify that it stays inside the worktree`）。
スクリプト経由なら通る。判断の詳細は `issue-worktree` スキルの手順 11 にある。

CI が落ちたら直してコミットし直す。**落ちたままマージへ進まない。**

### 11. release → main を merge commit で入れる（承認 3）

CI が通ったら、次の 3 点をチャットに出してユーザーの承認を待つ。

- CI の結果と、マージ可能かどうか（`mergeStateStatus`）
- マージ後のコミットタイトル … 手順 10 の PR タイトルと同じ
- 含まれる PR と issue が、マージ後にどうなる見込みか（手順 12 の確認項目）

**承認されるまでマージしない。** ユーザーが GitHub の UI で自分でマージする場合もあるため、
「マージしておいて」と明示的に言われたときだけ進む。

- **11-a** worktree を出る

  `ExitWorktree` ツールに `action: "keep"` を渡す。ここでは `remove` を使わない
  （このスキルの worktree は `.claude/worktrees/` の外にあり `ExitWorktree` の管理外。
  実際に消すのは 12-c）。

  🔴 **マージより先に出る。** worktree の中から `gh pr merge` を実行すると、GitHub 側の
  マージは成功するのに `gh` のローカル後処理が
  `fatal: '<デフォルトブランチ>' is already checked out at '<メインのパス>'` で失敗する。
  **コマンドは非ゼロ終了するがマージは完了している。**

- **11-b** マージする

  ```bash
  gh pr merge <PR番号> --merge --subject "release: <プラグイン名> <version>"
  ```

  🔴 **`--squash` を使わない。** squash すると head SHA が変わり、**含まれる PR が
  1 本も自動クローズしない。** release ブランチを使う目的そのものが失われ、
  全部を手でクローズすることになる。

  🔴 **`--delete-branch` を付けない。** ローカル側はこの時点で worktree が checkout した
  ままなので必ず失敗する。ブランチの削除は 12-c でまとめて行う。

  🔴 **release ブランチを main に入れずに破棄しない。** 手順 6 の既定に従っていれば
  PR は OPEN のままなので実害は小さいが、base を張り替えていた場合は
  **PR が Merged なのに main には何も無い状態で固定される。**

  失敗したときは、**再実行の前に `gh pr view <PR番号> --json state,mergedAt` で
  マージ済みかどうかを確かめる**（`state: MERGED` なら完了している）。

### 12. 自動クローズを確認し、閉じ損ねを手当てして片付ける

PR と issue で自動クローズの条件が違い、issue のほうは**発火源が 2 つある**
（PR 本文の `resolves:` とコミットメッセージの `resolves:` は**別経路**）。
手順 6 の既定に従っていれば PR 本文の `resolves:` がそのまま効くが、
**確認は必ずする。** 条件の一覧・#11 と #12 で挙動が割れた実例・対策は
[reference/auto-close.md](reference/auto-close.md) にある。

- **12-a** 自動クローズを確認する

  ```bash
  git fetch origin
  gh pr view <各PR番号> --json number,state,mergedAt
  gh issue list --state open
  ```

  含まれる PR が Merged になっているか、対応する issue が閉じているかを見る。

- **12-b** 閉じ損ねを手当てする

  ```bash
  gh issue close <番号> --comment "..."
  ```

  **どのコミットで対応したかをコメントに残す。** 黙って閉じない。
  PR が OPEN のまま残っていたら、head が main に到達しているかを確認する。

  ```bash
  git branch -r --contains origin/<PR のブランチ> | grep <デフォルトブランチ>
  ```

- **12-c** worktree とローカルブランチを片付ける

  ```bash
  git worktree remove <パス>
  git branch -D release/<プラグイン名>-<version>
  git push origin --delete release/<プラグイン名>-<version>
  git fetch --prune
  ```

  **順序が要る。** `git worktree remove` を先に済ませないと、ブランチは checkout 中の扱いで
  消せない。`-D` を使うのは、`-d` が squash やリベースを跨いだブランチを拒むため。

  `git worktree remove` が未コミットの変更を理由に拒んだら、**`--force` を付けずに止まる。**
  何が残っているかをユーザーに伝えて判断を仰ぐ。

  リポジトリが「マージ後にブランチを自動削除」する設定なら `git push origin --delete` は
  「remote ref does not exist」で失敗する。**それは正常なので無視してよい。**

- **12-d** `*.code-workspace` から worktree の記載を消す

  手順 4 で追記・作成した `folders` の要素を取り除く。**この worktree の `path` を持つ要素だけを
  消し、メイン自身の要素・他の worktree の要素・`settings` などの設定は残す。**
  JSONC なので **Edit で該当要素の行だけを取り除く。**

  この編集はメインチェックアウト側への書き込みなので、**11-a で worktree を出た後に行う。**

- **12-e** マージ済みであることを確認して報告する

  ```bash
  git log --oneline -1 origin/<デフォルトブランチ>
  ```

  あわせて、含まれる各 PR と issue の最終状態を報告する。

## 統合をやめるとき

release ブランチを main に入れずに終える場合、**手順 6 の既定（base を張り替えない）に
従っていれば実害はない。** 含まれる PR は OPEN のまま残るので、release ブランチと worktree を
片付ければ元に戻る（12-c / 12-d の手順をそのまま使う）。

base を張り替えていた場合は戻せない。**PR は Merged で固定され、再オープンできない。**
その状態に気づいたら、release ブランチを**破棄せずに** main へ入れる。

## 落ちる原因（既知）

- **`gh pr view` の `mergeable` を PR 同士の衝突判定に使う** … 答えているのは「PR と main」で
  あって「PR と PR」ではない。互いを壊す 2 本がどちらも `MERGEABLE` と表示される。
  手順 1 の `git merge-tree` で突き合わせる
- **`git merge-tree --write-tree` を古い git で叩く** … `fatal: unknown rev --write-tree` になる。
  2.38 未満は 3 引数形式。`git --version` で分岐する
- **3 引数の `git merge-tree` の終了コードで衝突を判定する** … **衝突しても exit 0 を返す。**
  しかもきれいに自動マージできる場合でも diff を出力するので、出力の有無も使えない。
  `<<<<<<<` マーカーを grep する
- **`gh pr edit --base` で base を張り替える** … PR が release へのマージ時点で Merged になり、
  再オープンできなくなる。autodelete が有効なら feature ブランチも消えて
  release ブランチが単一障害点になる
- **base を張り替えた PR の本文に書いた `resolves:` が永久に発火しない** …
  PR は既に Merged 済みで、main に入っても再評価されない。
  [reference/auto-close.md](reference/auto-close.md) を読む
- **PR → release を squash する** … head SHA が変わり、PR が Merged にならない。
  `--no-ff` の merge commit で入れる
- **release → main を squash する** … 同じ理由で含まれる PR が 1 本も自動クローズしない。
  `gh pr merge --merge` を使う
- **release ブランチへのマージで issue が閉じると思い込む** … issue の条件は
  デフォルトブランチへの到達。release へ入れただけでは閉じない
- **統合対象が同じ version を主張しているのに、さらに version を上げる** …
  リリースが 1 回なら version は 1 つ（手順 2）
- **release ブランチを main に入れずに破棄する** … base を張り替えていた場合、
  PR は Merged なのに main には何も無い状態で固定される
- **モノレポで `release/<version>` と名付ける** … プラグインごとに version が独立しているため
  識別子にならず、別プラグインが同じ version に達した時点で衝突する
- **リリース作業をメインチェックアウトでやる** … 衝突解消の途中で
  メインチェックアウトが人質になる。worktree を使う（手順 3〜5）
- **`gh pr create --template` でテンプレートを読ませようとする** … 対話エディタの初期値を
  入れるだけで、非対話実行では効かない。読んで埋めて `--body-file` で渡す（手順 9）
- **worktree の中から `gh pr merge` を実行する** … GitHub 側は成功するのに
  `gh` のローカル後処理が落ちる。非ゼロ終了を失敗と読んで再実行しない（11-a）
- **監視ループを Monitor の `command` に直接書く** … worktree 滞在中はハーネスに弾かれる。
  `scripts/watch-pr.sh` に逃がす（手順 10）
- **`git worktree remove` が拒む** … 未コミットの変更が残っている。
  `--force` を付けずに止まり、内容をユーザーに伝える
