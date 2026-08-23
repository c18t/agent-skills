# PR 同士の衝突を事前に検出する

`release-merge` スキルの手順 1 から参照する。

## `mergeable` を PR 同士の衝突判定に使わない

🔴 `gh pr view --json mergeable` が答えているのは「その PR と main」であって「PR と PR」ではない。
**互いを壊す 2 本が、どちらも `MERGEABLE` と表示される。** 衝突に気づけるのは片方をマージした
あとになる。

## `git merge-tree` でペアごとに突き合わせる

**git のバージョンで書式が違う。**

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

`--write-tree` を古い git で叩くと `fatal: unknown rev --write-tree` になる。`git --version` で分岐する。

## どのペアも衝突しないとき

**release ブランチは要らない。** その旨を伝えて、1 本ずつ通常どおりマージすればよいと言って止まる。
手順を続けない。

## merge-tree では拾えない衝突

ファイル単位で重ならなければ merge は成功するが、統合後の整合は壊れていることがある
（説明文の数え違い、リネームを跨いだ新規ファイルの着地先など）。これは手順 8 で目で見る。
リネームを含む PR の扱いは [rename-merge.md](rename-merge.md)。
