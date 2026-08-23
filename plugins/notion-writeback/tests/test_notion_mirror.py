"""notion_mirror.py の正規化・照合の回帰テスト。

なぜ要るか
----------
Notion は保存時に「ドットを含む英数字トークン」を自動でリンクにする
（`notion_mirror.py` → `notion_[mirror.py](http://mirror.py)`）。normalize() が
これを吸収しないと、書き戻した直後の diff が恒久的に DIRTY になり収束しない（#5）。

吸収の限定条件は「リンクテキストとリンク先が一致するものだけ」。手で貼った本物の
リンク（テキストと URL が違う）は畳まないので、それを消す編集は差分として残る。
その両側をここで固定する。

difflib の tag は a（＝ローカル）基準で付くので、`delete` は「自分の追記」、
`insert` が「書き戻すと消える Notion 側」になる。SKILL.md はここを逆に説明していた（#6）。
文言を直しても出力が英単語のままだと読み違いは再発しうるので、意味の分かるラベルを
前置し、生の tag は [] で残す。CompareLabelTestCase がその対応づけを固定する。

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


class CompareLabelTestCase(unittest.TestCase):
    def run_compare(self, local, remote):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            clean = notion_mirror.compare(local, remote, "テスト")
        return clean, buf.getvalue()

    def diff_lines(self, out):
        """差分 1 件ごとの見出し行だけを拾う（文脈 2 行は除く）。"""
        return [ln for ln in out.splitlines() if ln.startswith("  - ")]

    def test_local_only_is_labeled_as_own_edit(self):
        """ローカルにだけある本文は delete。自分の追記なので危険側に見せない。"""
        clean, out = self.run_compare(
            "共通の本文です。\nローカルだけの追記。\n",
            "共通の本文です。\n")
        self.assertFalse(clean)
        # 見出し行だけを見る。DIRTY ヘッダは 3 ラベルすべてを凡例として並べるので、
        # 出力全体に対する assertNotIn は成立しない。
        lines = self.diff_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertIn("追記(ローカルのみ)", lines[0])
        self.assertIn("[delete]", lines[0])
        self.assertNotIn("⚠️", lines[0])

    def test_notion_only_is_labeled_as_disappearing(self):
        """Notion にだけある本文は insert。書き戻すと消える側。"""
        clean, out = self.run_compare(
            "共通の本文です。\n",
            "共通の本文です。\nNotion側で足された行。\n")
        self.assertFalse(clean)
        lines = self.diff_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertIn("⚠️消える(Notionのみ)", lines[0])
        self.assertIn("[insert]", lines[0])
        self.assertIn("Notion側で足された行。", lines[0])
        self.assertNotIn("追記(ローカルのみ)", lines[0])

    def test_mixed_case_marks_only_the_dangerous_side(self):
        """両方を含むケースで、⚠️ が付くのは消える側の 1 本だけ。"""
        clean, out = self.run_compare(
            "# 見出し\n共通の本文です。\nローカルだけの追記。\n最後の共通行。\n",
            "# 見出し\n共通の本文です。\n最後の共通行。\nNotion側で足された行。\n")
        self.assertFalse(clean)
        self.assertIn("2 件の差分", out)
        lines = self.diff_lines(out)
        self.assertEqual(len(lines), 2)
        self.assertEqual([ln for ln in lines if ln.startswith("  - ⚠️")],
                         [ln for ln in lines if "[insert]" in ln])

    def test_replace_is_flagged_for_review(self):
        """両側にあって食い違うものは要確認として ⚠️ を付ける。"""
        clean, out = self.run_compare(
            "共通です。数値は 100 円。共通おわり。",
            "共通です。数値は 250 円。共通おわり。")
        self.assertFalse(clean)
        self.assertIn("⚠️食い違い", out)
        self.assertIn("[replace]", out)

    def test_clean_when_only_markup_differs(self):
        """normalize() が落とす整形差だけなら CLEAN。ラベル化で壊していないこと。"""
        clean, out = self.run_compare("# 見出し\n\n- **項目**\n", "見出し\n項目\n")
        self.assertTrue(clean)
        self.assertTrue(out.startswith("CLEAN:"))
        self.assertEqual(self.diff_lines(out), [])

    def test_truncates_at_twenty_diffs(self):
        """20 件で打ち切り、残件数を出す。"""
        local = "".join(f"共通{i}ローカル{i}" for i in range(25))
        remote = "".join(f"共通{i}リモート{i}" for i in range(25))
        clean, out = self.run_compare(local, remote)
        self.assertFalse(clean)
        self.assertEqual(len(self.diff_lines(out)), 20)
        self.assertIn("（ほか", out)

    def test_labels_cover_every_non_equal_opcode(self):
        """SKILL.md がこの文字列を引き写しているので、変えたらここで落とす。"""
        self.assertEqual(set(notion_mirror.DIFF_LABELS), {"delete", "insert", "replace"})
        self.assertEqual(notion_mirror.DIFF_LABELS["delete"], "追記(ローカルのみ)")
        self.assertEqual(notion_mirror.DIFF_LABELS["insert"], "⚠️消える(Notionのみ)")
        self.assertEqual(notion_mirror.DIFF_LABELS["replace"], "⚠️食い違い")


if __name__ == "__main__":
    unittest.main()
