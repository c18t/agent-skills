# common-sense

AI と利用者の共通認識となる判断手順をまとめるプラグイン。名前は Perl の
[`common::sense`](https://metacpan.org/pod/common::sense) に由来する。

## Skills

### `commit-message`

コミットメッセージを書く前に diff を読み、変更の説明を適切な宛先へ振り分ける。
コミットには「なぜ今 / なぜこの形か」を残し、差分から読める列挙や作業報告を持ち込まない。

リポジトリ固有の宛先表は `AGENTS.md` に置ける。表が無い場合はスキル内の既定を使う。
