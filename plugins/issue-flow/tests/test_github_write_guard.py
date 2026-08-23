"""github_write_guard.py の回帰テスト。

フックは stdin に PreToolUse の JSON を受け取り stdout に JSON を返すだけなので、
subprocess で本体をそのまま実行する。サーバーもモックも使わない。

分離の方針:
- 基準ディレクトリの外（`../outside.md`）を表現できるよう、root は tmpdir から 1 段掘る。
- CLAUDE_PROJECT_DIR は既定で env から外す（CI ランナーが持っていることがある）。

本文定数には PR #28 で実際に化けた一文を使っている。「進めて」が「進んで」へ
静かに書き換わり、目視レビューを通り抜けた——このテストはその記録も兼ねる。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "github_write_guard.py")

BODY = "✅ 続けて進めてよい。\n🔴 ここを飛ばさない\n本文です。\n"


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

    def run_guard(self, tool_input, tool_name="mcp__github__create_pull_request",
                  env_extra=None, cwd=None):
        payload = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": self.root if cwd is None else cwd,
            "session_id": "test-session",
        }
        return self.run_raw(json.dumps(payload).encode("utf-8"), env_extra)

    def run_raw(self, raw_stdin, env_extra=None):
        env = dict(os.environ)
        env["HOME"] = self.fake_home
        env["USERPROFILE"] = self.fake_home
        env.pop("CLAUDE_PROJECT_DIR", None)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            input=raw_stdin, capture_output=True, env=env, timeout=30)
        out = proc.stdout.decode("utf-8")
        return proc, (json.loads(out) if out.strip() else None)

    def write_file(self, rel, content=BODY):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    def assert_ok(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))

    def updated(self, result):
        self.assertIsNotNone(result, "注入は JSON を出力するはず")
        hso = result.get("hookSpecificOutput") or {}
        self.assertIn("updatedInput", hso, result)
        return hso["updatedInput"]

    def assert_deny(self, result, fragment=None):
        self.assertIsNotNone(result, "deny は JSON を出力するはず")
        hso = result.get("hookSpecificOutput") or {}
        self.assertEqual(hso.get("permissionDecision"), "deny", result)
        if fragment:
            self.assertIn(fragment, hso.get("permissionDecisionReason", ""))

    def assert_passthrough(self, proc, result):
        self.assert_ok(proc)
        self.assertIsNone(result, "素通しは何も出力しないはず")


class TestScalarInjection(GuardTestCase):
    def test_pr_body_is_injected(self):
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard({"body": "@@FILE:docs/pr-body.md@@"})
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_injects_and_preserves_other_keys(self):
        """updatedInput は部分マージではなく tool_input 全体を置き換える（回帰ポイント）。

        注入フィールド以外が欠けると owner / repo / title が丸ごと失われる。
        """
        self.write_file("docs/pr-body.md")
        ti = {
            "owner": "c18t", "repo": "agent-skills", "title": "t",
            "head": "feature/x", "base": "main",
            "body": "@@FILE:docs/pr-body.md@@",
        }
        proc, result = self.run_guard(ti)
        self.assert_ok(proc)
        expected = dict(ti)
        expected["body"] = BODY
        self.assertEqual(self.updated(result), expected)

    def test_issue_write_body_is_injected(self):
        self.write_file("docs/issue.md")
        proc, result = self.run_guard(
            {"method": "create", "body": "@@FILE:docs/issue.md@@"},
            tool_name="mcp__github__issue_write")
        self.assert_ok(proc)
        updated = self.updated(result)
        self.assertEqual(updated["body"], BODY)
        self.assertEqual(updated["method"], "create")

    def test_add_issue_comment_body_is_injected(self):
        self.write_file("docs/comment.md")
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/comment.md@@"},
            tool_name="mcp__github__add_issue_comment")
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_merge_commit_message_is_injected_and_title_untouched(self):
        self.write_file("docs/merge.md")
        proc, result = self.run_guard(
            {"merge_method": "squash", "commit_title": "feat: x",
             "commit_message": "@@FILE:docs/merge.md@@"},
            tool_name="mcp__github__merge_pull_request")
        self.assert_ok(proc)
        updated = self.updated(result)
        self.assertEqual(updated["commit_message"], BODY)
        self.assertEqual(updated["commit_title"], "feat: x")

    def test_create_or_update_file_content_is_injected(self):
        self.write_file("docs/page.md")
        proc, result = self.run_guard(
            {"path": "docs/page.md", "message": "m",
             "content": "@@FILE:docs/page.md@@"},
            tool_name="mcp__github__create_or_update_file")
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["content"], BODY)

    def test_no_sentinel_passes_through(self):
        proc, result = self.run_guard({"body": "ふつうの本文"})
        self.assert_passthrough(proc, result)

    def test_partial_sentinel_text_passes_through(self):
        """文中に埋め込まれたセンチネルは展開しない（deny でもない）。

        fullmatch の意味論。「なぜ展開されないのか」を説明する必要が出る箇所なので固定する。
        """
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard(
            {"body": "前置き\n@@FILE:docs/pr-body.md@@\n後書き"})
        self.assert_passthrough(proc, result)

    def test_sentinel_with_surrounding_whitespace_is_injected(self):
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard({"body": "\n  @@FILE:docs/pr-body.md@@\n"})
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_missing_field_passes_through(self):
        proc, result = self.run_guard({"owner": "c18t", "repo": "agent-skills"})
        self.assert_passthrough(proc, result)


class TestPushFilesArray(GuardTestCase):
    """push_files の files[] は要素ごとに独立して判定する（notion に無い構造）。"""

    def push(self, files, **extra):
        ti = {"owner": "c18t", "repo": "agent-skills", "branch": "x",
              "message": "m", "files": files}
        ti.update(extra)
        return self.run_guard(ti, tool_name="mcp__github__push_files")

    def test_all_files_injected_preserving_path_and_order(self):
        self.write_file("docs/a.md", "AAA\n")
        self.write_file("docs/b.md", "BBB\n")
        proc, result = self.push([
            {"path": "x/a.md", "content": "@@FILE:docs/a.md@@"},
            {"path": "x/b.md", "content": "@@FILE:docs/b.md@@"},
        ])
        self.assert_ok(proc)
        files = self.updated(result)["files"]
        self.assertEqual([f["path"] for f in files], ["x/a.md", "x/b.md"])
        self.assertEqual([f["content"] for f in files], ["AAA\n", "BBB\n"])

    def test_mixed_sentinel_and_literal(self):
        """一部だけセンチネルでもよい。非センチネル要素は byte 同一で残る。"""
        self.write_file("docs/a.md", "AAA\n")
        literal = "そのままの文字列\n"
        proc, result = self.push([
            {"path": "x/a.md", "content": "@@FILE:docs/a.md@@"},
            {"path": "x/b.md", "content": literal},
        ])
        self.assert_ok(proc)
        files = self.updated(result)["files"]
        self.assertEqual(files[0]["content"], "AAA\n")
        self.assertEqual(files[1]["content"], literal)

    def test_no_sentinel_in_any_file_passes_through(self):
        proc, result = self.push([
            {"path": "x/a.md", "content": "aaa"},
            {"path": "x/b.md", "content": "bbb"},
        ])
        self.assert_passthrough(proc, result)

    def test_missing_file_in_one_element_denies_whole_call(self):
        """1 要素でも解決できなければ呼び出し全体を止める（部分注入で push しない）。"""
        self.write_file("docs/a.md", "AAA\n")
        proc, result = self.push([
            {"path": "x/a.md", "content": "@@FILE:docs/a.md@@"},
            {"path": "x/b.md", "content": "@@FILE:docs/nope.md@@"},
        ])
        self.assert_ok(proc)
        self.assert_deny(result, "見つからない")
        self.assert_deny(result, "files[1].content")

    def test_outside_base_dir_in_one_element_denies(self):
        with open(os.path.join(os.path.dirname(self.root), "outside.md"),
                  "w", encoding="utf-8") as f:
            f.write("secret\n")
        proc, result = self.push([
            {"path": "x/a.md", "content": "ok"},
            {"path": "x/b.md", "content": "ok"},
            {"path": "x/c.md", "content": "@@FILE:../outside.md@@"},
        ])
        self.assert_ok(proc)
        self.assert_deny(result, "基準ディレクトリ")
        self.assert_deny(result, "files[2].content")

    def test_non_list_files_passes_through(self):
        proc, result = self.push({"a": {"content": "@@FILE:docs/a.md@@"}})
        self.assert_passthrough(proc, result)

    def test_non_dict_element_is_left_alone(self):
        """要素が dict でなくても TypeError で落ちない。"""
        self.write_file("docs/b.md", "BBB\n")
        proc, result = self.push([
            "@@FILE:docs/a.md@@",
            {"path": "x/b.md", "content": "@@FILE:docs/b.md@@"},
        ])
        self.assert_ok(proc)
        files = self.updated(result)["files"]
        self.assertEqual(files[0], "@@FILE:docs/a.md@@")
        self.assertEqual(files[1]["content"], "BBB\n")

    def test_other_top_level_keys_survive(self):
        self.write_file("docs/a.md", "AAA\n")
        proc, result = self.push(
            [{"path": "x/a.md", "content": "@@FILE:docs/a.md@@"}])
        self.assert_ok(proc)
        updated = self.updated(result)
        self.assertEqual(updated["owner"], "c18t")
        self.assertEqual(updated["repo"], "agent-skills")
        self.assertEqual(updated["branch"], "x")
        self.assertEqual(updated["message"], "m")

    def test_commit_message_field_is_not_touched(self):
        """push_files の message は対象外（意図的なスコープ境界）。"""
        self.write_file("docs/a.md", "AAA\n")
        proc, result = self.push(
            [{"path": "x/a.md", "content": "@@FILE:docs/a.md@@"}],
            message="@@FILE:docs/a.md@@")
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["message"], "@@FILE:docs/a.md@@")


class TestFailClosed(GuardTestCase):
    def test_missing_file_is_denied(self):
        proc, result = self.run_guard({"body": "@@FILE:docs/nope.md@@"})
        self.assert_ok(proc)
        self.assert_deny(result, "見つからない")

    def test_outside_base_dir_is_denied(self):
        with open(os.path.join(os.path.dirname(self.root), "outside.md"),
                  "w", encoding="utf-8") as f:
            f.write("secret\n")
        proc, result = self.run_guard({"body": "@@FILE:../outside.md@@"})
        self.assert_ok(proc)
        self.assert_deny(result, "基準ディレクトリ")

    def test_symlink_escaping_base_dir_is_denied(self):
        outside = os.path.join(os.path.dirname(self.root), "outside.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("secret\n")
        link = os.path.join(self.root, "link.md")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("symlink を作れない環境")
        proc, result = self.run_guard({"body": "@@FILE:link.md@@"})
        self.assert_ok(proc)
        self.assert_deny(result, "基準ディレクトリ")

    def test_directory_is_denied(self):
        os.makedirs(os.path.join(self.root, "docs"))
        proc, result = self.run_guard({"body": "@@FILE:docs@@"})
        self.assert_ok(proc)
        self.assert_deny(result, "見つからない")

    def test_deny_reason_names_the_field(self):
        proc, result = self.run_guard(
            {"commit_message": "@@FILE:docs/nope.md@@"},
            tool_name="mcp__github__merge_pull_request")
        self.assert_ok(proc)
        self.assert_deny(result, "commit_message")


class TestRootResolution(GuardTestCase):
    """基準ディレクトリは CLAUDE_PROJECT_DIR →フック入力の cwd →カレントの順。

    cwd を先に見ると、リポジトリのサブディレクトリで起動しただけで基準がそこへずれる。
    """

    def test_project_dir_wins_over_cwd(self):
        self.write_file("docs/pr-body.md")
        sub = os.path.join(self.root, "sub")
        os.makedirs(sub)
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/pr-body.md@@"},
            env_extra={"CLAUDE_PROJECT_DIR": self.root}, cwd=sub)
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_falls_back_to_cwd_without_project_dir(self):
        """CLAUDE_PROJECT_DIR が無い環境（Cowork 等）では cwd が基準になる。"""
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard({"body": "@@FILE:docs/pr-body.md@@"})
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_outside_project_dir_is_denied_even_when_inside_cwd(self):
        outside = os.path.dirname(self.root)
        with open(os.path.join(outside, "outside.md"), "w", encoding="utf-8") as f:
            f.write("secret\n")
        proc, result = self.run_guard(
            {"body": "@@FILE:../outside.md@@"},
            env_extra={"CLAUDE_PROJECT_DIR": self.root}, cwd=outside)
        self.assert_ok(proc)
        self.assert_deny(result, "基準ディレクトリ")


class TestEncoding(GuardTestCase):
    """cp932 で出力が消えるとフックは「意見なし」扱いになり、センチネルがそのまま通る。"""

    def test_emoji_survives_cp932_stdio(self):
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/pr-body.md@@"},
            env_extra={"PYTHONIOENCODING": "cp932"})
        self.assert_ok(proc)
        self.assertIsNotNone(result, "cp932 でも出力が消えてはいけない")
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_cp932_push_files_array(self):
        """配列経路は systemMessage が長くファイル名も載るので別途見る。"""
        self.write_file("docs/a.md")
        proc, result = self.run_guard(
            {"files": [{"path": "x/a.md", "content": "@@FILE:docs/a.md@@"}]},
            tool_name="mcp__github__push_files",
            env_extra={"PYTHONIOENCODING": "cp932"})
        self.assert_ok(proc)
        self.assertIsNotNone(result, "cp932 でも出力が消えてはいけない")
        self.assertEqual(self.updated(result)["files"][0]["content"], BODY)

    def test_japanese_filename_in_sentinel(self):
        self.write_file("docs/本文.md")
        proc, result = self.run_guard({"body": "@@FILE:docs/本文.md@@"})
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)


class TestScope(GuardTestCase):
    """対象は GitHub MCP の書き込み系ツールだけ。"""

    def test_bare_github_prefix_is_matched(self):
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/pr-body.md@@"},
            tool_name="mcp__github__create_pull_request")
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_remote_devices_prefix_is_matched(self):
        """ハーネスによる接頭辞の揺れを吸収する。"""
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/pr-body.md@@"},
            tool_name="mcp__remote-devices__github__create_pull_request")
        self.assert_ok(proc)
        self.assertEqual(self.updated(result)["body"], BODY)

    def test_read_tool_passes_through(self):
        self.write_file("docs/pr-body.md")
        proc, result = self.run_guard(
            {"body": "@@FILE:docs/pr-body.md@@"},
            tool_name="mcp__github__issue_read")
        self.assert_passthrough(proc, result)

    def test_other_mcp_servers_pass_through(self):
        """🔴 別サーバーの同名ツールに割り込まない。

        issue_write / create_pull_request / add_issue_comment は GitHub 固有の名前ではない。
        ツール名だけの判定に戻すとこのテストが落ちる——フェイルクローズなので、
        誤爆は空振りでは済まず無関係な呼び出しを deny しうる。
        """
        self.write_file("docs/pr-body.md")
        for tool in ("mcp__gitea__issue_write",
                     "mcp__gitlab__create_pull_request",
                     "mcp__forgejo__add_issue_comment"):
            with self.subTest(tool=tool):
                proc, result = self.run_guard(
                    {"body": "@@FILE:docs/pr-body.md@@"}, tool_name=tool)
                self.assert_passthrough(proc, result)

    def test_superstring_tool_names_pass_through(self):
        """🔴 部分一致で別ツールを誤爆しない（`if name in tool` に戻すと落ちる）。"""
        self.write_file("docs/a.md")
        for tool in ("mcp__github__push_files_v2", "mcp__github__list_push_files"):
            with self.subTest(tool=tool):
                proc, result = self.run_guard(
                    {"files": [{"path": "x", "content": "@@FILE:docs/a.md@@"}]},
                    tool_name=tool)
                self.assert_passthrough(proc, result)

    def test_missing_tool_input_passes_through(self):
        proc, result = self.run_raw(json.dumps(
            {"tool_name": "mcp__github__create_pull_request",
             "cwd": self.root}).encode("utf-8"))
        self.assert_passthrough(proc, result)

    def test_non_dict_tool_input_passes_through(self):
        proc, result = self.run_raw(json.dumps(
            {"tool_name": "mcp__github__create_pull_request",
             "tool_input": "not-a-dict", "cwd": self.root}).encode("utf-8"))
        self.assert_passthrough(proc, result)

    def test_malformed_stdin_passes_through(self):
        """入力が読めないときはフェイルオープン（フックの故障で書き込みを止めない）。"""
        proc, result = self.run_raw(b"not json at all")
        self.assert_passthrough(proc, result)


if __name__ == "__main__":
    unittest.main()
