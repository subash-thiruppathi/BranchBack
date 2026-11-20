# BranchBack

A local, read-only CLI for a developer who committed the latest change on the wrong branch and wants it on a fresh branch. Requires Git and Python 3. Run the executable from the affected repository, or place it on PATH and run `git branchback feature/invoice`.

## Install and run

Use a terminal with Git and Python 3 on PATH (macOS, Linux, or WSL). npm is needed only for npm installation. To use the current checkout immediately, install it from the directory containing this README:

```sh
npm install --global .
```

Once version 0.1.0 is published to npm, the registry installation command is `npm install --global branchback@0.1.0`. The package installs the executable as `git-branchback`, which Git discovers as a subcommand.

Inside the repository where the mistake happened, choose a new branch name:

```sh
git branchback feature/invoice
```

For help, run `git branchback -h`. If Git cannot find the command, check that the npm global executable directory is on PATH and that `git-branchback -h` works directly.

## Multiple commits on the wrong branch (development checkout)

Suppose you committed an invoice fix and then its tests on main. Run the following from that repository:

```sh
git branchback --commits 2 feature/invoice
```

The destination would keep both commits at the current tip. The source would move to the parent of the older commit. The preview lists the selected IDs oldest first and counts unfinished edits. Choose a consecutive range ending at HEAD. A range crossing a merge, root, shallow boundary, or known remote-tracking history is declined. The published 0.1.0 CLI supports the single-commit form.

## Read the preview

The first commit ID is the current tip. It would become the tip of the new branch. The second ID is its parent. It would become the original branch’s tip. The path counts describe the current index and working tree. For example, one file staged and then edited again contributes to both the staged and unstaged totals. An untracked file contributes only to the third total.

A successful preview exits with status 0 and stops there. BranchBack has no apply command. Review the branch names and commit IDs and verify that nobody else relies on the commit before performing any recovery separately.

## When a preview is unavailable

| Situation | What to check |
|---|---|
| Destination already exists | Choose an unused branch name, including an available slash-separated prefix. |
| HEAD is detached or has zero or multiple visible parents | Inspect `git status` and `git log -2 --oneline`. This workflow expects an attached branch with an ordinary latest commit. |
| Merge, rebase, or other tracked operation in progress | Inspect `git status` and resolve that operation before revisiting the preview. |
| A remote-tracking branch contains the commit | Review how the commit was shared. This workflow is for private commits. |

## Use case

Mira commits an invoice fix on main, stages a test adjustment, then edits the same file again. She wants the fix and both layers of unfinished work on feature/invoice. She runs the preview before touching either branch. It displays the proposed destination at the original commit and the source at its parent. Staged and unstaged counts overlap when a file has changes in both layers. Untracked files stay in the working directory. The plan assumes the developer confirms the tip was never shared. Re-run after any repository change.

## Architecture

| Component | Input and responsibility | Output |
|---|---|---|
| CLI boundary | Accept one new branch name, validate its spelling and Git ref syntax | Validated target or exit 1 (argument syntax errors exit 2) |
| Repository reader | Ask local Git for worktree state, attached branch, parent history, branch namespace and remote-tracking refs | Full object IDs and local evidence |
| Eligibility checks | Require a fresh target, an ordinary single-parent tip, no detected operation or conflicts, and no known remote branch containing the tip | Specific refusal or eligible snapshot |
| Change inventory | Parse NUL-delimited porcelain records with rename detection disabled; count index, working tree and untracked paths independently | Three path counts |
| Renderer | Describe creating the destination at the tip, switching at the same tree, then moving the original branch to its parent | Human-readable hypothetical result, exit 0 |

Git runs as a subprocess with argument arrays. The CLI invokes inspection commands only and disables optional index writes. It stores no credentials, telemetry or repository data. There is no server. Inputs are trusted local repositories and their Git configuration. Multiple reads do not form an atomic snapshot. Ref counts and publication evidence reflect local state only. Case-insensitive filesystem collisions, external processes and server-side rules can still prevent a future operation.

## Acceptance and development

Run `python3 -m unittest -v` in this checkout. Integration tests create throwaway Git repositories. A successful preview must preserve the current branch, HEAD, refs, index and working changes. Refused scenarios must exit nonzero. Existing destination branches, selecting a historical commit and executing recovery are outside this release. A future executor would require fresh precondition checks, a persistent recovery ref, and interruption and rollback tests before exposing an apply command.
