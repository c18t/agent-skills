"""release-merge のリリースブランチ命名を固定する手順テスト。"""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "release-merge" / "SKILL.md"
TROUBLESHOOTING = (
    PLUGIN_ROOT / "skills" / "release-merge" / "reference" / "troubleshooting.md"
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


if __name__ == "__main__":
    unittest.main()
