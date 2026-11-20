"""Inspect the current branch's locally known push target, without contacting a remote."""

import json
import os


def inspect_repo(git):
    """Report one branch update. Explicit push arguments and other refs are out of scope."""
    data = {
        "branch": None, "destination": None, "local_tip": None, "destination_tip": None,
        "status": "unavailable", "reason": None, "ahead": None, "behind": None,
        "outgoing_commits": [], "changed_paths": None,
    }
    # %(push) uses Git's push configuration, including a separate pushRemote.
    # A fetch upstream can point somewhere entirely different.
    fields = "%(HEAD)%00%(refname)%00%(objectname)%00%(push)%00%(push:remotename)"
    fields += "%00%(upstream)%00%(upstream:remotename)"
    rows = git("for-each-ref", "--format=" + fields, "refs/heads").splitlines()
    for row in rows:
        active, source, tip, destination, push_remote, upstream, fetch_remote = row.split(b"\0")
        if active == b"*":
            break
    else:
        data["reason"] = "An attached branch with a commit is required."
        return data

    data["branch"] = os.fsdecode(source[len(b"refs/heads/"):])
    data["local_tip"] = tip.decode("ascii")
    if destination == upstream and push_remote != fetch_remote:
        data["reason"] = "Git resolved the push reference and upstream to conflicting remotes."
        return data
    if not destination.startswith(b"refs/remotes/"):
        data["reason"] = "Git could not identify a remote-tracking push destination."
        return data

    target = os.fsdecode(destination)
    data["destination"] = target
    targets = git("for-each-ref", "--format=%(refname)%00%(objectname)", target)
    for row in targets.splitlines():
        ref, remote_tip = row.split(b"\0")
        if ref == destination:
            break
    else:
        data["reason"] = "The push destination has no locally recorded tip."
        return data

    local = data["local_tip"]
    remote = data["destination_tip"] = remote_tip.decode("ascii")
    ahead, behind = map(int, git("rev-list", "--left-right", "--count",
                                 local + "..." + remote).split())
    data.update(ahead=ahead, behind=behind)
    if behind:
        data["status"] = "non-fast-forward"
    elif ahead:
        data["status"] = "fast-forward"
    else:
        data["status"] = "up-to-date"

    if ahead:
        # NUL delimiters preserve spaces and punctuation in commit subjects.
        fields = git("log", "--reverse", "--no-show-signature", "--encoding=UTF-8",
                     "-z", "--format=%H%x00%s", remote + ".." + local).split(b"\0")
        data["outgoing_commits"] = [
            {"id": oid.decode("ascii"), "subject": subject.decode("utf-8", "replace")}
            for oid, subject in zip(fields[::2], fields[1::2])
        ]
    if not behind:
        paths = git("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                    "--name-only", "-z", remote, local, "--").split(b"\0")
        data["changed_paths"] = [os.fsdecode(path) for path in paths if path]
    return data


def render(data):
    lines = ["Current branch push review (local tracking data may be stale)."]
    if data["branch"]:
        lines.append("Branch: " + data["branch"])
    if data["destination"]:
        lines.append("Destination tracking ref: " + data["destination"])
    if data["reason"]:
        lines.append(data["reason"])
        return "\n".join(lines)
    lines.append(f'{data["status"]}: {data["ahead"]} outgoing, {data["behind"]} destination-only commits.')
    for commit in data["outgoing_commits"]:
        lines.append(f'  {commit["id"][:12]}  {json.dumps(commit["subject"], ensure_ascii=True)}')
    if data["changed_paths"] is not None:
        lines.append(f'Net changed paths: {len(data["changed_paths"])}')
        lines.extend("  " + json.dumps(path, ensure_ascii=True) for path in data["changed_paths"])
    return "\n".join(lines)
