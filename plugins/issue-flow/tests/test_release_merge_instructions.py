"""release-merge の worktree 配置規約と Codex 境界規約を固定する手順テスト。"""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "release-merge" / "SKILL.md"
TROUBLESHOOTING = (
    PLUGIN_ROOT / "skills" / "release-merge" / "reference" / "troubleshooting.md"
)
BOUNDARIES = (
    PLUGIN_ROOT / "skills" / "issue-work" / "reference" / "runtime-boundaries.md"
)


class TestReleaseWorktreePlacement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.troubleshooting = TROUBLESHOOTING.read_text(encoding="utf-8")

    def test_worktree_lives_inside_the_repository(self):
        self.assertIn(".claude/worktrees/", self.skill)
        self.assertIn(".claude/worktrees/release-my-plugin-1.2.0", self.skill)

    def test_sibling_path_is_not_offered_as_the_placement(self):
        # 0.7.1 までの既定。配置としては消え、禁止としてだけ残る。
        self.assertNotIn(
            "worktree パス … `../", self.skill,
            "sibling パスが worktree パスの定義に残っている",
        )
        self.assertIn(
            "🔴 **リポジトリ外の sibling パス（`../<リポジトリ名>-...`）へ作らない**",
            self.skill,
        )
        self.assertIn("../<リポジトリ名>-release-", self.troubleshooting)

    def test_worktrees_directory_is_gitignored(self):
        self.assertIn(".gitignore", self.skill)

    def test_workspace_registration_is_skippable(self):
        # エディタがリポジトリを開いていない環境（Cowork 等）では 4 と 12-d を揃えて飛ばす。
        self.assertIn("12-d もスキップする", self.skill)


class TestReleaseMergeCodexBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.boundaries = BOUNDARIES.read_text(encoding="utf-8")

    def test_skill_routes_codex_to_the_shared_boundary_reference(self):
        self.assertIn(
            "../issue-work/reference/runtime-boundaries.md", self.skill
        )
        self.assertIn("絶対パスを `workdir`", self.skill)

    def test_boundary_reference_covers_both_skills(self):
        self.assertIn("issue-work", self.boundaries)
        self.assertIn("release-merge", self.boundaries)
        self.assertIn("sibling", self.boundaries)

    def test_temporary_files_stay_in_a_writable_root(self):
        self.assertIn(".codex/tmp/<ID>/", self.skill)
        self.assertIn("writable root", self.skill)

    def test_merge_and_cleanup_run_from_the_main_checkout(self):
        self.assertIn("メイン checkout の絶対パスを `workdir`", self.skill)
        self.assertIn("git status --short", self.skill)


if __name__ == "__main__":
    unittest.main()
