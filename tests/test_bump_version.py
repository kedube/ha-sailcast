"""Tests for working out the next release's version."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(name="script")
def script_fixture() -> ModuleType:
    """Load the script the Release workflow runs."""
    spec = importlib.util.spec_from_file_location(
        "bump_version", ROOT / "scripts" / "bump_version.py"
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("tags", "kind", "version", "previous"),
    [
        (["1.0.0b1"], "beta", "1.0.0b2", "1.0.0b1"),
        # Tags are compared as versions, and other tags are left out.
        (
            ["1.0.0b2", "1.0.0b10", "1.0.0b9", "v0.1", "draft"],
            "beta",
            "1.0.0b11",
            "1.0.0b10",
        ),
        # The first stable release lists what changed since the last beta.
        (["1.0.0b1", "1.0.0b2"], "stable", "1.0.0", "1.0.0b2"),
        # After a stable release, a beta starts the next minor version, and a
        # stable release fixes it.
        (["1.0.0b2", "1.0.0"], "beta", "1.1.0b1", "1.0.0"),
        (["1.0.0b2", "1.0.0"], "stable", "1.0.1", "1.0.0"),
        (["1.9.0"], "beta", "1.10.0b1", "1.9.0"),
        # A stable release lists everything since the last stable one.
        (["1.0.0", "1.1.0b1", "1.1.0b2"], "stable", "1.1.0", "1.0.0"),
    ],
)
def test_next_release(
    script: ModuleType, tags: list[str], kind: str, version: str, previous: str
) -> None:
    """The next version follows the last release's tag."""
    assert script.next_release(tags, kind) == (version, previous)


def test_no_release_yet(script: ModuleType) -> None:
    """Without a release to follow, there's no next version."""
    with pytest.raises(ValueError, match="no release"):
        script.next_release(["draft"], "beta")


def test_write_version(script: ModuleType, tmp_path: Path) -> None:
    """Only the version changes in the manifest, which keeps its formatting."""
    text = script.MANIFEST.read_text()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(text)

    script.write_version(manifest, "9.9.9b9")
    old = json.loads(text)["version"]
    assert manifest.read_text() == text.replace(
        f'"version": "{old}"', '"version": "9.9.9b9"'
    )
