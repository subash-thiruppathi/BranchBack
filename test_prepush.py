import subprocess
import tempfile
import unittest
from pathlib import Path

from branchback_prepush import inspect_repo, render


class PrepushTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-qb", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.org")
        self.git("commit", "--allow-empty", "-qm", "base")
        self.git("remote", "add", "origin", "/unused")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("branch", "--set-upstream-to=origin/main", "main")
        self.git("config", "push.default", "simple")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo)

    def test_divergent_push_and_fetch_remotes(self):
        self.git("remote", "add", "fork", "/unused-fork")
        self.git("config", "branch.main.pushRemote", "fork")
        self.git("config", "push.default", "current")
        self.git("update-ref", "refs/remotes/fork/main", "HEAD")
        (self.repo / "two\nlines").write_text("change")
        self.git("add", ".")
        self.git("commit", "-qm", "review this")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        report = inspect_repo(self.git)
        self.assertEqual(report["destination"], "refs/remotes/fork/main")
        self.assertEqual(report["status"], "fast-forward")
        self.assertEqual(report["changed_paths"], ["two\nlines"])
        self.assertEqual(report["outgoing_commits"], [
            {"id": self.git("rev-parse", "HEAD").decode().strip(), "subject": "review this"}])
        self.assertIn(r'two\nlines', render(report))

    def test_clean_then_behind(self):
        self.assertEqual(inspect_repo(self.git)["status"], "up-to-date")
        self.git("commit", "--allow-empty", "-qm", "remote change")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("reset", "--hard", "HEAD^")
        self.assertEqual(inspect_repo(self.git)["status"], "non-fast-forward")
        self.git("commit", "--allow-empty", "-qm", "local change")
        report = inspect_repo(self.git)
        self.assertEqual((report["ahead"], report["behind"]), (1, 1))
        self.assertEqual(report["status"], "non-fast-forward")
        self.assertIsNone(report["changed_paths"])

    def test_missing_destination_and_detached(self):
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(inspect_repo(self.git)["status"], "unavailable")
        self.git("config", "push.default", "nothing")
        self.assertEqual(inspect_repo(self.git)["status"], "unavailable")
        self.git("switch", "--detach", "-q")
        self.assertIsNone(inspect_repo(self.git)["branch"])
