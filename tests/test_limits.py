"""Tests for the safety limits table and its generated page."""

from __future__ import annotations

import importlib.util
from itertools import pairwise
from pathlib import Path
from types import ModuleType

from custom_components.sailcast.limits import (
    BOAT_LIMITS,
    WARNING_FLOORS,
    Level,
    WarningGroup,
    warning_group,
)
from custom_components.sailcast.profiles import SizeClass

ROOT = Path(__file__).resolve().parent.parent


def _page_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "safety_limits_doc", ROOT / "scripts" / "safety_limits_doc.py"
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_page_is_current() -> None:
    """docs/safety-limits.md matches the table. Run its script to update it."""
    script = _page_script()
    assert script.PAGE.read_text() == script.render()


def test_each_size_has_rising_limits() -> None:
    """Each boat size's levels start in order, from caution up."""
    for limits in BOAT_LIMITS.values():
        assert limits.wind[0] < limits.wind[1]
        assert limits.gust[0] < limits.gust[1]
        assert list(limits.wave) == sorted(set(limits.wave))
        assert limits.ideal_wind[0] < limits.ideal_wind[1] <= limits.wind[0]


def test_bigger_boats_handle_more() -> None:
    """No limit is lower for a bigger boat."""
    sizes = [BOAT_LIMITS[size] for size in SizeClass]
    for smaller, bigger in pairwise(sizes):
        assert smaller.wind <= bigger.wind
        assert smaller.gust <= bigger.gust
        assert smaller.wave <= bigger.wave
        for group in WarningGroup:
            floors = WARNING_FLOORS[group]
            assert floors[SizeClass.DINGHY] >= floors[SizeClass.LARGE_CRUISER]


def test_warning_groups() -> None:
    """NWS events map to their group, and any watch is a watch."""
    assert warning_group("Small Craft Advisory") is WarningGroup.ADVISORY
    assert warning_group("Hurricane Force Wind Warning") is WarningGroup.STORM
    assert warning_group("Storm Surge Watch") is WarningGroup.WATCH
    assert warning_group("Marine Weather Statement") is None
    assert WARNING_FLOORS[WarningGroup.STORM][SizeClass.LARGE_CRUISER] is (
        Level.DANGEROUS
    )
