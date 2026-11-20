import json
import subprocess
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).with_name("git-branchback").resolve()


class ExplainTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.org")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo)

    def explain(self):
        return json.loads(subprocess.check_output([CLI, "explain", "--json"], cwd=self.repo))

    def test_unborn_with_partial_and_untracked_files(self):
        path = self.repo / "invoice"
        path.write_text("test")
        self.git("add", "invoice")
        path.write_text("modified")
        (self.repo / "two\nlines").touch()
        index = self.repo / ".git/index"
        before = index.read_bytes()
        state = self.explain()
        self.assertEqual(state["branch"], "main")
        self.assertIsNone(state["head"])
        self.assertEqual(state["changes"], dict(staged=1, unstaged=1, untracked=1, conflicted=0))
        self.assertEqual(index.read_bytes(), before)

    def test_diverged_then_detached(self):
        self.git("commit", "-qm", "root", "--allow-empty")
        self.git("switch", "-qc", "upstream")
        self.git("commit", "-qm", "remote", "--allow-empty")
        self.git("switch", "-q", "main")
        self.git("commit", "-qm", "local", "--allow-empty")
        self.git("branch", "--set-upstream-to", "upstream")
        state = self.explain()
        self.assertEqual((state["upstream"], state["ahead"], state["behind"]), ("upstream", 1, 1))
        self.git("switch", "--detach", "-q")
        self.assertIsNone(self.explain()["branch"])

    def test_merge_conflict(self):
        path = self.repo / "invoice"
        path.write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-qm", "root")
        self.git("switch", "-qc", "other")
        path.write_text("theirs\n")
        self.git("commit", "-qam", "theirs")
        self.git("switch", "-q", "main")
        path.write_text("ours\n")
        self.git("commit", "-qam", "ours")
        result = subprocess.run(["git", "merge", "other"], cwd=self.repo, capture_output=True)
        self.assertEqual(result.returncode, 1)
        state = self.explain()
        self.assertEqual(state["operations"], ["merge"])
        self.assertEqual(state["changes"]["conflicted"], 1)
