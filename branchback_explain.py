"""Describe a working tree using local Git metadata."""
import os
from pathlib import Path


def inspect_repo(git):
    records = git("status", "--porcelain=v2", "--branch", "--ahead-behind", "-z",
                  "--no-renames", "--untracked-files=all", "--ignore-submodules=none")
    headers = {}
    changes = dict(staged=0, unstaged=0, untracked=0, conflicted=0)
    for record in records.split(b"\0"):
        if record.startswith(b"# "):
            key, _, value = record[2:].partition(b" ")
            headers[key] = value
        elif record.startswith(b"1 "):
            xy = record.split(b" ", 2)[1]
            changes["staged"] += xy[:1] != b"."
            changes["unstaged"] += xy[1:] != b"."
        elif record.startswith(b"? "):
            changes["untracked"] += 1
        elif record.startswith(b"u "):
            changes["conflicted"] += 1

    head = headers[b"branch.oid"]
    branch = headers[b"branch.head"]
    upstream = headers.get(b"branch.upstream")
    ahead = behind = None
    if b"branch.ab" in headers:
        ahead_field, behind_field = headers[b"branch.ab"].split()
        ahead, behind = int(ahead_field[1:]), int(behind_field[1:])

    directory = Path(os.fsdecode(git("rev-parse", "--absolute-git-dir")[:-1]))
    operations = []
    for marker, name in (("rebase-merge", "rebase"), ("rebase-apply/applying", "am"),
                         ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge"),
                         ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"),
                         ("sequencer", "sequencer")):
        if (directory / marker).exists():
            operations.append(name)
            break
    if (directory / "BISECT_START").exists():
        operations.append("bisect")
    return dict(branch=None if branch == b"(detached)" else os.fsdecode(branch),
                head=None if head == b"(initial)" else head.decode("ascii"),
                upstream=os.fsdecode(upstream) if upstream else None,
                ahead=ahead, behind=behind, changes=changes, operations=operations)


def render(data):
    if data["head"] is None:
        lines = [f'On {data["branch"]}, awaiting the first commit.']
    elif data["branch"] is None:
        lines = [f'Detached HEAD at {data["head"][:12]}.']
    else:
        lines = [f'On {data["branch"]} at {data["head"][:12]}.']
    if data["ahead"] is not None:
        lines.append(f'Compared with {data["upstream"]} locally, '
                     f'{data["ahead"]} ahead and {data["behind"]} behind.')
    elif data["upstream"]:
        lines.append(f'The configured upstream {data["upstream"]} is unavailable locally.')
    else:
        lines.append("No upstream is configured for this checkout.")
    if any(data["changes"].values()):
        lines.append(("Paths: {staged} staged, {unstaged} unstaged, "
                      "{untracked} untracked, {conflicted} conflicted.").format(**data["changes"]))
    else:
        lines.append("The working tree is clean.")
    if data["operations"]:
        lines.append("In progress: " + ", ".join(data["operations"]) + ".")
    return "\n".join(lines)
