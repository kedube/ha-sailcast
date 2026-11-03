"""Tests for reading and checking profiles."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast import profiles
from custom_components.sailcast.profiles import Profiles, SizeClass, Skill, WaterType


def test_profiles_from_entry(full_entry: MockConfigEntry) -> None:
    """Profiles are read from the subentries, with typed values."""
    read = Profiles.from_entry(full_entry)

    spot = read.spots["spot_harbor"]
    assert spot.name == "Harbor"
    assert spot.water_type is WaterType.BAY
    assert spot.exposed == ("sw", "w")
    assert read.boats["boat_cruiser"].size_class is SizeClass.CRUISER

    alex = read.sailors["sailor_alex"]
    assert alex.skill is Skill.INTERMEDIATE
    assert alex.boats == ("boat_keelboat", "boat_cruiser")
    assert alex.start == "09:00:00"
    assert alex.end is None


def test_removed_boats_are_left_out(full_entry: MockConfigEntry) -> None:
    """A sailor's removed boat is dropped, and the next one becomes usual."""
    data = full_entry.subentries["sailor_alex"].data
    sailor = profiles.Sailor.from_subentry(
        full_entry.subentries["sailor_alex"], boats={"boat_cruiser"}
    )
    assert data["boats"] == ["boat_keelboat", "boat_cruiser"]
    assert sailor.boats == ("boat_cruiser",)


def test_as_dict_is_sorted_by_name(full_entry: MockConfigEntry) -> None:
    """The panel gets each kind of profile sorted by name."""
    result = Profiles.from_entry(full_entry).as_dict()
    assert [boat["name"] for boat in result["boats"]] == ["Cruiser", "Keelboat"]
    assert result["sailors"][0] == {
        "id": "sailor_alex",
        "name": "Alex",
        "skill": "intermediate",
        "boats": ("boat_keelboat", "boat_cruiser"),
        "days": ("sat", "sun"),
        "start": "09:00:00",
        "end": None,
    }


def test_check_name() -> None:
    """Names must be present, short enough, and unique ignoring case."""
    assert profiles.check_name("Harbor", ["Bay"]) is None
    assert profiles.check_name(" ", []) == "name_required"
    assert profiles.check_name("x" * 41, []) == "name_too_long"
    assert profiles.check_name(" HARBOR ", ["Bay", "harbor"]) == "name_taken"


def test_check_sailor() -> None:
    """A sailor needs known boats, a day, and a finish after the start."""
    good = {
        "boats": ["a"],
        "days": ["sat"],
        "start": "08:00:00",
        "end": "12:00:00",
    }
    assert profiles.check_sailor(good, {"a"}) == {}
    assert profiles.check_sailor(good | {"boats": []}, {"a"}) == {
        "boats": "unknown_boat"
    }
    assert profiles.check_sailor(good | {"end": "08:00:00"}, {"a"}) == {
        "end": "end_before_start"
    }
    assert profiles.check_sailor(good | {"start": None}, {"a"}) == {}
