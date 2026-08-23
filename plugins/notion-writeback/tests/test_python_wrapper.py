"""scripts/python.sh の回帰テスト。

`python3` をコマンド名として決め打ちすると Windows で起動できず、
@@FILE: センチネルが未展開のままページ本文に書き込まれる（#2）。
ラッパーは python3 / python / py -3 のうち最初に見つかったもので実行し、
どれも無ければ **素通しではなく exit 2 で止める**。

分離の方針:
- PATH を一時ディレクトリだけに差し替えて「どのインタプリタが居るか」を作る。
  実環境の python3 を見に行かせない。
- 偽インタプリタは引数をそのまま出力するだけのスクリプトにして、
  ラッパーがどれを選び何を渡したかを stdout から確かめる。
- sh 自体は PATH から外れても解決できるよう絶対パスで起動する。
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

WRAPPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "python.sh")

# Windows ランナーでも Git Bash の sh が居る。PATH を潰すので絶対パスで押さえる。
SH = shutil.which("sh") or shutil.which("bash")


@unittest.skipIf(SH is None, "sh が無い環境ではラッパーを起動できない")
class PythonWrapperTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bindir = os.path.join(self._tmp.name, "bin")
        os.makedirs(self.bindir)

    def fake_interpreter(self, name):
        """引数をそのまま 1 行ずつ出力する偽インタプリタを PATH に置く。

        `py -3 foo` のように追加引数が付くかどうかを、呼ばれた側から観測する。
        """
        path = os.path.join(self.bindir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n")
            f.write(f'echo "CALLED:{name}"\n')
            f.write('for a in "$@"; do echo "ARG:$a"; done\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def run_wrapper(self, *args):
        env = dict(os.environ)
        # PATH をテスト用ディレクトリだけにして、実環境のインタプリタを隠す。
        env["PATH"] = self.bindir
        env.pop("PYTHONHOME", None)
        return subprocess.run(
            [SH, WRAPPER, *args],
            capture_output=True, env=env, timeout=30)

    def lines(self, proc):
        return proc.stdout.decode("utf-8", "replace").splitlines()


class TestInterpreterSelection(PythonWrapperTestCase):
    def test_prefers_python3_when_present(self):
        for name in ("python3", "python", "py"):
            self.fake_interpreter(name)
        proc = self.run_wrapper("script.py", "--flag")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            self.lines(proc), ["CALLED:python3", "ARG:script.py", "ARG:--flag"])

    def test_falls_back_to_python(self):
        """python3 が無い環境（Windows の python.org インストーラ版など）。"""
        for name in ("python", "py"):
            self.fake_interpreter(name)
        proc = self.run_wrapper("script.py")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.lines(proc), ["CALLED:python", "ARG:script.py"])

    def test_py_launcher_gets_dash_3(self):
        """py ランチャのときだけ -3 を前置する（Python 2 を掴まないため）。"""
        self.fake_interpreter("py")
        proc = self.run_wrapper("script.py", "--flag")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            self.lines(proc),
            ["CALLED:py", "ARG:-3", "ARG:script.py", "ARG:--flag"])

    def test_arguments_with_spaces_are_not_split(self):
        """引数の分割は @@FILE: のパスに空白があると壊れるので "$@" を守る。"""
        self.fake_interpreter("python3")
        proc = self.run_wrapper("my script.py", "--out", "a b/c d.md")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            self.lines(proc),
            ["CALLED:python3", "ARG:my script.py", "ARG:--out", "ARG:a b/c d.md"])


class TestNoInterpreter(PythonWrapperTestCase):
    def test_exits_2_when_nothing_found(self):
        """🔴 素通し（exit 0）にしてはいけない。

        フックが exit 0 で何も出力しないと Claude Code は「意見なし」として
        通すため、@@FILE:...@@ が展開されないまま本文になる。
        exit 2 で初めてツール呼び出しがブロックされる。
        """
        proc = self.run_wrapper("script.py")
        self.assertEqual(
            proc.returncode, 2,
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn("python not found", proc.stderr.decode("utf-8", "replace"))


class TestRealInterpreter(unittest.TestCase):
    """PATH を触らず、実環境のインタプリタで本当に Python が動くこと。"""

    @unittest.skipIf(SH is None, "sh が無い環境ではラッパーを起動できない")
    def test_runs_real_python(self):
        proc = subprocess.run(
            [SH, WRAPPER, "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(proc.stdout.decode("utf-8", "replace").strip(), "3")


if __name__ == "__main__":
    unittest.main()
