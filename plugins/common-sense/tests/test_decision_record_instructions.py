"""decision-record の保存先選択が非公開 ADR を漏らさないことを固定する。"""

from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1] / "skills" / "decision-record" / "SKILL.md"


class TestStorageSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")

    def test_asks_public_or_private_when_storage_is_ambiguous(self):
        self.assertIn(
            "公開 ADR と非公開\nADR のどちらにするかをユーザーへ確認する",
            self.skill)

    def test_does_not_default_to_public_storage_before_answer(self):
        self.assertIn(
            "回答を得るまで `docs/decisions/` へ自動的に保存しない",
            self.skill)

    def test_routes_private_choice_to_setup(self):
        self.assertIn("非公開 ADR を選んだ場合は手順 6 に従う", self.skill)


if __name__ == "__main__":
    unittest.main()
