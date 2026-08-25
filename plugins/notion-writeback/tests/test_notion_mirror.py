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

CliContractTestCase だけは subprocess で叩く。対象が終了コードと stderr——
in-process では観測できないもの——だからで、そこは #31 の要になる。サブエージェントは
出力ファイルの**先頭の印**で報告する語を決めるので、「どの経路でも印つきの 1 行が出る」
「exit 1 は DIRTY / STALE だけ」が崩れると、空を CLEAN と読む事故に戻る。
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PLUGIN_ROOT, "scripts", "notion_mirror.py")

sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

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


class CliContractTestCase(unittest.TestCase):
    """CLI の「必ず 1 行は出す」「終了コードで意味が割れる」を固定する。

    サブエージェントは出力ファイルの**先頭の印**で報告する語を決める（#31）。
    その前提——どの経路でも stdout か stderr に印つきの 1 行が出ること——が崩れると、
    空を CLEAN と読む事故に戻る。compare() と違って終了コードと stderr が対象なので、
    ここだけ subprocess で本物の CLI を叩く。
    """

    PAGE = "0" * 32
    OTHER = "1" * 32

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def write_transcript(self, body, page_id=None):
        """<page url=...> と <content> を含む最小のトランスクリプト 1 行を書く。

        本物と同じ二重エンコード（JSON 文字列の中の JSON 文字列）で入れる。
        """
        page_id = page_id or self.PAGE
        inner = json.dumps({
            "text": f'<page url="https://app.notion.com/p/{page_id}">\n'
                    f"<content>\n{body}\n</content>\n</page>"})
        rec = {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": inner}]}}
        path = os.path.join(self.tmp, "session.jsonl")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path

    def write_local(self, body, name="page.md"):
        path = os.path.join(self.tmp, name)
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(body + "\n")
        return path

    def run_cli(self, *args):
        """python.sh は経由しない（Windows ランナーでも sh 依存を持ち込まないため）。

        ⚠️ text=True に任せない。Windows では子プロセスの出力がコンソールの
        コードページ（cp932）で来るので、UTF-8 として読むと落ちて stdout が None になる。
        子には PYTHONIOENCODING=utf-8 を渡し、こちらはバイト列で受けて明示的に decode する
        （test_notion_write_guard.py と同じ作法）。
        """
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, env=env, timeout=60)
        out = proc.stdout.decode("utf-8")
        err = proc.stderr.decode("utf-8")
        # 印は stdout か stderr のどちらかに必ず出る。空なら判定不能＝#31 の事故。
        self.assertTrue((out + err).strip(),
                        "出力が空。CLEAN でも DIRTY でも 1 行は出るはずで、"
                        "空は「差分なし」ではなくスクリプトが走らなかった合図")
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def run_diff(self, local_body, remote_body, page=None):
        transcript = self.write_transcript(remote_body)
        local = self.write_local(local_body)
        return self.run_cli("--transcript", transcript, "diff",
                            "--page", page or self.PAGE, "--file", local)

    def test_clean_prints_a_line_and_exits_zero(self):
        proc = self.run_diff("同じ本文", "同じ本文")
        self.assertTrue(proc.stdout.startswith("CLEAN:"), proc.stdout)
        self.assertEqual(proc.returncode, 0)

    def test_dirty_prints_a_line_and_exits_one(self):
        proc = self.run_diff("ローカルだけの追記", "Notion の本文")
        self.assertTrue(proc.stdout.startswith("DIRTY:"), proc.stdout)
        self.assertIn("件の差分", proc.stdout)
        self.assertEqual(proc.returncode, 1)

    def test_stale_prints_a_line_and_exits_one(self):
        """fetch が別ページの分しか無い＝照合できない。"""
        proc = self.run_diff("本文", "本文", page=self.OTHER)
        self.assertTrue(proc.stdout.startswith("STALE:"), proc.stdout)
        self.assertEqual(proc.returncode, 1)

    def test_pull_ok_prefix_keeps_its_two_spaces(self):
        """`OK  :` の空白 2 つはエージェントが照合する印そのもの。詰めない。"""
        transcript = self.write_transcript("Notion の本文")
        out = os.path.join(self.tmp, "out.md")
        proc = self.run_cli("--transcript", transcript, "pull",
                            "--page", self.PAGE, "--out", out)
        self.assertTrue(proc.stdout.startswith("OK  :"), repr(proc.stdout[:20]))
        self.assertEqual(proc.returncode, 0)
        with io.open(out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "Notion の本文\n")

    def test_pull_stale_prints_a_line_and_exits_one(self):
        transcript = self.write_transcript("本文", page_id=self.OTHER)
        proc = self.run_cli("--transcript", transcript, "pull",
                            "--page", self.PAGE,
                            "--out", os.path.join(self.tmp, "out.md"))
        self.assertTrue(proc.stdout.startswith("STALE:"), proc.stdout)
        self.assertEqual(proc.returncode, 1)

    def test_bad_page_id_is_error_not_one(self):
        """exit 1 は「差分を読め」の合図。本物の失敗をそこに混ぜない。"""
        transcript = self.write_transcript("本文")
        proc = self.run_cli("--transcript", transcript, "diff",
                            "--page", "not-a-page-id",
                            "--file", self.write_local("本文"))
        self.assertTrue(proc.stderr.startswith("ERROR:"), proc.stderr)
        self.assertEqual(proc.returncode, notion_mirror.EXIT_ERROR)

    def test_missing_local_file_is_error_not_one(self):
        transcript = self.write_transcript("本文")
        proc = self.run_cli("--transcript", transcript, "diff",
                            "--page", self.PAGE,
                            "--file", os.path.join(self.tmp, "not-there.md"))
        self.assertTrue(proc.stderr.startswith("ERROR:"), proc.stderr)
        self.assertEqual(proc.returncode, notion_mirror.EXIT_ERROR)

    def test_error_exit_code_is_distinct_from_every_other_meaning(self):
        """1 は DIRTY/STALE、2 は argparse と python.sh のインタプリタ不在が使う。"""
        self.assertNotIn(notion_mirror.EXIT_ERROR, (0, 1, 2))


class ReportContractDocTestCase(unittest.TestCase):
    """報告形式の文字列は 2 箇所に複製されている。ドリフトをここで落とす。

    エージェント定義と SKILL.md が食い違うと、本体が期待する語と
    サブエージェントが返す語がずれる。#31 で開いたゲートはそこに戻る。
    """

    FORMAT = ("差分 <N> 件 (exit=<code>) → ")
    WORDS = "<CLEAN|DIRTY|STALE|OK|ERROR>"

    def read(self, *parts):
        with io.open(os.path.join(PLUGIN_ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_agent_and_skill_quote_the_same_format(self):
        agent = self.read("agents", "notion-fetcher.md")
        skill = self.read("skills", "notion-writeback", "SKILL.md")
        for name, text in (("notion-fetcher.md", agent), ("SKILL.md", skill)):
            for fragment in (self.WORDS, self.FORMAT):
                with self.subTest(doc=name, fragment=fragment):
                    # 本文を assertIn に渡すと落ちたときにファイル全文が出るので、
                    # 探した断片と落ちた側のファイル名だけを見せる。
                    self.assertTrue(
                        fragment in text,
                        f"{name} に {fragment!r} が無い。報告形式が 2 箇所で食い違っている")

    def test_agent_lists_every_marker_the_script_prints(self):
        """印は表の見出しであると同時に、スクリプトの実出力そのもの。"""
        agent = self.read("agents", "notion-fetcher.md")
        for marker in ("`CLEAN:`", "`DIRTY:`", "`STALE:`", "`OK  :`"):
            with self.subTest(marker=marker):
                self.assertTrue(marker in agent,
                                f"notion-fetcher.md に印 {marker} が無い")

    def test_agent_forbids_reporting_empty_output_as_clean(self):
        agent = self.read("agents", "notion-fetcher.md")
        self.assertTrue("ERROR" in agent, "notion-fetcher.md に ERROR の扱いが無い")
        self.assertTrue(re.search(r"空.*(0 行|0 バイト)", agent),
                        "notion-fetcher.md に「空＝異常」が書かれていない")

    def test_agent_appends_nothing_to_the_report_line(self):
        """#32 の例外（1 行目を添えてよい）を復活させない。

        実測（#33、12 回）で、末尾に何を添える形にしても報告行の前後に
        文章が付いた。添えさせること自体をやめたので、旧文が戻っていないか見る。
        """
        agent = self.read("agents", "notion-fetcher.md")
        self.assertNotIn("空なら「空」と書く", agent,
                         "#32 の「空なら『空』と書く」が復活している（#33 で削除した）")
        self.assertNotIn("末尾に添えてよい", agent,
                         "「添えてよい」が復活している。許可を残すと自然言語の余地が戻る")
        self.assertTrue(re.search(r"`ERROR` でも末尾に何も添えない", agent),
                        "notion-fetcher.md に「ERROR でも何も添えない」が無い")

    def test_agent_forbids_prose_around_the_report_line(self):
        """観測①は実在しないコマンドを創作した。診断させないこと自体に価値がある。"""
        agent = self.read("agents", "notion-fetcher.md")
        for fragment in ("報告行の前後に文章を書かない", "コマンドの修正案"):
            with self.subTest(fragment=fragment):
                self.assertTrue(fragment in agent,
                                f"notion-fetcher.md に {fragment!r} の禁止が無い")

    def test_body_is_told_to_ignore_prose_around_the_report_line(self):
        """禁止しても前置きは出る（実測 9/12）。本体側で読み捨てる契約が要る。"""
        skill = self.read("skills", "notion-writeback", "SKILL.md")
        prompt = self.read("skills", "notion-writeback", "reference",
                           "subagent-prompt.md")
        for name, text in (("SKILL.md", skill), ("subagent-prompt.md", prompt)):
            with self.subTest(doc=name):
                self.assertTrue(re.search(r"報告行だけを抜き出", text),
                                f"{name} に「報告行だけを抜き出す」が無い")


if __name__ == "__main__":
    unittest.main()
