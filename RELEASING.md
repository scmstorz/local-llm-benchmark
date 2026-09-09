# Public release procedure

The public repository is a sanitized product of a richer local research
repository. It is not a mirror, and the research branch must never be pushed
directly. See [PUBLICATION.md](PUBLICATION.md) for the exact content boundary.

## Safety invariants

- Start from a clean, committed research worktree.
- Use a dedicated clean clone of the public repository on branch `main`.
- Fetch the remote and fast-forward that clone before preparing an update.
- Generate public content only through the allowlisted exporter.
- Pass the repository-owned privacy audit and public offline tests locally.
- Review every changed path, the complete diff, and the Git author identity.
- Commit and push only after that manual review.

The preparation command never commits, tags, pushes, runs Ollama, or starts a
benchmark. GitHub Actions, if introduced later, will be an additional
portability and regression check; it will not replace the local pre-push
privacy gate.

## Prepare the public clone

Create a dedicated clone once. Before each release, update it explicitly:

```bash
git -C /path/to/public-clone fetch origin main
git -C /path/to/public-clone switch main
git -C /path/to/public-clone merge --ff-only origin/main
```

The preparation script requires the clone's `HEAD` to equal its fetched
`origin/main`. It also refuses a dirty clone, a detached head, a different
remote, a clone inside the research repository, or ignored/untracked files.
These constraints keep synchronization narrow and reviewable.

From the clean research repository, run:

```bash
python3 scripts/prepare_public_release.py /path/to/public-clone
```

The script performs the following gates in order:

1. verifies both worktrees and the public remote;
2. creates a temporary allowlisted snapshot from tracked research files;
3. audits that snapshot for excluded paths, credential patterns, private
   absolute paths, email addresses, binary or oversized files, unsafe symlinks,
   and broken local Markdown links;
4. synchronizes the exact snapshot into the public clone, including intentional
   deletions of formerly public tracked files;
5. audits the synchronized clone again;
6. runs `git diff --cached --check` through a temporary index so modified and
   newly added files are both covered without staging the real candidate; and
7. runs the dependency-free public test suite with bytecode generation disabled
   and verifies that the tests did not modify the candidate tree.

It finishes by printing the changed paths and diff summary. It performs no
remote write.

## Manual publication gate

Inspect the candidate in the dedicated clone:

```bash
git -C /path/to/public-clone status --short
git -C /path/to/public-clone diff --stat
git -C /path/to/public-clone diff
git -C /path/to/public-clone diff --check
git -C /path/to/public-clone var GIT_AUTHOR_IDENT
```

Confirm that the diff contains only intended public material and that the
author identity is appropriate for a public commit. Then commit and push from
the public clone using ordinary fast-forward Git operations.

After pushing, compare the local `HEAD` with the remote `main` ref and inspect
the rendered README and changed files on GitHub. Tags and GitHub Releases are
separate, intentional publication decisions; this procedure does not create
them automatically.

## Tagged releases

Repository tags use project-level semantic versions such as `v0.1.0`. Versions
embedded in task IDs, prompts, verifiers, harnesses and study protocols are
independent frozen contract versions and must not be inferred from the project
tag.

Create an annotated tag only after the intended public commit has passed the
full release procedure and its remote `main` ref has been verified. Review the
corresponding [CHANGELOG.md](CHANGELOG.md) entry, push the tag separately, and
then create the GitHub Release from that exact tag. Verify the remote tag target
and published release page afterwards. Do not move or silently replace a
published tag.

If any gate or review fails, do not commit. Discard the dedicated clone and
start again from a fresh clone after correcting the research repository. This
is safer than repairing an uncertain release worktree in place.
