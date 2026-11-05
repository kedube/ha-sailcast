#!/usr/bin/env python3
"""Work out the next release's version, from the last release's tag.

Versions look like 1.0.0, and betas like 1.0.0b2. Tags are the bare version,
with no "v" in front, and the version lives in the integration's manifest.json.

- beta, a pre-release: 1.0.0b1 is followed by 1.0.0b2, and 1.0.0 by 1.1.0b1.
- stable: 1.0.0b2 is followed by 1.0.0, and 1.0.0 by 1.0.1.

  python3 scripts/bump_version.py beta            # print the next beta
  python3 scripts/bump_version.py stable --write  # and save it in manifest.json

The Release workflow (.github/workflows/release.yml) runs this, and reads the
version, the release its notes start from, and whether it's a pre-release from
what it prints.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "sailcast" / "manifest.json"
KINDS = ("beta", "stable")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:b([1-9]\d*))?")
MANIFEST_VERSION = re.compile(r'"version"\s*:\s*"[^"]*"')

# Major, minor and patch, then the beta's number, or None for a stable release.
type Version = tuple[int, int, int, int | None]


def git(*args: str) -> str:
    """Run git in the repository and return its output."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, cwd=ROOT
    ).stdout


def parse(tag: str) -> Version | None:
    """Return the version a tag names, or None if it isn't a release's."""
    match = VERSION.fullmatch(tag)
    if match is None:
        return None
    major, minor, patch, beta = match.groups()
    return int(major), int(minor), int(patch), None if beta is None else int(beta)


def format_version(version: Version) -> str:
    """Write a version as its tag, such as 1.0.0b2."""
    major, minor, patch, beta = version
    return f"{major}.{minor}.{patch}" + ("" if beta is None else f"b{beta}")


def _order(version: Version) -> tuple[int, int, int, bool, int]:
    """Sort a version after its betas, and its betas by number."""
    major, minor, patch, beta = version
    return major, minor, patch, beta is None, beta or 0


def following(last: Version, kind: str) -> Version:
    """Return the version after the last release, for a beta or a stable one."""
    major, minor, patch, beta = last
    if kind == "beta":
        if beta is None:
            # After a stable release, betas start the next minor version.
            return major, minor + 1, 0, 1
        return major, minor, patch, beta + 1
    if beta is None:
        # A stable release after a stable one fixes it.
        return major, minor, patch + 1, None
    return major, minor, patch, None


def next_release(tags: Iterable[str], kind: str) -> tuple[str, str]:
    """Return the next version, and the release its notes list changes since.

    A stable release's notes start from the last stable release, so they also
    list what its betas brought.
    """
    released = sorted(filter(None, map(parse, tags)), key=_order)
    if not released:
        raise ValueError("there's no release to follow")
    since = released[-1]
    if kind == "stable":
        since = next((old for old in reversed(released) if old[3] is None), since)
    return format_version(following(released[-1], kind)), format_version(since)


def write_version(path: Path, version: str) -> None:
    """Change only the version in manifest.json, keeping its formatting."""
    text = path.read_text()
    manifest = json.loads(text)
    updated, count = MANIFEST_VERSION.subn(f'"version": "{version}"', text)
    if count != 1 or json.loads(updated) != {**manifest, "version": version}:
        raise SystemExit(f"{path}: couldn't find the version to change")
    path.write_text(updated)


def main() -> int:
    """Print the next release, and save its version with --write."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("kind", choices=KINDS, help="a beta or a stable release")
    parser.add_argument(
        "--write", action="store_true", help="save the version in manifest.json"
    )
    args = parser.parse_args()

    try:
        version, since = next_release(git("tag", "--list").split(), args.kind)
    except ValueError as err:
        print(f"Can't work out the version: {err}", file=sys.stderr)
        return 1
    if args.write:
        write_version(MANIFEST, version)
    print(f"version={version}")
    print(f"previous={since}")
    print(f"prerelease={'true' if args.kind == 'beta' else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
