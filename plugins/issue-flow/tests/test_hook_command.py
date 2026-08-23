"""hooks.json の登録内容そのものを検査する。

test_github_write_guard.py はスクリプトを直接叩くので、**起動経路を通らない**。
「ガードは正しいのに呼ばれない」という壊れ方はそこでは捕まらないので、ここで
(1) matcher が対象ツールを実際に捕まえるか、(2) コマンド文字列がそのまま実行できるか、
を見る。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
SH = shutil.which("sh")

sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))
from github_write_guard import FIELDS  # noqa: E402

BODY = "✅ 続けて進めてよい。\n🔴 ここを飛ばさない\n本文です。\n"
PREFIXES = ("mcp__github__", "mcp__remote-devices__github__")


def hook_entries():
    with open(HOOKS_JSON, encoding="utf-8") as f:
        hooks = json.load(f)
    return hooks["hooks"]["PreToolUse"]


def hook_matcher():
    matchers = [e["matcher"] for e in hook_entries()]
    assert len(matchers) == 1, f"matcher が 1 つでない: {matchers}"
    return matchers[0]


def hook_command():
    commands = [h["command"] for e in hook_entries() for h in e["hooks"]
                if h.get("type") == "command"]
    assert len(commands) == 1, f"command が 1 つでない: {commands}"
    return commands[0]


class TestHookCommandString(unittest.TestCase):
    def test_does_not_hardcode_python3(self):
        """python3 直書きは Windows でフックが起動しない（notion 側 #2 の再発防止）。"""
        cmd = hook_command()
        self.assertFalse(cmd.startswith("python3 "), cmd)
        self.assertIn("python.sh", cmd)

    def test_references_existing_paths(self):
        cmd = hook_command()
        self.assertIn("github_write_guard.py", cmd)
        for rel in (os.path.join("scripts", "python.sh"),
                    os.path.join("scripts", "github_write_guard.py")):
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN_ROOT, rel)), rel)


class TestHookMatcher(unittest.TestCase):
    def test_matcher_covers_every_guarded_tool(self):
        """FIELDS に足して matcher を忘れる、を捕まえる。

        ガードが正しくても matcher が捕まえなければフックは呼ばれず、
        @@FILE:...@@ がそのまま API に届く。
        """
        matcher = re.compile(hook_matcher())
        for name in FIELDS:
            for prefix in PREFIXES:
                with self.subTest(tool=prefix + name):
                    self.assertRegex(prefix + name, matcher)

    def test_matcher_does_not_match_other_mcp_servers(self):
        """🔴 別サーバーの同名ツールを捕まえない。

        matcher から `github` の限定を外すとここが落ちる。
        """
        matcher = re.compile(hook_matcher())
        for tool in ("mcp__gitea__issue_write",
                     "mcp__gitlab__create_pull_request",
                     "mcp__forgejo__add_issue_comment",
                     "mcp__notion__notion-update-page"):
            with self.subTest(tool=tool):
                self.assertNotRegex(tool, matcher)

    def test_matcher_does_not_match_superstring_tools(self):
        matcher = re.compile(hook_matcher())
        for tool in ("mcp__github__push_files_v2", "mcp__github__list_push_files"):
            with self.subTest(tool=tool):
                self.assertNotRegex(tool, matcher)

    def test_matcher_does_not_match_read_tools(self):
        matcher = re.compile(hook_matcher())
        for tool in ("mcp__github__issue_read", "mcp__github__pull_request_read"):
            with self.subTest(tool=tool):
                self.assertNotRegex(tool, matcher)


@unittest.skipIf(SH is None, "sh が無い")
class TestHookCommandExecutes(unittest.TestCase):
    """hooks.json のコマンド文字列を実際に sh へ渡して通す。

    ${CLAUDE_PLUGIN_ROOT} の展開・python.sh のインタプリタ解決・UTF-8 stdout を
    まとめて 1 度に通す経路。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "project")
        os.makedirs(self.root)
        with open(os.path.join(self.root, "body.md"), "w",
                  encoding="utf-8", newline="") as f:
            f.write(BODY)

    def run_hook(self, payload):
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
        env.pop("CLAUDE_PROJECT_DIR", None)
        proc = subprocess.run(
            [SH, "-c", hook_command()],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, env=env, timeout=60)
        out = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertTrue(out.strip(), "フックが何も出力していない")
        return json.loads(out)["hookSpecificOutput"]["updatedInput"]

    def test_pr_body_expanded_through_the_hook_command(self):
        updated = self.run_hook({
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"owner": "c18t", "repo": "r", "title": "t",
                           "body": "@@FILE:body.md@@"},
            "cwd": self.root})
        self.assertEqual(updated["body"], BODY)
        self.assertNotIn("@@FILE:", updated["body"])

    def test_push_files_expanded_through_the_hook_command(self):
        """コミット内容を git へ運ぶ経路なので、配列側も実コマンドで通す。"""
        updated = self.run_hook({
            "tool_name": "mcp__remote-devices__github__push_files",
            "tool_input": {"owner": "c18t", "repo": "r", "branch": "b", "message": "m",
                           "files": [{"path": "x.md", "content": "@@FILE:body.md@@"}]},
            "cwd": self.root})
        self.assertEqual(updated["files"][0]["content"], BODY)
        self.assertNotIn("@@FILE:", updated["files"][0]["content"])
        self.assertEqual(updated["files"][0]["path"], "x.md")


if __name__ == "__main__":
    unittest.main()
