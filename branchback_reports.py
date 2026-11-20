"""Local branch synchronization, pull request review, and release summaries."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re


def commit_id(git, revision):
    return git("rev-parse", "--verify", "--end-of-options",
               revision + "^{commit}").decode("ascii").strip()


def commits(git, start, end):
    fields = git("log", "--reverse", "--no-show-signature", "-z", "--format=%H%x00%s",
                 start + ".." + end, "--").split(b"\0")
    return [{"id": oid.decode("ascii"), "subject": os.fsdecode(subject)}
            for oid, subject in zip(fields[::2], fields[1::2])]


def sync_plan(git):
    from branchback_explain import inspect_repo
    state = inspect_repo(git)
    head, upstream = state["head"], state["upstream"]
    path = Path(os.fsdecode(git("rev-parse", "--git-path", "FETCH_HEAD").rstrip(b"\n")))
    try:
        refreshed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except FileNotFoundError:
        refreshed = None
    report = dict(branch=state["branch"], upstream=upstream, head=head,
                  fetch_head_updated_at=refreshed, local_only=[], upstream_only=[])
    if not head or state["ahead"] is None:
        report.update(status="unavailable", guidance="An existing local tip and upstream tracking tip are required.")
        return report
    remote = commit_id(git, "@{upstream}")
    local_only = commits(git, remote, head)
    upstream_only = commits(git, head, remote)
    if local_only and upstream_only:
        status = "diverged"
        guidance = ("With a common ancestor, merging joins both histories with a merge commit. "
                    "Rebasing replays local changes on the upstream tip and can replace local commit IDs.")
    elif local_only:
        status, guidance = "ahead", "A push could fast-forward the recorded upstream tip."
    elif upstream_only:
        status, guidance = "behind", "Your branch could fast-forward to the recorded upstream tip."
    else:
        status, guidance = "up-to-date", "The recorded branch and upstream tips match."
    report.update(status=status, guidance=guidance, local_only=local_only,
                  upstream_only=upstream_only, upstream_tip=remote)
    return report


def paths_changed(git, start, end):
    delta = git("diff", "--no-renames", "--no-ext-diff", "--no-textconv", "--name-only", "-z",
                start, end, "--")
    return [os.fsdecode(path) for path in delta.split(b"\0") if path]


def review(git, args):
    head, base = commit_id(git, "HEAD"), commit_id(git, args.base)
    ancestor = git("merge-base", base, head).decode("ascii").strip()
    changed = paths_changed(git, ancestor, head)
    wanted = set(changed)
    large = []
    for row in git("ls-tree", "-rlz", head).split(b"\0"):
        if row:
            metadata, raw_path = row.split(b"\t", 1)
            path = os.fsdecode(raw_path)
            size = metadata.split()[-1]
            if path in wanted and size.isdigit() and int(size) >= args.large_bytes:
                large.append(dict(path=path, bytes=int(size)))
    prefixes = [(path[2:] if path.startswith("./") else path).rstrip("/") for path in args.expect_dir]
    outside = [path for path in changed if prefixes and
               not any(prefix in ("", ".") or path == prefix or path.startswith(prefix + "/") for prefix in prefixes)]
    report = dict(base=args.base, merge_base=ancestor, head=head, commits=commits(git, base, head),
                  changed_paths=changed, large_files=large, outside_expected=outside)
    if args.patch:
        report["patch"] = git("diff", "--no-color", "--no-ext-diff", "--no-textconv",
                              ancestor, head, "--").decode("utf-8", "replace")
    return report


def release_notes(git, args):
    endpoints = args.range.split("..")
    if len(endpoints) != 2 or not all(endpoints) or "..." in args.range:
        raise ValueError("Specify two release endpoints, for example v1.0..v1.1.")
    start, end = [commit_id(git, name) for name in endpoints]
    rows = commits(git, start, end)
    remotes = git("remote").splitlines()
    if b"origin" in remotes:
        remote = os.fsdecode(git("remote", "get-url", "origin").strip())
        match = re.fullmatch(r"(?:https://|git@|ssh://git@)(github\.com|gitlab\.com)[:/]([\w./-]+)", remote)
        if match:
            host, project = match.groups()
            if project.endswith(".git"):
                project = project[:-4]
            route = "/commit/" if host == "github.com" else "/-/commit/"
            for row in rows:
                row["url"] = "https://" + host + "/" + project + route + row["id"]
    report = dict(range=args.range, start=start, end=end, commits=rows)
    if args.files:
        report["changed_paths"] = paths_changed(git, start, end)
    return report


def render(report, command):
    if command == "release-notes":
        lines = ["# Release " + report["range"], ""]
        for row in report["commits"]:
            short = row["id"][:12]
            link = f"[{short}]({row['url']})" if "url" in row else short
            lines.append(f"- {row['subject']} ({link})")
        if not report["commits"]:
            lines.append("No commits in range.")
    elif command == "sync-plan":
        lines = [f"{report['branch'] or '(detached)'} · {report['status']}", report["guidance"],
                 "Upstream: " + (report["upstream"] or "unavailable"),
                 "Repository FETCH_HEAD updated: " + (report["fetch_head_updated_at"] or "unknown")]
        for label, key in (("Local-only commits", "local_only"), ("Upstream-only commits", "upstream_only")):
            lines.append(f"{label} ({len(report[key])})")
            lines.extend(f"  {row['id'][:12]} {row['subject']}" for row in report[key])
    else:
        lines = [f"Branch review against {report['base']} at merge base {report['merge_base'][:12]}",
                 f"Commits ({len(report['commits'])})"]
        lines.extend(f"  {row['id'][:12]} {row['subject']}" for row in report["commits"])
    if "changed_paths" in report:
        lines.append(f"Changed paths ({len(report['changed_paths'])})")
        lines.extend("  " + path for path in report["changed_paths"])
    for item in report.get("large_files", []):
        lines.append(f"Large file: {item['path']} ({item['bytes']} bytes)")
    lines.extend("Outside expected directories: " + path for path in report.get("outside_expected", []))
    if report.get("patch"):
        lines.append(report["patch"])
    return "\n".join(lines)


def run(argv, git):
    command = argv[0]
    parser = argparse.ArgumentParser(prog="git branchback " + command)
    parser.add_argument("--json", action="store_true")
    if command == "review":
        parser.add_argument("--base", required=True)
        parser.add_argument("--patch", action="store_true", help="include cumulative patch")
        parser.add_argument("--expect-dir", action="append", default=[], help="expected repo-relative directory")
        parser.add_argument("--large-bytes", type=int, default=1024 * 1024)
    elif command == "release-notes":
        parser.add_argument("range", metavar="START..END")
        parser.add_argument("--files", action="store_true")
    args = parser.parse_args(argv[1:])
    if command == "review":
        if args.large_bytes < 1:
            raise ValueError("--large-bytes must be positive.")
        report = review(git, args)
    elif command == "release-notes":
        report = release_notes(git, args)
    else:
        report = sync_plan(git)
    print(json.dumps(report, indent=2) if args.json else render(report, command))
    return 0
