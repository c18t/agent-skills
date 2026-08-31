"""scripts/python.sh と scripts/python.cmd の回帰テスト。

`python3` をコマンド名として決め打ちすると Windows で起動できず、
@@FILE: センチネルが未展開のままページ本文に書き込まれる（#2）。
ラッパーは python3 / python / py -3 のうち最初に見つかったもので実行し、
どれも無ければ **素通しではなく exit 2 で止める**。

`python.cmd` は同じ契約の Windows 版（#38）。`.sh` しか無いと PowerShell 側の
サブエージェントが `sh` を呼び出し演算子 `&` に「移植」してスクリプトが起動せず、
外部プロセスが 1 つも走らないので `$LASTEXITCODE` が空文字のままになる。

分離の方針:
- PATH を一時ディレクトリだけに差し替えて「どのインタプリタが居るか」を作る。
  実環境の python3 を見に行かせない。
- 偽インタプリタは引数をそのまま出力するだけのスクリプトにして、
  ラッパーがどれを選び何を渡したかを stdout から確かめる。
- sh 自体は PATH から外れても解決できるよう絶対パスで起動する。
"""
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
WRAPPER = os.path.join(SCRIPTS, "python.sh")
WRAPPER_CMD = os.path.join(SCRIPTS, "python.cmd")

# python.sh と python.cmd が共有する契約。どちらかだけ書き換わるのを落とす。
NOT_FOUND_MESSAGE = "python not found (tried: python3, python, py)"

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


class CmdWrapperTestCase(unittest.TestCase):
    """python.cmd 用の土台。

    .cmd は Windows でしか起動できないので、他のプラットフォームでは丸ごと skip する。
    CI の hook-tests は matrix に windows-latest を持っているのでそこで走る。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bindir = os.path.join(self._tmp.name, "bin")
        os.makedirs(self.bindir)

    def fake_interpreter(self, name, exit_code=0):
        """引数をそのまま出力して指定の終了コードで終わる偽インタプリタを PATH に置く。

        ⚠️ `.exe` の名前では置けない。Windows は `.exe` を PE 形式として検証するので、
        中身がバッチだと起動時に 216（not a valid Win32 application）で落ちる。
        `.bat` で置く——python.cmd は .exe / .bat / .cmd を探すので拾われる。
        """
        path = os.path.join(self.bindir, name + ".bat")
        with io.open(path, "w", encoding="ascii", newline="\r\n") as f:
            f.write("@echo off\n")
            f.write("echo CALLED:%s\n" % name)
            f.write(":loop\n")
            f.write('if "%~1"=="" goto done\n')
            f.write("echo ARG:%~1\n")
            f.write("shift\n")
            f.write("goto loop\n")
            f.write(":done\n")
            f.write("exit /b %d\n" % exit_code)
        return path

    def run_wrapper(self, *args, **kwargs):
        env = dict(os.environ)
        # PATH をテスト用ディレクトリだけにして、実環境のインタプリタを隠す。
        env["PATH"] = kwargs.pop("path", self.bindir)
        env.pop("PYTHONHOME", None)
        return subprocess.run(
            [WRAPPER_CMD, *args],
            capture_output=True, env=env, timeout=30)

    def lines(self, proc):
        return proc.stdout.decode("utf-8", "replace").splitlines()


@unittest.skipUnless(os.name == "nt", "python.cmd は Windows でしか起動できない")
class TestCmdExitCodePropagation(CmdWrapperTestCase):
    """🔴 このクラスが本 issue の本体（#38）。

    for ブロック内で %ERRORLEVEL% を使うと解析時に展開されて実行前の値（0）で固まり、
    **終了コードが常に 0 になる**。そうなると STALE も ERROR も `exit=0` として
    報告され、本体は「CLEAN だから差分を読まなくてよい」と誤読する。
    空出力より質の悪い壊れ方なので、ここで番号ごと固定する。
    """

    def test_propagates_every_exit_code(self):
        for code in (0, 1, 2, 3):
            with self.subTest(exit_code=code):
                self.setUp()
                self.fake_interpreter("python3", exit_code=code)
                proc = self.run_wrapper("script.py")
                self.assertEqual(
                    proc.returncode, code,
                    "終了コードが素通りしていない（enabledelayedexpansion と "
                    "!ERRORLEVEL! を確認する）: "
                    f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

    def test_error_exit_code_is_not_flattened_to_zero(self):
        """notion_mirror.py の EXIT_ERROR=3 が 0 に潰れないこと。

        3 は「照合できていない」の合図で、0 は「CLEAN」。ここが潰れると
        本体は書き戻してよいと判断してしまう。
        """
        self.fake_interpreter("python3", exit_code=3)
        proc = self.run_wrapper("notion_mirror.py", "diff")
        self.assertNotEqual(
            proc.returncode, 0,
            "ERROR(3) が 0 に潰れている。本体が CLEAN と誤読する")
        self.assertEqual(proc.returncode, 3)


@unittest.skipUnless(os.name == "nt", "python.cmd は Windows でしか起動できない")
class TestCmdInterpreterSelection(CmdWrapperTestCase):
    def test_prefers_python3_when_present(self):
        for name in ("python3", "python", "py"):
            self.fake_interpreter(name)
        proc = self.run_wrapper("script.py", "--flag")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            self.lines(proc), ["CALLED:python3", "ARG:script.py", "ARG:--flag"])

    def test_falls_back_to_python(self):
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
        """`--file wiki/my page.md` が 2 引数に割れないこと。

        %1 は引用を 1 段剥がすので、渡しは %* でなければならない。
        """
        self.fake_interpreter("python3")
        proc = self.run_wrapper("my script.py", "--out", "a b/c d.md")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            self.lines(proc),
            ["CALLED:python3", "ARG:my script.py", "ARG:--out", "ARG:a b/c d.md"])


@unittest.skipUnless(os.name == "nt", "python.cmd は Windows でしか起動できない")
class TestCmdNoInterpreter(CmdWrapperTestCase):
    def test_exits_2_when_nothing_found(self):
        """python.sh と同じく素通し（exit 0）にしない。"""
        proc = self.run_wrapper("script.py")
        self.assertEqual(
            proc.returncode, 2,
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn(NOT_FOUND_MESSAGE, proc.stderr.decode("utf-8", "replace"))

    def test_message_goes_to_stderr_not_stdout(self):
        """報告の出力ファイルは `> file 2>&1` で作られるが、stdout を汚さない。"""
        proc = self.run_wrapper("script.py")
        self.assertEqual(proc.stdout.decode("utf-8", "replace").strip(), "")


@unittest.skipUnless(os.name == "nt", "python.cmd は Windows でしか起動できない")
class TestCmdRealInterpreter(unittest.TestCase):
    """PATH を触らず、実環境のインタプリタで本当に Python が動くこと。"""

    def test_runs_real_python(self):
        proc = subprocess.run(
            [WRAPPER_CMD, "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(proc.stdout.decode("utf-8", "replace").strip(), "3")


class TestWrapperContractParity(unittest.TestCase):
    """python.sh と python.cmd が同じ契約を持つことの検査（プラットフォーム非依存）。

    Windows 専用テストは Linux で skip されるので、片方だけ書き換わる事故は
    windows-latest レグでしか捕まらない。ここは両方の環境で走る。
    """

    def read(self, path):
        with io.open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_both_wrappers_exist(self):
        for path in (WRAPPER, WRAPPER_CMD):
            self.assertTrue(os.path.isfile(path), f"{path} が無い")

    def test_both_print_the_same_not_found_message(self):
        for path in (WRAPPER, WRAPPER_CMD):
            with self.subTest(wrapper=os.path.basename(path)):
                self.assertIn(
                    NOT_FOUND_MESSAGE, self.read(path),
                    f"{os.path.basename(path)} の not found メッセージが "
                    "python.sh と食い違っている")

    def test_both_try_the_same_interpreters_in_order(self):
        """探索順は python3 → python → py。

        字面の出現位置ではなく、実際に候補を並べている行から取る
        （コメント中の "python3" が "python" として当たるため）。
        """
        expected = ["python3", "python", "py"]
        cases = (
            # python.sh: for p in python3 python py; do
            (WRAPPER, r"for p in ([^;]+);"),
            # python.cmd: for %%p in (python3.exe python.exe py.exe) do
            (WRAPPER_CMD, r"for %%p in \(([^)]+)\)"),
        )
        for path, pattern in cases:
            with self.subTest(wrapper=os.path.basename(path)):
                match = re.search(pattern, self.read(path))
                self.assertIsNotNone(
                    match, f"{os.path.basename(path)} に候補を並べた for が無い")
                found = [w.split(".")[0] for w in match.group(1).split()]
                self.assertEqual(
                    found, expected,
                    "インタプリタの探索順が python3 → python → py でない")

    def test_cmd_uses_delayed_expansion(self):
        """🔴 これが無いと終了コードが常に 0 になる（#38）。

        python.cmd を手で直すときに最も落としやすい 1 行なので、字面で押さえる。
        """
        text = self.read(WRAPPER_CMD)
        self.assertIn("enabledelayedexpansion", text,
                      "setlocal enabledelayedexpansion が無い。"
                      "for ブロック内の %ERRORLEVEL% は解析時に展開されて 0 で固まる")
        self.assertIn("!ERRORLEVEL!", text,
                      "!ERRORLEVEL! でなく %ERRORLEVEL% を使うと 0 が返る")

    def test_cmd_is_ascii_only(self):
        """cmd.exe は .cmd を OEM コードページ（日本語 Windows では cp932）で読む。

        UTF-8 の日本語コメントを置くと解析が壊れ、コメントの断片が
        コマンドとして実行される（実測）。日本語の説明は SKILL.md に置く。
        """
        with io.open(WRAPPER_CMD, "rb") as fh:
            raw = fh.read()
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as exc:
            self.fail(
                "python.cmd に非 ASCII 文字がある（cp932 で解析が壊れる）: "
                f"{raw[max(0, exc.start - 20):exc.start + 20]!r}")


if __name__ == "__main__":
    unittest.main()
