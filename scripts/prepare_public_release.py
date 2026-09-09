#!/usr/bin/env python3
"""Prepare and verify a sanitized update in a dedicated public clone."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH_ROOT))

from scripts.audit_public_snapshot import audit  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def canonical_remote(url: str) -> str:
    """Normalize common Git remote spellings for a conservative comparison."""

    value = re.sub(r"\.git$", "", url.strip().rstrip("/"))
    scp_match = re.fullmatch(r"[^@]+@([^:]+):(.+)", value)
    if scp_match:
        return f"{scp_match.group(1).lower()}/{scp_match.group(2).lower()}"

    parsed = urlsplit(value)
    if parsed.hostname:
        return f"{parsed.hostname.lower()}/{parsed.path.strip('/').lower()}"

    return str(Path(value).expanduser().resolve())


def disk_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        current_path = Path(current)
        for name in files:
            path = current_path / name
            paths.add(path.relative_to(root).as_posix())
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                paths.add(path.relative_to(root).as_posix())
    return paths


def tree_fingerprint(root: Path) -> str:
    """Hash public paths, file types, modes, symlink targets, and contents."""

    digest = hashlib.sha256()
    for relative in sorted(disk_paths(root)):
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{path.lstat().st_mode & 0o777:o}".encode("ascii"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"L")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            digest.update(b"F")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_public_clone(research: Path, public_clone: Path) -> list[str]:
    if not public_clone.is_dir():
        raise SystemExit(f"Public clone does not exist: {public_clone}")
    if (
        public_clone == research
        or research in public_clone.parents
        or public_clone in research.parents
    ):
        raise SystemExit("Public clone must be outside the research repository.")

    try:
        top_level = Path(git(public_clone, "rev-parse", "--show-toplevel")).resolve()
    except subprocess.CalledProcessError as error:
        raise SystemExit("Public clone is not a Git worktree.") from error
    if top_level != public_clone:
        raise SystemExit(f"Target must be the Git worktree root: {top_level}")

    branch = git(public_clone, "branch", "--show-current")
    if branch != "main":
        current = branch or "detached HEAD"
        raise SystemExit(f"Public clone must be on main, not {current}.")
    if git(public_clone, "status", "--porcelain", "--untracked-files=all"):
        raise SystemExit("Public clone must have a clean worktree.")

    try:
        head = git(public_clone, "rev-parse", "HEAD")
        tracked_main = git(public_clone, "rev-parse", "refs/remotes/origin/main")
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "Public clone must have an origin/main tracking ref; fetch it first."
        ) from error
    if head != tracked_main:
        raise SystemExit(
            "Public clone HEAD must equal its fetched origin/main; update it first."
        )

    research_remote = canonical_remote(git(research, "remote", "get-url", "origin"))
    public_remote = canonical_remote(
        git(public_clone, "remote", "get-url", "origin")
    )
    if research_remote != public_remote:
        raise SystemExit(
            "Research repository and public clone do not point to the same origin."
        )

    tracked = [line for line in git(public_clone, "ls-files").splitlines() if line]
    extras = sorted(disk_paths(public_clone) - set(tracked))
    if extras:
        sample = ", ".join(extras[:5])
        suffix = " ..." if len(extras) > 5 else ""
        raise SystemExit(
            "Public clone contains ignored or otherwise untracked files: "
            f"{sample}{suffix}. Use a dedicated clean clone."
        )
    return tracked


def sync_snapshot(snapshot: Path, public_clone: Path, tracked: list[str]) -> None:
    snapshot_paths = disk_paths(snapshot)

    for relative in sorted(set(tracked) - snapshot_paths, reverse=True):
        target = public_clone / relative
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            raise SystemExit(f"Refusing to replace unexpected directory: {target}")

    for relative in sorted(snapshot_paths):
        source = snapshot / relative
        target = public_clone / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        elif target.exists() and target.is_dir():
            raise SystemExit(f"Refusing to replace unexpected directory: {target}")

        if source.is_symlink():
            if target.exists():
                target.unlink()
            target.symlink_to(source.readlink())
        else:
            shutil.copy2(source, target)

    for directory in sorted(
        (path for path in public_clone.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if ".git" not in directory.relative_to(public_clone).parts:
            try:
                directory.rmdir()
            except OSError:
                pass


def run_checked(
    command: list[str], cwd: Path, *, env: dict[str, str] | None = None
) -> None:
    print(f"Running: {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True, env=env)


def run_full_candidate_diff_check(public_clone: Path) -> None:
    """Run Git's whitespace check over tracked and newly added candidate files."""

    with TemporaryDirectory(prefix="local-llm-benchmark-index-") as directory:
        index_path = Path(directory) / "index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index_path)
        run_checked(["git", "read-tree", "HEAD"], public_clone, env=environment)
        run_checked(["git", "add", "-A"], public_clone, env=environment)
        run_checked(
            ["git", "diff", "--cached", "--check"],
            public_clone,
            env=environment,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export the committed public subset, synchronize it into a dedicated "
            "clean public clone, and run all local publication gates."
        )
    )
    parser.add_argument("public_clone", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    research = RESEARCH_ROOT.resolve()
    public_clone = args.public_clone.expanduser().resolve()

    if git(research, "status", "--porcelain"):
        raise SystemExit("Research repository must be clean and committed first.")
    tracked = validate_public_clone(research, public_clone)

    with TemporaryDirectory(prefix="local-llm-benchmark-public-") as directory:
        snapshot = Path(directory) / "snapshot"
        run_checked(
            [sys.executable, "scripts/export_public_snapshot.py", str(snapshot)],
            research,
        )

        findings = audit(snapshot)
        if findings:
            for finding in findings:
                print(f"  {finding.path}: {finding.detail}", file=sys.stderr)
            raise SystemExit("Exported snapshot failed the public audit.")

        sync_snapshot(snapshot, public_clone, tracked)

    findings = audit(public_clone)
    if findings:
        for finding in findings:
            print(f"  {finding.path}: {finding.detail}", file=sys.stderr)
        raise SystemExit("Synchronized public clone failed the public audit.")

    run_full_candidate_diff_check(public_clone)
    candidate_fingerprint = tree_fingerprint(public_clone)
    test_env = os.environ.copy()
    test_env["PYTHONDONTWRITEBYTECODE"] = "1"
    run_checked(
        [sys.executable, "-B", "scripts/run_public_tests.py"],
        public_clone,
        env=test_env,
    )
    if tree_fingerprint(public_clone) != candidate_fingerprint:
        raise SystemExit("Public tests modified the release candidate worktree.")

    status = git(public_clone, "status", "--short")
    summary = git(public_clone, "diff", "--stat")
    print("\nPublic release candidate passed all automated local gates.")
    print("No commit or push was performed.")
    print("\nChanged paths:")
    print(status or "  (none)")
    print("\nDiff summary:")
    print(summary or "  (no content changes)")
    print("\nReview the complete diff and author identity before committing manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
