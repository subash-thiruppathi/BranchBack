# Recovery and history search

Run these commands inside the repository you want to inspect. Each accepts `--json`. All five commands inspect local data. The optional `recover --create` action creates a new local branch.

## Recover a lost commit

```sh
git branchback recover invoice --since="2 weeks ago" --path src/invoice.py --limit 20
git branchback recover --show abc1234
git branchback recover --show abc1234 --create rescue/invoice
```

Searches available local reflogs for a case-insensitive substring of the commit subject or reflog event message. Git applies the time filter to the reflog walk. Each result includes its timestamped reflog selector, commit date, event, subject and immutable object ID. The optional literal path filter includes commits that changed that path. The default result limit is 50 distinct commits. Results can include commits already present on branches. Expired reflogs and objects absent from this clone limit recovery.

Inspect the candidate’s diff with `--show`, replacing the example ID with a result. For merge commits, the preview compares against the first parent. Adding `--create` anchors that commit to a fresh branch and leaves the active checkout in place. Git rejects a branch name already in use.

## Find a commit across branches and tags

```sh
git branchback find --commit abc1234
git branchback find --commit abc1234 --equivalents
```

The first command checks reachability from local branches, locally recorded remote branches and tags. The optional second pass asks Git to compare patches on refs without exact containment. This can recognize a cherry-pick with a different commit ID. Patch matches are reported separately because later edits and reverts can change behavior. Merge commits have multiple parent comparisons and support exact containment only. On large repositories, examining many refs can take time.

## Search stashed changes

```sh
git branchback stash-find invoice
git branchback stash-find --show 'stash@{0}'
```

Matches the stash message, changed filename or patch text. Results include the selector, commit ID, original stash message and paths, including untracked content captured in that stash. Git’s normal stash message identifies the source branch. `--show` adds the complete patch. Use the returned object ID for a stable selection while the entry remains in the stash list.

## Understand conflicts

```sh
git branchback conflicts
git branchback conflicts --path src/invoice.py
```

The list includes unresolved paths and the mode and object ID of each available index stage. The path argument is relative to the repository root and adds text content for that file. The three stages are the common base, the current side and the incoming side. A missing stage can indicate a deletion or an independently added file. Binary files and submodules are identified by their object IDs. During rebase, the current side is the rebased history and the incoming side is the replayed commit.

## Plan an undo

```sh
git branchback undo-plan
git branchback undo-plan --commit abc1234
git branchback undo-plan --path src/invoice.py
```

The default examines HEAD. A commit plan describes reverting the commit, names remote-tracking branches containing it and reports workspace changes and operations. A single-parent tip with no known remote containment also receives a soft-reset explanation. Confirm privately shared history separately because local tracking information can be stale. With `--path`, the plan checks staged changes for that literal path and explains how unstaging affects the index and working file.
