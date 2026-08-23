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

このスキルは複数 PR を**まとめて出す**側。1 本で完結する PR は `issue-work` スキルの担当で、
このスキルからは呼び出さない（リリースには対応する issue が無く、入口が違う）。
重なるのは worktree 作成 → `EnterWorktree` → 片付けの 3 点セットだけで、それも自前で持つ。

うまくいかないときは [reference/troubleshooting.md](reference/troubleshooting.md) を見る。
統合をやめるときの扱いも同じファイルにある。

## 手順

### 1. 対象 PR を読み、衝突を事前に検出する

```bash
gh pr view <番号> --json number,title,headRefName,baseRefName,state,mergeable,body
gh pr view <番号> --json commits --jq '.commits[].messageBody'
```

head ブランチ名と、`resolves:` が **PR 本文だけにあるのか、コミットメッセージにもあるのか**を
記録する（手順 12 の判断材料）。

PR 同士の衝突は `git merge-tree` でペアごとに突き合わせる。git 2.38 以降なら次のとおり。

```bash
git fetch origin
git merge-tree --write-tree origin/<A> origin/<B>   # 衝突すると exit 1
```

🔴 `mergeable` を PR 同士の衝突判定に使わない（「PR と main」しか答えない）。
2.38 未満の書式と判定の違いは [reference/conflict-detection.md](reference/conflict-detection.md)。

どのペアも衝突しないなら **release ブランチは要らない。** その旨を伝えて止まる。

### 2. リリースブランチ名と統合方針を決める 🛑

対象 PR が触っているパスからプラグイン名を、`plugin.json` の差分から version を割り出す。
**ユーザーに version を聞かない。** 統合対象が同じ minor を主張していたら、それ以上上げない
（リリースが 1 回なら version は 1 つ）。

- ブランチ名 … **`release/<プラグイン名>-<version>`**（例 `release/issue-flow-0.3.0`）。
  プラグイン名は必須（モノレポで version が独立しているため）。ドットはそのまま。issue 番号は付けない
- worktree パス … `../<リポジトリ名>-<ブランチ名のスラッシュをハイフンに置換>`
  （例 `../agent-skills-release-issue-flow-0.3.0`）
- 複数プラグインを同時にリリースするなら、プラグインごとに release ブランチを分ける

```bash
basename "$(git rev-parse --show-toplevel)"
```

次をチャットに出してユーザーの承認を待つ。**この手順ではまだブランチを作らない。**

- 対象 PR の一覧と**マージ順**。衝突が小さいほうを先に入れ、あとの 1 本で解消をまとめる。
  **リネーム（ディレクトリ改名）を含む PR があれば最初に入れる**
  （[reference/rename-merge.md](reference/rename-merge.md)）
- ブランチ名と worktree パス
- version と、それ以上上げない根拠
- 手順 1 で見つかった衝突（ファイルと内容）

### 3. worktree を作る

release ブランチは**必ず新規**。起点は `origin/<デフォルトブランチ>` と明示する
（手元の main が遅れていても古い土台に乗らないように）。

```bash
git fetch origin
git worktree add -b release/<プラグイン名>-<version> <パス> origin/<デフォルトブランチ>
git worktree list
```

同名のブランチが既にあれば**止まってユーザーに聞く。**

### 4. `*.code-workspace` に worktree を登録する

**移動する前に行う。** リポジトリルートの `*.code-workspace` の `folders` に、`name` にブランチ名を
そのまま、`path` に worktree パスを入れた要素を **Edit で**追記する（JSONC なので全体を
書き直さない）。同じ `path` が既にあれば何もしない。形式と分岐は `issue-work` スキルの手順 4 と同じ。

### 5. worktree へ移動する

`EnterWorktree` ツールに `path: "<パス>"` を渡してセッションを移す。初回は承認プロンプトが出るので
待つ。移動できたことを `pwd` で確かめてから次へ進む。

🔴 **リリース作業をメインチェックアウトでやらない**（衝突解消でメインが人質になる）。

### 6. PR を 1 本ずつローカル merge する

手順 2 で決めた順に、worktree の中で入れていく。

```bash
git fetch origin
git merge --no-ff origin/<PR のブランチ>   # 衝突があればここで解消
git push -u origin release/<プラグイン名>-<version>
```

- 🔴 **`--no-ff` の merge commit で入れる。** squash すると head SHA が変わり、
  PR が Merged と判定されなくなる（[reference/auto-close.md](reference/auto-close.md)）
- 🔴 **`gh pr edit --base` で PR の base を release へ張り替えない。** PR の base は main のまま。
  張り替えると release へマージした時点で Merged になり再オープンできない
  （[reference/troubleshooting.md](reference/troubleshooting.md)）
- ⚠️ **リネームを含む PR が対象にあるときは、各マージ後に `git status` の `A` を確認する。**
  旧パスに足された新規ファイルは衝突として報告されず、削除したはずの旧ディレクトリを復活させて
  そこに着地する。着地していたら `git mv` で正しい場所へ移し、空になった旧ディレクトリを消す
  （[reference/rename-merge.md](reference/rename-merge.md)）

衝突を解消したら、**どのファイルを・どちら側で・なぜ**を都度記録する（手順 9 の「競合解消」欄）。
version の衝突は、片方に寄せるのではなく**手順 2 で決めた値**に揃える。

### 7. 統合状態で CI を回す

**各 PR が個別に緑でも、統合状態は別物。** 実行コマンドはプロジェクトから判断する
（`issue-work` 手順 7 と同じ表の見方）。このリポジトリでは次の 4 つ。

```bash
npx --yes markdownlint-cli2 "**/*.md"
claude plugin validate .
claude plugin validate ./plugins/<プラグイン名>
python3 .github/scripts/check_manifests.py
```

出力は控えておく（手順 9 の「補足」欄）。失敗したら直してコミットし直す。

### 8. version と README の整合を確認する

**衝突が出なくても整合は壊れる。** テキストが重ならなければ merge は成功するのに、
統合後の説明がどちらの実態とも合わないことがある。lint では拾えないので目で見る。

- `plugin.json` の `version` が手順 2 で決めた値になっているか
- `plugin.json` と `marketplace.json` の `description` が一致し、統合後の実態と合っているか
- README が機能を数え違えていないか。「N スキル」のように数を書く表現は数えない形に改める
- 統合後のディレクトリ（`ls plugins/` など対象の親）を目で見て、孤立した旧ディレクトリが無いか
- リネームを含む統合では、旧名の残留を grep する。**置換先は意味に応じて変わる**
  （スキル参照なら新名へ、ブランチ名や PR タイトルの例示なら個別に判断）。
  `sed` で一括置換しない（[reference/rename-merge.md](reference/rename-merge.md)）

直したら通常どおりコミットする（Conventional Commits）。

### 9. リリース PR の内容をチャットに書き出す 🛑

テンプレートを決めて、見出しを埋めた本文をチャットに全文書き出す。

| リポジトリ側 | 使うテンプレート |
| --- | --- |
| `.github/PULL_REQUEST_TEMPLATE/release.md` がある | それ |
| 無い | 同梱の既定 [templates/release.md](templates/release.md) |

| 見出し | 埋めるもの |
| --- | --- |
| リリース対象 | 対象 PR が解決する **issue** の番号 |
| 含まれる PR | 手順 6 のマージ順に列挙する |
| 競合解消 | 手順 6 で記録した「どのファイルを・どちら側で・なぜ」。無ければ「なし」 |
| マージ方法 | テンプレートの `> [!IMPORTANT]` をそのまま残す |
| マージ後の確認 | 手順 12 で見るもの（自動クローズ、main の CI） |
| 補足 | 手順 7 の検証結果と、version をそれ以上上げない根拠 |

どちらのテンプレートを使ったかを本文と一緒に 1 行で伝える。
⚠️ `gh pr create --template` は使わない（非対話実行では何もしない）。
**この手順では `gh pr create` を実行しない。** 承認されるまで待つ。

### 10. 承認されたら PR を作り、CI を待つ

```bash
git push
gh pr create --base <デフォルトブランチ> --title "release: <プラグイン名> <version>" --body-file <本文ファイル>
```

CI は同梱スクリプトを `Monitor` ツールの `command` に渡して待つ。

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr.sh" <PR番号>
```

🔴 `gh pr checks --watch` は使わない。監視ループを Monitor に直接書かない（worktree 滞在中は
ハーネスに弾かれる）。詳細は `issue-work` スキルの
[reference/ci-watch.md](../issue-work/reference/ci-watch.md)。

CI が落ちたら直してコミットし直す。**落ちたままマージへ進まない。**

### 11. release → main を merge commit で入れる 🛑

CI が通ったら、次の 3 点をチャットに出してユーザーの承認を待つ。

- CI の結果と、マージ可能かどうか（`mergeStateStatus`）
- マージ後のコミットタイトル … 手順 10 の PR タイトルと同じ
- 含まれる PR と issue が、マージ後にどうなる見込みか（手順 12 の確認項目）

**「マージしておいて」と明示的に言われたときだけ進む。**

- **11-a** worktree を出る

  `ExitWorktree` ツールに `action: "keep"` を渡す（`remove` は使わない。実際に消すのは 12-c）。
  🔴 **マージより先に出る**（worktree の中から `gh pr merge` を実行すると `gh` のローカル後処理が
  失敗して非ゼロ終了する。マージ自体は完了している）。

- **11-b** マージする

  ```bash
  gh pr merge <PR番号> --merge --subject "release: <プラグイン名> <version>"
  ```

  🔴 **`--squash` を使わない**（含まれる PR が 1 本も自動クローズしなくなる）。
  🔴 **`--delete-branch` を付けない**（ローカル側が worktree に checkout されたまま。削除は 12-c）。
  失敗したときは、再実行の前に `gh pr view <PR番号> --json state,mergedAt` でマージ済みか確かめる。

### 12. 自動クローズを確認し、閉じ損ねを手当てして片付ける

PR と issue で自動クローズの条件が違い、issue のほうは発火源が 2 つある。
条件の一覧と実例は [reference/auto-close.md](reference/auto-close.md)。**確認は必ずする。**

- **12-a** 自動クローズを確認する

  ```bash
  git fetch origin
  gh pr view <各PR番号> --json number,state,mergedAt
  gh issue list --state open
  ```

- **12-b** 閉じ損ねを手当てする

  ```bash
  gh issue close <番号> --comment "..."
  ```

  **どのコミットで対応したかをコメントに残す。** PR が OPEN のまま残っていたら、
  head が main に到達しているかを確認する。

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

  この順序で行う。`git worktree remove` が未コミットの変更を理由に拒んだら、
  **`--force` を付けずに止まり**ユーザーに伝える。

- **12-d** `*.code-workspace` から worktree の記載を消す

  手順 4 で追記した `folders` の要素だけを **Edit で**取り除く。
  メインチェックアウト側への書き込みなので **11-a で出た後に**行う。

- **12-e** マージ済みであることを確認して報告する

  ```bash
  git log --oneline -1 origin/<デフォルトブランチ>
  ```

  あわせて、含まれる各 PR と issue の最終状態を報告する。

## 例外時の参照先

| ファイル | 内容 |
| --- | --- |
| [reference/troubleshooting.md](reference/troubleshooting.md) | 落ちる原因（既知）、統合をやめるとき、base 張り替えの実害 |
| [reference/conflict-detection.md](reference/conflict-detection.md) | `git merge-tree` の版ごとの書式と判定、`mergeable` が使えない理由 |
| [reference/rename-merge.md](reference/rename-merge.md) | リネームを含む PR の統合で新規ファイルが旧ディレクトリに着地する罠、旧名残留の grep |
| [reference/auto-close.md](reference/auto-close.md) | PR と issue の自動クローズ条件、#11 / #12 で挙動が割れた実例 |
| [templates/release.md](templates/release.md) | リポジトリにリリース PR テンプレートが無いときの既定 |
