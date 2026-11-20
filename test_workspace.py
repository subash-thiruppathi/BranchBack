import json
import subprocess
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).with_name("git-branchback").resolve()


class WorkspaceTest(unittest.TestCase):
    def test_scan_from_outside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root / "sample")], check=True)
            (root / "sample" / "notes").write_text("draft")
            result = subprocess.check_output([CLI, "workspace", tmp, "--json"], cwd=tmp)
            report = json.loads(result)
            self.assertEqual(report["checked"], 1)
            self.assertEqual(report["repositories"][0]["changes"]["untracked"], 1)
            self.assertEqual(report["errors"], [])
