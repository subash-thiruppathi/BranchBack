"""Public entry points shared by the inspection workflows."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).with_name("git-branchback").resolve()


class ReportCommandTest(unittest.TestCase):
    def test_json_errors_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            for command in ("explain", "prepush"):
                with self.subTest(command=command):
                    result = subprocess.run([CLI, command, "--json"], cwd=directory,
                                            capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(json.loads(result.stdout)["error"])

    def test_help_documents_reserved_names(self):
        result = subprocess.check_output([CLI, "-h"], text=True)
        self.assertIn("explain", result)
        self.assertIn("prepush", result)
