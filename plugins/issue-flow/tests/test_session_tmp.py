"""Codex thread ごとの一時ディレクトリを分離する。"""
from pathlib import Path
import tempfile
import unittest

from importlib.util import module_from_spec, spec_from_file_location


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_tmp.py"
SPEC = spec_from_file_location("session_tmp", SCRIPT)
session_tmp = module_from_spec(SPEC)
SPEC.loader.exec_module(session_tmp)


class TestSessionTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_prefers_thread_id(self):
        env = {"CODEX_THREAD_ID": "thread-123", "CODEX_SESSION_ID": "session-456"}
        path = session_tmp.session_tmp(self.root, env)
        self.assertEqual(
            path, self.root.resolve() / ".codex" / "tmp" / "thread-123")
        self.assertTrue(path.is_dir())

    def test_falls_back_to_session_id(self):
        path = session_tmp.session_tmp(
            self.root, {"CODEX_SESSION_ID": "session-456"})
        self.assertEqual(path.name, "session-456")

    def test_rejects_unsafe_ids_and_creates_random_directory(self):
        path = session_tmp.session_tmp(
            self.root, {"CODEX_THREAD_ID": "../outside", "CODEX_SESSION_ID": ""})
        self.assertEqual(path.parent, self.root.resolve() / ".codex" / "tmp")
        self.assertTrue(path.name.startswith("session-"))
        self.assertTrue(path.is_dir())

    def test_random_directories_do_not_collide(self):
        first = session_tmp.session_tmp(self.root, {})
        second = session_tmp.session_tmp(self.root, {})
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
