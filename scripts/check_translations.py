#!/usr/bin/env python3
"""Check that every translation has exactly the keys English has.

Integration strings live in custom_components/sailcast/translations and the
panel's in frontend/src/translations. In each folder, en.json is complete and
every other language must match it.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = (
    ROOT / "custom_components" / "sailcast" / "translations",
    ROOT / "frontend" / "src" / "translations",
)


def keys(value: Any, prefix: str = "") -> Iterator[str]:
    """Yield the dotted path of every string."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from keys(child, f"{prefix}{key}.")
    else:
        yield prefix.removesuffix(".")


def main() -> int:
    """Print each missing or unexpected key and return 1 if there are any."""
    problems = []
    for folder in FOLDERS:
        english = set(keys(json.loads((folder / "en.json").read_text("utf-8"))))
        for path in sorted(folder.glob("*.json")):
            if path.name == "en.json":
                continue
            found = set(keys(json.loads(path.read_text("utf-8"))))
            name = path.relative_to(ROOT)
            problems += [f"{name}: missing {key}" for key in sorted(english - found)]
            problems += [f"{name}: unexpected {key}" for key in sorted(found - english)]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
