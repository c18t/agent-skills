"""notion_write_guard.py の回帰テスト。

フックは stdin に PreToolUse の JSON を受け取り stdout に JSON を返すだけなので、
subprocess で本体をそのまま実行する。サーバーもモックも使わない。

分離の方針:
- 状態ファイルは <tmpdir>/claude-notion-guard/<session_id>.json なので、
  テストごとに session_id を UUID にして衝突を避ける。
- fetched_this_session() が実環境のトランスクリプト（$HOME/.claude 配下）を
  読みに行かないよう、HOME / USERPROFILE を一時ディレクトリへ向ける。
  トランスクリプトが見つからないときはフェイルオープン（素通し）になる。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "notion_write_guard.py")
PAGE_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
EMOJI_TEXT = "✅ 完了\n🔴 ここを飛ばさない\n本文です。\n"


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = self._tmp.name
        # project/ の外に outside.md を置けるよう、root は 1 段掘る
        self.root = os.path.join(base, "project")
        os.makedirs(self.root)
        self.fake_home = os.path.join(base, "home")
        os.makedirs(self.fake_home)
        self.session_id = f"test-{uuid.uuid4().hex}"

    def run_guard(self, tool_input, env_extra=None, tool_name="mcp__notion__notion-update-page",
                  cwd=None):
        payload = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": self.root if cwd is None else cwd,
            "session_id": self.session_id,
        }
        env = dict(os.environ)
        env["HOME"] = self.fake_home
        env["USERPROFILE"] = self.fake_home
        env.pop("CLAUDE_PROJECT_DIR", None)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, env=env, timeout=30)
        out = proc.stdout.decode("utf-8")
        return proc, (json.loads(out) if out.strip() else None)

    def write_file(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    def assert_deny(self, result, fragment=None):
        self.assertIsNotNone(result, "deny は JSON を出力するはず")
        hso = result.get("hookSpecificOutput") or {}
        self.assertEqual(hso.get("permissionDecision"), "deny", result)
        if fragment:
            self.assertIn(fragment, hso.get("permissionDecisionReason", ""))


class TestSentinelInjection(GuardTestCase):
    def test_injects_file_and_preserves_other_keys(self):
        """@@FILE:@@ はファイル全文に置換され、元の入力の他のキーが保たれる。

        updatedInput は部分マージではなく tool_input 全体を置き換えるため、
        注入フィールド以外が欠けると引数が丸ごと失われる（回帰ポイント）。
        """
        self.write_file(os.path.join("docs", "page.md"), EMOJI_TEXT)
        ti = {
            "command": "replace_content",
            "page_id": PAGE_ID,
            "new_str": "@@FILE:docs/page.md@@",
            "extra_key": "must-survive",
        }
        proc, result = self.run_guard(ti)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        updated = result["hookSpecificOutput"]["updatedInput"]
        expected = dict(ti)
        expected["new_str"] = EMOJI_TEXT
        self.assertEqual(updated, expected)

    def test_outside_project_is_denied(self):
        with open(os.path.join(os.path.dirname(self.root), "outside.md"),
                  "w", encoding="utf-8") as f:
            f.write("secret\n")
        ti = {
            "command": "replace_content",
            "page_id": PAGE_ID,
            "new_str": "@@FILE:../outside.md@@",
        }
        proc, result = self.run_guard(ti)
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "基準ディレクトリ")

    def test_missing_file_is_denied(self):
        ti = {
            "command": "replace_content",
            "page_id": PAGE_ID,
            "new_str": "@@FILE:docs/no-such-file.md@@",
        }
        proc, result = self.run_guard(ti)
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "見つからない")

    def test_emoji_survives_cp932_stdio(self):
        """PYTHONIOENCODING=cp932 でも異常終了せず UTF-8 JSON を出力する。

        emit() が print() だと cp932 で UnicodeEncodeError → 出力なしで終了 →
        Claude Code が「意見なし」として素通し、という事故の再現条件。
        """
        self.write_file(os.path.join("docs", "page.md"), EMOJI_TEXT)
        ti = {
            "command": "replace_content",
            "page_id": PAGE_ID,
            "new_str": "@@FILE:docs/page.md@@",
        }
        proc, result = self.run_guard(ti, env_extra={"PYTHONIOENCODING": "cp932"})
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIsNotNone(result, "cp932 でも出力が消えてはいけない")
        self.assertEqual(
            result["hookSpecificOutput"]["updatedInput"]["new_str"], EMOJI_TEXT)


class TestRootResolution(GuardTestCase):
    """@@FILE: の基準ディレクトリは CLAUDE_PROJECT_DIR →フック入力の cwd →カレントの順。

    cwd を先に見ると、リポジトリのサブディレクトリで Claude Code を起動しただけで
    基準がそこへずれ、ドキュメントが言う「プロジェクトルートからの相対パス」が
    起動位置任せになる（issue #4）。
    """

    def sentinel(self, rel):
        return {
            "command": "replace_content",
            "page_id": PAGE_ID,
            "new_str": f"@@FILE:{rel}@@",
        }

    def test_project_dir_wins_over_cwd(self):
        """サブディレクトリで起動しても、ルート相対のパスが通る。"""
        self.write_file(os.path.join("docs", "page.md"), EMOJI_TEXT)
        sub = os.path.join(self.root, "sub")
        os.makedirs(sub)
        proc, result = self.run_guard(
            self.sentinel("docs/page.md"),
            env_extra={"CLAUDE_PROJECT_DIR": self.root},
            cwd=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            result["hookSpecificOutput"]["updatedInput"]["new_str"], EMOJI_TEXT)

    def test_falls_back_to_cwd_without_project_dir(self):
        """CLAUDE_PROJECT_DIR が無い環境（Cowork 等）では cwd が基準になる。"""
        self.write_file(os.path.join("docs", "page.md"), EMOJI_TEXT)
        proc, result = self.run_guard(self.sentinel("docs/page.md"))
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            result["hookSpecificOutput"]["updatedInput"]["new_str"], EMOJI_TEXT)

    def test_outside_project_dir_is_denied_even_when_inside_cwd(self):
        """cwd の内側でも CLAUDE_PROJECT_DIR の外なら deny する（優先順位入れ替えの副作用）。"""
        outside = os.path.dirname(self.root)
        with open(os.path.join(outside, "outside.md"), "w", encoding="utf-8") as f:
            f.write("secret\n")
        proc, result = self.run_guard(
            self.sentinel("../outside.md"),
            env_extra={"CLAUDE_PROJECT_DIR": self.root},
            cwd=outside)
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "基準ディレクトリ")


class TestPageIdValidation(GuardTestCase):
    def test_non_hex_page_id_is_denied(self):
        ti = {
            "command": "update_content",
            "page_id": "not-a-page-id",
            "content_updates": [{"old_str": "a", "new_str": "b"}],
        }
        proc, result = self.run_guard(ti)
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "page_id")

    def test_hyphenated_uuid_is_accepted(self):
        hyphenated = f"{PAGE_ID[:8]}-{PAGE_ID[8:12]}-{PAGE_ID[12:16]}-{PAGE_ID[16:20]}-{PAGE_ID[20:]}"
        ti = {
            "command": "update_content",
            "page_id": hyphenated,
            "content_updates": [{"old_str": "a", "new_str": "b"}],
        }
        proc, result = self.run_guard(ti)
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(result, f"素通しのはずが出力があった: {result}")


class TestUpdateContentSuppression(GuardTestCase):
    def _update(self, n_updates=1):
        return {
            "command": "update_content",
            "page_id": PAGE_ID,
            "content_updates": [
                {"old_str": f"a{i}", "new_str": f"b{i}"} for i in range(n_updates)
            ],
        }

    def test_multiple_updates_in_one_call_is_denied(self):
        proc, result = self.run_guard(self._update(n_updates=2))
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "1 件ずつ")

    def test_fourth_call_to_same_page_is_denied(self):
        for i in range(3):
            proc, result = self.run_guard(self._update())
            self.assertEqual(proc.returncode, 0)
            self.assertIsNone(result, f"{i + 1} 回目は素通しのはず: {result}")
        proc, result = self.run_guard(self._update())
        self.assertEqual(proc.returncode, 0)
        self.assert_deny(result, "上限")

    def test_other_session_is_not_affected(self):
        for _ in range(3):
            self.run_guard(self._update())
        self.session_id = f"test-{uuid.uuid4().hex}"
        proc, result = self.run_guard(self._update())
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(result, "セッションが変われば回数はリセットされる")


class TestScope(GuardTestCase):
    def test_unrelated_tool_passes_through(self):
        proc, result = self.run_guard(
            {"command": "update_content"}, tool_name="mcp__other__something-else")
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(result)

    def test_update_properties_passes_through(self):
        proc, result = self.run_guard(
            {"command": "update_properties", "page_id": "not-checked"})
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
