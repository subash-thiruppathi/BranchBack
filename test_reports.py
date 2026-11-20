import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from branchback_reports import run


class ReportsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("commit", "--allow-empty", "-m", "base")
        self.git("tag", "v1")
        self.git("switch", "-c", "feature")
        (self.path / "odd\nname").write_text("content")
        self.git("add", ".")
        self.git("commit", "-m", "add feature")

    def git(self, *argv):
        return subprocess.check_output(["git", *argv], cwd=self.path, stderr=subprocess.PIPE)

    def report(self, *args):
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            run([*args, "--json"], self.git)
        return json.loads(text.getvalue())

    def test_review(self):
        result = self.report("review", "--base", "main", "--patch", "--large-bytes", "3", "--expect-dir", "src")
        self.assertEqual(result["outside_expected"], ["odd\nname"])
        self.assertEqual(result["large_files"][0]["bytes"], 7)
        self.assertIn("+content", result["patch"])

    def test_release(self):
        self.git("remote", "add", "origin", "git@github.com:test/repo.git")
        result = self.report("release-notes", "v1..HEAD", "--files")
        self.assertEqual(result["changed_paths"], ["odd\nname"])
        self.assertTrue(result["commits"][0]["url"].startswith("https://github.com/test/repo/commit/"))
        with self.assertRaises(ValueError):
            self.report("release-notes", "v1...HEAD")

    def test_sync(self):
        self.assertEqual(self.report("sync-plan")["status"], "unavailable")
        self.git("branch", "--set-upstream-to", "main")
        self.assertEqual(self.report("sync-plan")["status"], "ahead")
        self.git("switch", "main")
        self.git("commit", "--allow-empty", "-m", "other")
        self.git("switch", "feature")
        result = self.report("sync-plan")
        self.assertEqual(result["status"], "diverged")
        self.assertEqual(result["upstream_only"][0]["subject"], "other")
