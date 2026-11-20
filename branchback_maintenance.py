"""Worktree, checkpoint and local branch workflows."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PREFIX = "refs/branchback/checkpoints/"


def invoke(*args, env=None):
    result = subprocess.run(["git", *args], capture_output=True,
                            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0",
                                 "GIT_NO_LAZY_FETCH": "1", **(env or {})})
    if result.returncode:
        raise ValueError(os.fsdecode(result.stderr).strip() or "Git operation failed")
    return result.stdout


def ref_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", name):
        raise ValueError("Use a plain branch or checkpoint name.")
    invoke("check-ref-format", "refs/heads/" + name)
    return name


def resolve(revision):
    return invoke("rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()


def new_path(path):
    dest = Path(path).expanduser().absolute()
    if os.path.lexists(dest):
        raise ValueError("Choose a new directory; the given path already exists.")
    for item in invoke("worktree", "list", "--porcelain", "-z").split(b"\0"):
        if item.startswith(b"worktree "):
            root = Path(os.fsdecode(item[9:])).resolve()
            if dest.resolve() == root or root in dest.resolve().parents:
                raise ValueError("Choose a directory outside existing worktrees.")
    return str(dest)


def hotfix(args):
    base = resolve(args.base)
    branch = ref_name(args.branch or "hotfix/" + args.base)
    if invoke("for-each-ref", "--format=%(refname)", "refs/heads/" + branch):
        raise ValueError("Choose an unused hotfix branch name.")
    top = Path(os.fsdecode(invoke("rev-parse", "--show-toplevel")[:-1]))
    directory = new_path(args.path or top.with_name(top.name + "-" + branch.replace("/", "-")))
    if args.apply:
        invoke("worktree", "add", "-b", branch, directory, base)
    return dict(action="hotfix", applied=args.apply, base=base, branch=branch, directory=directory)


def checkpoint_create(args):
    name = ref_name(args.name)
    ref = PREFIX + name
    if ref.encode() in invoke("for-each-ref", "--format=%(refname)", ref).splitlines():
        raise ValueError("Choose an unused checkpoint name.")
    base = resolve("HEAD")
    top = os.fsdecode(invoke("rev-parse", "--show-toplevel")[:-1])
    if invoke("-C", top, "ls-files", "--unmerged"):
        raise ValueError("Resolve index conflicts before creating a checkpoint.")
    if any(row.startswith(b"S ") or row[:1].islower()
           for row in invoke("-C", top, "ls-files", "-v", "-z").split(b"\0")):
        raise ValueError("Checkpoints require a fully populated working tree without assume-unchanged entries.")
    changes = invoke("-C", top, "status", "--porcelain=v2", "-z", "--ignore-submodules=none")
    for record in changes.split(b"\0"):
        if record.startswith((b"1 ", b"2 ")):
            fields = record.split(b" ", 3)
            if fields[1] == b".A" or fields[2].startswith(b"S") and fields[2][2:] != b"..":
                raise ValueError("Intent-to-add entries and uncommitted submodule contents require separate capture.")
    paths = set(os.fsdecode(p) for p in invoke("-C", top, "ls-files", "-z", "--others",
                                               "--exclude-standard").split(b"\0") if p)
    if set(args.untracked) - paths:
        raise ValueError("Each --untracked path must name an individual untracked, nonignored file relative to the repository root.")
    report = dict(action="checkpoint-create", name=name, base=base, applied=args.apply,
                  untracked=sorted(set(args.untracked)), excluded_untracked=len(paths-set(args.untracked)))
    if not args.apply:
        return report
    index = os.fsdecode(invoke("rev-parse", "--path-format=absolute", "--git-path", "index")[:-1])
    with tempfile.TemporaryDirectory() as temp:
        copy = str(Path(temp) / "index")
        env = {"GIT_INDEX_FILE": copy}
        if os.path.isfile(index):
            shutil.copyfile(index, copy)
        index_tree = invoke("-C", top, "write-tree", env=env).decode().strip()
        invoke("-C", top, "add", "-u", "--", ".", env=env)
        for path in report["untracked"]:
            invoke("-C", top, "--literal-pathspecs", "add", "--", path, env=env)
        work_tree = invoke("-C", top, "write-tree", env=env).decode().strip()
    index_commit = invoke("commit-tree", index_tree, "-p", base, "-m", "BranchBack index").decode().strip()
    snapshot = invoke("commit-tree", work_tree, "-p", base, "-p", index_commit,
                      "-m", "BranchBack checkpoint " + name).decode().strip()
    invoke("update-ref", ref, snapshot, "0" * len(snapshot))
    report["checkpoint"] = snapshot
    return report


def checkpoint(args):
    if args.operation == "create":
        return checkpoint_create(args)
    if args.operation == "list":
        names = invoke("for-each-ref", "--format=%(refname:strip=3)", PREFIX)
        return {"checkpoints": list(map(os.fsdecode, names.splitlines()))}
    name = ref_name(args.name)
    snapshot = resolve(PREFIX + name)
    base = resolve(snapshot + "^1")
    index = resolve(snapshot + "^2")
    dest = new_path(args.path)
    if args.apply:
        invoke("worktree", "add", "--detach", dest, base)
        try:
            invoke("-C", dest, "read-tree", "-u", "-m", base, snapshot)
            invoke("-C", dest, "read-tree", index)
        except ValueError as error:
            raise ValueError(f"Restore stopped in {dest}. The checkpoint remains available. {error}") from error
    return dict(action="checkpoint-restore", name=name, checkpoint=snapshot, base=base,
                index_commit=index, directory=dest, applied=args.apply)


def cleanup(args):
    base = resolve(args.base)
    base_ref = os.fsdecode(invoke("rev-parse", "--symbolic-full-name", "--end-of-options", args.base).strip())
    merged = set(invoke("for-each-ref", "--merged=" + base, "--format=%(refname)", "refs/heads").splitlines())
    rows = invoke("for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads").splitlines()
    active = {item[7:] for item in invoke("worktree", "list", "--porcelain", "-z").split(b"\0")
              if item.startswith(b"branch ")}
    branches = []
    for row in rows:
        ref, tip = row.split(b"\0")
        state = "not-reachable"
        if ref in active:
            state = "checked-out"
        elif os.fsdecode(ref) == base_ref:
            state = "base"
        elif ref in merged:
            state = "merged"
        branches.append(dict(branch=os.fsdecode(ref[len(b"refs/heads/"):]), status=state, tip=tip.decode()))
    if args.delete:
        ref_name(args.delete)
        if not any(b["branch"] == args.delete and b["status"] == "merged" for b in branches):
            raise ValueError("Only a merged branch outside all worktrees can be deleted.")
    if args.apply:
        if not args.delete:
            raise ValueError("Specify the individual branch with --delete.")
        invoke("branch", "-d", "--", args.delete)
    return dict(base=base, branches=branches, selected=args.delete, applied=args.apply)


def render(command, report):
    if command == "cleanup":
        lines = [f"Local branches compared with {report['base'][:12]}"]
        lines.extend(f"  {item['branch']}  {item['status']}  {item['tip'][:12]}"
                     for item in report["branches"])
        if report["selected"]:
            verb = "Deleted" if report["applied"] else "Would delete"
            lines.append(f"{verb} {report['selected']}.")
        return "\n".join(lines)
    if "checkpoints" in report:
        return "\n".join(report["checkpoints"]) or "No local checkpoints."
    applied = report["applied"]
    if command == "hotfix":
        verb = "Created" if applied else "Would create"
        return f"{verb} {report['branch']} at {report['base'][:12]} in {report['directory']}."
    if report["action"] == "checkpoint-create":
        verb = "Saved" if applied else "Would save"
        lines = [f"{verb} checkpoint {report['name']} at {report['base'][:12]} with the index and tracked working changes."]
        lines.extend("  Include untracked " + repr(path) for path in report["untracked"])
        lines.append(f"Excluded untracked paths: {report['excluded_untracked']}.")
        return "\n".join(lines)
    verb = "Restored" if applied else "Would restore"
    return f"{verb} checkpoint {report['name']} to a detached worktree at {report['directory']}."


def run(argv, git):
    command = argv[0]
    parser = argparse.ArgumentParser(prog="git branchback " + command)
    if command == "checkpoint":
        ops = parser.add_subparsers(dest="operation", required=True)
        create = ops.add_parser("create")
        create.add_argument("name")
        create.add_argument("--untracked", action="append", default=[], metavar="PATH")
        restore = ops.add_parser("restore")
        restore.add_argument("name")
        restore.add_argument("--path", required=True)
        listing = ops.add_parser("list")
        for op in (create, restore):
            op.add_argument("--apply", action="store_true")
        for op in (create, restore, listing):
            op.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    elif command == "hotfix":
        parser.add_argument("base")
        parser.add_argument("--path")
        parser.add_argument("--branch")
        parser.add_argument("--apply", action="store_true")
    else:
        parser.add_argument("--base", default="HEAD")
        parser.add_argument("--delete")
        parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        overrides = ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")
        if any(key in os.environ for key in overrides):
            raise ValueError("Run this workflow from a checkout using its ordinary Git directories and index.")
        report = {"checkpoint": checkpoint, "cleanup": cleanup, "hotfix": hotfix}[command](args)
    except (OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print("Unable to complete the workflow:", error)
        return 1
    if args.json:
        print(json.dumps(report))
    else:
        print(render(command, report))
    return 0
