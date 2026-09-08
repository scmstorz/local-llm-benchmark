#!/usr/bin/env python3
"""Audit an exported public snapshot before it becomes a Git repository."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


FORBIDDEN_PATHS = {
    "PROJECT_STATUS.md",
    "docs/case-study-log.md",
    "docs/case-study-writing-agent-brief.md",
}
FORBIDDEN_PREFIXES = (
    ".git/",
    "data/private/",
    "docs/case-study-assets/",
    "results/",
)

SECRET_PATTERNS = {
    "private key": re.compile(
        r"-----BEGIN (?:RSA |OPENSSH |EC |PGP )?PRIVATE KEY-----"
    ),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "OpenAI-style token": re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "private macOS path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "private Linux path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "email address": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
}

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class Finding:
    path: str
    detail: str


def relative_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and ".git" not in path.relative_to(root).parts
    )


def audit(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []

    for path in relative_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in FORBIDDEN_PATHS or relative.startswith(FORBIDDEN_PREFIXES):
            findings.append(Finding(relative, "path is outside the public boundary"))
            continue
        if path.lstat().st_size > MAX_FILE_BYTES:
            findings.append(
                Finding(relative, f"file exceeds {MAX_FILE_BYTES} bytes")
            )
        if path.is_symlink():
            try:
                path.resolve().relative_to(root)
            except ValueError:
                findings.append(Finding(relative, "symlink escapes the snapshot"))
            continue

        content = path.read_bytes()
        if b"\x00" in content:
            findings.append(Finding(relative, "binary file contains a NUL byte"))
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(Finding(relative, "file is not valid UTF-8 text"))
            continue

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding(relative, f"matched {label} pattern"))

        if path.suffix.lower() != ".md":
            continue
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if (
                not target
                or target.startswith("#")
                or "://" in target
                or target.startswith("mailto:")
            ):
                continue
            local = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (path.parent / local).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                findings.append(Finding(relative, f"link escapes snapshot: {target}"))
                continue
            if not resolved.exists():
                findings.append(Finding(relative, f"broken local link: {target}"))

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check privacy, file, and local-link gates in a public snapshot."
    )
    parser.add_argument("snapshot", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.snapshot.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Snapshot directory does not exist: {root}")

    files = relative_files(root)
    findings = audit(root)
    if findings:
        print(f"Public snapshot audit failed with {len(findings)} finding(s):")
        for finding in findings:
            print(f"  {finding.path}: {finding.detail}")
        return 1

    total_bytes = sum(path.lstat().st_size for path in files)
    print(f"Public snapshot audit passed: {len(files)} files, {total_bytes} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
