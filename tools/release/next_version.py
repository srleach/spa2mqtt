#!/usr/bin/env python3
"""Compute the next semantic version for a release.

The release workflow runs this script on every push to main. It reads the newest
``vX.Y.Z`` tag that HEAD contains and the commits made since that tag, and it prints
the next version without the leading ``v``. It prints nothing when no release is due.

Rules, in order:

1. The HEAD commit message contains ``[skip release]``: no release.
2. No previous ``vX.Y.Z`` tag: release the fallback version unchanged (first release).
3. A previous tag and no new commits: no release (HEAD is already released).
4. Any commit is breaking: bump major. A commit is breaking when its subject uses the
   ``type!:`` or ``type(scope)!:`` form, or a body line starts with ``BREAKING CHANGE``
   (or ``BREAKING-CHANGE``), which is the Conventional Commits footer.
5. Any commit is a feature (``feat:`` or ``feat(scope):``): bump minor.
6. Otherwise: bump patch.

Merge commit subjects such as ``Merge pull request #1 from ...`` carry no type, so the
script ignores them. The commits that the merge brings in are still in the range and
are classified one by one. For a GitHub merge commit the first body line is the pull
request title, so the script classifies that line like a subject.

The classification is a pure function (:func:`next_version`) so that tests need no git.
Only the standard library is used, so the workflow needs no ``pip install`` step.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

SKIP_MARKER = "[skip release]"
DEFAULT_FALLBACK = "2.0.0"

TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# type, optional (scope), optional "!", then ":" and a space or end of line.
CONVENTIONAL_RE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?(?P<bang>!)?:(?:\s|$)")
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE\b", re.MULTILINE)
MERGE_SUBJECT_RE = re.compile(r"^Merge (pull request|branch|remote-tracking branch|tag) ")

PATCH, MINOR, MAJOR = 0, 1, 2


@dataclass(frozen=True)
class Commit:
    """One commit: its subject (first line) and its body (the rest)."""

    subject: str
    body: str = ""


def parse_tag(tag: str) -> tuple[int, int, int] | None:
    """Return (major, minor, patch) for a strict ``vX.Y.Z`` tag, else None."""
    m = TAG_RE.match(tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def latest_tag(tags: Iterable[str]) -> str | None:
    """Pick the highest strict ``vX.Y.Z`` tag. Other tags (``legacy-v0``, ``v1.0.0-rc1``) are ignored."""
    best: tuple[tuple[int, int, int], str] | None = None
    for tag in tags:
        parsed = parse_tag(tag)
        if parsed is not None and (best is None or parsed > best[0]):
            best = (parsed, tag.strip())
    return best[1] if best else None


def _classify_line(line: str) -> int | None:
    m = CONVENTIONAL_RE.match(line.strip())
    if not m:
        return None
    if m.group("bang"):
        return MAJOR
    if m.group("type").lower() == "feat":
        return MINOR
    return PATCH


def classify(commit: Commit) -> int:
    """Return the bump level (PATCH, MINOR or MAJOR) that one commit asks for."""
    level = PATCH
    if BREAKING_FOOTER_RE.search(commit.body):
        return MAJOR
    if MERGE_SUBJECT_RE.match(commit.subject):
        # The subject says nothing; the PR title is the first body line.
        first_body_line = commit.body.strip().splitlines()[0] if commit.body.strip() else ""
        found = _classify_line(first_body_line)
    else:
        found = _classify_line(commit.subject)
    if found is not None:
        level = max(level, found)
    return level


def bump(version: tuple[int, int, int], level: int) -> tuple[int, int, int]:
    major, minor, patch = version
    if level == MAJOR:
        return major + 1, 0, 0
    if level == MINOR:
        return major, minor + 1, 0
    return major, minor, patch + 1


def next_version(
    previous_tag: str | None,
    commits: Sequence[Commit],
    head_message: str = "",
    fallback: str = DEFAULT_FALLBACK,
) -> str | None:
    """Compute the next version string (no ``v``), or None when no release is due.

    ``previous_tag`` is the newest ``vX.Y.Z`` tag that HEAD contains, or None.
    ``commits`` are the commits after that tag up to and including HEAD.
    ``head_message`` is the full HEAD commit message, checked for ``[skip release]``.
    """
    if SKIP_MARKER in head_message.lower():
        return None
    if previous_tag is None:
        if not VERSION_RE.match(fallback):
            raise ValueError(f"fallback version {fallback!r} is not X.Y.Z")
        return fallback
    parsed = parse_tag(previous_tag)
    if parsed is None:
        raise ValueError(f"previous tag {previous_tag!r} is not vX.Y.Z")
    if not commits:
        return None
    level = max(classify(c) for c in commits)
    return "{}.{}.{}".format(*bump(parsed, level))


# --------------------------------------------------------------------------- git I/O


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def read_git(repo: Path) -> tuple[str | None, list[Commit], str]:
    """Read (previous tag, commits since it, HEAD message) from a git checkout.

    The checkout needs full history and tags (``fetch-depth: 0``), or the result is wrong.
    """
    tags = _git(repo, "tag", "--merged", "HEAD", "--list", "v*").split()
    prev = latest_tag(tags)
    rev_range = f"{prev}..HEAD" if prev else "HEAD"
    # %x1e separates records, %x1f separates subject from body.
    raw = _git(repo, "log", "--format=%s%x1f%b%x1e", rev_range)
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        subject, _, body = record.partition("\x1f")
        commits.append(Commit(subject=subject, body=body.strip()))
    head_message = _git(repo, "log", "-1", "--format=%B", "HEAD")
    return prev, commits, head_message


def read_fallback(pyproject: Path) -> str:
    """Read ``[tool.hatch.version] fallback-version`` from pyproject.toml."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULT_FALLBACK
    value = data.get("tool", {}).get("hatch", {}).get("version", {}).get("fallback-version")
    return str(value) if value else DEFAULT_FALLBACK


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--git", action="store_true", help="read the tag and commits from the git checkout")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="git checkout to read (default: cwd)")
    ap.add_argument("--previous-tag", help="previous vX.Y.Z tag, when not using --git")
    ap.add_argument("--subject", action="append", default=[], help="a commit subject, when not using --git")
    ap.add_argument("--fallback", help="first-release version (default: pyproject fallback-version)")
    args = ap.parse_args(argv)

    fallback = args.fallback or read_fallback(root / "pyproject.toml")
    if args.git:
        prev, commits, head = read_git(args.repo)
    else:
        prev = args.previous_tag
        commits = [Commit(s) for s in args.subject]
        head = args.subject[0] if args.subject else ""
    version = next_version(prev, commits, head, fallback)
    if version:
        print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
