"""Cross-platform CI watcher regression tests."""

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_pr.py"
SPEC = importlib.util.spec_from_file_location("watch_pr", SCRIPT)
watch_pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch_pr)


class TestWatch(unittest.TestCase):
    def test_emits_new_terminal_checks_and_waits_for_every_check(self):
        snapshots = [
            [{"name": "lint", "bucket": "pass"},
             {"name": "test", "bucket": "pending"}],
            [{"name": "lint", "bucket": "pass"},
             {"name": "test", "bucket": "fail"},
             {"name": "docs", "bucket": "skipping"}],
            {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
        ]
        with mock.patch.object(watch_pr, "gh_json", side_effect=snapshots), \
                mock.patch.object(watch_pr.time, "sleep") as sleep, \
                mock.patch("builtins.print") as output:
            self.assertEqual(0, watch_pr.watch("45", interval=0))
        sleep.assert_called_once_with(0)
        lines = [call.args[0] for call in output.call_args_list]
        self.assertEqual(
            ["lint: pass", "docs: skipping", "test: fail",
             "MERGE STATE: MERGEABLE / CLEAN"],
            lines,
        )

    def test_transient_failure_keeps_polling(self):
        snapshots = [
            None,
            [{"name": "test", "bucket": "cancel"}],
            {"mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"},
        ]
        with mock.patch.object(watch_pr, "gh_json", side_effect=snapshots), \
                mock.patch.object(watch_pr.time, "sleep") as sleep, \
                mock.patch("builtins.print"):
            self.assertEqual(0, watch_pr.watch("45", interval=1))
        sleep.assert_called_once_with(1)

    def test_invalid_arguments_exit_2(self):
        self.assertEqual(2, watch_pr.main(["watch_pr.py"]))
        self.assertEqual(2, watch_pr.main(["watch_pr.py", "45", "-1"]))


if __name__ == "__main__":
    unittest.main()
