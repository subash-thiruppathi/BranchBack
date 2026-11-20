# Compare local history

## Plan a sync

Run `git branchback sync-plan` to compare the checked-out branch with its configured upstream. The report lists commit IDs unique to each side and explains fast-forward, merge, or rebase implications. The reported time is the modification time of the repository’s FETCH_HEAD file. A fetch from a different remote can update this file. An unavailable comparison has status `unavailable`. Commit lists use reachability and can include patch-equivalent cherry-picks.

## Review a pull request

```sh
git branchback review --base origin/main --expect-dir src --expect-dir tests --patch
```

Read the commits included in the proposed branch, the net changed paths since the merge base, and the optional cumulative patch. Repeat `--expect-dir` to declare expected repository-relative directory prefixes. Large changed blobs are flagged at 1 MiB by default. Change this threshold with `--large-bytes`. The report compares committed trees. Pending edits belong in the separate explain report.

## Draft release notes

```sh
git branchback release-notes v1.0..v1.1 --files > release-notes.md
```

The Markdown draft lists the subjects and IDs of commits reachable from the second revision and absent from the first. Public GitHub and GitLab host URLs recognized from origin supply commit links. Other origin formats retain plain IDs. The optional file list reports net changes between the two endpoint trees.

All three commands accept `--json` and inspect local history. Refresh remote-tracking refs separately when the comparison requires current remote data.
