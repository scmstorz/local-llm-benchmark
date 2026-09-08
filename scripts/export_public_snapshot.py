#!/usr/bin/env python3
"""Export the public subset of the local research repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT_FILES = {
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSE.md",
    "PUBLICATION.md",
    "RELEASING.md",
    "README.md",
    "pyproject.toml",
}

PUBLIC_PREFIXES = (
    ".github/",
    "capabilities/",
    "integrations/",
    "local_llm_benchmark/",
    "models/",
    "reports/",
    "scripts/",
    "tasks/",
    "tests/",
)

PUBLIC_DOCS = {
    "docs/benchmark-design.md",
    "docs/coding-routing-roadmap.md",
    "docs/hard-knowledge-v0.2.md",
    "docs/non-coding-agentic-roadmap.md",
    "docs/study-modes.md",
    "docs/summarization-v0.1.md",
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def is_public(path: str) -> bool:
    return (
        path in ROOT_FILES
        or path in PUBLIC_DOCS
        or path.startswith(PUBLIC_PREFIXES)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy the allowlisted public snapshot to an empty directory."
    )
    parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    destination = args.destination.expanduser().resolve()

    if git(repo, "status", "--porcelain"):
        raise SystemExit("Refusing to export: commit or stash worktree changes first.")

    if destination == repo or repo in destination.parents:
        raise SystemExit("Destination must be outside the research repository.")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    tracked = [line for line in git(repo, "ls-files").splitlines() if line]
    included = sorted(path for path in tracked if is_public(path))
    excluded = sorted(set(tracked) - set(included))

    for relative in included:
        source = repo / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(source.readlink())
        else:
            shutil.copy2(source, target)

    total_bytes = sum(
        (destination / relative).lstat().st_size for relative in included
    )
    print(f"Exported {len(included)} tracked files ({total_bytes} bytes).")
    print(f"Destination: {destination}")
    print("Excluded tracked paths:")
    for relative in excluded:
        print(f"  {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
