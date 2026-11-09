"""Tests for working out the next release's version."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from awesomeversion import AwesomeVersion, AwesomeVersionStrategy
import pytest

ROOT = Path(__file__).resolve().parent.parent
# What Home Assistant accepts in a custom integration's version (loader.py).
HOME_ASSISTANT_STRATEGIES = [
    AwesomeVersionStrategy.CALVER,
    AwesomeVersionStrategy.SEMVER,
    AwesomeVersionStrategy.SIMPLEVER,
    AwesomeVersionStrategy.BUILDVER,
    AwesomeVersionStrategy.PEP440,
]


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
            ["1.0.0b2", "1.0.0b10", "1.0.0b9", "v0.1", "1.1", "draft"],
            "beta",
            "1.0.0b11",
            "1.0.0b10",
        ),
        # The first stable release lists what changed since the first beta.
        (["1.0.0b1", "1.0.0b2", "1.0.0b4"], "stable", "1.00", "1.0.0b1"),
        # Then each stable release adds one hundredth, and lists what changed
        # since the last one.
        (["1.0.0b4", "1.00"], "stable", "1.01", "1.00"),
        (["1.00", "1.09", "1.08"], "stable", "1.10", "1.09"),
        (["1.98", "1.99"], "stable", "2.00", "1.99"),
        (["2.00", "2.01"], "stable", "2.02", "2.01"),
    ],
)
def test_next_release(
    script: ModuleType, tags: list[str], kind: str, version: str, previous: str
) -> None:
    """The next version follows the last release's tag."""
    assert script.next_release(tags, kind) == (version, previous)


def test_no_betas_after_stable(script: ModuleType) -> None:
    """Home Assistant can't load a version like 1.01b1, so 1.00 ends the betas."""
    with pytest.raises(ValueError, match=r"no betas after 1\.00"):
        script.next_release(["1.0.0b4", "1.00"], "beta")


def test_versions_home_assistant_loads(script: ModuleType) -> None:
    """Every version the script makes is one Home Assistant accepts and orders."""
    tags = ["1.0.0b4"]
    for _ in range(105):
        tags.append(script.next_release(tags, "stable")[0])
    assert tags[1:4] == ["1.00", "1.01", "1.02"]
    assert tags[100:103] == ["1.99", "2.00", "2.01"]
    versions = [
        AwesomeVersion(tag, ensure_strategy=HOME_ASSISTANT_STRATEGIES) for tag in tags
    ]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def test_no_release_yet(script: ModuleType) -> None:
    """Without a release to follow, there's no next version."""
    with pytest.raises(ValueError, match="no release"):
        script.next_release(["draft"], "beta")


def test_write_version(script: ModuleType, tmp_path: Path) -> None:
    """Only the version changes in the manifest, which keeps its formatting."""
    text = script.MANIFEST.read_text()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(text)

    script.write_version(manifest, "9.99")
    old = json.loads(text)["version"]
    assert manifest.read_text() == text.replace(
        f'"version": "{old}"', '"version": "9.99"'
    )
