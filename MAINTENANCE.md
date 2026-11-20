# Worktrees and checkpoints

Run these commands inside the repository. Each accepts `--json`. Operations that write start as previews. Repeat the command with `--apply` to perform it.

## Switch to an urgent fix

```sh
git branchback hotfix release/2.4 --branch fix/invoices --path ../invoice-hotfix
git branchback hotfix release/2.4 --branch fix/invoices --path ../invoice-hotfix --apply
```

The new linked worktree checks out a fresh branch at the resolved base commit. Choose an unused directory outside existing worktrees. When omitted, the branch defaults to `hotfix/<base>` and the directory to a sibling of your current worktree. Your current checkout keeps its unfinished edits.

## Save and restore a checkpoint

```sh
git branchback checkpoint create before-rebase --untracked fixtures/new.json
git branchback checkpoint create before-rebase --untracked fixtures/new.json --apply
git branchback checkpoint list
git branchback checkpoint restore before-rebase --path ../recovered
git branchback checkpoint restore before-rebase --path ../recovered --apply
```

The named local ref under `refs/branchback/checkpoints/` keeps the base commit, index snapshot, and working snapshot reachable. File contents use Git's normal clean and checkout filters. Tracked paths are captured together. Repeat `--untracked` for each individual nonignored file to include, using repository-root-relative paths. The report counts unselected untracked paths. Use a fresh name for each checkpoint. Creation requires a configured Git commit identity. Pause edits during capture so the snapshots describe the same moment.

Restoration checks out the original base in a fresh detached worktree and reconstructs the saved index and working tree there. Review `git status` inside that directory and create a branch there when ready. The original checkout and checkpoint remain available. Submodule working files, ignored files and in-progress operation metadata fall outside the snapshot. Conflicts, sparse/assume-unchanged entries, intent-to-add paths and dirty submodule contents require separate handling.

## Identify merged branches

```sh
git branchback cleanup --base main
git branchback cleanup --base main --delete feature/finished
git branchback cleanup --base main --delete feature/finished --apply
```

Cleanup compares each local branch tip with the chosen base (default HEAD). A candidate has a tip reachable from the base and is outside every registered worktree. BranchBack reports the base and checked-out branches separately. Squash-merged changes can appear as `not-reachable` because their original commits have different IDs. Deletion accepts one explicitly selected candidate. Git's ordinary `branch -d` checks also apply, including upstream merge requirements.
