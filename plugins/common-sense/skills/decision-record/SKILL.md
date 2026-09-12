---
name: decision-record
description: "捨てた選択肢がある判断を ADR として起草・更新するときに、選択理由と強制手段を残す。今回の差分を説明するコミットメッセージの作成には使わない。"
---

# 判断を記録する

コードから復元できない「なぜこの形を選び、何を捨てたか」を、人と AI が後から判断するときの
拠り所として ADR に残す。

## 1. 記録するか判定する

実際に複数の選択肢を検討し、1 つ以上を捨てた判断だけを記録する。他の選択肢を検討せずに決まった
実装や、diff から分かる変更内容は ADR にしない。

`commit-message` が扱うのは今回の変更を説明するコミットメッセージである。このスキルは、変更を
越えて参照する判断と捨てた選択肢を扱う。作業経緯だけなら PR 本文の候補にする。

## 2. 既存の判断を調べる

リポジトリの `AGENTS.md` に ADR の規約があれば従う。既存の `docs/adr/` があればそこを使い、
無ければ `docs/decisions/` を使う。同じ論点の ADR と、それを supersede する ADR が無いかを調べる。

既存の ADR は不変として扱い、採択後の内容を書き換えない。判断を変えるときは新しい ADR を作り、
新旧双方を `superseded by ADR-NNNN` と関連情報で辿れるようにする。判断の一覧や現状は索引側で更新する。

## 3. 判断を起草する

[templates/decision-record.md](templates/decision-record.md) をコピーし、既存の採番規則に従う。
規則が無ければ `NNNN-short-title.md` とする。テンプレートは
[MADR v4](https://github.com/adr/madr/blob/4.0.0/template/adr-template.md) を基にしている。

テンプレートの固定見出しは英語のまま使い、それ以外のタイトル、本文、frontmatter の値は
decision-makers が共通して理解できる言語で書く。共同で判断する全員の共通言語が不明なら、起草前に
ユーザーへ確認する。

- Context には、判断が必要になった状況と解く問題を書く
- Considered Options には、実際に比較した案だけを書く
- Decision Outcome には、採用案と選択理由を書く
- Pros and Cons には、採用案を正当化するための後付けではなく、判断時の比較を残す
- Confirmation には、判断が守られていると確認する方法を書く

frontmatter の値はすべて 1 行のスカラーにする。各要素の意味は次のとおり。

| 要素 | 内容 |
| --- | --- |
| `status` | 判断の状態。`proposed`、`rejected`、`accepted`、`deprecated`、`superseded by ADR-NNNN` など |
| `date` | 判断を最後に更新した日。`YYYY-MM-DD` |
| `decision-makers` | 判断に責任を持ち、決定へ参加した人 |
| `consulted` | 判断前に意見を求め、双方向にやり取りした人 |
| `informed` | 判断や進捗を共有し、一方向に知らせる人 |
| `enforced_by` | 判断を守っていることを確認する 1 つの手段 |

`decision-makers`、`consulted`、`informed` は RACI に由来する。分かる場合だけ埋め、個人開発などで
不要なら空欄のままでよい。

## 4. 強制手段を指名する

`enforced_by` には判断を検証する手段を 1 つだけ書く。

- 機械検証できるなら、既存ツールの設定を `path#rule` の形で参照する
- 人のレビューで確認するなら、`review — <確認箇所>` と書く
- 検証不能なら、`none — <理由>` と書く

専用 DSL や ADR 専用の検証設定は作らない。機械検証の設定側にも ADR 番号をコメントで置き、ルールを
変える人が根拠へ辿れるようにする。

## 5. 提示する

ADR の全文と保存先を一度に提示する。ユーザーが作成や更新も求めている場合だけファイルへ書き込む。
判断に未解決の部分があれば、確定事項に見せず `status: proposed` と More Information に残す。
