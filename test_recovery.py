import json
from pathlib import Path
import subprocess
import tempfile
import unittest

CLI = Path(__file__).with_name("git-branchback").resolve()


class RecoveryCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.net")
        self.edit("one")
        self.commit("root")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE).decode().strip()

    def edit(self, text):
        (self.repo / "invoice").write_text(text + "\n")

    def commit(self, message):
        self.git("add", "invoice")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def report(self, *args):
        return json.loads(subprocess.check_output([CLI, *args, "--json"], cwd=self.repo))

    def test_rescue_lost_commit(self):
        self.edit("two")
        oid = self.commit("lost invoice fix")
        self.git("reset", "--hard", "HEAD~")
        candidates = self.report("recover", "lost", "--path", "invoice")["candidates"]
        self.assertEqual(candidates[0]["commit"], oid)
        result = self.report("recover", "--show", oid, "--create", "rescued")
        self.assertIn("+two", result["diff"])
        self.assertEqual(self.git("rev-parse", "rescued"), oid)
        self.assertEqual(self.git("branch", "--show-current"), "main")

    def test_find_cherry_pick(self):
        base = self.git("rev-parse", "HEAD")
        self.edit("two")
        oid = self.commit("candidate")
        self.git("checkout", "-b", "release", base)
        self.git("commit", "--allow-empty", "-m", "release start")
        self.git("cherry-pick", oid)
        report = self.report("find", "--commit", oid, "--equivalents")
        self.assertIn("refs/heads/main", report["contains"])
        self.assertIn("refs/heads/release", report["possible_patch_equivalents"])

    def test_stash_content_and_untracked(self):
        (self.repo / "extra").write_text("search this content")
        self.git("stash", "push", "-u", "-m", "wip")
        stash = self.report("stash-find", "this content", "--show", "stash@{0}")["stashes"][0]
        self.assertIn("extra", stash["paths"])
        self.assertIn("search this content", stash["diff"])

    def test_conflicts_and_undo(self):
        self.git("checkout", "-b", "feature")
        self.edit("left")
        self.commit("left")
        self.git("checkout", "main")
        self.edit("right")
        self.commit("right")
        self.assertIn("soft reset", str(self.report("undo-plan")["options"]))
        with self.assertRaises(subprocess.CalledProcessError):
            self.git("merge", "feature")
        versions = self.report("conflicts", "--path", "invoice")["files"]["invoice"]
        self.assertEqual(versions["base"]["content"], "one\n")
        self.assertEqual(versions["ours"]["content"], "right\n")
        self.assertEqual(versions["theirs"]["content"], "left\n")
