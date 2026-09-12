"""release-merge の統合対象 PR の安全な片付け手順テスト。"""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "release-merge" / "SKILL.md"


class TestMergedPullRequestCleanupInstructions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")

    def test_discovers_both_worktree_layouts(self):
        self.assertIn("git worktree list --porcelain", self.skill)
        self.assertIn("sibling path", self.skill)
        self.assertIn(".claude/worktrees/", self.skill)

    def test_requires_merge_evidence_before_deleting_branch(self):
        self.assertIn("git merge-base --is-ancestor", self.skill)
        self.assertIn("gh pr list --state merged --head", self.skill)
        self.assertIn("どちらの根拠も取れない", self.skill)

    def test_protects_dirty_and_current_worktrees(self):
        self.assertIn("git status --short", self.skill)
        self.assertIn("現在のセッションの居場所", self.skill)
        self.assertIn("`--force` は使わない", self.skill)

    def test_cleans_only_removed_workspace_entries(self):
        self.assertIn("実際に削除した統合対象 PR", self.skill)
        self.assertIn("入口として残す", self.skill)

    def test_reports_removed_and_retained_items(self):
        self.assertIn("片付け:", self.skill)
        self.assertIn("削除 … <パス> / <ブランチ名>", self.skill)
        self.assertIn("残置 … <パス>", self.skill)


if __name__ == "__main__":
    unittest.main()
