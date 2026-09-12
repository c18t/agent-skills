"""release-merge のブランチ命名・worktree 配置・Codex 境界規約を固定する手順テスト。"""
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

SINGLE = "release/<プラグイン名>-<version>"
MERGED = "release/merge-<日付>"


class TestReleaseBranchNaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.troubleshooting = TROUBLESHOOTING.read_text(encoding="utf-8")

    def test_skill_documents_both_naming_forms(self):
        for name in (SINGLE, MERGED):
            with self.subTest(name=name):
                self.assertIn(name, self.skill)

    def test_overview_presents_the_naming_as_a_choice(self):
        overview = self.skill.split("## 手順", 1)[0]
        for name in (SINGLE, MERGED):
            with self.subTest(name=name):
                self.assertIn(name, overview)

    def test_split_criterion_is_the_plugin_boundary_not_dependency(self):
        self.assertIn("プラグイン境界で切れるか", self.skill)
        self.assertIn("依存の有無ではない", self.skill)
        # 依存が無くても境界をまたぐ（分割できない変更）ケースを残す
        self.assertIn("変更そのものが分割できない", self.skill)

    def test_merged_branch_name_carries_no_version(self):
        self.assertIn("プラグイン名も version も名前に入れない", self.skill)
        self.assertIn("MAX_PATH", self.skill)
        self.assertIn("含まれる PR", self.skill)

    def test_commands_do_not_hardcode_the_single_plugin_form(self):
        for command in ("git worktree add -b", "git push -u origin",
                        "git branch -D", "git push origin --delete"):
            with self.subTest(command=command):
                line = next(
                    line for line in self.skill.splitlines()
                    if line.strip().startswith(command)
                )
                self.assertNotIn("<プラグイン名>-<version>", line)

    def test_troubleshooting_covers_the_enumerated_form(self):
        self.assertIn("MAX_PATH", self.troubleshooting)
        self.assertIn(
            "release/agent-skills-issue-flow-0.7.1-notion-writeback-0.2.1",
            self.troubleshooting,
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
