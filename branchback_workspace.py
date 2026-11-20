"""Report actionable working-tree state across a local projects directory."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from branchback_explain import inspect_repo


def run(argv, git):
    parser = argparse.ArgumentParser(prog="git branchback workspace")
    parser.add_argument("directory", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])
    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Workspace directory does not exist.")
    findings = []
    failures = []
    checked = 0

    def record_error(error):
        failures.append({"path": error.filename, "error": error.strerror})

    for folder, dirs, files in os.walk(root, onerror=record_error):
        is_repo = ".git" in dirs or ".git" in files
        dirs[:] = sorted(name for name in dirs if name not in
                         {".git", "node_modules", ".venv", "__pycache__"})
        if not is_repo:
            continue
        checked += 1

        def local_git(*arguments):
            env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
            for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
                env.pop(key, None)
            return subprocess.check_output(["git", "-C", folder, *arguments],
                                           env=env, stderr=subprocess.PIPE)
        try:
            state = inspect_repo(local_git)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            failures.append({"path": folder, "error": str(error)})
            continue
        if (any(state["changes"].values()) or state["operations"] or state["ahead"]
                or state["behind"] or not state["upstream"] or state["ahead"] is None):
            findings.append({"path": folder, **state})
    if args.json:
        print(json.dumps({"checked": checked, "repositories": findings, "errors": failures}))
    else:
        print(f"Checked {checked} repositories; {len(findings)} need review.")
        from branchback_explain import render
        for item in findings:
            print(f'\n{item["path"]}\n{render(item)}')
        for failure in failures:
            print(f'{failure["path"]}: {failure["error"]}')
    return int(bool(failures))
