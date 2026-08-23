"""notion_mirror.py の正規化・照合の回帰テスト。

なぜ要るか
----------
Notion は保存時に「ドットを含む英数字トークン」を自動でリンクにする
（`notion_mirror.py` → `notion_[mirror.py](http://mirror.py)`）。normalize() が
これを吸収しないと、書き戻した直後の diff が恒久的に DIRTY になり収束しない（#5）。

吸収の限定条件は「リンクテキストとリンク先が一致するものだけ」。手で貼った本物の
リンク（テキストと URL が違う）は畳まないので、それを消す編集は差分として残る。
その両側をここで固定する。

他のテストは subprocess でスクリプトを叩いているが、normalize() / compare() は
副作用の無い純関数なので直接 import する（notion_mirror のトップレベルは定数と
関数定義だけで、main() は __main__ ガード下にある）。
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import notion_mirror  # noqa: E402


def compare_quiet(local, remote):
    """compare() は stdout に差分を吐くので、テストでは握って返り値だけ見る。"""
    with contextlib.redirect_stdout(io.StringIO()):
        return notion_mirror.compare(local, remote, "test")


class TestAutoLinkFolding(unittest.TestCase):
    """Notion の自動リンク化を吸収する（畳む側）。"""

    def assertRoundTrips(self, local, remote):
        self.assertEqual(notion_mirror.normalize(local), notion_mirror.normalize(remote))
        self.assertTrue(compare_quiet(local, remote))

    def test_bare_filename(self):
        # アンダースコアがトークンを切るので notion_ が外れる
        self.assertRoundTrips("notion_mirror.py", "notion_[mirror.py](http://mirror.py)")

    def test_extension_only(self):
        self.assertRoundTrips("hoge.io", "[hoge.io](http://hoge.io)")

    def test_https_scheme_on_target(self):
        self.assertRoundTrips("hoge.io", "[hoge.io](https://hoge.io)")

    def test_trailing_slash_on_target(self):
        self.assertRoundTrips("hoge.io", "[hoge.io](http://hoge.io/)")

    def test_scheme_in_link_text_is_preserved(self):
        # 🔴 回帰テストの本命。畳んだ結果に \2（スキーム抜き）を残すと
        # [https://example.com](https://example.com) が example.com になり、
        # ローカル正本側の素の https://example.com と一致しなくなる。
        self.assertRoundTrips(
            "https://example.com", "[https://example.com](https://example.com)")

    def test_folding_inside_surrounding_text(self):
        self.assertRoundTrips(
            "スクリプトは notion_mirror.py にある",
            "スクリプトは notion_[mirror.py](http://mirror.py) にある")

    def test_multiple_links_in_one_line(self):
        self.assertRoundTrips(
            "hoge.io と fuga.sh",
            "[hoge.io](http://hoge.io) と [fuga.sh](http://fuga.sh)")


class TestHandWrittenLinksSurvive(unittest.TestCase):
    """テキストと URL が違うリンクは畳まない（差分として残る側）。"""

    def test_label_link_is_not_folded(self):
        self.assertIn("サンプル", notion_mirror.normalize("[サンプル](https://example.com)"))
        self.assertFalse(compare_quiet("サンプル", "[サンプル](https://example.com)"))

    def test_path_suffix_is_not_folded(self):
        self.assertFalse(compare_quiet("docs", "[docs](https://example.com/docs)"))

    def test_deleting_a_hand_written_link_shows_as_a_diff(self):
        # 手貼りリンクを消した編集が引き続き差分に出ること（issue #5 の検証項目）
        remote = "前文\n[サンプル](https://example.com)\n後文\n"
        local = "前文\n後文\n"
        self.assertFalse(compare_quiet(local, remote))


class TestExistingNormalization(unittest.TestCase):
    """既存の正規化が壊れていないこと。"""

    def test_tags_are_stripped(self):
        self.assertEqual(notion_mirror.normalize("あ<table_of_contents/>い"), "あい")

    def test_checkboxes_are_stripped(self):
        self.assertEqual(notion_mirror.normalize("- [ ] やる\n- [x] やった"), "やるやった")

    def test_whitespace_and_markup_are_stripped(self):
        self.assertEqual(
            notion_mirror.normalize("## 見出し\n\n| a | b |\n| --- | --- |\n"), "見出しab")

    def test_identical_text_is_clean(self):
        self.assertTrue(compare_quiet("本文です。\n", "本文です。\n"))

    def test_real_edit_is_dirty(self):
        self.assertFalse(compare_quiet("本文です。\n", "別の本文です。\n"))


if __name__ == "__main__":
    unittest.main()
