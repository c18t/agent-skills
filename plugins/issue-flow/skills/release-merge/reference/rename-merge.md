# リネームを含む PR を統合するとき

`release-merge` スキルの手順 2・6・8 から参照する。
PR #25（`release/issue-flow-0.3.0`）で #23 と #24 を統合したときに踏んだ罠と、その対処。

## 新規ファイルが旧ディレクトリに着地する

PR #24 が `plugins/issue-worktree/` → `plugins/issue-flow/` へディレクトリを改名し、
PR #23 が `plugins/issue-worktree/skills/release-merge/` に新規ファイルを 2 つ追加していた。
この 2 本を #24 → #23 の順で merge すると、こうなる。

```text
CONFLICT (modify/delete): plugins/issue-worktree/.claude-plugin/plugin.json deleted in HEAD and modified in ...
A  plugins/issue-worktree/skills/release-merge/SKILL.md
A  plugins/issue-worktree/skills/release-merge/reference/auto-close.md
```

**新規ファイルの 2 つは衝突として報告されない。** git がリネームを追跡できるのはマージベースに
存在したファイルだけで、`release-merge/` の 2 ファイルはマージベースに無いため対応付けができない。
結果として**削除したはずの `plugins/issue-worktree/` が復活し、そこに置かれる。**

## 検証が全部通ってしまう

この状態でも手順 7 の検証は通る。実際に確認した。

- `markdownlint-cli2` … 通る（Markdown として妥当）
- `claude plugin validate` … 通る（`marketplace.json` の `source` が指す `issue-flow` 側は正しい）
- `check_manifests.py` … 通る（`source` の実在と name の一致しか見ない）

**孤立したディレクトリを検出する仕組みは無い。** `plugins/` 直下を目で見るか、
`git status` の `A` を読むまで気づかない。

## 対処

- **リネームを含む PR を先にマージする**（手順 2 のマージ順）。構成を確定させてから
  新規ファイルを載せれば、移動が 1 回で済む。#25 ではこの順にして正解だった
- リネームを含む PR が対象にあるときは、**各マージ後に `git status` の `A` を確認する**（手順 6）。
  新規ファイルが旧パスに着地していないか
- 着地していたら `git mv` で正しい場所へ移し、空になった旧ディレクトリを消す。
  衝突解消と同じコミットに含め、手順 9 の「競合解消」欄に記録する
- 統合後に `ls plugins/`（あるいは対象ディレクトリの親）を**目で見る**（手順 8）

## 旧名の残留を grep する

リネームを含む統合では、lint が全部通ったあとに旧名が残る。#25 では次の 2 つが残っていた。

- `marketplace.json` の description が「3 スキル」という数え方のままだった
  （スキルが増えるたびに古くなる書き方なので、数えない表現に改めた）
- `release-merge/SKILL.md` の旧名が 12 箇所

```bash
grep -rn "<旧名>" plugins/ README.md .claude-plugin/
```

⚠️ **置換先は意味に応じて変わる。** 12 箇所のうち 4 箇所は、ブランチ名・PR タイトルの
**例示**として出てくるプラグイン名で、機械置換すると壊れた。

| 出現箇所 | 扱い |
| --- | --- |
| スキル参照（`/plugin:skill` の呼び出し文字列、相互参照、パス） | 新名へ置換する |
| ブランチ名・PR タイトル・コミットメッセージの例示 | 例示が成り立つ名前に個別に直す |
| 過去の経緯の説明（「旧名 X から改名した」など） | そのまま残す |

1 件ずつ意味を見て判断する。`sed` で一括置換しない。
