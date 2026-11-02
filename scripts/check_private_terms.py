#!/usr/bin/env python3
"""Stop private terms from reaching the public repository.

The terms live in a local file that is never committed: the path in
$SAILCAST_PRIVATE_TERMS, or ~/.config/sailcast/private-terms.txt.
Each line is a term, matched as a whole word and ignoring case.
Lines starting with "re:" are regular expressions, and "#" starts a comment.

Usage:
  check_private_terms.py                  check the staged files (pre-commit hook)
  check_private_terms.py --message FILE   check a commit message (commit-msg hook)
  check_private_terms.py --all            check every tracked file
  check_private_terms.py PATH...          check files in the working tree
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

DEFAULT_LIST = Path.home() / ".config" / "sailcast" / "private-terms.txt"


def list_path() -> Path:
    """Return where the private terms list is kept."""
    return Path(os.environ.get("SAILCAST_PRIVATE_TERMS", DEFAULT_LIST)).expanduser()


def load_patterns(path: Path) -> list[tuple[int, re.Pattern[str]]]:
    """Read the list into (line number, pattern) pairs."""
    patterns = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            source = line[3:]
        else:
            words = r"\s+".join(re.escape(word) for word in line.split())
            source = rf"(?<!\w){words}(?!\w)"
        patterns.append((number, re.compile(source, re.IGNORECASE)))
    return patterns


def git(*args: str) -> bytes:
    """Run git and return its output."""
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_files() -> list[tuple[str, bytes]]:
    """Return the staged files, as they will be committed."""
    names = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    return [
        (name, git("show", f":{name}")) for name in names.decode().split("\0") if name
    ]


def tracked_files() -> list[tuple[str, bytes]]:
    """Return every tracked file, as it is in the working tree."""
    names = git("ls-files", "-z").decode().split("\0")
    return [(name, Path(name).read_bytes()) for name in names if Path(name).is_file()]


def find(
    label: str, text: str, patterns: list[tuple[int, re.Pattern[str]]]
) -> list[str]:
    """Return one line per match, naming where it is and which list entry hit."""
    hits = []
    for number, pattern in patterns:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{label}:{line}: matches line {number} of the list")
    return hits


def main() -> int:
    """Check what was asked for and return 1 if anything matched."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--message", type=Path, help="commit message file to check")
    parser.add_argument("--all", action="store_true", help="check every tracked file")
    parser.add_argument("paths", nargs="*", type=Path, help="files to check")
    args = parser.parse_args()

    terms = list_path()
    if not terms.is_file():
        print(f"Privacy check skipped: no list at {terms}", file=sys.stderr)
        return 0
    patterns = load_patterns(terms)

    hits = []
    if args.message:
        lines = args.message.read_text(encoding="utf-8").splitlines()
        message = "\n".join(line for line in lines if not line.startswith("#"))
        hits += find("commit message", message, patterns)
    else:
        if args.paths:
            files = [(str(path), path.read_bytes()) for path in args.paths]
        elif args.all:
            files = tracked_files()
        else:
            files = staged_files()
        for name, data in files:
            hits += find(f"{name} (path)", name, patterns)
            hits += find(name, data.decode("utf-8", errors="replace"), patterns)

    if hits:
        print("Private terms found:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print(f"Remove them, or fix the list at {terms}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
