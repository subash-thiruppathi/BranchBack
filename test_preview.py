import subprocess
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).with_name("git-branchback").resolve()


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.git("init", "-b", "main")
        self.file = self.repo / "invoice"
        for value in ("initial", "fix"):
            self.file.write_text(value)
            self.git("add", ".")
            self.git("-c", "user.name=Test", "-c", "user.email=test@example.org",
                     "commit", "-m", value)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo)

    def preview(self, name="feature/invoice"):
        return subprocess.run([CLI, name], cwd=self.repo, capture_output=True, text=True)

    def snapshot(self):
        return (self.git("symbolic-ref", "HEAD"), self.git("show-ref"),
                (self.repo / ".git/index").read_bytes(), self.file.read_bytes())

    def test_dirty_preview_preserves_repository(self):
        self.file.write_text("staged")
        self.git("add", ".")
        self.file.write_text("unstaged")
        untracked = self.repo / "new\nfile"
        untracked.write_text("keep")
        before = self.snapshot()
        result = self.preview()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 staged, 1 unstaged, 1 untracked", result.stdout)
        for rev in ("HEAD", "HEAD^"):
            self.assertIn(self.git("rev-parse", rev).decode().strip(), result.stdout)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(untracked.read_text(), "keep")

    def test_existing_target(self):
        self.assertNotEqual(self.preview("main").returncode, 0)

    def test_remote_contains_tip(self):
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertIn("remote-tracking", self.preview().stderr)

    def test_detached_head(self):
        self.git("switch", "--detach", "-q")
        self.assertNotEqual(self.preview().returncode, 0)

    def test_root_commit(self):
        self.git("reset", "--hard", "HEAD^")
        self.assertIn("one visible parent", self.preview().stderr)
