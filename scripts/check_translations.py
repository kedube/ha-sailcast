#!/usr/bin/env python3
"""Check that every language is there and matches English.

Integration strings live in custom_components/sailcast/translations and the
panel's in frontend/src/translations. In each folder, en.json is complete,
every other language must have exactly its keys, and each string must use the
same {placeholders} as its English, so no value goes missing in a sentence.
Name languages, such as `de fr`, to check only those.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = (
    ROOT / "custom_components" / "sailcast" / "translations",
    ROOT / "frontend" / "src" / "translations",
)
# English and the 11 languages with the most Home Assistant installs.
LANGUAGES = (
    "en",
    "de",
    "fr",
    "nl",
    "es",
    "zh-Hans",
    "it",
    "pl",
    "sv",
    "ru",
    "cs",
    "pt-BR",
)
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def strings(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield the dotted path and value of every string."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, f"{prefix}{key}.")
    else:
        yield prefix.removesuffix("."), value


def placeholders(text: str) -> list[str]:
    """Return the placeholders a string uses, sorted; a language may repeat one."""
    return sorted(set(PLACEHOLDER.findall(text)))


def check(path: Path, english: dict[str, Any]) -> list[str]:
    """Return what's wrong with one language's file."""
    name = path.relative_to(ROOT)
    found = dict(strings(json.loads(path.read_text("utf-8"))))
    problems = [f"{name}: missing {key}" for key in english if key not in found]
    problems += [f"{name}: unexpected {key}" for key in found if key not in english]
    for key, text in found.items():
        if key not in english:
            continue
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{name}: {key} is empty")
        elif placeholders(text) != placeholders(english[key]):
            problems.append(
                f"{name}: {key} has {placeholders(text)}, "
                f"English has {placeholders(english[key])}"
            )
    return problems


def main(wanted: list[str]) -> int:
    """Print each problem and return 1 if there are any."""
    languages = [language for language in LANGUAGES if language in wanted] or LANGUAGES
    problems = [
        f"{language} isn't one of SailCast's languages"
        for language in wanted
        if language not in LANGUAGES
    ]
    for folder in FOLDERS:
        english = dict(strings(json.loads((folder / "en.json").read_text("utf-8"))))
        names = {path.stem for path in folder.glob("*.json")}
        problems += [
            f"{folder.relative_to(ROOT)}: no {language}.json"
            for language in languages
            if language not in names
        ]
        problems += [
            f"{folder.relative_to(ROOT)}: {name}.json isn't one of SailCast's languages"
            for name in sorted(names - set(LANGUAGES))
        ]
        for language in languages:
            path = folder / f"{language}.json"
            if language == "en":
                continue
            if path.exists():
                problems += check(path, english)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
