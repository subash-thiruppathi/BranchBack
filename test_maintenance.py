import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from branchback_maintenance import run


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        old = Path.cwd()
        self.addCleanup(os.chdir, old)
        os.chdir(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "test@example.org")
        Path("file").write_text("base")
        self.git("add", "file")
        self.git("commit", "-qm", "base")

    def git(self, *args):
        return subprocess.check_output(["git", *args])

    def command(self, *args, success=True):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = run([*args, "--json"], None)
        self.assertEqual(rc, 0 if success else 1, output.getvalue())
        return json.loads(output.getvalue())

    def test_checkpoint_restores_distinct_layers_and_selected_files(self):
        Path("file").write_text("staged")
        self.git("add", "file")
        Path("file").write_text("working")
        Path("-odd\nname").write_text("include")
        Path("private").write_text("exclude")
        create = ["checkpoint", "create", "before", "--untracked=-odd\nname"]
        self.command(*create)
        self.assertEqual(self.command("checkpoint", "list")["checkpoints"], [])
        index = Path(".git/index").read_bytes()
        self.command(*create, "--apply")
        self.assertEqual(Path(".git/index").read_bytes(), index)
        self.assertEqual(self.command("checkpoint", "list")["checkpoints"], ["before"])
        dest = self.root / "restored"
        restore = ["checkpoint", "restore", "before", "--path", str(dest)]
        self.command(*restore)
        self.assertFalse(dest.exists())
        self.command(*restore, "--apply")
        self.command(*restore, "--apply", success=False)
        self.assertEqual(self.git("-C", str(dest), "show", ":file"), b"staged")
        self.assertEqual((dest / "file").read_text(), "working")
        self.assertEqual((dest / "-odd\nname").read_text(), "include")
        self.assertFalse((dest / "private").exists())
        self.assertEqual(Path("private").read_text(), "exclude")
        self.command(*create, "--apply", success=False)

    def test_hotfix_and_cleanup_protect_other_worktree(self):
        Path("file").write_text("unfinished")
        dest = self.root / "fix"
        args = ["hotfix", "main", "--branch", "fix/one", "--path", str(dest)]
        self.command(*args)
        self.assertFalse(dest.exists())
        self.command(*args, "--apply")
        self.assertEqual((dest / "file").read_text(), "base")
        self.assertEqual(Path("file").read_text(), "unfinished")
        self.command("cleanup", "--delete", "fix/one", "--apply", success=False)
        self.git("branch", "done")
        self.command("cleanup", "--delete", "done")
        self.assertIn(b"done", self.git("branch", "--list"))
        self.command("cleanup", "--delete", "done", "--apply")
        self.assertNotIn(b"done", self.git("branch", "--list"))
