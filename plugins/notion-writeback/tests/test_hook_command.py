"""hooks.json の command 文字列そのものの回帰テスト。

test_notion_write_guard.py はガード本体を sys.executable で直接叩くので、
**フックの起動経路（command 文字列）は一切通らない**。#2 で壊れていたのは
まさにそこ（`python3` 決め打ちで Windows では起動すらしない）なので、
JSON に書いてある文字列を読み出して、シェル経由でそのまま実行する。

センチネルが展開されずに @@FILE:...@@ がページ本文になる事故は、
「ガードのロジック」ではなく「ガードが起動しない」ことで起きる。
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
PAGE_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
BODY = "✅ 本文です。\n"

SH = shutil.which("sh") or shutil.which("bash")


def hook_command():
    """PreToolUse フックの command 文字列を hooks.json から読み出す。"""
    with open(HOOKS_JSON, encoding="utf-8") as f:
        hooks = json.load(f)
    entries = hooks["hooks"]["PreToolUse"]
    commands = [h["command"] for e in entries for h in e["hooks"]
                if h.get("type") == "command"]
    assert len(commands) == 1, f"command が 1 つでない: {commands}"
    return commands[0]


class TestHookCommandString(unittest.TestCase):
    def test_does_not_hardcode_python3(self):
        """`python3 ...` で始まる決め打ちに戻っていないこと（#2 の回帰）。

        Windows では python3 が無いことが多く、フックが起動できないと
        センチネルが未展開のまま本文になる。
        """
        cmd = hook_command()
        self.assertFalse(
            cmd.startswith("python3 "),
            f"インタプリタを決め打ちしている: {cmd}")
        self.assertIn(
            "python.sh", cmd,
            f"インタプリタ探索ラッパーを経由していない: {cmd}")

    def test_references_existing_paths(self):
        """command が指すスクリプトが実在すること。"""
        cmd = hook_command()
        for rel in ("scripts/python.sh", "scripts/notion_write_guard.py"):
            self.assertIn(rel, cmd, f"{rel} を参照していない: {cmd}")
            self.assertTrue(
                os.path.isfile(os.path.join(PLUGIN_ROOT, *rel.split("/"))),
                f"{rel} が存在しない")

    def test_supports_codex_plugin_root(self):
        cmd = hook_command()
        self.assertIn("PLUGIN_ROOT", cmd)
        self.assertIn("CLAUDE_PLUGIN_ROOT", cmd)

    def test_windows_command_uses_codex_plugin_root(self):
        with open(HOOKS_JSON, encoding="utf-8") as f:
            hooks = json.load(f)
        handler = hooks["hooks"]["PreToolUse"][0]["hooks"][0]
        command = handler.get("commandWindows", "")
        self.assertIn("PLUGIN_ROOT", command)
        self.assertIn("python.cmd", command)


@unittest.skipIf(SH is None, "sh が無い環境ではフックコマンドを起動できない")
class TestHookCommandExecutes(unittest.TestCase):
    """command 文字列をシェルに渡して、実際にセンチネルが展開されること。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "project")
        os.makedirs(self.root)
        self.fake_home = os.path.join(self._tmp.name, "home")
        os.makedirs(self.fake_home)
        docs = os.path.join(self.root, "docs")
        os.makedirs(docs)
        with open(os.path.join(docs, "page.md"), "w",
                  encoding="utf-8", newline="") as f:
            f.write(BODY)

    def run_hook(self, payload):
        env = dict(os.environ)
        # フックランナーが渡す変数。command 文字列はこれを展開する。
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
        env["HOME"] = self.fake_home
        env["USERPROFILE"] = self.fake_home
        env.pop("CLAUDE_PROJECT_DIR", None)
        proc = subprocess.run(
            [SH, "-c", hook_command()],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, env=env, timeout=60)
        out = proc.stdout.decode("utf-8", "replace")
        return proc, (json.loads(out) if out.strip() else None)

    def test_sentinel_is_expanded_through_the_hook_command(self):
        """@@FILE:...@@ がファイル全文に置換されて返ること。

        ここが通らない＝センチネルがそのまま Notion に書き込まれる、
        という #2 の事故そのもの。
        """
        proc, result = self.run_hook({
            "tool_name": "mcp__notion__notion-update-page",
            "tool_input": {
                "command": "replace_content",
                "page_id": PAGE_ID,
                "new_str": "@@FILE:docs/page.md@@",
            },
            "cwd": self.root,
            "session_id": "hook-command-test",
        })
        self.assertEqual(
            proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIsNotNone(
            result, "フックが起動していない（出力が空＝素通し）")
        updated = result["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["new_str"], BODY)
        self.assertNotIn("@@FILE:", updated["new_str"])


if __name__ == "__main__":
    unittest.main()
