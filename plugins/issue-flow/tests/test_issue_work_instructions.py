"""issue-work のランタイム別安全境界を固定する手順テスト。"""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "issue-work" / "SKILL.md"
BOUNDARIES = PLUGIN_ROOT / "skills" / "issue-work" / "reference" / "runtime-boundaries.md"
GITHUB_MCP = PLUGIN_ROOT / "skills" / "issue-work" / "reference" / "github-mcp.md"


class TestCodexWorktreeBoundaryInstructions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.boundaries = BOUNDARIES.read_text(encoding="utf-8")
        cls.github_mcp = GITHUB_MCP.read_text(encoding="utf-8")

    def test_skill_routes_codex_to_boundary_reference(self):
        self.assertIn("reference/runtime-boundaries.md", self.skill)
        self.assertIn(".claude/worktrees/", self.skill)

    def test_preflight_checks_root_and_branch(self):
        for command in ("pwd", "git rev-parse --show-toplevel",
                        "git branch --show-current"):
            with self.subTest(command=command):
                self.assertIn(command, self.boundaries)
        self.assertIn("絶対 `workdir`", self.boundaries)

    def test_cleanup_protects_user_files(self):
        self.assertIn("git status --short", self.boundaries)
        self.assertIn("git worktree remove --force", self.boundaries)
        self.assertIn("ユーザー所有", self.boundaries)

    def test_temporary_files_are_scoped_to_the_thread(self):
        self.assertIn("scripts/session_tmp.py", self.boundaries)
        self.assertIn("CODEX_THREAD_ID", self.boundaries)
        self.assertIn("CODEX_SESSION_ID", self.boundaries)
        self.assertIn(".codex/tmp/<ID>/", self.skill)

    def test_hook_verification_is_runtime_aware(self):
        for marker in ("Source / Matcher / Trust", "updatedInput",
                       "systemMessage", "今回送った一意な"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.github_mcp)


if __name__ == "__main__":
    unittest.main()
