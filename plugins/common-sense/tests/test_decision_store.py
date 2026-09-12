"""Private decision store resolution and safety tests."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "decision_store.py"
SPEC = spec_from_file_location("decision_store", SCRIPT)
decision_store = module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = decision_store
SPEC.loader.exec_module(decision_store)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class DecisionStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sample"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "remote", "add", "origin", "git@github.com:acme/sample.git")
        (self.root / ".gitignore").write_text(
            ".claude/decisions/\n", encoding="utf-8")
        (self.root / "README.md").write_text("sample\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "initial")
        self.worktree = Path(self.temp.name) / "linked"
        git(self.root, "worktree", "add", "-b", "topic", str(self.worktree))

    def make_private_clone(self) -> Path:
        clone = self.root / ".claude" / "decisions" / "sample-decisions"
        clone.mkdir(parents=True)
        git(clone, "init", "-b", "main")
        return clone

    def test_main_and_linked_worktree_resolve_one_clone(self):
        main = decision_store.resolve(self.root)
        linked = decision_store.resolve(self.worktree)
        self.assertEqual(main.clone_root, linked.clone_root)
        self.assertEqual(main.slug, "acme/sample-decisions")

    def test_check_creates_only_private_docs_directory(self):
        clone = self.make_private_clone()
        store = decision_store.resolve(self.worktree)
        decision_store.require_ignored(store)
        decision_store.require_clone(store)
        self.assertEqual(
            store.decisions.resolve(), (clone / "docs" / "decisions").resolve())
        self.assertTrue(store.decisions.is_dir())
        self.assertEqual(git(self.root, "status", "--short"), "")
        self.assertEqual(git(self.worktree, "status", "--short"), "")

    def test_missing_clone_stops_without_public_fallback(self):
        store = decision_store.resolve(self.worktree)
        with self.assertRaisesRegex(decision_store.StoreError, "not cloned"):
            decision_store.require_clone(store)
        self.assertFalse((self.worktree / "docs" / "decisions").exists())

    def test_non_repository_at_canonical_path_is_rejected(self):
        store = decision_store.resolve(self.root)
        store.clone_root.mkdir(parents=True)
        with self.assertRaisesRegex(decision_store.StoreError, "independent git"):
            decision_store.require_clone(store)

    def test_setup_requires_ignore_rule(self):
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        store = decision_store.resolve(self.root)
        with self.assertRaisesRegex(decision_store.StoreError, "not ignored"):
            decision_store.require_ignored(store)

    def test_setup_stops_before_remote_creation_without_approval(self):
        store = decision_store.resolve(self.root)
        with patch.object(decision_store, "require_ignored"), \
                patch.object(decision_store, "remote_visibility", return_value=None), \
                patch.object(decision_store, "run") as run:
            with self.assertRaisesRegex(decision_store.StoreError, "Ask the user"):
                decision_store.setup(store, approve_create=False)
        run.assert_not_called()

    def test_public_remote_is_rejected_before_clone(self):
        store = decision_store.resolve(self.root)
        with patch.object(decision_store, "require_ignored"), \
                patch.object(decision_store, "remote_visibility", return_value="PUBLIC"), \
                patch.object(decision_store, "run") as run:
            with self.assertRaisesRegex(decision_store.StoreError, "expected PRIVATE"):
                decision_store.setup(store, approve_create=False)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
