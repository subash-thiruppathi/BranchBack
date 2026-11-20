"""Inspect local reflogs, stash entries, commit containment and conflicts."""
import argparse
import json
import os

from branchback_explain import inspect_repo


def commit_id(git, revision):
    return git("rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()


def paths(raw):
    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


def patch(git, commit):
    return git("show", "--format=", "--no-color", "--no-ext-diff", "--no-textconv",
               "--diff-merges=first-parent", commit, "--").decode(errors="replace")


def recover(args, git):
    if args.create and not args.show:
        raise ValueError("--create requires --show COMMIT")
    if args.show:
        oid = commit_id(git, args.show)
        report = {"commit": oid, "diff": patch(git, oid)}
        if args.create:
            name = args.create
            if git("check-ref-format", "--branch", name).rstrip(b"\n") != os.fsencode(name):
                raise ValueError("Choose a literal branch name")
            git("branch", "--no-track", "--", name, oid)
            report["created_branch"] = name
        return report
    command = ["log", "-g", "--all", "--no-show-signature", "-z",
               "--date=iso-strict", "--format=%H%x00%cI%x00%s%x00%gs%x00%gD"]
    if args.since:
        command.append("--since=" + args.since)
    fields = git(*command, "--").split(b"\0")
    candidates, seen = [], set()
    for oid, date, subject, action, selector in zip(*[iter(fields)] * 5):
        oid = oid.decode()
        if oid in seen:
            continue
        subject, action = subject.decode(errors="replace"), action.decode(errors="replace")
        if args.query.casefold() not in (subject + " " + action).casefold():
            continue
        if args.path:
            matches = git("--literal-pathspecs", "diff-tree", "--root", "-m", "--no-commit-id",
                          "--name-only", "-r", "-z", oid, "--", args.path)
            if not matches:
                continue
        seen.add(oid)
        candidates.append(dict(commit=oid, commit_date=date.decode(), subject=subject,
                               event=action, reflog=os.fsdecode(selector)))
        if len(candidates) >= args.limit:
            break
    return {"candidates": candidates}


def find(args, git):
    oid = commit_id(git, args.commit)
    namespaces = ("refs/heads", "refs/remotes", "refs/tags")
    exact = paths_from_lines(git("for-each-ref", "--format=%(refname)", "--contains", oid, *namespaces))
    equivalent = []
    if args.equivalents:
        parents = git("rev-list", "--parents", "-n1", oid).split()
        if len(parents) > 2:
            raise ValueError("Patch equivalence requires a non-merge commit")
        limit = [parents[1].decode()] if len(parents) == 2 else []
        refs = git("for-each-ref", "--format=%(refname)%00%(objecttype)%00%(*objecttype)", *namespaces)
        for record in refs.splitlines():
            ref, kind, peeled = record.split(b"\0")
            name = os.fsdecode(ref)
            if name in exact or b"commit" not in (kind, peeled):
                continue
            lines = git("cherry", name, oid, *limit).splitlines()
            if b"- " + oid.encode() in lines:
                equivalent.append(name)
    return {"commit": oid, "contains": exact, "possible_patch_equivalents": equivalent,
            "checked_equivalents": args.equivalents}


def paths_from_lines(raw):
    return [os.fsdecode(line) for line in raw.splitlines()]


def stash_find(args, git):
    fields = git("stash", "list", "--format=%gd%x00%H%x00%gs", "-z").split(b"\0")
    entries = []
    for selector, raw_oid, message in zip(*[iter(fields)] * 3):
        ref, oid, subject = selector.decode(), raw_oid.decode(), message.decode(errors="replace")
        if args.show and args.show not in (ref, oid):
            continue
        base = ["stash", "show", "--include-untracked", "--no-color", "--no-ext-diff", "--no-textconv"]
        changed = paths(git(*base, "--name-only", "-z", oid))
        haystack = "\n".join([subject, *changed]).casefold()
        entry = dict(stash=ref, commit=oid, message=subject, paths=changed)
        term = args.query.casefold()
        if args.show or term not in haystack:
            diff = git(*base, "--patch", oid).decode(errors="replace")
            if term not in haystack and term not in diff.casefold():
                continue
            if args.show:
                entry["diff"] = diff
        entries.append(entry)
    if args.show and not entries:
        raise ValueError("No matching stash entry")
    return {"stashes": entries}


def conflicts(args, git):
    state = inspect_repo(git)
    records = {}
    for record in git("ls-files", "--unmerged", "-z", "--full-name").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = os.fsdecode(raw_path)
        if args.path and path != args.path:
            continue
        mode, oid, stage = metadata.decode().split()
        item = {"object": oid, "mode": mode}
        if args.path and mode != "160000":
            blob = git("cat-file", "blob", oid)
            item["content"] = None if b"\0" in blob else blob.decode(errors="replace")
        records.setdefault(path, {})[{"1": "base", "2": "ours", "3": "theirs"}[stage]] = item
    if args.path and not records:
        raise ValueError("No unresolved index stages for this repository-relative path")
    operations = state["operations"]
    replay = None
    if records and "rebase" in operations:
        replay_path = os.fsdecode(git("rev-parse", "--git-path", "REBASE_HEAD")[:-1])
        if os.path.isfile(replay_path):
            replay = commit_id(git, "REBASE_HEAD")
    return {"operations": operations, "replayed_commit": replay, "files": records,
            "stage_meaning": ("During rebase, ours is the rebased history and theirs is the commit being replayed."
                              if "rebase" in operations else "Ours is the current side; theirs is the incoming side.")}


def undo_plan(args, git):
    state = inspect_repo(git)
    if args.path:
        staged = paths(git("--literal-pathspecs", "diff", "--cached", "--name-only", "-z", "--", args.path))
        return {"path": args.path, "staged_paths": staged,
                "effect": "Unstaging restores the index entry while keeping working files."
                          if staged else "No staged change matched this path."}
    oid = commit_id(git, args.commit or "HEAD")
    shared = paths_from_lines(git("for-each-ref", "--contains", oid, "--format=%(refname)", "refs/remotes"))
    parents = git("rev-list", "-n1", "--parents", oid).decode().split()[1:]
    options = ["Revert would record a new inverse commit; applying it can produce conflicts."]
    if len(parents) > 1:
        options.append("A merge revert requires choosing the mainline parent.")
    if not shared and state["branch"] and state["head"] == oid and len(parents) == 1:
        options.append("After confirming this tip is private, a soft reset to its parent would keep the index and working files.")
    return {"commit": oid, "parents": parents, "remote_tracking_refs": shared, "options": options,
            "operations": state["operations"], "changes": state["changes"],
            "evidence": "Remote-tracking references reflect local knowledge only."}


def render(report):
    def lines(value, indent=0):
        prefix = " " * indent
        if isinstance(value, dict):
            for key, item in value.items():
                yield prefix + key.replace("_", " ") + ":"
                yield from lines(item, indent + 2)
        elif isinstance(value, list):
            for item in value:
                yield from lines(item, indent)
            if not value:
                yield prefix + "(none)"
        else:
            yield prefix + str(value if value is not None else "(unavailable)")
    return "\n".join(lines(report))


def run(argv, git):
    command = argv[0]
    parser = argparse.ArgumentParser(prog="git branchback " + command)
    parser.add_argument("--json", action="store_true")
    if command == "recover":
        parser.add_argument("query", nargs="?", default="", help="commit message or reflog event substring")
        parser.add_argument("--since", help="include reflog events since this Git date")
        parser.add_argument("--path", help="filter commits changing this path")
        parser.add_argument("--show", metavar="COMMIT", help="inspect a candidate diff")
        parser.add_argument("--create", metavar="BRANCH", help="create a new branch at the inspected commit")
        parser.add_argument("--limit", type=int, default=50)
    elif command == "find":
        parser.add_argument("--commit", required=True)
        parser.add_argument("--equivalents", action="store_true", help="also check possible cherry-picks")
    elif command == "stash-find":
        parser.add_argument("query", nargs="?", default="")
        parser.add_argument("--show", metavar="STASH", help="include the patch for a selector or stash ID")
    elif command == "conflicts":
        parser.add_argument("--path", help="show each side for one repository-relative path")
    else:
        choice = parser.add_mutually_exclusive_group()
        choice.add_argument("--commit")
        choice.add_argument("--path")
    args = parser.parse_args(argv[1:])
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be positive")
    workflows = {"recover": recover, "find": find, "stash-find": stash_find,
                 "conflicts": conflicts, "undo-plan": undo_plan}
    report = workflows[command](args, git)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0
